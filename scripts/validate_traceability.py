#!/usr/bin/env python3
"""Validate AEMS traceability graphs and render a compact matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ARTIFACT_CLASSES = {
    "governance",
    "standard",
    "requirement",
    "specification",
    "decision",
    "research",
    "risk",
    "issue",
    "commit",
    "implementation",
    "test",
    "evidence",
    "waiver",
    "release",
}

RELATIONSHIP_TYPES = {
    "governs",
    "defines",
    "derives-from",
    "depends-on",
    "tracks",
    "implements",
    "verifies",
    "evidences",
    "mitigates",
    "waives",
    "supersedes",
    "released-in",
    "owned-by",
}

AUTHORITIES = {"canonical", "reference", "generated-evidence"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an AEMS traceability graph."
    )
    parser.add_argument("graph", help="Traceability graph JSON path")
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="markdown"
    )
    return parser.parse_args()


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_graph(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["graph root must be an object"]
    if value.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if not _text(value.get("graph_id")):
        errors.append("graph_id must be a non-empty string")
    if not _text(value.get("owner_repository")):
        errors.append("owner_repository must be a non-empty string")

    raw_nodes = value.get("nodes")
    raw_relationships = value.get("relationships")
    if not isinstance(raw_nodes, list):
        errors.append("nodes must be a list")
        raw_nodes = []
    if not isinstance(raw_relationships, list):
        errors.append("relationships must be a list")
        raw_relationships = []

    node_ids: set[str] = set()
    for index, node in enumerate(raw_nodes):
        prefix = f"nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{prefix} must be an object")
            continue
        identifier = node.get("id")
        if not _text(identifier):
            errors.append(f"{prefix}.id must be a non-empty string")
        elif identifier in node_ids:
            errors.append(f"{prefix}.id is duplicated: {identifier}")
        else:
            node_ids.add(identifier)
        if node.get("artifact_class") not in ARTIFACT_CLASSES:
            errors.append(f"{prefix}.artifact_class is not recognized")
        if not _text(node.get("title")):
            errors.append(f"{prefix}.title must be a non-empty string")
        repository = node.get("repository")
        if not _text(repository) or str(repository).count("/") != 1:
            errors.append(f"{prefix}.repository must use owner/name form")
        if node.get("authority") not in AUTHORITIES:
            errors.append(f"{prefix}.authority is not recognized")
        if not _text(node.get("status")):
            errors.append(f"{prefix}.status must be a non-empty string")
        if not (_text(node.get("path")) or _text(node.get("url"))):
            errors.append(f"{prefix} must include path or url")

    relationship_ids: set[str] = set()
    for index, relationship in enumerate(raw_relationships):
        prefix = f"relationships[{index}]"
        if not isinstance(relationship, dict):
            errors.append(f"{prefix} must be an object")
            continue
        identifier = relationship.get("id")
        if not _text(identifier):
            errors.append(f"{prefix}.id must be a non-empty string")
        elif identifier in relationship_ids:
            errors.append(f"{prefix}.id is duplicated: {identifier}")
        else:
            relationship_ids.add(identifier)
        if relationship.get("type") not in RELATIONSHIP_TYPES:
            errors.append(f"{prefix}.type is not recognized")
        source = relationship.get("source")
        target = relationship.get("target")
        if source not in node_ids:
            errors.append(f"{prefix}.source does not resolve: {source}")
        if target not in node_ids:
            errors.append(f"{prefix}.target does not resolve: {target}")
        if source == target and source is not None:
            errors.append(f"{prefix} must not be a self-relationship")
    return errors


def markdown(value: dict[str, Any], errors: list[str]) -> str:
    nodes = {
        node["id"]: node
        for node in value.get("nodes", [])
        if isinstance(node, dict) and _text(node.get("id"))
    }
    lines = [
        f"# Traceability Validation: `{value.get('graph_id', 'unknown')}`",
        "",
        f"- Result: `{'PASS' if not errors else 'FAIL'}`",
        f"- Nodes: `{len(nodes)}`",
        f"- Relationships: `{len(value.get('relationships', [])) if isinstance(value.get('relationships'), list) else 0}`",
        f"- Errors: `{len(errors)}`",
        "",
    ]
    if errors:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
        lines.append("")
    lines.extend(
        [
            "## Relationship matrix",
            "",
            "| Type | Source | Target |",
            "|---|---|---|",
        ]
    )
    for relationship in value.get("relationships", []):
        if not isinstance(relationship, dict):
            continue
        source = nodes.get(relationship.get("source"), {})
        target = nodes.get(relationship.get("target"), {})
        lines.append(
            f"| `{relationship.get('type', '')}` | "
            f"`{relationship.get('source', '')}` — {source.get('title', '')} | "
            f"`{relationship.get('target', '')}` — {target.get('title', '')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    try:
        value = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    errors = validate_graph(value)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "graph_id": value.get("graph_id")
                    if isinstance(value, dict)
                    else None,
                    "result": "PASS" if not errors else "FAIL",
                    "errors": errors,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(markdown(value if isinstance(value, dict) else {}, errors), end="")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
