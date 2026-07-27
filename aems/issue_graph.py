"""Typed, dependency-aware engineering issue graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import json
from typing import Any, Iterable

from .structured import canonical_json


class IssueGraphError(ValueError):
    """Raised when an issue graph is incomplete or cyclic."""


@dataclass(frozen=True)
class IssueNode:
    identifier: str
    title: str
    scope: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    parent: str | None = None
    labels: tuple[str, ...] = ()
    state: str = "open"
    source: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "IssueNode":
        identifier = str(value.get("id", "")).strip()
        title = str(value.get("title", "")).strip()
        if not identifier or not title:
            raise IssueGraphError("every issue node requires non-empty id and title")

        def strings(key: str) -> tuple[str, ...]:
            raw = value.get(key, [])
            if isinstance(raw, str):
                return (raw,)
            if not isinstance(raw, list):
                raise IssueGraphError(
                    f"{identifier}: {key} must be a string or list of strings"
                )
            result = tuple(str(item).strip() for item in raw if str(item).strip())
            return result

        scope = strings("scope")
        acceptance = strings("acceptance_criteria")
        if not scope:
            raise IssueGraphError(f"{identifier}: scope must not be empty")
        if not acceptance:
            raise IssueGraphError(
                f"{identifier}: acceptance_criteria must not be empty"
            )
        return cls(
            identifier=identifier,
            title=title,
            scope=scope,
            acceptance_criteria=acceptance,
            dependencies=strings("dependencies"),
            parent=(
                str(value["parent"]).strip()
                if value.get("parent") is not None
                else None
            ),
            labels=tuple(sorted(set(strings("labels")))),
            state=str(value.get("state", "open")),
            source=str(value["source"]) if value.get("source") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.identifier,
            "title": self.title,
            "scope": list(self.scope),
            "acceptance_criteria": list(self.acceptance_criteria),
            "dependencies": list(self.dependencies),
            "parent": self.parent,
            "labels": list(self.labels),
            "state": self.state,
        }
        if self.source is not None:
            result["source"] = self.source
        return result

    def github_body(self, *, children: tuple[str, ...] = ()) -> str:
        scope = "\n".join(f"- {item}" for item in self.scope)
        acceptance = "\n".join(f"- [ ] {item}" for item in self.acceptance_criteria)
        dependencies = (
            "\n".join(f"- `{item}`" for item in self.dependencies)
            if self.dependencies
            else "None."
        )
        parent = f"`{self.parent}`" if self.parent else "None."
        child_list = (
            "\n".join(f"- `{item}`" for item in children)
            if children
            else "None."
        )
        source = f"\n\nSource: `{self.source}`" if self.source else ""
        return (
            f"<!-- aems-node:{self.identifier} -->\n"
            f"## Scope\n\n{scope}\n\n"
            f"## Parent\n\n{parent}\n\n"
            f"## Children\n\n{child_list}\n\n"
            f"## Dependencies\n\n{dependencies}\n\n"
            f"## Acceptance criteria\n\n{acceptance}"
            f"{source}\n"
        )

    def github_payload(
        self, *, children: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        return {
            "title": f"[{self.identifier}] {self.title}",
            "body": self.github_body(children=children),
            "labels": list(self.labels),
        }


@dataclass
class IssueGraph:
    nodes: dict[str, IssueNode] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "IssueGraph":
        raw_nodes = value.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise IssueGraphError("nodes must be a list")
        graph = cls()
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                raise IssueGraphError("each issue node must be an object")
            graph.add(IssueNode.from_dict(raw))
        graph.validate()
        return graph

    @classmethod
    def from_nodes(cls, nodes: Iterable[IssueNode]) -> "IssueGraph":
        graph = cls()
        for node in nodes:
            graph.add(node)
        graph.validate()
        return graph

    def add(self, node: IssueNode) -> None:
        if node.identifier in self.nodes:
            raise IssueGraphError(f"duplicate issue node: {node.identifier}")
        self.nodes[node.identifier] = node

    def validate(self) -> None:
        for node in self.nodes.values():
            missing = [
                dependency
                for dependency in node.dependencies
                if dependency not in self.nodes
            ]
            if missing:
                raise IssueGraphError(
                    f"{node.identifier}: unknown dependencies: {', '.join(missing)}"
                )
            if node.identifier in node.dependencies:
                raise IssueGraphError(
                    f"{node.identifier}: an issue cannot depend on itself"
                )
            if node.parent is not None and node.parent not in self.nodes:
                raise IssueGraphError(
                    f"{node.identifier}: unknown parent: {node.parent}"
                )
            if node.parent == node.identifier:
                raise IssueGraphError(
                    f"{node.identifier}: an issue cannot be its own parent"
                )
        for identifier in self.nodes:
            lineage: set[str] = set()
            current: str | None = identifier
            while current is not None:
                if current in lineage:
                    raise IssueGraphError(
                        f"parent cycle detected at: {current}"
                    )
                lineage.add(current)
                current = self.nodes[current].parent
        self.topological_order()

    def children(self, identifier: str) -> tuple[str, ...]:
        if identifier not in self.nodes:
            raise IssueGraphError(f"unknown issue node: {identifier}")
        return tuple(
            sorted(
                node_id
                for node_id, node in self.nodes.items()
                if node.parent == identifier
            )
        )

    def blocks(self, identifier: str) -> tuple[str, ...]:
        if identifier not in self.nodes:
            raise IssueGraphError(f"unknown issue node: {identifier}")
        return tuple(
            sorted(
                node_id
                for node_id, node in self.nodes.items()
                if identifier in node.dependencies
            )
        )

    def topological_order(self) -> list[str]:
        indegree = {
            identifier: len(node.dependencies)
            for identifier, node in self.nodes.items()
        }
        dependents: dict[str, list[str]] = {
            identifier: [] for identifier in self.nodes
        }
        for identifier, node in self.nodes.items():
            for dependency in node.dependencies:
                dependents[dependency].append(identifier)

        ready = [identifier for identifier, count in indegree.items() if count == 0]
        heapq.heapify(ready)
        ordered: list[str] = []
        while ready:
            identifier = heapq.heappop(ready)
            ordered.append(identifier)
            for dependent in sorted(dependents[identifier]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heapq.heappush(ready, dependent)
        if len(ordered) != len(self.nodes):
            cyclic = sorted(
                identifier for identifier, count in indegree.items() if count > 0
            )
            raise IssueGraphError(
                f"dependency cycle detected among: {', '.join(cyclic)}"
            )
        return ordered

    def execution_levels(self) -> list[list[str]]:
        remaining = set(self.nodes)
        completed: set[str] = set()
        levels: list[list[str]] = []
        while remaining:
            ready = sorted(
                identifier
                for identifier in remaining
                if set(self.nodes[identifier].dependencies) <= completed
            )
            if not ready:
                raise IssueGraphError(
                    "dependency cycle detected while constructing execution levels"
                )
            levels.append(ready)
            completed.update(ready)
            remaining.difference_update(ready)
        return levels

    def to_dict(self) -> dict[str, Any]:
        ordered = self.topological_order()
        node_records = []
        for identifier in ordered:
            record = self.nodes[identifier].to_dict()
            record["children"] = list(self.children(identifier))
            record["blocked_by"] = list(self.nodes[identifier].dependencies)
            record["blocks"] = list(self.blocks(identifier))
            node_records.append(record)
        return {
            "schema_version": "1.0.0",
            "nodes": node_records,
            "safe_execution_order": ordered,
            "parallel_execution_levels": self.execution_levels(),
            "github_issue_payloads": [
                {
                    "aems_node_id": identifier,
                    **self.nodes[identifier].github_payload(
                        children=self.children(identifier)
                    ),
                }
                for identifier in ordered
            ],
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    def to_markdown(self) -> str:
        levels = self.execution_levels()
        lines = [
            "# Engineering Issue Dependency Report",
            "",
            f"- Nodes: `{len(self.nodes)}`",
            f"- Execution levels: `{len(levels)}`",
            "- Graph validation: `PASS`",
            "",
            "## Safe execution order",
            "",
        ]
        for index, identifiers in enumerate(levels, start=1):
            lines.append(f"### Level {index}")
            lines.append("")
            for identifier in identifiers:
                node = self.nodes[identifier]
                blockers = (
                    ", ".join(f"`{item}`" for item in node.dependencies)
                    if node.dependencies
                    else "none"
                )
                lines.append(
                    f"- `{identifier}` — {node.title} (blocked by: {blockers})"
                )
            lines.append("")

        lines.extend(
            [
                "## Issue payload summary",
                "",
                "| Node | Title | Parent | Children | Blocked by | Blocks | Labels |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for identifier in self.topological_order():
            node = self.nodes[identifier]
            labels = ", ".join(node.labels) or "none"
            dependencies = ", ".join(node.dependencies) or "none"
            children = ", ".join(self.children(identifier)) or "none"
            blocks = ", ".join(self.blocks(identifier)) or "none"
            lines.append(
                f"| `{identifier}` | {node.title} | "
                f"`{node.parent or 'none'}` | `{children}` | "
                f"`{dependencies}` | `{blocks}` | `{labels}` |"
            )
        return "\n".join(lines) + "\n"


def graph_from_json(text: str) -> IssueGraph:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IssueGraphError(f"invalid JSON issue graph: {exc}") from exc
    if not isinstance(value, dict):
        raise IssueGraphError("issue graph root must be an object")
    return IssueGraph.from_dict(value)
