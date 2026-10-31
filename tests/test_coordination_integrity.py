import importlib.util
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "coordination_integrity", Path(__file__).resolve().parents[1] / "scripts/coordination_integrity.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class CoordinationIntegrityTests(unittest.TestCase):
    """Synthetic records only: no Dropbox, network or credentials."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "records"
        (self.root / "events").mkdir(parents=True)
        self.write("PROTOCOL.md", "# Protocol\n")
        self.write("events/0001.json", json.dumps({"id": "EVT-0001", "kind": "claim"}))
        self.write("events/0002.json", json.dumps({"id": "EVT-0002", "kind": "handoff"}))

    def write(self, relative, text):
        (self.root / relative).write_text(text, encoding="utf-8")

    def anchored(self, manifest):
        return ci.verify(self.root, manifest, "genesis", ci.manifest_digest(manifest))

    def test_unchanged_complete_records_verify_deterministically(self):
        first, second = ci.build(self.root), ci.build(self.root)
        self.assertEqual(first, second)
        self.assertEqual(ci.manifest_digest(first), ci.manifest_digest(second))
        self.assertEqual([e["path"] for e in first["files"]],
                         ["PROTOCOL.md", "events/0001.json", "events/0002.json"])
        self.assertEqual(first["files"][1]["record_id"], "EVT-0001")
        report = self.anchored(first)
        self.assertEqual((report["status"], report["problems"]), ("verified", []))

    def test_missing_anchor_is_unverified_not_trusted(self):
        report = ci.verify(self.root, ci.build(self.root), "genesis")
        self.assertEqual(report["status"], "unverified")
        self.assertEqual((report["anchor_checked"], report["chain_checked"]), (False, True))
        self.assertIn("not trusted", report["notes"][0])
        self.assertIn("latest", report["notes"][-2])
        self.assertIn("authorship", report["notes"][-1])

    def test_anchor_without_predecessor_check_is_unverified(self):
        manifest = ci.build(self.root)
        report = ci.verify(self.root, manifest, anchor=ci.manifest_digest(manifest))
        self.assertEqual(report["status"], "unverified")
        self.assertEqual((report["anchor_checked"], report["chain_checked"]), (True, False))
        self.assertIn("chain was not checked", report["notes"][0])

    def test_malformed_manifest_fields_are_rejected_not_raised(self):
        manifest = ci.build(self.root)
        cases = {"record_id": ["X"], "size": "7", "sha256": None}
        for field, value in cases.items():
            tampered = json.loads(json.dumps(manifest))
            for entry in tampered["files"][:2]:
                entry[field] = value
            report = ci.verify(self.root, tampered, "genesis", ci.manifest_digest(tampered))
            self.assertEqual(report["status"], "rejected", field)
            self.assertTrue(any(p.startswith(f"malformed {field}") for p in report["problems"]), field)
        tampered = json.loads(json.dumps(manifest))
        tampered["files"][0]["size"] = True
        self.assertIn("malformed size: PROTOCOL.md", ci.verify(self.root, tampered)["problems"])

    def test_empty_record_id_is_refused_by_build_and_verify_alike(self):
        manifest = ci.build(self.root)
        self.write("events/0002.json", json.dumps({"id": ""}))
        with self.assertRaisesRegex(ci.IntegrityError, "empty record id: events/0002.json"):
            ci.build(self.root)
        report = ci.verify(self.root, manifest, "genesis", ci.manifest_digest(manifest))
        self.assertEqual(report["status"], "rejected")
        self.assertIn("empty record id: events/0002.json", report["problems"])

    def test_listed_record_id_must_match_the_file(self):
        tampered = ci.build(self.root)
        tampered["files"][1]["record_id"] = "EVT-9999"
        report = ci.verify(self.root, tampered, "genesis", ci.manifest_digest(tampered))
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["problems"], ["record id does not match the file: events/0001.json"])

    def test_tampered_missing_and_extra_files_are_rejected(self):
        manifest = ci.build(self.root)
        self.write("events/0001.json", json.dumps({"id": "EVT-0001", "kind": "release"}))
        (self.root / "events/0002.json").unlink()
        self.write("events/0003.json", "{}")
        report = self.anchored(manifest)
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["problems"], ["missing: events/0002.json",
                                              "extra: events/0003.json",
                                              "changed: events/0001.json"])

    def test_duplicate_record_ids_are_refused(self):
        self.write("events/0002.json", json.dumps({"id": "EVT-0001"}))
        with self.assertRaisesRegex(ci.IntegrityError, "duplicate record ids: EVT-0001"):
            ci.build(self.root)
        manifest = {"schema": ci.SCHEMA, "predecessor_sha256": None, "files": [
            {"path": "a.json", "sha256": "0" * 64, "size": 1, "record_id": "X"},
            {"path": "b.json", "sha256": "0" * 64, "size": 1, "record_id": "X"}]}
        self.assertIn("duplicate record id: X", ci.verify(self.root, manifest)["problems"])

    def test_path_traversal_and_duplicate_paths_are_rejected(self):
        manifest = ci.build(self.root)
        for bad in ("../outside.json", "/etc/passwd", "events/../PROTOCOL.md", "a\\b"):
            tampered = json.loads(json.dumps(manifest))
            tampered["files"][0]["path"] = bad
            report = ci.verify(self.root, tampered)
            self.assertEqual(report["status"], "rejected", bad)
            self.assertTrue(report["problems"][0].startswith("unsafe or malformed path"), bad)
        doubled = json.loads(json.dumps(manifest))
        doubled["files"].append(dict(doubled["files"][0]))
        self.assertIn("duplicate path: PROTOCOL.md", ci.verify(self.root, doubled)["problems"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinks_are_refused(self):
        os.symlink(self.root / "PROTOCOL.md", self.root / "link.md")
        with self.assertRaisesRegex(ci.IntegrityError, "symlink not allowed: link.md"):
            ci.build(self.root)
        (self.root / "link.md").unlink()
        manifest = ci.build(self.root)
        os.symlink(self.root / "PROTOCOL.md", self.root / "link.md")
        self.assertIn("symlink not allowed: link.md", self.anchored(manifest)["problems"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_root_symlink_is_refused_by_build_and_verify_alike(self):
        link = Path(self.tmp.name) / "records-link"
        os.symlink(self.root, link)
        out = Path(self.tmp.name) / "m.json"
        with redirect_stderr(io.StringIO()):
            self.assertEqual(ci.main(["build", str(link), "--output", str(out)]), 2)
        self.assertFalse(out.exists())
        report = ci.verify(link, ci.build(self.root), "genesis")
        self.assertEqual(report["status"], "rejected")
        self.assertIn("is not a directory", report["problems"][0])
        # A symlinked directory above the root is allowed in both commands.
        parent = Path(self.tmp.name) / "parent-link"
        os.symlink(self.root.parent, parent)
        manifest = ci.build(parent / "records")
        self.assertEqual(self.anchored(manifest)["status"], "verified")
        self.assertEqual(ci.verify(parent / "records", manifest, "genesis",
                                   ci.manifest_digest(manifest))["status"], "verified")

    def test_chain_predecessor_must_match(self):
        first = ci.build(self.root)
        self.write("events/0003.json", json.dumps({"id": "EVT-0003"}))
        second = ci.build(self.root, first)
        self.assertEqual(second["predecessor_sha256"], ci.manifest_digest(first))
        good = ci.verify(self.root, second, ci.manifest_digest(first), ci.manifest_digest(second))
        self.assertEqual(good["status"], "verified")
        stale = ci.verify(self.root, second, "f" * 64, ci.manifest_digest(second))
        self.assertIn("predecessor does not match the expected previous manifest", stale["problems"])
        not_genesis = ci.verify(self.root, second, "genesis")
        self.assertEqual(not_genesis["status"], "rejected")

    def test_wrong_anchor_is_rejected(self):
        manifest = ci.build(self.root)
        report = ci.verify(self.root, manifest, "genesis", "e" * 64)
        self.assertIn("manifest digest does not match the trusted anchor", report["problems"])

    def test_cli_build_then_verify_and_refuses_manifest_inside_root(self):
        out = Path(self.tmp.name) / "manifest.json"
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(ci.main(["build", str(self.root), "--output", str(out)]), 0)
        digest = printed.getvalue().strip()
        with redirect_stdout(io.StringIO()) as printed:
            code = ci.main(["verify", str(self.root), "--manifest", str(out),
                            "--expected-predecessor", "genesis", "--anchor", digest])
        self.assertEqual((code, json.loads(printed.getvalue())["status"]), (0, "verified"))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(ci.main(["verify", str(self.root), "--manifest", str(out)]), 1)
        self.write("PROTOCOL.md", "# Changed\n")
        with redirect_stdout(io.StringIO()) as printed:
            code = ci.main(["verify", str(self.root), "--manifest", str(out), "--expected-predecessor",
                            "genesis", "--anchor", digest, "--format", "markdown"])
        self.assertEqual(code, 3)
        self.assertIn("# Coordination record integrity: rejected", printed.getvalue())
        self.assertIn("- Problem: changed: PROTOCOL.md", printed.getvalue())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(ci.main(["verify", str(self.root / "missing"), "--manifest", str(out)]), 2)
        inside = self.root / "manifest.json"
        with redirect_stderr(io.StringIO()):
            self.assertEqual(ci.main(["build", str(self.root), "--output", str(inside)]), 2)
        self.assertFalse(inside.exists())


if __name__ == "__main__":
    unittest.main()
