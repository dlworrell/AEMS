from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import unittest

from aems.inventory import build_inventory


class InventoryTests(unittest.TestCase):
    def _repository(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "AEMS Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "aems@example.invalid"],
            check=True,
        )

    def test_inventory_is_tracked_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._repository(root)
            (root / "docs").mkdir()
            (root / "docs" / "SPEC-001.md").write_text(
                "# Specification\n", encoding="utf-8"
            )
            (root / "source.c").write_text("int main(void) { return 0; }\n")
            (root / "untracked.txt").write_text("not evidence\n")
            subprocess.run(
                ["git", "-C", str(root), "add", "docs/SPEC-001.md", "source.c"],
                check=True,
            )

            first = build_inventory(root, repository="example/inventory")
            second = build_inventory(root, repository="example/inventory")

            self.assertEqual(first.digest, second.digest)
            self.assertTrue(first.tracked_worktree_changes)
            self.assertEqual(
                [entry.path for entry in first.entries],
                ["docs/SPEC-001.md", "source.c"],
            )
            self.assertEqual(len(first.documentation_entries), 1)
            self.assertEqual(
                first.documentation_entries[0].documentation_class,
                "specification-or-standard",
            )
            self.assertTrue(
                first.documentation_entries[0].documentation_subtree
            )

    def test_filesystem_fallback_excludes_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# Example\n", encoding="utf-8")
            output = root / "build" / "aems"
            output.mkdir(parents=True)
            (output / "report.json").write_text("{}\n", encoding="utf-8")

            report = build_inventory(
                root,
                repository="example/fallback",
                excluded_roots=("build/aems",),
            )
            self.assertEqual(report.source, "filesystem-fallback")
            self.assertIsNone(report.tracked_worktree_changes)
            self.assertEqual([entry.path for entry in report.entries], ["README.md"])


if __name__ == "__main__":
    unittest.main()
