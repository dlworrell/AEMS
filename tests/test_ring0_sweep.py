from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ring0_sweep as r0


REPO = "dlworrell/ruleset-sandbox"
CATYLIST = "dlworrell/Catylist"
OWNER = "dlworrell"
HEAD = "a" * 40
NOW = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)
ADR0000 = "docs/adr/ADR-0000-catylist-code-of-conduct.md"

# Built at runtime so this file never contains a literal credential.
FAKE_GITHUB_TOKEN = "ghp" + "_" + "Z" * 36
FAKE_ANTHROPIC_KEY = "sk-" + "ant-" + "x" * 30
FAKE_KEY_HEADER = "-----BEGIN " + "RSA PRIVATE KEY-----"


def b64(text: str) -> dict:
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode(), "sha": "f" * 40}


def commit(sha: str = HEAD, verified: bool = True, date: str = "2026-10-26T10:00:00Z", message: str = "change") -> dict:
    return {"sha": sha, "commit": {"message": message, "verification": {"verified": verified},
                                   "committer": {"date": date}}}


def facts(**overrides) -> r0.PullRequestFacts:
    base = dict(
        repository=REPO, owner=OWNER, number=7, head_sha=HEAD, author="contributor",
        body="Fixes the parser.\n\nADR: ADR-0004", files=[{"filename": "src/a.py", "status": "modified",
                                                           "patch": "@@ -1,1 +1,2 @@\n x = 1\n+y = 2"}],
        commits=[commit()], comments=[], tree_paths=[ADR0000, "src/a.py"],
        adr0000_text="# ADR-0000\n\nCode version: 1.1.0\n", code_version="1.1.0", today="2026-10-26",
    )
    base.update(overrides)
    return r0.PullRequestFacts(**base)


def by_law(findings: list[r0.Finding], law: int) -> list[str]:
    return [f.outcome for f in findings if f.law == law]


class ParsingTests(unittest.TestCase):
    def test_adr_line_kinds(self):
        self.assertEqual(r0.parse_adr_line("x\nADR: ADR-0007 and ADR-0010")[0], "refs")
        self.assertEqual(r0.parse_adr_line("ADR: n/a - typo fix in the README only")[0], "na")
        self.assertEqual(r0.parse_adr_line("ADR: n/a")[0], "na-without-reason")
        self.assertEqual(r0.parse_adr_line("ADR:")[0], "empty")
        self.assertEqual(r0.parse_adr_line("ADR: something")[0], "empty")
        self.assertEqual(r0.parse_adr_line("no line here")[0], "missing")
        self.assertEqual(r0.parse_adr_line("ADR: this PR introduces ADR-0010")[0], "refs")

    def test_versions(self):
        self.assertEqual(r0.parse_code_version("# Code\n\nVersion: 1.1.0\nStatus: Accepted"), "1.1.0")
        self.assertEqual(r0.parse_adr0000_version("Code version: 1.0.0 (amended to 1.1.0 by ADR-0010)"), "1.0.0")
        self.assertIsNone(r0.parse_code_version(None))

    def test_added_lines_numbers_new_file_lines(self):
        patch = "@@ -10,3 +20,4 @@\n keep\n-gone\n+new one\n keep2\n+new two"
        self.assertEqual(r0.added_lines(patch), [(21, "new one"), (23, "new two")])

    def test_trusted_list(self):
        self.assertEqual(r0.parse_trusted("@Alice, bob\ncarol"), frozenset({"alice", "bob", "carol"}))
        self.assertEqual(r0.parse_trusted(""), frozenset())

    def test_secrets_never_echo_the_value(self):
        for secret in (FAKE_GITHUB_TOKEN, FAKE_ANTHROPIC_KEY, FAKE_KEY_HEADER):
            found = r0.scan_secrets(f"line one\nkey={secret}", "body")
            self.assertEqual([(f.law, f.outcome, f.location) for f in found], [(5, "violation", "body, line 2")])
            self.assertNotIn(secret, json.dumps([f.as_dict() for f in found]))
        self.assertEqual(r0.scan_secrets("nothing to see", "body"), [])

    def test_moderation_matrix(self):
        self.assertEqual(r0.moderation_action("violation", True), "hide")
        self.assertEqual(r0.moderation_action("violation", False), "hide")
        self.assertEqual(r0.moderation_action("indeterminate", False), "hide")
        self.assertEqual(r0.moderation_action("indeterminate", True), "review")
        self.assertEqual(r0.moderation_action("pass", False), "show")

    def test_combine(self):
        self.assertEqual(r0.combine(["pass", "indeterminate", "violation"]), "violation")
        self.assertEqual(r0.combine(["pass", "indeterminate"]), "indeterminate")
        self.assertEqual(r0.combine(["pass"]), "pass")
        self.assertEqual(r0.combine([]), "indeterminate")


class PullRequestCheckTests(unittest.TestCase):
    def test_conforming_pull_request_passes_every_law(self):
        findings = r0.check_pull_request(facts())
        self.assertEqual(r0.overall(findings), "pass", r0.render_findings(findings))
        self.assertEqual(sorted({f.law for f in findings}), [0, 1, 2, 3, 4, 5, 6, 7])

    def test_law0_missing_and_stale_adr0000(self):
        self.assertIn("violation", by_law(r0.check_pull_request(facts(tree_paths=["src/a.py"])), 0))
        stale = facts(adr0000_text="Code version: 1.0.0\n")
        self.assertIn("violation", by_law(r0.check_pull_request(stale), 0))
        self.assertIn("indeterminate", by_law(r0.check_pull_request(facts(code_version=None)), 0))

    def test_law0_adr0000_only_version_line_may_change(self):
        bump = {"filename": ADR0000, "status": "modified",
                "patch": "@@ -8 +8 @@\n-Code version: 1.0.0\n+Code version: 1.1.0"}
        self.assertNotIn("violation", by_law(r0.check_pull_request(facts(
            files=[bump], comments=[approval(r0.APPROVE_GOVERNANCE)])), 0))
        edit = {"filename": ADR0000, "status": "modified", "patch": "@@ -9 +9 @@\n-Ring 0 binds.\n+Ring 0 is optional."}
        self.assertIn("violation", by_law(r0.check_pull_request(facts(files=[edit])), 0))
        removed = {"filename": ADR0000, "status": "removed", "patch": ""}
        self.assertIn("violation", by_law(r0.check_pull_request(facts(files=[removed])), 0))

    def test_law1_adr_line(self):
        self.assertEqual(by_law(r0.check_pull_request(facts(body="no line")), 1), ["violation"])
        self.assertEqual(by_law(r0.check_pull_request(facts(body="ADR: n/a")), 1), ["violation"])
        self.assertEqual(by_law(r0.check_pull_request(facts(body="ADR: n/a, bumps a pinned action")), 1), ["pass"])
        bot = facts(body="Bump x", author="dependabot[bot]", standing_adr={"dependabot[bot]": "ADR-0011"})
        self.assertEqual(by_law(r0.check_pull_request(bot), 1), ["pass"])

    def test_law2_waiver_expiry(self):
        name = "docs/adr/ADR-0012-waiver-sec.md"
        files = [{"filename": name, "status": "added", "patch": "@@ -0,0 +1 @@\n+x"}]
        approved = [approval(r0.APPROVE_GOVERNANCE)]
        expired = facts(files=files, comments=approved, file_texts={name: "Status: Waiver\nExpires: 2026-01-01\n"})
        self.assertIn("violation", by_law(r0.check_pull_request(expired), 2))
        missing = facts(files=files, comments=approved, file_texts={name: "Status: Waiver\n"})
        self.assertIn("violation", by_law(r0.check_pull_request(missing), 2))
        valid = facts(files=files, comments=approved, file_texts={name: "Status: Waiver\nExpires: 2027-01-01\n"})
        self.assertEqual(by_law(r0.check_pull_request(valid), 2), ["pass"])

    def test_law3_unsigned_commit(self):
        findings = r0.check_pull_request(facts(commits=[commit(verified=False)]))
        self.assertEqual(by_law(findings, 3), ["violation"])
        self.assertEqual(by_law(r0.check_pull_request(facts(commits=[])), 3), ["indeterminate"])

    def test_law4_governance_change_needs_owner_approval_after_head(self):
        files = [{"filename": ".github/workflows/ci.yml", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"}]
        self.assertEqual(by_law(r0.check_pull_request(facts(files=files)), 4), ["violation"])
        ok = facts(files=files, comments=[approval(r0.APPROVE_GOVERNANCE)])
        self.assertEqual(by_law(r0.check_pull_request(ok), 4), ["pass"])
        stale = facts(files=files, comments=[approval(r0.APPROVE_GOVERNANCE, at="2026-10-26T09:00:00Z")])
        self.assertEqual(by_law(r0.check_pull_request(stale), 4), ["violation"])
        stranger = facts(files=files, comments=[approval(r0.APPROVE_GOVERNANCE, user="someone")])
        self.assertEqual(by_law(r0.check_pull_request(stranger), 4), ["violation"])

    def test_law5_secret_in_added_line(self):
        files = [{"filename": "config.py", "status": "modified",
                  "patch": f"@@ -1 +1,2 @@\n x = 1\n+TOKEN = '{FAKE_GITHUB_TOKEN}'"}]
        findings = [f for f in r0.check_pull_request(facts(files=files)) if f.law == 5]
        self.assertEqual([(f.outcome, f.location) for f in findings], [("violation", "config.py, line 2")])
        self.assertNotIn(FAKE_GITHUB_TOKEN, json.dumps([f.as_dict() for f in findings]))

    def test_law6_skipped_or_deleted_tests(self):
        skip = [{"filename": "tests/test_a.py", "status": "modified", "patch": "@@ -1 +1,2 @@\n x\n+@unittest.skip('flaky')"}]
        self.assertEqual(by_law(r0.check_pull_request(facts(files=skip)), 6), ["violation"])
        gone = [{"filename": "tests/test_b.py", "status": "removed", "patch": ""}]
        self.assertEqual(by_law(r0.check_pull_request(facts(files=gone)), 6), ["violation"])
        ok = facts(files=skip, comments=[approval(r0.APPROVE_TESTS)])
        self.assertEqual(by_law(r0.check_pull_request(ok), 6), ["pass"])

    def test_law7_code_restated_outside_catylist(self):
        files = [{"filename": "CODE_OF_CONDUCT.md", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"}]
        texts = {"CODE_OF_CONDUCT.md": "### Law 0: Ring 0\n"}
        approved = [approval(r0.APPROVE_GOVERNANCE)]
        self.assertEqual(by_law(r0.check_pull_request(facts(files=files, file_texts=texts, comments=approved)), 7),
                         ["violation"])
        pointer = {"CODE_OF_CONDUCT.md": "See the Catylist Code of Conduct.\n"}
        self.assertEqual(by_law(r0.check_pull_request(facts(files=files, file_texts=pointer, comments=approved)), 7),
                         ["pass"])
        catylist = facts(files=files, file_texts=texts, comments=approved, is_catylist=True)
        self.assertEqual(by_law(r0.check_pull_request(catylist), 7), ["pass"])


def approval(marker: str, user: str = OWNER, at: str = "2026-10-26T11:00:00Z") -> dict:
    return {"id": 99, "user": {"login": user}, "body": marker, "created_at": at}


class AttributionTests(unittest.TestCase):
    def test_title_line_is_parsed(self):
        a = r0.agent_attribution("**Claude for @dlworrell**\n\nDone.")
        self.assertEqual((a.agent, a.prompted_by), ("claude", "dlworrell"))
        a = r0.agent_attribution("ChatGPT for @dlworrell\nhello")
        self.assertEqual((a.agent, a.prompted_by), ("chatgpt", "dlworrell"))
        self.assertIsNone(r0.agent_attribution("I asked Claude for @dlworrell's help").agent)

    def test_law4_attribution_findings(self):
        self.assertEqual([f.outcome for f in r0.attribution_findings("**Notion for @dlworrell**\nx", "dlworrell", "c")],
                         ["pass"])
        wrong = r0.attribution_findings("**Claude for @someone**\nx", "dlworrell", "c")
        self.assertEqual([f.outcome for f in wrong], ["violation"])
        untitled = r0.attribution_findings("Fixed.\n\n_Generated by [Claude Code](https://claude.ai/code)_", "dlworrell", "c")
        self.assertEqual([f.outcome for f in untitled], ["violation"])
        self.assertEqual(r0.attribution_findings("A person wrote this.", "dlworrell", "c"), [])

    def test_agent_trust_needs_agent_and_prompter(self):
        trusted = frozenset({"dlworrell", "claude"})
        self.assertTrue(r0.trusted_author("dlworrell", "plain text", trusted))
        self.assertTrue(r0.trusted_author("dlworrell", "**Claude for @dlworrell**\nx", trusted))
        self.assertFalse(r0.trusted_author("dlworrell", "**ChatGPT for @dlworrell**\nx", trusted))
        self.assertFalse(r0.trusted_author("visitor", "**Claude for @visitor**\nx", trusted))

    def test_agent_cannot_give_owner_approval(self):
        files = [{"filename": ".github/workflows/ci.yml", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"}]
        agent = approval("**Claude for @dlworrell**\n\n" + r0.APPROVE_GOVERNANCE)
        self.assertEqual(by_law(r0.check_pull_request(facts(files=files, comments=[agent])), 4), ["violation"])
        footer = approval(r0.APPROVE_GOVERNANCE + "\n\n_Generated by [Claude Code](https://claude.ai/code)_")
        self.assertEqual(by_law(r0.check_pull_request(facts(files=files, comments=[footer])), 4), ["violation"])

    def test_untitled_agent_pull_request_fails_law4(self):
        body = "Change.\n\nADR: ADR-0004\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"
        self.assertIn("violation", by_law(r0.check_pull_request(facts(body=body, author="dlworrell")), 4))
        titled = "**Claude for @dlworrell**\n\n" + body
        self.assertNotIn("violation", by_law(r0.check_pull_request(facts(body=titled, author="dlworrell")), 4))


class VerdictTests(unittest.TestCase):
    def verdict(self, outcome="pass", findings=None):
        return {"outcome": outcome, "summary": "s", "findings": findings if findings is not None else [
            {"law": 8, "outcome": "pass", "evidence": "respectful", "location": "", "remedy": "", "condition_note": ""}]}

    def test_valid_verdict(self):
        findings, summary = r0.parse_verdict(self.verdict())
        self.assertEqual((r0.overall(findings), summary), ("pass", "s"))

    def test_stated_pass_cannot_outrank_a_failing_finding(self):
        bad = self.verdict("pass", [{"law": 8, "outcome": "violation", "evidence": "insult", "location": "c1",
                                     "remedy": "edit", "condition_note": "pressure"}])
        findings, _ = r0.parse_verdict(bad)
        self.assertEqual(r0.overall(findings), "violation")
        self.assertIn("Condition: pressure", findings[0].evidence)

    def test_stated_violation_outranks_passing_findings(self):
        findings, _ = r0.parse_verdict(self.verdict("violation"))
        self.assertEqual(r0.overall(findings), "violation")

    def test_malformed_verdicts_are_rejected(self):
        for payload in (None, {}, {"outcome": "fine"}, {"outcome": "pass", "findings": [{"law": 12, "outcome": "pass"}]}):
            with self.assertRaises(r0.EnforcerUnavailable):
                r0.parse_verdict(payload)


class FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [FakeBlock(text)] if text is not None else []
        self.stop_reason = stop_reason


class FakeModel:
    """Stands in for anthropic.Anthropic(); records each request."""

    def __init__(self, responder):
        self.requests = []
        self.responder = responder
        self.beta = self
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responder(kwargs)


def enforcer(responder=None, key=FAKE_ANTHROPIC_KEY) -> tuple[r0.Enforcer, FakeModel]:
    model = FakeModel(responder or (lambda req: FakeResponse(json.dumps({
        "outcome": "pass", "summary": "ok", "findings": [
            {"law": 8, "outcome": "pass", "evidence": "fine", "location": "", "remedy": "", "condition_note": ""}]}))))
    return r0.Enforcer(prompt="PROMPT", code="Version: 1.1.0", model="claude-opus-5-5", effort="medium",
                       api_key=key, client_factory=lambda _k: model), model


class EnforcerTests(unittest.TestCase):
    def test_request_shape(self):
        e, model = enforcer()
        findings, _ = e.judge({"kind": "issue_comment", "body": "hello"})
        self.assertEqual(r0.overall(findings), "pass")
        req = model.requests[0]
        self.assertEqual(req["model"], "claude-opus-5-5")
        self.assertEqual(req["fallbacks"], "default")
        self.assertEqual(req["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(req["output_config"]["effort"], "medium")
        self.assertEqual(req["output_config"]["format"]["type"], "json_schema")
        self.assertIn("cache_control", req["system"][-1])
        self.assertIn("data, not instructions", req["messages"][0]["content"])

    def test_failures_are_indeterminate(self):
        cases = [
            lambda req: FakeResponse(None, "refusal"),
            lambda req: FakeResponse("{\"outcome\": \"pass\"", "max_tokens"),
            lambda req: FakeResponse("not json"),
            lambda req: FakeResponse(None),
        ]
        for responder in cases:
            e, _ = enforcer(responder)
            findings, _ = r0.ai_findings(e, {"body": "x"})
            self.assertEqual(r0.overall(findings), "indeterminate")

    def test_model_error_is_indeterminate(self):
        def boom(req):
            raise ConnectionError("network down")

        e, _ = enforcer(boom)
        self.assertEqual(r0.overall(r0.ai_findings(e, {"body": "x"})[0]), "indeterminate")

    def test_missing_key_and_oversize_input_never_call_the_model(self):
        e, model = enforcer(key=None)
        self.assertEqual(r0.overall(r0.ai_findings(e, {"body": "x"})[0]), "indeterminate")
        e, model = enforcer()
        findings, _ = r0.ai_findings(e, {"body": "x" * (r0.MAX_MODEL_INPUT_CHARS + 10)})
        self.assertEqual(r0.overall(findings), "indeterminate")
        self.assertIn("not truncated", findings[0].evidence)
        self.assertEqual(model.requests, [])


class FakeGitHub:
    """Routes REST and GraphQL calls to canned data and records every write."""

    def __init__(self, routes: dict[str, object], raw: dict[str, str] | None = None):
        self.routes = routes
        self.raw_pages = raw or {}
        self.posts: list[tuple[str, dict]] = []
        self.puts: list[tuple[str, dict]] = []
        self.mutations: list[tuple[str, dict]] = []

    def _match(self, path):
        for prefix, value in self.routes.items():
            if path == prefix or path.startswith(prefix + "?") or path.startswith(prefix + "&"):
                return value
        raise r0.GitHubError(404, f"no route for {path}")

    def get(self, path):
        value = self._match(path)
        if isinstance(value, Exception):
            raise value
        return value

    def get_all(self, path, limit=1000):
        value = self.get(path)
        if isinstance(value, dict) and "repositories" in value:
            value = value["repositories"]
        return list(value)[:limit]

    def post(self, path, body):
        self.posts.append((path, body))
        return {"number": len(self.posts)}

    def put(self, path, body):
        self.puts.append((path, body))
        return {}

    def graphql(self, query, variables):
        if "mutation" in query:
            self.mutations.append(("unminimize" if "unminimizeComment" in query else "minimize", variables))
            return {}
        return self.routes.get("graphql", {})

    def raw(self, url):
        return self.raw_pages.get(url)


def routes(**extra) -> dict:
    base = {
        f"/repos/{CATYLIST}/contents/CODE_OF_CONDUCT.md": b64("# Code\n\nVersion: 1.1.0\n"),
        "/installation/repositories": {"repositories": [{"full_name": REPO}]},
        f"/repos/{REPO}/pulls?state=open&sort=updated&direction=desc&per_page=100": [],
        f"/repos/{REPO}/issues": [],
        f"/repos/{REPO}/issues/comments": [],
        f"/repos/{REPO}/pulls/comments": [],
        f"/repos/{REPO}/comments": [],
        f"/repos/{REPO}/pulls?state=all&sort=updated&direction=desc&per_page=50": [],
        f"/repos/{REPO}/releases": [],
        f"/repos/{REPO}/events": [],
        "graphql": {"repository": {"discussions": {"nodes": []}}},
    }
    base.update(extra)
    return base


def comment(body: str, user: str = "visitor", node: str = "IC_1", updated: str = "2026-10-26T11:50:00Z") -> dict:
    return {"id": 1, "node_id": node, "html_url": f"https://github.com/{REPO}/issues/1#c1", "body": body,
            "user": {"login": user}, "updated_at": updated}


def make_sweep(gh: FakeGitHub, responder=None, key=FAKE_ANTHROPIC_KEY, trusted=frozenset(), dry_run=False,
               state=None, tmp=None, publishing=None):
    config = r0.Config(CATYLIST, "dlworrell/AEMS", "claude-opus-5-5", "medium", [REPO], {}, publishing or {})
    ledger = r0.LedgerStore(None, "dlworrell/AEMS", dry_run, Path(tmp))
    if state is not None:
        ledger.load_state = lambda: state  # type: ignore[assignment]
    e, model = enforcer(responder, key)
    sweep = r0.Sweep(github=gh, ledger=ledger, enforcer=e, config=config, now=NOW, trusted=trusted,
                     dry_run=dry_run, log=lambda _m: None)
    return sweep, model


def violation_responder(req):
    return FakeResponse(json.dumps({"outcome": "violation", "summary": "Personal attack.", "findings": [
        {"law": 8, "outcome": "violation", "evidence": "\"you are an idiot\"", "location": "comment",
         "remedy": "Edit the comment to address the work.", "condition_note": ""}]}))


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def pr_routes(self, body="Change.\n\nADR: ADR-0004", verified=True):
        pr = {"number": 7, "head": {"sha": HEAD}, "body": body, "title": "Change", "user": {"login": "contributor"},
              "html_url": f"https://github.com/{REPO}/pull/7", "updated_at": "2026-10-26T11:55:00Z"}
        return routes(**{
            f"/repos/{REPO}/pulls?state=open&sort=updated&direction=desc&per_page=100": [pr],
            f"/repos/{REPO}/issues/7/comments": [],
            f"/repos/{REPO}/pulls/7/files": [{"filename": "src/a.py", "status": "modified",
                                              "patch": "@@ -1 +1,2 @@\n x\n+y"}],
            f"/repos/{REPO}/pulls/7/commits": [commit(verified=verified)],
            f"/repos/{REPO}/pulls/7/reviews": [],
            f"/repos/{REPO}/git/trees/{HEAD}": {"tree": [{"path": ADR0000, "type": "blob"}]},
            f"/repos/{REPO}/contents/{ADR0000.replace('/', '%2F')}": b64("Code version: 1.1.0\n"),
            f"/repos/{REPO}/contents/{ADR0000}": b64("Code version: 1.1.0\n"),
        })

    def test_pull_request_gets_both_check_runs(self):
        gh = FakeGitHub(self.pr_routes())
        sweep, _ = make_sweep(gh, tmp=self.tmp.name)
        self.assertEqual(sweep.run(), 0, sweep.errors)
        checks = {b["name"]: b for p, b in gh.posts if p.endswith("/check-runs")}
        self.assertEqual(set(checks), {"ring-0", "ring-0/conduct"})
        self.assertEqual(checks["ring-0"]["conclusion"], "success")
        self.assertEqual(checks["ring-0/conduct"]["conclusion"], "success")
        self.assertIn("not human review", checks["ring-0/conduct"]["output"]["summary"])

    def test_unsigned_pull_request_fails_ring0(self):
        gh = FakeGitHub(self.pr_routes(verified=False))
        sweep, _ = make_sweep(gh, tmp=self.tmp.name)
        sweep.run()
        checks = {b["name"]: b for p, b in gh.posts if p.endswith("/check-runs")}
        self.assertEqual(checks["ring-0"]["conclusion"], "failure")

    def test_without_model_key_conduct_fails_closed(self):
        gh = FakeGitHub(self.pr_routes())
        sweep, model = make_sweep(gh, key=None, tmp=self.tmp.name)
        sweep.run()
        checks = {b["name"]: b for p, b in gh.posts if p.endswith("/check-runs")}
        self.assertEqual(checks["ring-0/conduct"]["conclusion"], "failure")
        self.assertIn("Indeterminate", checks["ring-0/conduct"]["output"]["title"])
        self.assertEqual(model.requests, [])

    def test_dry_run_writes_nothing(self):
        gh = FakeGitHub(self.pr_routes())
        sweep, _ = make_sweep(gh, dry_run=True, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual((gh.posts, gh.puts, gh.mutations), ([], [], []))
        self.assertTrue((Path(self.tmp.name) / "ledger.jsonl").read_text())

    def test_failing_comment_is_hidden_and_reported(self):
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues/comments": [comment("you are an idiot")]}))
        sweep, _ = make_sweep(gh, violation_responder, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(gh.mutations, [("minimize", {"id": "IC_1"})])
        issues = [b for p, b in gh.posts if p == f"/repos/{CATYLIST}/issues"]
        self.assertEqual(len(issues), 1)
        self.assertIn("ring-0 violation", issues[0]["title"])
        record = sweep.ledger.records[0]
        self.assertEqual((record["outcome"], record["action"]), ("violation", "hidden"))
        self.assertNotIn("you are an idiot\n", json.dumps(record))
        self.assertEqual(record["content_sha256"], r0.content_hash("you are an idiot"))

    def test_secret_in_comment_is_hidden_without_repeating_it(self):
        body = f"here is my token {FAKE_GITHUB_TOKEN}"
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues/comments": [comment(body)]}))
        sweep, _ = make_sweep(gh, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(gh.mutations, [("minimize", {"id": "IC_1"})])
        written = json.dumps([gh.posts, sweep.ledger.records])
        self.assertNotIn(FAKE_GITHUB_TOKEN, written)

    def test_untrusted_indeterminate_is_hidden_trusted_goes_to_review(self):
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues/comments": [comment("hello", user="visitor")]}))
        sweep, _ = make_sweep(gh, key=None, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(gh.mutations, [("minimize", {"id": "IC_1"})])

        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues/comments": [comment("hello", user="visitor")]}))
        sweep, _ = make_sweep(gh, key=None, trusted=frozenset({"visitor"}), tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(gh.mutations, [])
        self.assertEqual(sweep.ledger.records[0]["action"], "sent to the maintainer")

    def test_previously_hidden_post_is_shown_once_it_passes(self):
        state = {"last_sweep": {}, "checked": {}, "issues": {}, "hidden": {"IC_1": {"at": "2026-10-26T11:30:00Z"}}}
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues/comments": [comment("thanks, fixed")]}))
        sweep, _ = make_sweep(gh, state=state, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(gh.mutations, [("unminimize", {"id": "IC_1"})])
        self.assertNotIn("IC_1", state["hidden"])

    def test_issue_bodies_cannot_be_hidden_so_they_are_reported(self):
        issue = {"number": 3, "node_id": "I_3", "title": "Bug", "body": "you are an idiot",
                 "user": {"login": "visitor"}, "html_url": f"https://github.com/{REPO}/issues/3"}
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues": [issue]}))
        sweep, _ = make_sweep(gh, violation_responder, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(gh.mutations, [])
        self.assertIn("cannot hide", sweep.ledger.records[0]["action"])

    def test_unchanged_items_are_not_reevaluated(self):
        state = {"last_sweep": {}, "checked": {}, "issues": {}, "hidden": {}}
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues/comments": [comment("hello")]}))
        sweep, model = make_sweep(gh, state=state, tmp=self.tmp.name)
        sweep.run()
        sweep2, model2 = make_sweep(gh, state=state, tmp=self.tmp.name)
        sweep2.run()
        self.assertEqual((len(model.requests), len(model2.requests)), (1, 0))

    def test_discussions_and_wiki_edits_are_checked(self):
        disc = {"id": "D_1", "number": 1, "title": "Plan", "body": "Let's plan.", "url": "u",
                "updatedAt": "2026-10-26T11:50:00Z", "author": {"login": "visitor"},
                "comments": {"nodes": [{"id": "DC_1", "body": "you are an idiot", "url": "u2",
                                        "updatedAt": "2026-10-26T11:51:00Z", "author": {"login": "visitor"},
                                        "replies": {"nodes": []}}]}}
        gollum = {"type": "GollumEvent", "created_at": "2026-10-26T11:52:00Z", "actor": {"login": "visitor"},
                  "payload": {"pages": [{"page_name": "Architecture", "sha": "b" * 40, "action": "edited",
                                         "html_url": "w"}]}}

        def responder(req):
            if "idiot" in req["messages"][0]["content"]:
                return violation_responder(req)
            return FakeResponse(json.dumps({"outcome": "pass", "summary": "", "findings": []}))

        gh = FakeGitHub(routes(graphql={"repository": {"discussions": {"nodes": [disc]}}},
                               **{f"/repos/{REPO}/events": [gollum]}),
                        raw={f"{r0.RAW_WIKI_ROOT}/{REPO}/Architecture.md": "# Architecture\n"})
        sweep, _ = make_sweep(gh, responder, tmp=self.tmp.name)
        sweep.run()
        kinds = {(r["kind"], r["outcome"]) for r in sweep.ledger.records}
        self.assertIn(("discussion", "pass"), kinds)
        self.assertIn(("discussion_comment", "violation"), kinds)
        self.assertIn(("wiki_edit", "pass"), kinds)
        self.assertEqual(gh.mutations, [("minimize", {"id": "DC_1"})])

    def test_push_with_secret_is_reported(self):
        sha = "c" * 40
        push = {"type": "PushEvent", "created_at": "2026-10-26T11:52:00Z", "actor": {"login": "visitor"},
                "payload": {"ref": "refs/heads/feature", "commits": [{"sha": sha}]}}
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/events": [push],
            f"/repos/{REPO}/commits/{sha}": {"commit": {"message": "add", "verification": {"verified": True}},
                                              "files": [{"filename": "k.txt", "patch": f"@@ -0,0 +1 @@\n+{FAKE_ANTHROPIC_KEY}"}]},
        }))
        sweep, _ = make_sweep(gh, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(sweep.ledger.records[0]["outcome"], "violation")
        self.assertEqual(len([p for p, _ in gh.posts if p == f"/repos/{CATYLIST}/issues"]), 1)
        self.assertNotIn(FAKE_ANTHROPIC_KEY, json.dumps([gh.posts, sweep.ledger.records]))

    def test_ring0_does_not_judge_its_own_reports(self):
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues/comments": [comment("you are an idiot", user=r0.APP_BOT_LOGIN)]}))
        sweep, model = make_sweep(gh, violation_responder, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual((model.requests, gh.mutations, sweep.ledger.records), ([], [], []))

    def test_push_without_commit_list_uses_compare(self):
        before, head = "d" * 40, "e" * 40
        push = {"type": "PushEvent", "created_at": "2026-10-26T11:52:00Z", "actor": {"login": "visitor"},
                "payload": {"ref": "refs/heads/feature", "before": before, "head": head}}
        gh = FakeGitHub(routes(**{
            f"/repos/{REPO}/events": [push],
            f"/repos/{REPO}/compare/{before}...{head}": {"commits": [{"sha": head}]},
            f"/repos/{REPO}/commits/{head}": {"commit": {"message": "x", "verification": {"verified": False}}, "files": []},
        }))
        sweep, _ = make_sweep(gh, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual([(r["kind"], r["outcome"]) for r in sweep.ledger.records], [("push", "violation")])

    def test_trusted_agent_comment_is_not_hidden_when_indeterminate(self):
        body = "**Claude for @dlworrell**\n\nRebased the notes."
        gh = FakeGitHub(routes(**{f"/repos/{REPO}/issues/comments": [comment(body, user="dlworrell")]}))
        sweep, _ = make_sweep(gh, key=None, trusted=frozenset({"dlworrell", "claude"}), tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(gh.mutations, [])
        self.assertEqual(sweep.ledger.records[0]["trust"], "trusted")

    def test_trust_file_in_catylist_is_read(self):
        trust = {"schema": r0.TRUST_SCHEMA, "people": [{"login": "visitor"}],
                 "agents": [{"name": "claude", "github_login": "claude"}, {"name": "notion", "github_login": None}]}
        gh = FakeGitHub(routes(**{f"/repos/{CATYLIST}/contents/{r0.TRUST_FILE}": b64(json.dumps(trust)),
                                  f"/repos/{REPO}/issues/comments": [comment("hello", user="visitor")]}))
        sweep, _ = make_sweep(gh, key=None, tmp=self.tmp.name)
        sweep.run()
        self.assertEqual(sweep.trusted, frozenset({"visitor", "claude", "notion"}))
        self.assertEqual(gh.mutations, [])

    def test_bad_trust_file_stops_the_sweep(self):
        gh = FakeGitHub(routes(**{f"/repos/{CATYLIST}/contents/{r0.TRUST_FILE}": b64("{\"schema\": \"x\"}")}))
        sweep, _ = make_sweep(gh, tmp=self.tmp.name)
        with self.assertRaises(r0.Ring0Error):
            sweep.run()

    def test_uninstalled_repository_is_an_error(self):
        gh = FakeGitHub(routes(**{"/installation/repositories": {"repositories": []}}))
        sweep, _ = make_sweep(gh, tmp=self.tmp.name)
        self.assertEqual(sweep.run(), 1)
        self.assertIn("not installed", sweep.errors[0])


class ConfigTests(unittest.TestCase):
    def write(self, data) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(data, tmp)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_repository_config_loads(self):
        config = r0.Config.load(Path(__file__).resolve().parents[1] / "config" / "ring0.json")
        self.assertEqual(config.catylist, CATYLIST)
        self.assertIn(REPO, config.repositories)
        self.assertEqual(config.model, "claude-opus-5-5")

    def test_invalid_config_is_refused(self):
        good = {"schema": r0.CONFIG_SCHEMA, "catylist": CATYLIST, "ledger_repository": "dlworrell/AEMS",
                "model": "claude-opus-5-5", "effort": "medium", "repositories": [REPO]}
        for change in ({"schema": "x"}, {"repositories": ["not a repo"]}, {"effort": "extreme"}):
            with self.assertRaises(r0.Ring0Error):
                r0.Config.load(self.write({**good, **change}))


PUB_REPO = "dlworrell/atarix"
PUB_BRANCH = "automation/project-zero-inventory"
PUB_TARGET = r0.PublishTarget(PUB_BRANCH, ("project-zero/inventory/current/",), ("github-actions[bot]",))
GEN = "c" * 40


def generated(sha=GEN, verified=True, reason="valid", author="github-actions[bot]", committer="web-flow"):
    return {"sha": sha, "author": {"login": author}, "committer": {"login": committer},
            "commit": {"message": "chore: update Project Zero inventory\n\nbody",
                       "verification": {"verified": verified, "reason": reason}}}


def compare(commits=None, files=None, ahead=None):
    commits = [generated()] if commits is None else commits
    return {"ahead_by": len(commits) if ahead is None else ahead, "commits": commits,
            "html_url": f"https://github.com/{PUB_REPO}/compare/main...{PUB_BRANCH}",
            "files": [{"filename": f} for f in (files or ["project-zero/inventory/current/README.md"])]}


class PublicationRefusalTests(unittest.TestCase):
    def test_single_github_signed_generated_commit_is_accepted(self):
        self.assertIsNone(r0.publication_refusal(PUB_TARGET, compare()))

    def test_everything_else_is_refused(self):
        cases = {
            "commits ahead": compare(commits=[generated(), generated("d" * 40)]),
            "not GitHub-verified": compare(commits=[generated(verified=False, reason="unsigned")]),
            "not GitHub-verified ": compare(commits=[generated(reason="unknown_key")]),
            "authored by dlworrell": compare(commits=[generated(author="dlworrell")]),
            "not committed and signed by GitHub": compare(commits=[generated(committer="someone")]),
            "outside": compare(files=["project-zero/inventory/current/x.txt", ".github/workflows/ci.yml"]),
            "changes no files": {**compare(), "files": []},
        }
        for expected, value in cases.items():
            with self.subTest(expected):
                self.assertIn(expected.strip(), r0.publication_refusal(PUB_TARGET, value) or "")

    def test_path_prefix_is_a_directory_boundary(self):
        self.assertTrue(PUB_TARGET.covers("project-zero/inventory/current/a.txt"))
        self.assertFalse(PUB_TARGET.covers("project-zero/inventory/current-evil/a.txt"))

    def test_config_rejects_unsafe_targets(self):
        for value in ({"branch": "main", "paths": ["a/"], "authors": ["b"]},
                      {"branch": "automation/../main", "paths": ["a/"], "authors": ["b"]},
                      {"branch": "automation/x", "paths": [], "authors": ["b"]},
                      {"branch": "automation/x", "paths": ["../a"], "authors": ["b"]},
                      {"branch": "automation/x", "paths": ["a/"], "authors": []}):
            with self.subTest(value=value), self.assertRaises(r0.Ring0Error):
                r0.PublishTarget.parse(value, "test")


class PublicationSweepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def run_sweep(self, comparison, open_prs=None, dry_run=False):
        gh = FakeGitHub(routes(**{
            "/installation/repositories": {"repositories": [{"full_name": REPO}, {"full_name": PUB_REPO}]},
            f"/repos/{PUB_REPO}": {"default_branch": "main"},
            f"/repos/{PUB_REPO}/compare/main...{PUB_BRANCH}": comparison,
            f"/repos/{PUB_REPO}/pulls?state=open&head=dlworrell:{PUB_BRANCH}&base=main&per_page=10": open_prs or [],
        }))
        sweep, _ = make_sweep(gh, dry_run=dry_run, tmp=self.tmp.name, publishing={PUB_REPO: [PUB_TARGET]})
        status = sweep.run()
        return gh, sweep, status

    def test_verified_branch_gets_a_pull_request_without_approval(self):
        gh, sweep, status = self.run_sweep(compare())
        self.assertEqual(status, 0, sweep.errors)
        opened = [b for p, b in gh.posts if p == f"/repos/{PUB_REPO}/pulls"]
        self.assertEqual(len(opened), 1)
        self.assertEqual((opened[0]["head"], opened[0]["base"]), (PUB_BRANCH, "main"))
        self.assertEqual(opened[0]["title"], "chore: update Project Zero inventory")
        self.assertIn(GEN, opened[0]["body"])
        self.assertEqual(r0.parse_adr_line(opened[0]["body"])[0], "refs")
        self.assertIn("never approves or merges", opened[0]["body"])
        self.assertFalse(any("/reviews" in p or "/merge" in p for p, _ in gh.posts + gh.puts))
        self.assertEqual(sweep.ledger.records[0]["action"], "opened pull request #1")

    def test_existing_pull_request_is_not_duplicated(self):
        gh, _, _ = self.run_sweep(compare(), open_prs=[{"number": 63}])
        self.assertFalse([p for p, _ in gh.posts if p == f"/repos/{PUB_REPO}/pulls"])

    def test_unverified_branch_is_reported_not_opened(self):
        gh, sweep, _ = self.run_sweep(compare(commits=[generated(verified=False, reason="unsigned")]))
        self.assertFalse([p for p, _ in gh.posts if p == f"/repos/{PUB_REPO}/pulls"])
        self.assertEqual(len([p for p, _ in gh.posts if p == f"/repos/{CATYLIST}/issues"]), 1)
        self.assertEqual(sweep.ledger.records[0]["outcome"], "violation")

    def test_merged_or_missing_branch_is_skipped(self):
        gh, sweep, status = self.run_sweep(compare(commits=[], ahead=0))
        self.assertEqual((status, gh.posts, sweep.ledger.records), (0, [], []))
        gh, sweep, status = self.run_sweep(r0.GitHubError(404, "missing"))
        self.assertEqual((status, gh.posts), (0, []))

    def test_dry_run_only_records(self):
        gh, sweep, _ = self.run_sweep(compare(), dry_run=True)
        self.assertEqual(gh.posts, [])
        self.assertIn("dry run", sweep.ledger.records[0]["action"])


if __name__ == "__main__":
    unittest.main()
