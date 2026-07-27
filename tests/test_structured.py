from __future__ import annotations

import unittest

from aems.structured import StructuredDataError, loads_structured


class StructuredDataTests(unittest.TestCase):
    def test_loads_manifest_yaml_subset(self) -> None:
        value = loads_structured(
            """
            schema_version: 1
            repository:
              name: AEMS
              active: true
            standards:
              applicable:
                - AES-002
                - AES-003
              records:
                - id: AES-002
                  status: draft-complete
                - id: AES-003
                  status: draft
            """
        )
        self.assertEqual(value["schema_version"], 1)
        self.assertEqual(value["repository"]["name"], "AEMS")
        self.assertTrue(value["repository"]["active"])
        self.assertEqual(value["standards"]["applicable"], ["AES-002", "AES-003"])
        self.assertEqual(
            value["standards"]["records"][1],
            {"id": "AES-003", "status": "draft"},
        )

    def test_rejects_duplicate_mapping_keys(self) -> None:
        with self.assertRaisesRegex(StructuredDataError, "duplicate key"):
            loads_structured("repository:\n  name: one\n  name: two\n")

    def test_rejects_unsupported_block_scalar(self) -> None:
        with self.assertRaises(StructuredDataError):
            loads_structured("description: |\n  unsupported\n")

    def test_url_sequence_is_parsed_as_scalars_not_mappings(self) -> None:
        value = loads_structured(
            "evidence:\n"
            "  - https://github.com/example/repository/issues/1\n"
            "  - file:relative/path\n"
        )
        self.assertEqual(
            value,
            {
                "evidence": [
                    "https://github.com/example/repository/issues/1",
                    "file:relative/path",
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()
