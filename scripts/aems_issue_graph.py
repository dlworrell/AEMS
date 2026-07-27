#!/usr/bin/env python3
"""Validate, render, and optionally apply AEMS issue dependency graphs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aems.issue_graph import IssueGraph, IssueGraphError
from aems.structured import StructuredDataError, canonical_json, load_structured


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and render a dependency-aware AEMS issue graph."
    )
    parser.add_argument("input", help="JSON or constrained-YAML issue graph")
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="markdown"
    )
    parser.add_argument("--output", help="Write the report instead of stdout")
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Create missing issues through the GitHub API. This is explicit and "
            "idempotent by AEMS node marker."
        ),
    )
    parser.add_argument(
        "--repository",
        help="GitHub repository in owner/name form; required with --apply",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        help="GitHub API base URL",
    )
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing the GitHub token",
    )
    parser.add_argument(
        "--apply-report",
        help="Optional JSON path for issue creation/skip evidence",
    )
    return parser.parse_args()


def _request(
    url: str,
    token: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, str]]:
    data = (
        json.dumps(payload).encode("utf-8") if payload is not None else None
    )
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AEMS-issue-graph/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None, dict(response.headers)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(
            f"GitHub API {method} {url} failed with HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API {method} {url} failed: {exc.reason}") from exc


def _existing_issues(
    api_url: str, repository: str, token: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    encoded_repo = "/".join(
        urllib.parse.quote(component, safe="") for component in repository.split("/")
    )
    for page in range(1, 21):
        url = (
            f"{api_url.rstrip('/')}/repos/{encoded_repo}/issues"
            f"?state=all&per_page=100&page={page}"
        )
        values, _ = _request(url, token)
        if not isinstance(values, list):
            raise RuntimeError("GitHub issues response was not a list")
        for value in values:
            if not isinstance(value, dict) or "pull_request" in value:
                continue
            body = str(value.get("body") or "")
            marker = "<!-- aems-node:"
            start = body.find(marker)
            if start < 0:
                continue
            end = body.find(" -->", start)
            if end < 0:
                continue
            identifier = body[start + len(marker) : end].strip()
            if identifier:
                result[identifier] = value
        if len(values) < 100:
            break
    return result


def _existing_labels(api_url: str, repository: str, token: str) -> set[str]:
    encoded_repo = "/".join(
        urllib.parse.quote(component, safe="") for component in repository.split("/")
    )
    labels: set[str] = set()
    for page in range(1, 11):
        url = (
            f"{api_url.rstrip('/')}/repos/{encoded_repo}/labels"
            f"?per_page=100&page={page}"
        )
        values, _ = _request(url, token)
        if not isinstance(values, list):
            raise RuntimeError("GitHub labels response was not a list")
        labels.update(
            str(value.get("name"))
            for value in values
            if isinstance(value, dict) and value.get("name")
        )
        if len(values) < 100:
            break
    return labels


def apply_graph(
    graph: IssueGraph, *, api_url: str, repository: str, token: str
) -> dict[str, Any]:
    if repository.count("/") != 1:
        raise ValueError("--repository must use owner/name form")
    existing = _existing_issues(api_url, repository, token)
    available_labels = _existing_labels(api_url, repository, token)
    encoded_repo = "/".join(
        urllib.parse.quote(component, safe="") for component in repository.split("/")
    )
    issue_url = f"{api_url.rstrip('/')}/repos/{encoded_repo}/issues"
    records: list[dict[str, Any]] = []

    for identifier in graph.topological_order():
        node = graph.nodes[identifier]
        if identifier in existing:
            issue = existing[identifier]
            records.append(
                {
                    "aems_node_id": identifier,
                    "action": "skipped-existing",
                    "issue_number": issue.get("number"),
                    "url": issue.get("html_url"),
                }
            )
            continue

        payload = node.github_payload(children=graph.children(identifier))
        payload["labels"] = [
            label for label in payload["labels"] if label in available_labels
        ]
        created, _ = _request(
            issue_url, token, method="POST", payload=payload
        )
        if not isinstance(created, dict):
            raise RuntimeError("GitHub issue creation response was not an object")
        records.append(
            {
                "aems_node_id": identifier,
                "action": "created",
                "issue_number": created.get("number"),
                "url": created.get("html_url"),
                "labels_requested": list(node.labels),
                "labels_applied": payload["labels"],
            }
        )

    return {
        "schema_version": "1.0.0",
        "repository": repository,
        "records": records,
    }


def main() -> int:
    args = parse_args()
    try:
        loaded = load_structured(Path(args.input))
        if not isinstance(loaded, dict):
            raise IssueGraphError("issue graph root must be a mapping")
        graph = IssueGraph.from_dict(loaded)
    except (StructuredDataError, IssueGraphError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rendered = graph.to_json() if args.format == "json" else graph.to_markdown()
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if not args.apply:
        return 0
    if not args.repository:
        print("error: --repository is required with --apply", file=sys.stderr)
        return 2
    token = os.environ.get(args.token_env)
    if not token:
        print(
            f"error: token environment variable is unset: {args.token_env}",
            file=sys.stderr,
        )
        return 2
    try:
        report = apply_graph(
            graph,
            api_url=args.api_url,
            repository=args.repository,
            token=token,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    apply_report = canonical_json(report)
    if args.apply_report:
        path = Path(args.apply_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(apply_report, encoding="utf-8")
    else:
        print(apply_report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
