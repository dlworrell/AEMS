from __future__ import annotations

import unittest

from aems.issue_graph import IssueGraph, IssueGraphError, IssueNode


def node(
    identifier: str,
    dependencies: tuple[str, ...] = (),
    parent: str | None = None,
) -> IssueNode:
    return IssueNode(
        identifier=identifier,
        title=f"Complete {identifier}",
        scope=("Implement the bounded change.",),
        acceptance_criteria=("The result is verified.",),
        dependencies=dependencies,
        parent=parent,
        labels=("aems",),
    )


class IssueGraphTests(unittest.TestCase):
    def test_safe_order_and_parallel_levels(self) -> None:
        graph = IssueGraph.from_nodes(
            [
                node("A"),
                node("B", ("A",), parent="A"),
                node("C", ("A",), parent="A"),
                node("D", ("B", "C")),
            ]
        )
        self.assertEqual(graph.topological_order(), ["A", "B", "C", "D"])
        self.assertEqual(
            graph.execution_levels(), [["A"], ["B", "C"], ["D"]]
        )
        payload = graph.to_dict()["github_issue_payloads"][1]
        self.assertEqual(payload["aems_node_id"], "B")
        self.assertIn("## Acceptance criteria", payload["body"])
        self.assertIn("`A`", payload["body"])
        graph_data = graph.to_dict()
        root = graph_data["nodes"][0]
        self.assertEqual(root["children"], ["B", "C"])
        self.assertEqual(root["blocks"], ["B", "C"])
        self.assertEqual(graph_data["nodes"][3]["blocked_by"], ["B", "C"])

    def test_missing_dependency_is_rejected(self) -> None:
        with self.assertRaisesRegex(IssueGraphError, "unknown dependencies"):
            IssueGraph.from_nodes([node("B", ("A",))])

    def test_cycle_is_rejected(self) -> None:
        with self.assertRaisesRegex(IssueGraphError, "cycle"):
            IssueGraph.from_nodes([node("A", ("B",)), node("B", ("A",))])

    def test_unknown_parent_and_parent_cycle_are_rejected(self) -> None:
        with self.assertRaisesRegex(IssueGraphError, "unknown parent"):
            IssueGraph.from_nodes([node("A", parent="missing")])
        with self.assertRaisesRegex(IssueGraphError, "parent cycle"):
            IssueGraph.from_nodes(
                [node("A", parent="B"), node("B", parent="A")]
            )


if __name__ == "__main__":
    unittest.main()
