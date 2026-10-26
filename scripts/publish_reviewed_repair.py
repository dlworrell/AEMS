#!/usr/bin/env python3
"""Publish or resume a content-bound repair on a separate signing branch.

Only owner-triggered push/dispatch jobs on an explicitly named bootstrap branch
may invoke this entry point. The reviewed payload format is unchanged from the
2026-10-25 bootstrap. See docs/engineering/SIGNED-PR-PUBLISHING.md.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SHA = re.compile(r"[0-9a-f]{40}")
MUTATION = "mutation($input:CreateCommitOnBranchInput!){createCommitOnBranch(input:$input){commit{oid url}}}"


class RepairError(RuntimeError):
    """A failed safety check; no automatic rebase or overwrite is permitted."""


class APIError(RepairError):
    def __init__(self, status: int, method: str, path: str):
        self.status = status
        super().__init__(f"GitHub HTTP {status}: {method} {path}")


def request(method: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request("https://api.github.com" + path, data=data, method=method,
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raise APIError(error.code, method, path) from None


def safe_branch(branch: str) -> bool:
    return (isinstance(branch, str) and len(branch) <= 255
            and re.fullmatch(r"[A-Za-z0-9._/-]+", branch) is not None
            and ".." not in branch and all(part and not part.startswith(".")
                and not part.endswith((".", ".lock")) for part in branch.split("/")))


def safe_path(path: str) -> bool:
    return (isinstance(path, str) and bool(path) and "\\" not in path
            and not any(ord(char) < 32 or ord(char) == 127 for char in path)
            and all(part not in {"", ".", ".."} and part.lower() != ".git"
                    for part in path.split("/")))


def validate(raw: bytes, digest: str, env: dict) -> tuple[dict, set[str]]:
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RepairError("Expected payload SHA-256 must be explicit")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise RepairError("Payload identity mismatch")
    payload = json.loads(raw)
    repo = env.get("GITHUB_REPOSITORY", "")
    bootstrap = env.get("EXPECTED_BOOTSTRAP_BRANCH", "")
    if (not re.fullmatch(r"dlworrell/[A-Za-z0-9_.-]+", repo)
            or payload["repository"] != repo):
        raise RepairError("Unexpected repository")
    if (env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}
            or env.get("GITHUB_ACTOR") != "dlworrell"
            or env.get("GITHUB_TRIGGERING_ACTOR", "dlworrell") != "dlworrell"
            or not safe_branch(bootstrap) or not bootstrap.startswith("bootstrap/")
            or env.get("GITHUB_REF_NAME") != bootstrap):
        raise RepairError("Owner-triggered job on the expected bootstrap branch required")
    if not safe_branch(payload["branch"]) or not payload["branch"].startswith("signing/"):
        raise RepairError("Unsafe repair branch")
    if any(not isinstance(payload[key], str) or not SHA.fullmatch(payload[key])
           for key in ("base_sha", "tree_sha")):
        raise RepairError("Bad object identity")
    message = payload["message"]
    if (not isinstance(message, dict) or set(message) - {"headline", "body"}
            or not isinstance(message.get("headline"), str) or not message["headline"].strip()
            or ("body" in message and not isinstance(message["body"], str))):
        raise RepairError("Invalid commit message")
    changes = payload["file_changes"]
    if not isinstance(changes, dict) or set(changes) - {"additions", "deletions"}:
        raise RepairError("Unknown file-change operation")
    seen = set()
    for kind, entries in changes.items():
        if not isinstance(entries, list):
            raise RepairError("File changes must be lists")
        for item in entries:
            path = item["path"]
            keys = {"path", "contents", "blob_sha"} if kind == "additions" else {"path"}
            if set(item) != keys or not safe_path(path) or path in seen:
                raise RepairError("Unsafe, duplicate or malformed file change")
            seen.add(path)
            if kind == "additions":
                content = base64.b64decode(item["contents"], validate=True)
                blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
                if blob != item["blob_sha"]:
                    raise RepairError("Payload file hash mismatch: " + path)
    if not seen:
        raise RepairError("No reviewed file changes")
    return payload, seen


def ref(api, repo: str, branch: str) -> str | None:
    path = f"/repos/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='/')}"
    try:
        value = api("GET", path)
    except APIError as error:
        if error.status == 404:
            return None
        raise
    obj = value.get("object", {}) if isinstance(value, dict) else {}
    sha = obj.get("sha")
    if (value.get("ref") != "refs/heads/" + branch or obj.get("type") != "commit"
            or not isinstance(sha, str) or not SHA.fullmatch(sha)):
        raise RepairError("Malformed branch identity: " + branch)
    return sha


def verify(api, repo: str, sha: str, payload: dict, sleep=time.sleep) -> dict:
    for attempt in range(4):
        value = api("GET", f"/repos/{repo}/commits/{sha}")
        detail = value.get("commit", {}) or {}
        verification = detail.get("verification", {}) or {}
        if (value.get("sha") != sha or (detail.get("tree") or {}).get("sha") != payload["tree_sha"]
                or [parent.get("sha") for parent in value.get("parents", [])] != [payload["base_sha"]]):
            raise RepairError("Replacement identity, tree or ancestry differs from reviewed payload")
        if verification.get("verified") is True and verification.get("reason") == "valid":
            return value
        if attempt < 3:
            sleep(2)
    raise RepairError("GitHub did not verify replacement commit: " + str(verification.get("reason")))


def publish(raw: bytes, digest: str, env: dict, api=request, sleep=time.sleep) -> dict:
    payload, seen = validate(raw, digest, env)
    repo, branch, base = payload["repository"], payload["branch"], payload["base_sha"]
    default = api("GET", f"/repos/{repo}")["default_branch"]
    if not safe_branch(default) or branch == default:
        raise RepairError("Default branch writes forbidden")
    current = ref(api, repo, default)
    if current is None:
        raise RepairError("Default branch identity unavailable")
    head = ref(api, repo, branch)
    status = "already_published"
    if head is None or head == base:
        # A retry is allowed to resume an empty branch, never to rebase a payload.
        if current != base:
            raise RepairError(f"STALE_BASE: expected {base}; observed {current}. "
                              "Reprepare paths, tree and payload SHA-256 from the current base; do not rerun this payload.")
        if head is None:
            try:
                api("POST", f"/repos/{repo}/git/refs", {"ref": "refs/heads/" + branch, "sha": base})
            except APIError as error:
                if error.status not in {409, 422}:
                    raise
                # A concurrent creator may have finished the identical request.
            head = ref(api, repo, branch)
            if head is None:
                raise RepairError("Repair branch was not created")
        if head == base:
            current = ref(api, repo, default)
            if current != base:
                raise RepairError(f"STALE_BASE: expected {base}; observed {current}. Reprepare the reviewed payload.")
            changes = {kind: [{k: v for k, v in item.items() if k != "blob_sha"} for item in entries]
                       for kind, entries in payload["file_changes"].items()}
            response = api("POST", "/graphql", {"query": MUTATION, "variables": {"input": {
                "branch": {"repositoryNameWithOwner": repo, "branchName": branch},
                "expectedHeadOid": base, "message": payload["message"], "fileChanges": changes}}})
            if response.get("errors"):
                # Preserve useful API diagnostics without dumping the query, payload or token.
                errors = [{key: entry.get(key) for key in ("type", "message")}
                          for entry in response["errors"][:5]]
                raise RepairError("GraphQL commit creation failed: " + json.dumps(errors)[:2000])
            head = response["data"]["createCommitOnBranch"]["commit"]["oid"]
            if not isinstance(head, str) or not SHA.fullmatch(head):
                raise RepairError("Malformed replacement commit identity")
            status = "published"
    verified = verify(api, repo, head, payload, sleep)
    if ref(api, repo, branch) != head:
        raise RepairError("Repair branch moved during verification; inspect its current head")
    return {"schema": "aems.reviewed-repair.v1", "status": status, "repository": repo,
            "branch": branch, "base": base, "tree": payload["tree_sha"], "commit": head,
            "verified": True, "reason": "valid", "observed_default": current,
            "url": f"https://github.com/{repo}/commit/{head}", "payload_sha256": digest,
            "files": len(seen), "signer": (verified.get("committer") or {}).get("login")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--output", type=Path, default=Path("signing-result.json"))
    args = parser.parse_args(argv)
    try:
        raw = args.payload.read_bytes() if args.payload else base64.b64decode(
            os.environ["REVIEWED_PAYLOAD_BASE64"], validate=True)
        result = publish(raw, os.environ.get("EXPECTED_PAYLOAD_SHA256"), dict(os.environ))
    except (RepairError, KeyError, TypeError, AttributeError, ValueError, OSError) as error:
        print("SIGNING_REPAIR_ERROR=" + json.dumps({"status": "refused", "diagnostic": str(error)}), file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2) + "\n"
    args.output.write_text(text, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write("## Verified signing repair\n\n```json\n" + text + "```\n")
    print("SIGNING_REPAIR_RESULT=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
