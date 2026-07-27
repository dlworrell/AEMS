from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import unittest

from aems.project_zero import assess_project_zero


READY_MANIFEST = """\
manifest_version: 1.0.0
repository:
  id: READY
  name: ready
  full_name: example/ready
  owner: example
  role: test-repository
  ownership: project-owned
  lifecycle: active
  primary_branch: main
  issue_tracker: https://github.com/example/ready/issues
documentation:
  authority: local
  roots:
    - docs
standards:
  applicable:
    - AES-002
    - AES-003
project_zero:
  state: ENGINEERING_READY
  certification:
    status: approved
    evidence: docs/project-zero-certification.md
automation:
  enabled_modules:
    - inventory
    - manifest-validation
    - issue-graph
evidence:
  output_root: build/aems/project-zero
"""


class ProjectZeroTests(unittest.TestCase):
    def _git_repository(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "AEMS Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "aems@example.invalid"],
            check=True,
        )

    def test_uninitialized_repository_reports_manifest_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# Uninitialized\n", encoding="utf-8")
            assessment = assess_project_zero(root)

            self.assertEqual(assessment.current_state, "UNINITIALIZED")
            self.assertFalse(assessment.engineering_ready)
            self.assertEqual(
                assessment.issue_graph.topological_order(),
                ["AEMS-P0-UNINITIALIZED-REPOSITORY-MANIFEST"],
            )

    def test_ready_repository_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._git_repository(root)
            (root / "docs").mkdir()
            (root / "docs" / "project-zero-certification.md").write_text(
                "# Approved\n", encoding="utf-8"
            )
            (root / "aes-manifest.yaml").write_text(
                READY_MANIFEST, encoding="utf-8"
            )
            (root / "README.md").write_text("# Ready\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "fixture"],
                check=True,
            )

            first = assess_project_zero(root)
            second = assess_project_zero(root)

            self.assertEqual(first.current_state, "ENGINEERING_READY")
            self.assertTrue(first.engineering_ready)
            self.assertEqual(first.findings, [])
            self.assertEqual(first.to_json(), second.to_json())
            self.assertEqual(first.inventory.digest, second.inventory.digest)
            self.assertEqual(first.issue_graph.topological_order(), [])

    def test_unknown_module_blocks_automation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "docs" / "project-zero-certification.md").write_text(
                "# Approved\n", encoding="utf-8"
            )
            (root / "aes-manifest.yaml").write_text(
                READY_MANIFEST.replace(
                    "    - issue-graph\n", "    - issue-graph\n    - atarix-only\n"
                ),
                encoding="utf-8",
            )
            assessment = assess_project_zero(root)

            self.assertEqual(assessment.current_state, "AUTOMATION")
            self.assertTrue(
                any("atarix-only" in finding.title for finding in assessment.findings)
            )

    def test_enabled_modules_are_reported_and_deferrals_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "docs" / "project-zero-certification.md").write_text(
                "# Approved\n", encoding="utf-8"
            )
            manifest = READY_MANIFEST.replace(
                "    - manifest-validation\n    - issue-graph\n",
                "",
            ).replace(
                "  certification:\n",
                "  accepted_deferrals:\n"
                "    - id: DEF-001\n"
                "      requirement: AES-002:traceability\n"
                "      rationale: temporary\n"
                "      owner: example\n"
                "  certification:\n",
            )
            (root / "aes-manifest.yaml").write_text(
                manifest,
                encoding="utf-8",
            )
            assessment = assess_project_zero(root)

            self.assertEqual(assessment.modules_run, ["inventory"])
            self.assertEqual(assessment.current_state, "CERTIFICATION")
            self.assertTrue(
                any(
                    finding.requirement == "AES-002:accepted-deferrals"
                    for finding in assessment.findings
                )
            )


if __name__ == "__main__":
    unittest.main()
