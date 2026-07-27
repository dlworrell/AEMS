from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_traceability import validate_graph


class TraceabilityTests(unittest.TestCase):
    def test_example_graph_is_semantically_valid(self) -> None:
        root = Path(__file__).resolve().parents[1]
        value = json.loads(
            (root / "examples/traceability/project-zero-engine.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(validate_graph(value), [])

    def test_unresolved_endpoint_is_rejected(self) -> None:
        value = {
            "schema_version": "1.0.0",
            "graph_id": "example",
            "owner_repository": "example/repository",
            "nodes": [],
            "relationships": [
                {
                    "id": "rel:example:1",
                    "type": "verifies",
                    "source": "missing",
                    "target": "also-missing",
                }
            ],
        }
        errors = validate_graph(value)
        self.assertTrue(any("source does not resolve" in error for error in errors))
        self.assertTrue(any("target does not resolve" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
