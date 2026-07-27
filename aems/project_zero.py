"""AES-002 Project Zero lifecycle evaluation and evidence generation."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Iterable

from .inventory import InventoryReport, build_inventory
from .issue_graph import IssueGraph, IssueNode
from .structured import StructuredDataError, canonical_json, load_structured


PROJECT_ZERO_STATES = (
    "UNINITIALIZED",
    "INVENTORY",
    "METADATA",
    "CLASSIFICATION",
    "VALIDATION",
    "AUTOMATION",
    "CERTIFICATION",
    "ENGINEERING_READY",
)

KNOWN_MODULES = {
    "inventory",
    "manifest-validation",
    "issue-graph",
}

CORE_FIELDS: dict[str, tuple[str, ...]] = {
    "manifest-version": ("manifest_version", "schema_version"),
    "repository-identifier": (
        "repository.id",
        "repository.identifier",
        "repository.full_name",
    ),
    "repository-name": ("repository.name",),
    "repository-owner": ("repository.owner", "owner"),
    "repository-role": ("repository.role",),
    "lifecycle-state": ("repository.lifecycle", "lifecycle.state"),
    "project-zero-state": (
        "project_zero.state",
        "repository.project_zero_state",
    ),
    "applicable-standards": ("standards.applicable", "applicable_standards"),
    "primary-branch": (
        "repository.primary_branch",
        "repository.default_branch",
        "primary_branch",
    ),
    "issue-tracker": ("repository.issue_tracker", "links.issues", "issue_tracker"),
}

CLASSIFICATION_FIELDS: dict[str, tuple[str, ...]] = {
    "ownership-classification": (
        "repository.ownership",
        "classification.ownership",
    ),
    "documentation-authority": (
        "documentation.authority",
        "repository.documentation_authority",
        "authority.documentation",
    ),
}


@dataclass(frozen=True)
class ProjectZeroFinding:
    identifier: str
    state: str
    severity: str
    title: str
    requirement: str
    remediation: str
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.identifier,
            "state": self.state,
            "severity": self.severity,
            "title": self.title,
            "requirement": self.requirement,
            "remediation": self.remediation,
        }
        if self.evidence is not None:
            result["evidence"] = self.evidence
        return result


@dataclass(frozen=True)
class StateResult:
    state: str
    satisfied: bool
    finding_ids: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "satisfied": self.satisfied,
            "finding_ids": list(self.finding_ids),
            "evidence": list(self.evidence),
        }


@dataclass
class ProjectZeroAssessment:
    repository: str
    root: str
    source_revision: str | None
    observed_at: str | None
    manifest_path: str | None
    declared_state: str | None
    current_state: str
    completed_states: list[str]
    inventory: InventoryReport
    state_results: list[StateResult] = field(default_factory=list)
    findings: list[ProjectZeroFinding] = field(default_factory=list)
    issue_graph: IssueGraph = field(default_factory=IssueGraph)
    modules_run: list[str] = field(default_factory=list)

    @property
    def engineering_ready(self) -> bool:
        return self.current_state == "ENGINEERING_READY" and not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "standard": "AES-002",
            "manifest_standard": "AES-003",
            "repository": self.repository,
            "root": self.root,
            "source_revision": self.source_revision,
            "observed_at": self.observed_at,
            "manifest_path": self.manifest_path,
            "declared_state": self.declared_state,
            "current_state": self.current_state,
            "completed_states": self.completed_states,
            "engineering_ready": self.engineering_ready,
            "modules_run": self.modules_run,
            "inventory": {
                "source": self.inventory.source,
                "tracked_worktree_changes": (
                    self.inventory.tracked_worktree_changes
                ),
                "tracked_entry_count": len(self.inventory.entries),
                "documentation_candidate_count": len(
                    self.inventory.documentation_entries
                ),
                "sha256": self.inventory.digest,
            },
            "states": [result.to_dict() for result in self.state_results],
            "findings": [finding.to_dict() for finding in self.findings],
            "next_actions": self.issue_graph.to_dict(),
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    def to_markdown(self) -> str:
        lines = [
            f"# Project Zero Assessment: `{self.repository}`",
            "",
            f"- Standard: `AES-002`",
            f"- Manifest standard: `AES-003`",
            f"- Source revision: `{self.source_revision or 'unversioned'}`",
            f"- Manifest: `{self.manifest_path or 'not found'}`",
            f"- Declared state: `{self.declared_state or 'not declared'}`",
            f"- Determined state: `{self.current_state}`",
            f"- Engineering Ready: `{self.engineering_ready}`",
            f"- Inventory SHA-256: `{self.inventory.digest}`",
            "- Tracked worktree changes: "
            f"`{self.inventory.tracked_worktree_changes}`",
            "",
            "## Lifecycle",
            "",
            "| State | Exit criteria | Evidence or blockers |",
            "|---|---:|---|",
        ]
        findings_by_id = {finding.identifier: finding for finding in self.findings}
        for result in self.state_results:
            details = list(result.evidence)
            details.extend(
                findings_by_id[identifier].title
                for identifier in result.finding_ids
                if identifier in findings_by_id
            )
            lines.append(
                f"| `{result.state}` | `{'PASS' if result.satisfied else 'BLOCKED'}` | "
                f"{'; '.join(details) or 'none'} |"
            )

        lines.extend(["", "## Findings", ""])
        if self.findings:
            for finding in self.findings:
                lines.append(
                    f"- **{finding.severity.upper()}** `{finding.identifier}` — "
                    f"{finding.title}. {finding.remediation}"
                )
        else:
            lines.append("No Project Zero blockers were detected.")

        lines.extend(["", "## Safe next-action order", ""])
        levels = self.issue_graph.execution_levels()
        if not levels:
            lines.append("No next-action issues are required.")
        else:
            for level, identifiers in enumerate(levels, start=1):
                joined = ", ".join(f"`{identifier}`" for identifier in identifiers)
                lines.append(f"{level}. {joined}")
        return "\n".join(lines) + "\n"


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _lookup(document: dict[str, Any], paths: Iterable[str]) -> Any:
    for path in paths:
        value: Any = document
        found = True
        for component in path.split("."):
            if not isinstance(value, dict) or component not in value:
                found = False
                break
            value = value[component]
        if found and value not in (None, "", [], {}):
            return value
    return None


def _manifest_path(root: Path, requested: str | None) -> Path | None:
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = root / candidate
        return candidate
    for relative in (
        "aes-manifest.yaml",
        "aes-manifest.yml",
        ".aems/manifest.yaml",
        ".aems/manifest.yml",
        ".aems/manifest.json",
    ):
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def _repository_name(root: Path, manifest: dict[str, Any]) -> str:
    full_name = _lookup(manifest, ("repository.full_name",))
    if isinstance(full_name, str):
        return full_name
    name = _lookup(manifest, ("repository.name",))
    if isinstance(name, str):
        return name
    remote = _git(root, "config", "--get", "remote.origin.url")
    return remote or root.name


def _observed_at(root: Path) -> str | None:
    return _git(root, "show", "-s", "--format=%cI", "HEAD")


def _finding_id(state: str, requirement: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "-", requirement.upper()).strip("-")
    return f"AEMS-P0-{state}-{normalized}"


def _add_missing_field_findings(
    findings: list[ProjectZeroFinding],
    manifest: dict[str, Any],
    *,
    state: str,
    fields: dict[str, tuple[str, ...]],
) -> list[str]:
    identifiers: list[str] = []
    for requirement, paths in fields.items():
        if _lookup(manifest, paths) is not None:
            continue
        identifier = _finding_id(state, requirement)
        identifiers.append(identifier)
        findings.append(
            ProjectZeroFinding(
                identifier=identifier,
                state=state,
                severity="high",
                title=f"Required {requirement.replace('-', ' ')} is missing",
                requirement=f"AES-003:{requirement}",
                remediation=(
                    f"Declare one of {', '.join(f'`{path}`' for path in paths)} "
                    "in the repository manifest."
                ),
            )
        )
    return identifiers


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def _certification_findings(
    root: Path, manifest: dict[str, Any]
) -> list[ProjectZeroFinding]:
    findings: list[ProjectZeroFinding] = []
    raw_deferrals = _lookup(
        manifest,
        (
            "project_zero.accepted_deferrals",
            "accepted_deferrals",
        ),
    )
    if raw_deferrals is None:
        raw_deferrals = []
    if not isinstance(raw_deferrals, list):
        findings.append(
            ProjectZeroFinding(
                identifier=_finding_id(
                    "CERTIFICATION", "accepted-deferrals-list"
                ),
                state="CERTIFICATION",
                severity="high",
                title="Accepted deferrals are not represented as a list",
                requirement="AES-002:accepted-deferrals",
                remediation=(
                    "Declare `project_zero.accepted_deferrals` as a list; "
                    "use an empty list when no deferrals are approved."
                ),
            )
        )
    else:
        required_fields = (
            "id",
            "requirement",
            "rationale",
            "owner",
            "intended_resolution",
        )
        seen_deferrals: set[str] = set()
        for index, raw in enumerate(raw_deferrals):
            if not isinstance(raw, dict):
                missing = ", ".join(required_fields)
                findings.append(
                    ProjectZeroFinding(
                        identifier=_finding_id(
                            "CERTIFICATION", f"deferral-{index + 1}"
                        ),
                        state="CERTIFICATION",
                        severity="high",
                        title=f"Accepted deferral {index + 1} is malformed",
                        requirement="AES-002:accepted-deferrals",
                        remediation=(
                            "Represent the deferral as a mapping containing "
                            f"{missing}."
                        ),
                    )
                )
                continue
            identifier = str(raw.get("id", "")).strip()
            missing_fields = [
                field
                for field in required_fields
                if not str(raw.get(field, "")).strip()
            ]
            if identifier in seen_deferrals:
                missing_fields.append("unique-id")
            if identifier:
                seen_deferrals.add(identifier)
            if missing_fields:
                findings.append(
                    ProjectZeroFinding(
                        identifier=_finding_id(
                            "CERTIFICATION",
                            identifier or f"deferral-{index + 1}",
                        ),
                        state="CERTIFICATION",
                        severity="high",
                        title=(
                            f"Accepted deferral {identifier or index + 1} "
                            "is incomplete"
                        ),
                        requirement="AES-002:accepted-deferrals",
                        remediation=(
                            "Supply non-empty, reviewable values for: "
                            + ", ".join(missing_fields)
                            + "."
                        ),
                    )
                )
    certification = _lookup(manifest, ("project_zero.certification",))
    if not isinstance(certification, dict):
        certification = {}
    status = str(certification.get("status", "")).lower()
    if status not in {"approved", "accepted"}:
        identifier = _finding_id("CERTIFICATION", "approved-certification")
        findings.append(
            ProjectZeroFinding(
                identifier=identifier,
                state="CERTIFICATION",
                severity="high",
                title="Project Zero certification has not been approved",
                requirement="AES-002:certification",
                remediation=(
                    "Record a reviewed certification decision after validation "
                    "evidence and accepted deferrals are complete."
                ),
            )
        )
    decision_path = certification.get("evidence")
    if not _safe_relative_path(decision_path) or not (root / str(decision_path)).is_file():
        identifier = _finding_id("CERTIFICATION", "certification-evidence")
        findings.append(
            ProjectZeroFinding(
                identifier=identifier,
                state="CERTIFICATION",
                severity="high",
                title="Certification evidence is absent or unresolved",
                requirement="AES-002:certification-evidence",
                remediation=(
                    "Reference a repository-local, version-controlled certification "
                    "record from `project_zero.certification.evidence`."
                ),
                evidence=str(decision_path) if decision_path else None,
            )
        )
    return findings


def _state_result(
    state: str,
    findings: list[ProjectZeroFinding],
    evidence: Iterable[str] = (),
) -> StateResult:
    identifiers = tuple(
        finding.identifier for finding in findings if finding.state == state
    )
    return StateResult(
        state=state,
        satisfied=not identifiers,
        finding_ids=identifiers,
        evidence=tuple(evidence),
    )


def _issue_graph(findings: list[ProjectZeroFinding]) -> IssueGraph:
    nodes: list[IssueNode] = []
    previous_state_nodes: list[str] = []
    for state in PROJECT_ZERO_STATES:
        state_findings = [finding for finding in findings if finding.state == state]
        current_nodes: list[str] = []
        for finding in state_findings:
            current_nodes.append(finding.identifier)
            nodes.append(
                IssueNode(
                    identifier=finding.identifier,
                    title=finding.title,
                    scope=(finding.remediation,),
                    acceptance_criteria=(
                        f"{finding.requirement} is satisfied",
                        "Machine-readable Project Zero evidence is regenerated",
                        "No project-specific AEMS logic is introduced",
                    ),
                    dependencies=tuple(previous_state_nodes),
                    labels=(
                        "aems",
                        "project-zero",
                        f"p0:{state.lower().replace('_', '-')}",
                    ),
                    source=finding.requirement,
                )
            )
        if current_nodes:
            previous_state_nodes = current_nodes
    return IssueGraph.from_nodes(nodes)


def assess_project_zero(
    root: Path,
    *,
    manifest_path: str | None = None,
    output_root: str = "build/aems/project-zero",
) -> ProjectZeroAssessment:
    """Assess ``root`` against the AES-002 lifecycle.

    The function is read-only.  Callers decide where to persist its evidence.
    """

    root = root.resolve()
    findings: list[ProjectZeroFinding] = []
    manifest_file = _manifest_path(root, manifest_path)
    manifest: dict[str, Any] = {}
    parsed_manifest = False

    if manifest_file is None or not manifest_file.is_file():
        findings.append(
            ProjectZeroFinding(
                identifier=_finding_id("UNINITIALIZED", "repository-manifest"),
                state="UNINITIALIZED",
                severity="high",
                title="AES-003 repository manifest is missing",
                requirement="AES-002:repository-manifest",
                remediation=(
                    "Create `aes-manifest.yaml` with AES-003 identity, ownership, "
                    "lifecycle, Project Zero, standards, automation, and evidence fields."
                ),
            )
        )
    else:
        try:
            loaded = load_structured(manifest_file)
            if not isinstance(loaded, dict):
                raise StructuredDataError("manifest root must be a mapping")
            manifest = loaded
            parsed_manifest = True
        except StructuredDataError as exc:
            findings.append(
                ProjectZeroFinding(
                    identifier=_finding_id("UNINITIALIZED", "parseable-manifest"),
                    state="UNINITIALIZED",
                    severity="high",
                    title="Repository manifest is not parseable",
                    requirement="AES-003:parseability",
                    remediation="Correct the manifest syntax and rerun AEMS.",
                    evidence=str(exc),
                )
            )

    repository = _repository_name(root, manifest)
    inventory = build_inventory(
        root,
        repository=repository,
        manifest=manifest,
        excluded_roots=(output_root,),
    )

    if parsed_manifest:
        _add_missing_field_findings(
            findings,
            manifest,
            state="METADATA",
            fields=CORE_FIELDS,
        )
        _add_missing_field_findings(
            findings,
            manifest,
            state="CLASSIFICATION",
            fields=CLASSIFICATION_FIELDS,
        )

        declared = _lookup(
            manifest, ("project_zero.state", "repository.project_zero_state")
        )
        declared_state = str(declared).upper() if declared is not None else None
        if declared_state is not None and declared_state not in PROJECT_ZERO_STATES:
            findings.append(
                ProjectZeroFinding(
                    identifier=_finding_id("VALIDATION", "valid-project-zero-state"),
                    state="VALIDATION",
                    severity="high",
                    title=f"Unknown Project Zero state: {declared_state}",
                    requirement="AES-002:state-machine",
                    remediation=(
                        "Use one of the AES-002 states: "
                        + ", ".join(PROJECT_ZERO_STATES)
                        + "."
                    ),
                )
            )

        evidence_root = _lookup(
            manifest, ("evidence.output_root", "project_zero.evidence_output")
        )
        if evidence_root is not None and not _safe_relative_path(evidence_root):
            findings.append(
                ProjectZeroFinding(
                    identifier=_finding_id("VALIDATION", "safe-evidence-output"),
                    state="VALIDATION",
                    severity="high",
                    title="Evidence output must be a repository-relative path",
                    requirement="AES-002:evidence",
                    remediation=(
                        "Use a relative evidence output without `..` path traversal."
                    ),
                    evidence=str(evidence_root),
                )
            )

        enabled = _lookup(
            manifest, ("automation.enabled_modules", "automation.modules")
        )
        enabled_modules = (
            [str(item) for item in enabled]
            if isinstance(enabled, list)
            else []
        )
        unknown_modules = sorted(set(enabled_modules) - KNOWN_MODULES)
        for module in unknown_modules:
            findings.append(
                ProjectZeroFinding(
                    identifier=_finding_id("AUTOMATION", f"module-{module}"),
                    state="AUTOMATION",
                    severity="high",
                    title=f"Enabled automation module is unavailable: {module}",
                    requirement="AES-002:enabled-automation",
                    remediation=(
                        "Install a declared AEMS module implementation or remove the "
                        "unsupported capability from the manifest."
                    ),
                )
            )

        findings.extend(_certification_findings(root, manifest))
        if (
            declared_state != "ENGINEERING_READY"
            and not any(
                finding.state in PROJECT_ZERO_STATES[:-1] for finding in findings
            )
        ):
            findings.append(
                ProjectZeroFinding(
                    identifier=_finding_id(
                        "ENGINEERING_READY", "declared-engineering-ready"
                    ),
                    state="ENGINEERING_READY",
                    severity="medium",
                    title="Manifest does not declare ENGINEERING_READY",
                    requirement="AES-002:engineering-ready",
                    remediation=(
                        "After certification approval, update `project_zero.state` "
                        "to `ENGINEERING_READY` in a reviewed change."
                    ),
                )
            )
    else:
        declared_state = None
        enabled_modules = []

    state_results = [
        _state_result(
            "UNINITIALIZED",
            findings,
            ("manifest parsed" if parsed_manifest else "manifest unavailable",),
        ),
        _state_result(
            "INVENTORY",
            findings,
            (
                f"{len(inventory.entries)} tracked entries",
                f"inventory sha256 {inventory.digest}",
            ),
        ),
        _state_result("METADATA", findings),
        _state_result("CLASSIFICATION", findings),
        _state_result("VALIDATION", findings),
        _state_result(
            "AUTOMATION",
            findings,
            tuple(sorted(set(enabled_modules) & KNOWN_MODULES)),
        ),
        _state_result("CERTIFICATION", findings),
        _state_result("ENGINEERING_READY", findings),
    ]

    first_blocked = next(
        (result.state for result in state_results if not result.satisfied),
        "ENGINEERING_READY",
    )
    completed_states: list[str] = []
    for result in state_results:
        if result.state == first_blocked and not result.satisfied:
            break
        if result.satisfied:
            completed_states.append(result.state)

    graph = _issue_graph(findings)
    modules_run = sorted(set(enabled_modules) & KNOWN_MODULES)
    return ProjectZeroAssessment(
        repository=repository,
        root=str(root),
        source_revision=_git(root, "rev-parse", "HEAD"),
        observed_at=_observed_at(root),
        manifest_path=(
            manifest_file.relative_to(root).as_posix()
            if manifest_file is not None and manifest_file.is_relative_to(root)
            else str(manifest_file) if manifest_file is not None else None
        ),
        declared_state=declared_state,
        current_state=first_blocked,
        completed_states=completed_states,
        inventory=inventory,
        state_results=state_results,
        findings=findings,
        issue_graph=graph,
        modules_run=modules_run,
    )
