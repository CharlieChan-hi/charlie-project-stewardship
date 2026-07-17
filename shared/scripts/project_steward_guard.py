#!/usr/bin/env python3
"""Evidence-driven completion guard for project changes and validation."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import contextlib
import io
import json

from project_steward_audit import build_audit, is_path_within_root, safe_read_text
from project_steward_cli import parse_args_safely, safe_error_text
from project_steward_plan import PlanSecretError, iter_active_plans, read_plan
from project_steward_templates import (
    ConcurrentModificationError,
    ProjectPathError,
    atomic_write_text,
    project_lock,
    read_text_safe,
    reject_high_confidence_secret,
    safe_project_path,
)


PLACEHOLDER_PATTERNS = ["[需确认]", "[Add ", "[Explain ", "[List "]
CORE_DOCS = [
    "AGENTS.md",
    "docs/project_intake.md",
    "docs/ai_project_context.md",
    "docs/architecture.md",
    "docs/source_structure.md",
    "docs/project_preferences.md",
    "docs/agent_harness.md",
    "docs/capability_routing.md",
    "docs/coding_standards.md",
]

SCHEMA_VERSION = "3.0"
VALIDATION_STATUSES = {"pass", "fail", "not-run", "skipped"}
ACCEPTANCE_STATUSES = {
    "pass",
    "fail",
    "not-run",
    "not-required",
    "unspecified",
}


def _reject_report_text(value: object, label: str) -> str:
    """Reject secret-bearing or non-text values before they can enter a report."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    reject_high_confidence_secret(value, label)
    return value


def _reject_report_value(value: object, label: str) -> None:
    """Apply the shared secret boundary to every string in a report value."""
    if isinstance(value, str):
        reject_high_confidence_secret(value, label)
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_report_value(key, label)
            _reject_report_value(item, label)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _reject_report_value(item, label)


def _cli_report_text(label: str):
    """Return an argparse converter that never echoes a rejected raw value."""
    def parse(value: str) -> str:
        try:
            return _reject_report_text(value, label)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from None

    return parse


def unresolved_docs(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel_path in CORE_DOCS:
        path = root / rel_path
        text = safe_read_text(path, root=root)
        if not text:
            continue
        count = sum(text.count(pattern) for pattern in PLACEHOLDER_PATTERNS)
        if count:
            findings.append({"path": rel_path, "placeholder_count": count})
    return findings


def inspect_active_plans(
    root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Inspect each plan independently so one malformed file cannot abort Guard."""
    plans: list[dict[str, object]] = []
    malformed: list[dict[str, object]] = []
    try:
        paths = iter_active_plans(root)
    except PlanSecretError:
        raise
    except (OSError, ProjectPathError, ValueError) as exc:
        error = str(exc)
        _reject_report_text(error, "active plan listing error")
        return [], [{
            "path": "plans/active",
            "error_type": type(exc).__name__,
            "error": error,
        }]

    for path in paths:
        rel_path = str(path.relative_to(root))
        _reject_report_text(rel_path, "active plan path")
        if path.is_symlink() or not is_path_within_root(path, root):
            malformed.append({
                "path": rel_path,
                "error_type": "ProjectPathError",
                "error": "Plan path is unsafe or outside the project root.",
            })
            continue
        try:
            plan = read_plan(path, root)
        except PlanSecretError:
            raise
        except (
            ConcurrentModificationError,
            OSError,
            UnicodeError,
            ProjectPathError,
            ValueError,
        ) as exc:
            error = str(exc)
            _reject_report_text(error, "active plan parse error")
            malformed.append({
                "path": rel_path,
                "error_type": type(exc).__name__,
                "error": error,
            })
            continue
        summary = plan["summary"]
        nxt = plan["next_step"]
        title = _reject_report_text(plan["title"], "active plan title")
        plan_id = _reject_report_text(plan["plan_id"], "active plan id")
        next_step = (
            _reject_report_text(nxt["text"], "active plan next step")
            if nxt
            else None
        )
        plans.append({
            "path": rel_path,
            "filename": path.name,
            "stem": path.stem,
            "title": title,
            "plan_id": plan_id,
            "done": summary["done"],
            "total": summary["total"],
            "next_step": next_step,
            "unfinished": summary["total"] == 0 or summary["done"] < summary["total"],
        })
    return plans, malformed


def unfinished_plans(root: Path) -> list[dict[str, object]]:
    """Compatibility helper returning only valid unfinished plans."""
    plans, _ = inspect_active_plans(root)
    return [item for item in plans if item["unfinished"]]


def plan_matches_identifier(plan: dict[str, object], identifier: str) -> bool:
    return identifier in {
        str(plan["plan_id"]),
        str(plan["title"]),
        str(plan["stem"]),
        str(plan["filename"]),
    }


def _finding(
    code: str,
    severity: str,
    message: str,
    evidence: list[object] | None = None,
    related_paths: list[str] | None = None,
) -> dict[str, object]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "evidence": evidence or [],
        "related_paths": related_paths or [],
    }


def normalize_changed_paths(root: Path, values: list[str] | None) -> tuple[list[str], list[str]]:
    normalized: list[str] = []
    invalid: list[str] = []
    project_root = root.resolve(strict=False)
    for raw in values or []:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        if not is_path_within_root(candidate, project_root):
            invalid.append(raw)
            continue
        try:
            rel_path = candidate.resolve(strict=False).relative_to(project_root).as_posix()
        except (OSError, RuntimeError, ValueError):
            invalid.append(raw)
            continue
        normalized.append(rel_path or ".")
    return sorted(set(normalized)), sorted(set(invalid))


def _path_is_relevant(path: str, changed_paths: list[str]) -> bool:
    if not changed_paths:
        return True
    clean_path = path.split(":", 1)[0].rstrip("/")
    for changed in changed_paths:
        clean_changed = changed.rstrip("/")
        if clean_changed in {"", "."}:
            return True
        if (
            clean_path == clean_changed
            or clean_path.startswith(clean_changed + "/")
            or clean_changed.startswith(clean_path + "/")
        ):
            return True
    return False


def parse_validation_results(values: list[str] | None) -> dict[str, str]:
    results: dict[str, str] = {}
    for index, value in enumerate(values or []):
        raw = _reject_report_text(value, f"validation_result[{index}]")
        if "=" not in raw:
            raise ValueError(f"Validation result must use NAME=STATUS: {raw}")
        name, status = (part.strip() for part in raw.split("=", 1))
        _reject_report_text(name, f"validation_result[{index}] name")
        _reject_report_text(status, f"validation_result[{index}] status")
        if not name or status not in VALIDATION_STATUSES:
            allowed = ", ".join(sorted(VALIDATION_STATUSES))
            raise ValueError(f"Invalid validation result `{raw}`; allowed statuses: {allowed}")
        if name in results and results[name] != status:
            raise ValueError(
                f"Conflicting validation results for `{name}`: "
                f"{results[name]} and {status}"
            )
        results[name] = status
    return results


def build_guard(
    root: Path,
    max_lines: int,
    changed_paths: list[str] | None = None,
    validation_results: dict[str, str] | None = None,
    required_validations: list[str] | None = None,
    acceptance_status: str = "unspecified",
    current_plan: str | None = None,
) -> dict[str, object]:
    _reject_report_text(str(root), "project_root")
    declared_changes = list(changed_paths or [])
    for index, value in enumerate(declared_changes):
        _reject_report_text(value, f"changed_path[{index}]")
    declared_validation_results = dict(validation_results or {})
    for index, (name, status) in enumerate(declared_validation_results.items()):
        _reject_report_text(name, f"validation_results[{index}] name")
        _reject_report_text(status, f"validation_results[{index}] status")
    declared_required_validations = list(required_validations or [])
    for index, name in enumerate(declared_required_validations):
        _reject_report_text(name, f"required_validation[{index}]")
    _reject_report_text(acceptance_status, "acceptance_status")
    if current_plan is not None:
        _reject_report_text(current_plan, "current_plan")

    root = root.expanduser().resolve(strict=False)
    normalized_changes, invalid_changes = normalize_changed_paths(root, declared_changes)
    validation_results = declared_validation_results
    required_validations = sorted(set(declared_required_validations))
    invalid_statuses = {
        name: status
        for name, status in validation_results.items()
        if status not in VALIDATION_STATUSES
    }
    if invalid_statuses:
        raise ValueError(f"Invalid validation statuses: {invalid_statuses}")
    if acceptance_status not in ACCEPTANCE_STATUSES:
        raise ValueError(f"Invalid acceptance status: {acceptance_status}")

    audit = build_audit(root, max_lines=max_lines)
    code_signals = audit["code_signals"]
    unresolved = unresolved_docs(root)
    plan_records, malformed_plans = inspect_active_plans(root)
    plans = [item for item in plan_records if item["unfinished"]]

    blockers: list[dict[str, object]] = []
    review_items: list[dict[str, object]] = []
    signals: list[dict[str, object]] = []

    unignored_env_files = audit["secrets"]["unignored_env_files"]
    if unignored_env_files:
        blockers.append(_finding(
            "secrets.env-not-ignored",
            "blocker",
            "Real .env files are present without matching .gitignore coverage.",
            unignored_env_files,
            unignored_env_files,
        ))
    unknown_env_files = audit["secrets"].get("unknown_env_files", [])
    if unknown_env_files:
        review_items.append(_finding(
            "secrets.env-ignore-unknown",
            "review",
            "Environment-file ignore and tracking status is unknown; establish Git evidence before deciding safety.",
            audit["secrets"].get("env_file_statuses", []),
            list(unknown_env_files),
        ))
    exposed_credential_configs = audit["secrets"].get(
        "exposed_credential_config_files", []
    )
    if exposed_credential_configs:
        review_items.append(_finding(
            "secrets.credential-config-exposed",
            "review",
            "Credential-capable config files are tracked or unignored; review their Git-safe shape without reading secret values.",
            audit["secrets"].get("credential_config_statuses", []),
            list(exposed_credential_configs),
        ))
    unknown_credential_configs = audit["secrets"].get(
        "unknown_credential_config_files", []
    )
    if unknown_credential_configs:
        review_items.append(_finding(
            "secrets.credential-config-unknown",
            "review",
            "Credential-capable config-file tracking status is unknown; establish Git evidence before completion.",
            audit["secrets"].get("credential_config_statuses", []),
            list(unknown_credential_configs),
        ))

    for item in code_signals["complexity_hotspots"]:
        source_path = str(item.get("source_path", item["path"]))
        finding = _finding(
            "code.control-flow-density",
            "review",
            "Control-flow density warrants focused review; it does not require a rewrite by itself.",
            [item],
            [source_path],
        )
        if normalized_changes and _path_is_relevant(source_path, normalized_changes):
            review_items.append(finding)
        else:
            signals.append(finding)

    for item in code_signals["large_files"]:
        signals.append(_finding(
            "code.large-file",
            "info",
            "File length is a review signal only and never blocks completion by itself.",
            [item],
            [str(item["path"])],
        ))

    for item in code_signals.get("complexity_analysis_skipped", []):
        signals.append(_finding(
            "code.complexity-analysis-skipped:size-limit",
            "info",
            "Complexity analysis was skipped for a source file above the bounded read limit.",
            [item],
            [str(item["path"])],
        ))

    if code_signals["generic_name_files"]:
        signals.append(_finding(
            "code.generic-name",
            "info",
            "Generic filenames may be conventional; review only where ownership is unclear.",
            code_signals["generic_name_files"],
            list(code_signals["generic_name_files"]),
        ))
    if code_signals["dead_code_name_candidates"]:
        signals.append(_finding(
            "code.dead-name",
            "info",
            "Names suggest possible legacy code; usage must be proven before deletion.",
            code_signals["dead_code_name_candidates"],
            list(code_signals["dead_code_name_candidates"]),
        ))
    if code_signals["root_clutter"]["flagged"]:
        signals.append(_finding(
            "code.root-source-count",
            "info",
            "Several root source files were found; deeper structure is not automatically better.",
            code_signals["root_clutter"]["source_files"],
            list(code_signals["root_clutter"]["source_files"]),
        ))

    for item in unresolved:
        finding = _finding(
            "governance.placeholder",
            "info",
            "A governance document contains placeholders; this is not a universal completion blocker.",
            [item],
            [str(item["path"])],
        )
        if normalized_changes and _path_is_relevant(str(item["path"]), normalized_changes):
            finding["severity"] = "review"
            review_items.append(finding)
        else:
            signals.append(finding)

    if audit["governance_coverage"]["artifacts"]["missing"]:
        signals.append(_finding(
            "governance.coverage",
            "info",
            "Optional governance artifacts are missing; project health and completion are unaffected.",
            audit["governance_coverage"]["artifacts"]["missing"],
        ))

    selected_plan: dict[str, object] | None = None
    selected_malformed: dict[str, object] | None = None
    current_plan_identifier: str | None = None
    if current_plan is not None:
        current_plan_identifier = current_plan.strip()
        if (
            not current_plan_identifier
            or "\n" in current_plan_identifier
            or "\r" in current_plan_identifier
            or "\0" in current_plan_identifier
        ):
            raise ValueError("current_plan must be a non-empty single line")
        valid_matches = [
            item
            for item in plan_records
            if plan_matches_identifier(item, current_plan_identifier)
        ]
        malformed_matches = [
            item
            for item in malformed_plans
            if current_plan_identifier
            in {
                Path(str(item["path"])).name,
                Path(str(item["path"])).stem,
            }
        ]
        match_count = len(valid_matches) + len(malformed_matches)
        if match_count == 0:
            review_items.append(_finding(
                "plan.current-not-found",
                "review",
                f"The exact current plan `{current_plan_identifier}` was not found.",
                [{"identifier": current_plan_identifier}],
            ))
        elif match_count > 1:
            review_items.append(_finding(
                "plan.current-ambiguous",
                "review",
                f"The exact current plan `{current_plan_identifier}` matches more than one active plan.",
                [
                    *[item["path"] for item in valid_matches],
                    *[item["path"] for item in malformed_matches],
                ],
            ))
        elif valid_matches:
            selected_plan = valid_matches[0]
            if selected_plan["unfinished"]:
                review_items.append(_finding(
                    "plan.incomplete",
                    "review",
                    "The explicitly selected current plan still has open steps.",
                    [selected_plan],
                    [str(selected_plan["path"])],
                ))
        else:
            selected_malformed = malformed_matches[0]
            review_items.append(_finding(
                "plan.malformed",
                "review",
                "The explicitly selected current plan is malformed and could not be evaluated.",
                [selected_malformed],
                [str(selected_malformed["path"])],
            ))

    unrelated_unfinished = [
        item for item in plans if item is not selected_plan
    ]
    if unrelated_unfinished:
        signals.append(_finding(
            "plan.incomplete-unrelated",
            "info",
            "Other active plans have open steps but are not part of the declared current outcome.",
            unrelated_unfinished,
            [str(item["path"]) for item in unrelated_unfinished],
        ))
    unrelated_malformed = [
        item for item in malformed_plans if item is not selected_malformed
    ]
    if unrelated_malformed:
        signals.append(_finding(
            "plan.malformed-unrelated",
            "info",
            "An unrelated active plan is malformed; it does not determine the current outcome.",
            unrelated_malformed,
            [str(item["path"]) for item in unrelated_malformed],
        ))

    if invalid_changes:
        review_items.append(_finding(
            "scope.invalid-path",
            "review",
            "Some declared changed paths escape the project root or could not be resolved.",
            invalid_changes,
        ))

    evidence_declared = any((
        bool(changed_paths),
        bool(validation_results),
        bool(required_validations),
        acceptance_status != "unspecified",
        current_plan_identifier is not None,
    ))
    if not evidence_declared:
        review_items.append(_finding(
            "evidence.unspecified",
            "review",
            "No outcome scope, validation evidence, acceptance declaration, or current plan was provided.",
        ))

    reported_nonpassing_validations: set[str] = set()
    for name, status in sorted(validation_results.items()):
        if status == "fail":
            blockers.append(_finding(
                "validation.failed",
                "blocker",
                f"Relevant validation failed: {name}.",
                [{"name": name, "status": status}],
            ))
            reported_nonpassing_validations.add(name)
        elif status in {"not-run", "skipped"}:
            review_items.append(_finding(
                "validation.not-passed",
                "review",
                f"Declared validation has not passed: {name} ({status}).",
                [{"name": name, "status": status}],
            ))
            reported_nonpassing_validations.add(name)

    for name in required_validations:
        status = validation_results.get(name, "not-run")
        if (
            status in {"not-run", "skipped"}
            and name not in reported_nonpassing_validations
        ):
            review_items.append(_finding(
                "validation.missing",
                "review",
                f"Required validation has not passed: {name}.",
                [{"name": name, "status": status}],
            ))

    if acceptance_status == "fail":
        blockers.append(_finding(
            "acceptance.failed",
            "blocker",
            "The user-facing acceptance check failed.",
            [{"status": acceptance_status}],
        ))
    elif acceptance_status == "not-run":
        review_items.append(_finding(
            "acceptance.not-run",
            "review",
            "User-facing acceptance has not been checked.",
            [{"status": acceptance_status}],
        ))

    status = "blocked" if blockers else "needs-review" if review_items else "pass"
    if normalized_changes:
        scope_mode = "changed-paths"
    elif current_plan_identifier is not None:
        scope_mode = "current-plan"
    elif evidence_declared:
        scope_mode = "project"
    else:
        scope_mode = "unspecified"

    report = {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(root),
        "status": status,
        "scope": {
            "mode": scope_mode,
            "changed_paths": normalized_changes,
            "invalid_changed_paths": invalid_changes,
            "current_plan": current_plan_identifier,
        },
        "blockers": blockers,
        "review_items": review_items,
        "signals": signals,
        "evidence": {
            "validation_results": validation_results,
            "required_validations": required_validations,
            "acceptance_status": acceptance_status,
            "declared": evidence_declared,
        },
        "governance_coverage": audit["governance_coverage"],
        "unresolved_docs": unresolved,
        "unfinished_plans": plans,
        "malformed_plans": malformed_plans,
        "audit": audit,
        # Compatibility aliases for consumers of the original schema.
        "critical": [item["message"] for item in blockers],
        "high": [item["message"] for item in blockers],
        "medium": [item["message"] for item in review_items],
        "deprecated_aliases": {
            "critical": {"replacement": "blockers"},
            "high": {
                "replacement": "blockers",
                "semantics": "Retained for --fail-on-high compatibility; it mirrors evidenced blockers.",
            },
            "medium": {"replacement": "review_items"},
            "fail-on-high": {"replacement": "fail-on-blocked"},
        },
    }
    _reject_report_value(report, "completion guard report")
    return report


def print_markdown(guard: dict[str, object]) -> None:
    print("# 项目完成证据门控")
    print()
    print(f"- Project root: `{guard['project_root']}`")
    print(f"- Schema: `{guard['schema_version']}`")
    print(f"- Status: `{guard['status']}`")
    print(f"- Scope: `{guard['scope']['mode']}`")
    if guard["scope"]["current_plan"]:
        print(f"- Current plan: `{guard['scope']['current_plan']}`")
    print()
    for title, key in [("阻塞项", "blockers"), ("需复核", "review_items"), ("非阻塞信号", "signals")]:
        print(f"## {title}")
        items = guard[key]
        if items:
            for item in items:
                print(f"- [{item['code']}] {item['message']}")
        else:
            print("- None")
        print()
    print("## 治理覆盖（不影响状态）")
    coverage = guard["governance_coverage"]
    print(f"- Coverage: {coverage['coverage_percent']}%")
    missing = coverage["artifacts"]["missing"]
    if missing:
        for path in missing:
            print(f"- Missing optional artifact: `{path}`")
    else:
        print("- Missing optional artifacts: None")
    print()
    print("## 文档占位符")
    unresolved = guard["unresolved_docs"]
    if unresolved:
        for item in unresolved:
            print(f"- `{item['path']}`: {item['placeholder_count']} marker(s)")
    else:
        print("- None")
    print()
    print("## 未完成的活动计划")
    plans = guard["unfinished_plans"]
    if plans:
        for item in plans:
            nxt = f"；下一步: {item['next_step']}" if item["next_step"] else ""
            print(f"- `{item['path']}`: {item['done']}/{item['total']} 完成{nxt}")
    else:
        print("- None")
    print()
    print("## 损坏的活动计划")
    malformed = guard["malformed_plans"]
    if malformed:
        for item in malformed:
            print(f"- `{item['path']}`: {item['error_type']} — {item['error']}")
    else:
        print("- None")
    print()
    print("## 验证与验收证据")
    evidence = guard["evidence"]
    print(f"- Acceptance: `{evidence['acceptance_status']}`")
    print(f"- Evidence declared: `{evidence['declared']}`")
    if evidence["validation_results"]:
        for name, status in sorted(evidence["validation_results"].items()):
            print(f"- `{name}`: `{status}`")
    else:
        print("- Validation results: not provided")
    print()
    print("## 下一步")
    if guard["status"] == "pass":
        print("- 未检测到阻塞或待复核证据；按已明确声明的范围与证据可继续完成。")
    elif guard["status"] == "blocked":
        print("- 先解决有证据的阻塞项，再重新运行相关验证。")
    else:
        print("- 复核与当前变更相关的项目，补齐必要证据后再判断完成。")


def render_markdown(guard: dict[str, object]) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print_markdown(guard)
    return buffer.getvalue()


def safe_report_path(root: Path, filename: str) -> Path:
    return safe_project_path(
        root,
        f"architecture_reports/latest/{filename}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default=".",
        type=_cli_report_text("project_root"),
        help="Project root to inspect.",
    )
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--max-lines", type=int, default=450, help="Size-signal threshold; never blocks by itself.")
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        type=_cli_report_text("changed_path"),
        help="Project-relative changed path. Repeat to scope review signals.",
    )
    parser.add_argument(
        "--require-validation",
        action="append",
        default=[],
        type=_cli_report_text("required_validation"),
        help="Validation check required for this outcome. Repeatable.",
    )
    parser.add_argument(
        "--validation-result",
        action="append",
        default=[],
        metavar="NAME=STATUS",
        type=_cli_report_text("validation_result"),
        help="Relevant validation evidence; STATUS is pass, fail, not-run, or skipped.",
    )
    parser.add_argument(
        "--acceptance-status",
        choices=sorted(ACCEPTANCE_STATUSES),
        default="unspecified",
        type=_cli_report_text("acceptance_status"),
        help="User-facing acceptance evidence; declare not-required explicitly when applicable.",
    )
    parser.add_argument(
        "--current-plan",
        type=_cli_report_text("current_plan"),
        help="Exact active plan id, title, or filename for this outcome.",
    )
    parser.add_argument("--write", action="store_true", help="Write report to architecture_reports/latest.")
    parser.add_argument("--fail-on-blocked", action="store_true", help="Exit 1 only when status is blocked.")
    parser.add_argument(
        "--fail-on-high",
        action="store_true",
        help="Deprecated alias for --fail-on-blocked.",
    )
    args = parse_args_safely(parser)

    try:
        root = Path(args.project_root).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        parser.error(safe_error_text(exc))
    if not root.is_dir():
        parser.error(f"Project root is not a directory: {root}")
    if args.max_lines < 1:
        parser.error("--max-lines must be positive.")
    try:
        validation_results = parse_validation_results(args.validation_result)
    except ValueError as exc:
        parser.error(safe_error_text(exc))
    try:
        guard = build_guard(
            root,
            max_lines=args.max_lines,
            changed_paths=args.changed_path,
            validation_results=validation_results,
            required_validations=args.require_validation,
            acceptance_status=args.acceptance_status,
            current_plan=args.current_plan,
        )
    except (
        OSError,
        RuntimeError,
        ConcurrentModificationError,
        ProjectPathError,
        ValueError,
    ) as exc:
        parser.error(safe_error_text(exc))
    if args.format == "json":
        output = json.dumps(guard, ensure_ascii=False, indent=2)
        print(output)
    else:
        output = render_markdown(guard)
        print(output, end="")

    if args.write:
        filename = (
            "completion_guard_report.json"
            if args.format == "json"
            else "completion_guard_report.md"
        )
        try:
            report = safe_report_path(root, filename)
            payload = (output + "\n") if args.format == "json" else output
            with project_lock(root):
                _, signature = read_text_safe(report, root=root)
                atomic_write_text(
                    report,
                    payload,
                    root=root,
                    expected_signature=signature,
                )
        except (
            OSError,
            RuntimeError,
            ConcurrentModificationError,
            ProjectPathError,
            ValueError,
        ) as exc:
            parser.error(safe_error_text(exc))
        destination = sys.stderr if args.format == "json" else sys.stdout
        print(f"Report saved: {report}", file=destination)

    if (args.fail_on_blocked or args.fail_on_high) and guard["status"] == "blocked":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
