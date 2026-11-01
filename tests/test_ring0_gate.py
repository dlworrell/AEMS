import base64
import datetime as dt
import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("ring0_gate", ROOT / "scripts/ring0_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["ring0_gate"] = gate
spec.loader.exec_module(gate)

NOW = dt.datetime(2026, 11, 1, 20, 0, tzinfo=dt.timezone.utc)
REPO = "dlworrell/demo"


class FakeGitHub:
    def __init__(self):
        self.heads = {"dev-daily": "d1", "fitment": "f1", "main": "m1"}
        self.pulls = [{"number": 5, "base": {"ref": "fitment"}, "head": {"sha": "d1"}}]
        self.checks = {"f1": [{"name": "tests", "status": "completed", "conclusion": "success"}],
                       "d1": [{"name": "tests", "status": "in_progress", "conclusion": None}]}
        self.files = {}
        self.puts = []
        self.fail = None  # path fragment whose GET raises GitHubError(500)

    def get(self, path):
        if self.fail and self.fail in path:
            raise gate.GitHubError(500, "Server Error")
        if path == f"/repos/{REPO}":
            return {"default_branch": "main"}
        if "/branches/" in path:
            branch = path.rsplit("/", 1)[1]
            if branch not in self.heads:
                raise gate.GitHubError(404, "Branch not found")
            return {"commit": {"sha": self.heads[branch]}}
        if "/check-runs" in path:
            sha = path.split("/commits/")[1].split("/")[0]
            return {"check_runs": self.checks.get(sha, [])}
        if "/contents/" in path:
            name = path.split("/contents/")[1].split("?")[0]
            if name not in self.files:
                raise gate.GitHubError(404, "Not Found")
            return {"content": base64.b64encode(self.files[name].encode()).decode(), "encoding": "base64",
                    "sha": "blob1"}
        raise AssertionError(path)

    def get_all(self, path, limit=1000):
        assert "pulls?state=open" in path, path
        return self.pulls

    def put(self, path, body):
        name = path.split("/contents/")[1]
        self.files[name.replace("%2F", "/")] = base64.b64decode(body["content"]).decode()
        self.puts.append(body)
        return {}


class Ring0GateTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_ignores_own_checks(self):
        gh = FakeGitHub()
        first = gate.fingerprint(gh, [REPO])
        self.assertEqual(first, gate.fingerprint(gh, [REPO]))
        gh.checks["f1"].append({"name": "fitment/source", "status": "completed", "conclusion": "success"})
        self.assertEqual(first, gate.fingerprint(gh, [REPO]))  # ring-0's own check must not retrigger it

    def test_changes_that_must_trigger_a_run(self):
        mutations = {
            "new commit on dev-daily": lambda g: g.heads.__setitem__("dev-daily", "d2"),
            "new pull request": lambda g: g.pulls.append({"number": 6, "base": {"ref": "dev-daily"},
                                                         "head": {"sha": "x"}}),
            "CI finished on a promotion head": lambda g: g.checks.__setitem__(
                "d1", [{"name": "tests", "status": "completed", "conclusion": "success"}]),
            "CI result on fitment": lambda g: g.checks["f1"].__setitem__(0, dict(g.checks["f1"][0], conclusion="failure")),
            "branch deleted": lambda g: g.heads.pop("fitment"),
        }
        base = gate.fingerprint(FakeGitHub(), [REPO])
        for label, mutate in mutations.items():
            gh = FakeGitHub()
            mutate(gh)
            with self.subTest(label):
                self.assertNotEqual(base, gate.fingerprint(gh, [REPO]))

    def test_decide(self):
        fp = "a" * 64
        recent = {"fingerprint": fp, "recorded_at": (NOW - dt.timedelta(hours=1)).isoformat()}
        self.assertEqual(gate.decide(None, fp, NOW, 6), (True, "no recorded run yet"))
        self.assertEqual(gate.decide(recent, fp, NOW, 6)[0], False)
        self.assertEqual(gate.decide(recent, "b" * 64, NOW, 6), (True, "something changed"))
        old = dict(recent, recorded_at=(NOW - dt.timedelta(hours=7)).isoformat())
        self.assertTrue(gate.decide(old, fp, NOW, 6)[0])
        self.assertEqual(gate.decide({"fingerprint": fp}, fp, NOW, 6), (True, "unreadable record"))

    def test_check_then_record_then_skip_cli(self):
        gh = FakeGitHub()
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "fitment.json"
            config.write_text(json.dumps({"schema": "aems.fitment-config.v1", "repositories": [REPO]}))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(gate.main(["check", "--name", "fitment-cycle", "--config", str(config)],
                                           reader=gh, ledger=gh, now=NOW), 0)
            self.assertIn("run=true", out.getvalue())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main(["record", "--name", "fitment-cycle", "--config", str(config)],
                                           reader=gh, ledger=gh, now=NOW), 0)
            self.assertEqual(gh.puts[0]["branch"], gate.LEDGER_BRANCH)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(gate.main(["check", "--name", "fitment-cycle", "--config", str(config)],
                                           reader=gh, ledger=gh, now=NOW + dt.timedelta(minutes=30)), 0)
            self.assertIn("run=false", out.getvalue())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(gate.main(["record", "--name", "x", "--fingerprint", "short"],
                                           reader=gh, ledger=gh, now=NOW), 2)
                self.assertEqual(gate.main(["check", "--name", "bad/name", "--config", str(config)],
                                           reader=gh, ledger=gh, now=NOW), 2)

    def _config(self, tmp):
        config = Path(tmp) / "fitment.json"
        config.write_text(json.dumps({"schema": "aems.fitment-config.v1", "repositories": [REPO]}))
        return config

    def test_fingerprint_printed_by_check_round_trips_through_record(self):
        # Fixes #159: the workflow records exactly what `check` printed.
        import re
        gh = FakeGitHub()
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(gate.main(["check", "--name", "fitment-cycle", "--config", str(config)],
                                           reader=gh, ledger=gh, now=NOW), 0)
            printed = re.findall(r"^fingerprint=([0-9a-f]{64})$", out.getvalue(), re.M)
            self.assertEqual(len(printed), 1, out.getvalue())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main(["record", "--name", "fitment-cycle", "--fingerprint", printed[0]],
                                           reader=gh, ledger=gh, now=NOW), 0)
            out = io.StringIO()
            with redirect_stdout(out):
                gate.main(["check", "--name", "fitment-cycle", "--config", str(config)],
                          reader=gh, ledger=gh, now=NOW + dt.timedelta(minutes=30))
            self.assertIn("run=false", out.getvalue())
            gh.pulls.append({"number": 6, "base": {"ref": "fitment"}, "head": {"sha": "d1"}})  # the run opened a PR
            out = io.StringIO()
            with redirect_stdout(out):
                gate.main(["check", "--name", "fitment-cycle", "--config", str(config)],
                          reader=gh, ledger=gh, now=NOW + dt.timedelta(minutes=30))
            self.assertIn("run=true", out.getvalue())  # so the next tick runs and posts its checks

    def test_github_errors_other_than_404_exit_2_so_the_workflow_fails_open(self):
        # Fixes #149: snapshot re-raises a non-404 error; the workflow then runs the cycle.
        gh = FakeGitHub()
        gh.fail = "/branches/"
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()) as err:
            self.assertEqual(gate.main(["check", "--name", "fitment-cycle", "--config", str(self._config(tmp))],
                                       reader=gh, ledger=gh, now=NOW), 2)
        self.assertIn("500", err.getvalue())

    def test_second_record_overwrites_with_the_blob_sha(self):
        gh = FakeGitHub()
        value = "c" * 64
        with redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(["record", "--name", "fitment-cycle", "--fingerprint", value],
                                       reader=gh, ledger=gh, now=NOW), 0)
            self.assertEqual(gate.main(["record", "--name", "fitment-cycle", "--fingerprint", value],
                                       reader=gh, ledger=gh, now=NOW + dt.timedelta(hours=1)), 0)
        self.assertNotIn("sha", gh.puts[0])  # first write creates the file
        self.assertEqual(gh.puts[1]["sha"], "blob1")  # second write must name the blob it replaces

    def test_record_with_the_wrong_schema_forces_a_run(self):
        gh = FakeGitHub()
        current = gate.fingerprint(gh, [REPO])
        gh.files["ring0/gate-fitment-cycle.json"] = json.dumps(
            {"schema": "something-else", "fingerprint": current, "recorded_at": NOW.isoformat()})
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(gate.main(["check", "--name", "fitment-cycle", "--config", str(self._config(tmp))],
                                           reader=gh, ledger=gh, now=NOW), 0)
        self.assertIn("run=true", out.getvalue())
        self.assertIn("no recorded run yet", out.getvalue())


if __name__ == "__main__":
    unittest.main()
