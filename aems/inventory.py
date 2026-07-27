"""Deterministic repository and documentation inventory generation."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
from typing import Any, Iterable

from .structured import canonical_json


DOCUMENT_EXTENSIONS = {
    ".adoc",
    ".asc",
    ".md",
    ".markdown",
    ".org",
    ".rst",
    ".tex",
    ".txt",
}

DOCUMENT_NAMES = {
    "AUTHORS",
    "CHANGELOG",
    "CODE_OF_CONDUCT",
    "CONTRIBUTING",
    "GOVERNANCE",
    "LICENSE",
    "NOTICE",
    "README",
    "SECURITY",
}

DEFAULT_DOCUMENTATION_ROOTS = (
    "docs",
    "doc",
    "documentation",
    "adr",
    "standards",
    "specifications",
    "specs",
    "research",
    "references",
)

DEFAULT_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}


@dataclass(frozen=True)
class InventoryEntry:
    path: str
    git_mode: str
    kind: str
    size: int
    sha256: str
    executable: bool
    documentation_candidate: bool
    documentation_subtree: bool
    documentation_class: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "git_mode": self.git_mode,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
            "executable": self.executable,
            "documentation_candidate": self.documentation_candidate,
            "documentation_subtree": self.documentation_subtree,
            "documentation_class": self.documentation_class,
        }


@dataclass
class InventoryReport:
    repository: str
    source_revision: str | None
    source: str
    tracked_worktree_changes: bool | None
    documentation_roots: list[str]
    entries: list[InventoryEntry] = field(default_factory=list)

    @property
    def documentation_entries(self) -> list[InventoryEntry]:
        return [entry for entry in self.entries if entry.documentation_candidate]

    @property
    def digest(self) -> str:
        payload = {
            "schema_version": "1.0.0",
            "repository": self.repository,
            "source_revision": self.source_revision,
            "source": self.source,
            "tracked_worktree_changes": self.tracked_worktree_changes,
            "documentation_roots": self.documentation_roots,
            "entries": [entry.to_dict() for entry in self.entries],
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "repository": self.repository,
            "source_revision": self.source_revision,
            "source": self.source,
            "tracked_worktree_changes": self.tracked_worktree_changes,
            "documentation_roots": self.documentation_roots,
            "summary": {
                "tracked_entry_count": len(self.entries),
                "documentation_candidate_count": len(self.documentation_entries),
                "inventory_sha256": self.digest,
            },
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _tracked_paths(root: Path) -> list[tuple[str, str]]:
    try:
        process = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-s", "-z"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    records: list[tuple[str, str]] = []
    for raw in process.stdout.split(b"\0"):
        if not raw:
            continue
        metadata, separator, path_bytes = raw.partition(b"\t")
        if not separator:
            continue
        fields = metadata.decode("ascii", errors="strict").split()
        if len(fields) < 3:
            continue
        path = path_bytes.decode("utf-8", errors="surrogateescape")
        records.append((path, fields[0]))
    return sorted(records)


def _tracked_worktree_changes(root: Path) -> bool | None:
    try:
        process = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "--untracked-files=no",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return bool(process.stdout.strip())


def _filesystem_paths(root: Path, excluded_roots: set[str]) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in DEFAULT_EXCLUDED_DIRECTORIES for part in relative.parts[:-1]):
            continue
        relative_text = relative.as_posix()
        if any(
            relative_text == excluded
            or relative_text.startswith(f"{excluded.rstrip('/')}/")
            for excluded in excluded_roots
        ):
            continue
        records.append((relative_text, _filesystem_mode(path)))
    return sorted(records)


def _filesystem_mode(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return "000000"
    if stat.S_ISLNK(mode):
        return "120000"
    return "100755" if mode & stat.S_IXUSR else "100644"


def _read_payload(path: Path) -> tuple[str, bytes]:
    try:
        if path.is_symlink():
            return "symlink", os.readlink(path).encode(
                "utf-8", errors="surrogateescape"
            )
        return "file", path.read_bytes()
    except OSError as exc:
        marker = f"<unreadable:{type(exc).__name__}:{exc}>".encode("utf-8")
        return "unreadable", marker


def _under_root(path: str, roots: Iterable[str]) -> bool:
    pure = PurePosixPath(path)
    for root in roots:
        normalized = PurePosixPath(root.strip("/"))
        if not normalized.parts:
            continue
        if pure == normalized or normalized in pure.parents:
            return True
    return False


def is_documentation_candidate(path: str) -> bool:
    pure = PurePosixPath(path)
    suffix = pure.suffix.lower()
    stem_or_name = pure.name.upper()
    if suffix in DOCUMENT_EXTENSIONS:
        return True
    return stem_or_name in DOCUMENT_NAMES or pure.stem.upper() in DOCUMENT_NAMES


def classify_document(path: str) -> str | None:
    if not is_documentation_candidate(path):
        return None
    lowered = path.lower()
    name = PurePosixPath(path).name.lower()
    if "/adr/" in f"/{lowered}" or name.startswith("adr-"):
        return "architecture-decision"
    if "spec" in lowered or "/standards/" in f"/{lowered}":
        return "specification-or-standard"
    if "/research/" in f"/{lowered}":
        return "research"
    if "/evidence/" in f"/{lowered}" or "/reports/" in f"/{lowered}":
        return "evidence-or-report"
    if name.startswith("readme"):
        return "repository-guide"
    if name.startswith(("security", "governance", "contributing")):
        return "repository-policy"
    return "documentation"


def documentation_roots_from_manifest(manifest: dict[str, Any] | None) -> list[str]:
    roots: set[str] = set(DEFAULT_DOCUMENTATION_ROOTS)
    if not isinstance(manifest, dict):
        return sorted(roots)

    candidates: list[Any] = []
    repository = manifest.get("repository")
    authority = manifest.get("authority")
    documentation = manifest.get("documentation")
    if isinstance(repository, dict):
        candidates.extend(
            repository.get(key)
            for key in ("authoritative_paths", "documentation_paths")
        )
    if isinstance(authority, dict):
        candidates.extend(
            authority.get(key)
            for key in (
                "architecture_paths",
                "specification_paths",
                "adr_paths",
                "engineering_paths",
            )
        )
    if isinstance(documentation, dict):
        candidates.extend(documentation.get(key) for key in ("roots", "paths"))

    for candidate in candidates:
        if isinstance(candidate, str):
            roots.add(candidate.strip("/"))
        elif isinstance(candidate, list):
            for value in candidate:
                if isinstance(value, str) and value.strip("/"):
                    roots.add(value.strip("/"))
    return sorted(root for root in roots if root)


def build_inventory(
    root: Path,
    *,
    repository: str | None = None,
    manifest: dict[str, Any] | None = None,
    excluded_roots: Iterable[str] = (),
) -> InventoryReport:
    """Build a stable inventory from tracked files, with a safe fallback.

    Git is authoritative when available.  A non-Git directory is still
    inspectable, but the report labels that fallback explicitly.
    """

    root = root.resolve()
    tracked = _tracked_paths(root)
    source = "git-index" if tracked else "filesystem-fallback"
    paths = tracked or _filesystem_paths(root, set(excluded_roots))
    docs_roots = documentation_roots_from_manifest(manifest)
    entries: list[InventoryEntry] = []

    for relative, git_mode in paths:
        absolute = root / relative
        kind, payload = _read_payload(absolute)
        docs_candidate = is_documentation_candidate(relative)
        entries.append(
            InventoryEntry(
                path=relative,
                git_mode=git_mode,
                kind=kind,
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                executable=git_mode == "100755",
                documentation_candidate=docs_candidate,
                documentation_subtree=_under_root(relative, docs_roots),
                documentation_class=classify_document(relative),
            )
        )

    remote = _git(root, "config", "--get", "remote.origin.url")
    name = repository or remote or root.name
    return InventoryReport(
        repository=name,
        source_revision=_git(root, "rev-parse", "HEAD"),
        source=source,
        tracked_worktree_changes=(
            _tracked_worktree_changes(root) if source == "git-index" else None
        ),
        documentation_roots=docs_roots,
        entries=entries,
    )


def inventory_markdown(report: InventoryReport) -> str:
    lines = [
        f"# Repository Inventory: `{report.repository}`",
        "",
        f"- Schema: `1.0.0`",
        f"- Source: `{report.source}`",
        f"- Revision: `{report.source_revision or 'unversioned'}`",
        f"- Tracked worktree changes: `{report.tracked_worktree_changes}`",
        f"- Tracked entries: `{len(report.entries)}`",
        f"- Documentation candidates: `{len(report.documentation_entries)}`",
        f"- Inventory SHA-256: `{report.digest}`",
        "",
        "## Documentation inventory",
        "",
        "| Path | Class | Under declared documentation root | SHA-256 |",
        "|---|---|---:|---|",
    ]
    for entry in report.documentation_entries:
        lines.append(
            f"| `{entry.path}` | `{entry.documentation_class}` | "
            f"`{entry.documentation_subtree}` | `{entry.sha256}` |"
        )
    if not report.documentation_entries:
        lines.append("| _none_ |  |  |  |")

    lines.extend(
        [
            "",
            "## Full tracked file tree",
            "",
            "| Path | Mode | Kind | Bytes | SHA-256 |",
            "|---|---:|---|---:|---|",
        ]
    )
    for entry in report.entries:
        lines.append(
            f"| `{entry.path}` | `{entry.git_mode}` | `{entry.kind}` | "
            f"{entry.size} | `{entry.sha256}` |"
        )
    return "\n".join(lines) + "\n"


def inventory_json(report: InventoryReport) -> str:
    return canonical_json(report.to_dict())
