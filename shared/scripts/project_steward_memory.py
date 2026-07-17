#!/usr/bin/env python3
"""Persist one structured project-memory rule safely and deterministically."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import hashlib
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from project_steward_cli import parse_args_safely, safe_error_text
from project_steward_templates import (
    ConcurrentModificationError,
    PreparedWrite,
    ProjectPathError,
    atomic_write_batch,
    canonical_root,
    is_placeholder_value,
    project_lock,
    read_text_safe,
    reject_high_confidence_secret,
    safe_project_path,
)


VALID_PRIORITIES = {"hard", "preference", "pending"}
VALID_CATEGORIES = {"ui-platform", "architecture", "agent-behavior", "security", "validation", "product"}
VALID_KINDS = {"invariant", "preference", "decision", "failure", "pending"}
RULE_ID_PATTERN = re.compile(r"[\w][\w.-]{0,63}", re.UNICODE)
START_MARKER_PATTERN = re.compile(
    r"^\s*<!-- stewardship-rule-id:(?P<rule_id>[\w][\w.-]{0,63}) -->\s*$"
)
END_MARKER_PATTERN = re.compile(
    r"^\s*<!-- stewardship-rule-end:(?P<rule_id>[\w][\w.-]{0,63}) -->\s*$"
)
SEMANTIC_FIELDS = (
    "rule_id",
    "kind",
    "category",
    "scope",
    "priority",
    "source",
    "rule",
    "exceptions",
    "validation",
    "evidence",
    "detection",
    "last_verified",
    "expiry",
    "invalidation",
)

RULE_BLOCK_STATUS_LABELS = {
    "created": "rule block created",
    "replaced": "rule block updated",
    "current": "rule block current",
    "legacy-current": "rule block current (legacy format)",
}


@dataclass(frozen=True)
class Upsert:
    path: Path
    text: str
    signature: str | None
    status: str


def single_line(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned or any(character in cleaned for character in ("\n", "\r", "\0")):
        raise ValueError(f"{label} must be a non-empty single line")
    reject_high_confidence_secret(cleaned, label)
    return cleaned


def default_kind(priority: str) -> str:
    return {"hard": "invariant", "preference": "preference", "pending": "pending"}[priority]


def legacy_digest(args: argparse.Namespace) -> str:
    payload = "\0".join([args.category, args.scope, args.rule])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def default_rule_id(args: argparse.Namespace) -> str:
    return f"rule-{legacy_digest(args)}"


def semantic_digest(args: argparse.Namespace) -> str:
    payload = "\0".join(str(getattr(args, field)) for field in SEMANTIC_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def stable_marker(args: argparse.Namespace) -> str:
    """Return the full semantic version marker (legacy name kept for imports)."""
    return f"<!-- stewardship-rule-version:{semantic_digest(args)} -->"


def logical_marker(args: argparse.Namespace) -> str:
    return f"<!-- stewardship-rule-id:{args.rule_id} -->"


def end_marker(args: argparse.Namespace) -> str:
    return f"<!-- stewardship-rule-end:{args.rule_id} -->"


def rule_block(args: argparse.Namespace) -> str:
    return f"""
{logical_marker(args)}
{stable_marker(args)}

### {args.rule}

- Recorded: {date.today().isoformat()}
- Kind: {args.kind}
- Category: {args.category}
- Scope: {args.scope}
- Priority: {args.priority}
- Source: {args.source}
- Rule: {args.rule}
- Exceptions: {args.exceptions}
- Validation: {args.validation}
- Evidence: {args.evidence}
- Detection: {args.detection}
- Last verified: {args.last_verified}
- Expiry: {args.expiry}
- Invalidation: {args.invalidation}

{end_marker(args)}
""".strip()


def agents_rule_line(args: argparse.Namespace) -> str:
    return (
        f"- {args.rule} Scope: {args.scope}. Exceptions: {args.exceptions}. "
        f"Detection: {args.detection}. Validation: {args.validation}"
    )


def agents_block(args: argparse.Namespace) -> str:
    return f"""
{logical_marker(args)}
{stable_marker(args)}

### {args.rule}

{agents_rule_line(args)}

{end_marker(args)}
""".strip()


def validate_marker_integrity(text: str) -> dict[str, tuple[int, int]]:
    """Require every modern rule marker to form one unique, non-nested pair."""
    starts: dict[str, list[int]] = {}
    ends: dict[str, list[int]] = {}
    events: list[tuple[str, str, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        start = START_MARKER_PATTERN.match(line)
        end = END_MARKER_PATTERN.match(line)
        if start:
            rule_id = start.group("rule_id")
            starts.setdefault(rule_id, []).append(offset)
            events.append(("start", rule_id, offset))
        if end:
            rule_id = end.group("rule_id")
            ends.setdefault(rule_id, []).append(offset + len(line))
            events.append(("end", rule_id, offset + len(line)))
        offset += len(line)

    all_ids = sorted(set(starts) | set(ends))
    spans: dict[str, tuple[int, int]] = {}
    for rule_id in all_ids:
        start_positions = starts.get(rule_id, [])
        end_positions = ends.get(rule_id, [])
        if len(start_positions) != 1 or len(end_positions) != 1:
            raise ValueError(
                f"Rule marker `{rule_id}` must have exactly one start and one end marker"
            )
        if start_positions[0] >= end_positions[0]:
            raise ValueError(f"Rule marker `{rule_id}` is reversed")
        spans[rule_id] = (start_positions[0], end_positions[0])

    open_rule: str | None = None
    for event, rule_id, _position in sorted(events, key=lambda item: item[2]):
        if event == "start":
            if open_rule is not None:
                raise ValueError(
                    f"Rule marker `{rule_id}` is nested inside `{open_rule}`"
                )
            open_rule = rule_id
        elif open_rule != rule_id:
            raise ValueError(f"Rule marker `{rule_id}` closes out of order")
        else:
            open_rule = None
    if open_rule is not None:
        raise ValueError(f"Rule marker `{open_rule}` is missing its end marker")
    return spans


def _legacy_marker_span(text: str, args: argparse.Namespace) -> tuple[int, int] | None:
    token = f"<!-- stewardship-rule:{legacy_digest(args)} -->"
    lines = text.splitlines(keepends=True)
    positions: list[int] = []
    offset = 0
    for line in lines:
        if line.strip() == token:
            positions.append(offset)
        offset += len(line)
    if not positions:
        return None
    if len(positions) != 1:
        raise ValueError(f"Legacy rule marker `{args.rule_id}` is duplicated")
    start_offset = positions[0]
    offset = start_offset
    for line in text[start_offset:].splitlines(keepends=True):
        offset += len(line)
        if "Validation:" in line.strip():
            return start_offset, offset
    raise ValueError(
        f"Legacy rule marker `{args.rule_id}` has no Validation boundary; refusing replacement"
    )


def _marker_span(text: str, args: argparse.Namespace) -> tuple[int, int] | None:
    spans = validate_marker_integrity(text)
    if args.rule_id in spans:
        return spans[args.rule_id]
    return _legacy_marker_span(text, args)


def legacy_block_matches(current: str, args: argparse.Namespace) -> bool:
    """Recognize an unchanged pre-versioned record without duplicating it."""
    expected_lines = {
        f"- Category: {args.category}",
        f"- Scope: {args.scope}",
        f"- Priority: {args.priority}",
        f"- Source: {args.source}",
        f"- Rule: {args.rule}",
        f"- Exceptions: {args.exceptions}",
        f"- Validation: {args.validation}",
    }
    defaults_unchanged = (
        args.kind == default_kind(args.priority)
        and args.evidence == "[需确认]"
        and args.detection == "[需确认]"
        and args.last_verified == "[未验证]"
        and args.expiry == "none"
        and args.invalidation
        == "Superseded by a confirmed rule or invalidated by changed project evidence."
    )
    return defaults_unchanged and expected_lines.issubset(
        {line.strip() for line in current.splitlines()}
    )


def has_section_heading(text: str, section_heading: str) -> bool:
    """Match an existing Markdown heading without case or whitespace drift."""
    expected = " ".join(section_heading.strip().split()).casefold()
    return any(
        " ".join(line.strip().split()).casefold() == expected
        for line in text.splitlines()
    )


def prepare_upsert(
    path: Path,
    block: str,
    args: argparse.Namespace,
    *,
    root: Path,
    section_heading: str,
) -> Upsert:
    existing, signature = read_text_safe(path, root=root)
    span = _marker_span(existing, args)
    if span is not None:
        current = existing[span[0]:span[1]]
        if stable_marker(args) in current:
            return Upsert(path, existing, signature, "current")
        if f"<!-- stewardship-rule:{legacy_digest(args)} -->" in current and legacy_block_matches(current, args):
            return Upsert(path, existing, signature, "legacy-current")
        if not args.replace:
            raise ValueError(
                f"Rule `{args.rule_id}` already exists with different semantics in "
                f"{path.relative_to(root)}; rerun with --replace to update it explicitly"
            )
        replacement = block.strip() + "\n"
        updated = existing[:span[0]] + replacement + existing[span[1]:]
        validate_marker_integrity(updated)
        return Upsert(path, updated, signature, "replaced")

    body = existing
    if body and not body.endswith("\n"):
        body += "\n"
    if not has_section_heading(body, section_heading):
        body += ("\n" if body else "") + section_heading + "\n"
    body += "\n" + block.strip() + "\n"
    validate_marker_integrity(body)
    return Upsert(path, body, signature, "created")


def normalize_args(args: argparse.Namespace) -> None:
    evidence_defaults = {
        "source": "[需确认]",
        "validation": "[需确认]",
        "evidence": "[需确认]",
        "detection": "[需确认]",
        "last_verified": "[未验证]",
    }
    explicit_fields = {
        field for field in evidence_defaults if getattr(args, field) is not None
    }
    for field, default in evidence_defaults.items():
        if getattr(args, field) is None:
            setattr(args, field, default)
    for field in (
        "rule",
        "scope",
        "source",
        "exceptions",
        "validation",
        "evidence",
        "detection",
        "last_verified",
        "expiry",
        "invalidation",
    ):
        setattr(args, field, single_line(getattr(args, field), field))
    args.kind = args.kind or default_kind(args.priority)
    args.rule_id = single_line(args.rule_id or default_rule_id(args), "rule_id")
    if not RULE_ID_PATTERN.fullmatch(args.rule_id):
        raise ValueError("rule_id must contain only Unicode letters/numbers, dots, underscores, and hyphens")
    if (args.priority == "pending") != (args.kind == "pending"):
        raise ValueError("Unverified memory must use both --priority pending and --kind pending")
    if is_placeholder_value(args.source) and args.kind != "pending":
        raise ValueError(
            "A memory without an explicit source is unverified and can only be stored as pending"
        )
    if args.kind != "pending":
        required = ["scope", "source", "last_verified"]
        if args.priority == "hard" or args.kind == "invariant":
            required.extend(["evidence", "detection", "validation"])
        missing = [
            field for field in required if is_placeholder_value(getattr(args, field))
        ]
        if (
            args.priority != "hard"
            and args.kind != "invariant"
            and is_placeholder_value(args.evidence)
            and is_placeholder_value(args.detection)
        ):
            missing.append("evidence-or-detection")
        if missing:
            raise ValueError(
                "Non-pending memory requires explicit non-placeholder values for: "
                + ", ".join(missing)
            )
    if args.mirror_agents and not (args.priority == "hard" and args.kind == "invariant"):
        raise ValueError("--mirror-agents requires --priority hard and --kind invariant")
    if args.mirror_agents:
        required = ("source", "evidence", "detection", "validation", "last_verified")
        missing = [
            field
            for field in required
            if field not in explicit_fields or is_placeholder_value(getattr(args, field))
        ]
        if missing:
            raise ValueError(
                "--mirror-agents requires explicit non-placeholder values for: "
                + ", ".join(missing)
            )
    if args.kind == "failure":
        required = ("evidence", "detection", "last_verified")
        missing = [
            field
            for field in required
            if field not in explicit_fields or is_placeholder_value(getattr(args, field))
        ]
        if missing:
            raise ValueError(
                "Failure memory requires explicit non-placeholder values for: "
                + ", ".join(missing)
            )


def prepare_memory_operations(
    root: Path,
    args: argparse.Namespace,
    block: str,
) -> list[Upsert]:
    operations = [
        prepare_upsert(
            safe_project_path(root, "docs/project_preferences.md"),
            block,
            args,
            root=root,
            section_heading="## Structured rules",
        )
    ]
    if args.mirror_agents:
        operations.append(
            prepare_upsert(
                safe_project_path(root, "AGENTS.md"),
                agents_block(args),
                args,
                root=root,
                section_heading="## Project Hard Rules",
            )
        )
    return operations


def print_memory_result(
    root: Path,
    args: argparse.Namespace,
    block: str,
    operations: list[Upsert],
) -> None:
    print(("写入" if args.write else "试运行") + f": 结构化记忆规则，项目: {root}")
    print(f"- rule_id: {args.rule_id}")
    print(f"- semantic version: {semantic_digest(args)}")
    print(f"\n{block}\n")
    for operation in operations:
        status_label = RULE_BLOCK_STATUS_LABELS[operation.status]
        print(f"- {status_label}: {operation.path.relative_to(root)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root to update.")
    parser.add_argument("--rule", required=True, help="Stable rule to persist.")
    parser.add_argument("--rule-id", help="Stable logical identity used for explicit future replacement.")
    parser.add_argument("--kind", choices=sorted(VALID_KINDS), help="Rule kind; inferred from priority when omitted.")
    parser.add_argument("--scope", default="[需确认]", help="Where the rule applies.")
    parser.add_argument("--priority", choices=sorted(VALID_PRIORITIES), default="pending")
    parser.add_argument("--category", choices=sorted(VALID_CATEGORIES), default="architecture")
    parser.add_argument("--source", help="Why this rule is trusted; defaults to [需确认].")
    parser.add_argument("--exceptions", default="Only when the user explicitly confirms an exception.")
    parser.add_argument("--validation", help="How future agents verify compliance; defaults to [需确认].")
    parser.add_argument("--evidence", help="Issue, ADR, test, log, or other non-secret evidence reference; defaults to [需确认].")
    parser.add_argument("--detection", help="Check or review point that detects recurrence or drift; defaults to [需确认].")
    parser.add_argument("--last-verified", help="Date or revision where evidence was last checked; defaults to [未验证].")
    parser.add_argument("--expiry", default="none", help="Expiry date/condition, or `none`.")
    parser.add_argument(
        "--invalidation",
        default="Superseded by a confirmed rule or invalidated by changed project evidence.",
        help="Condition that makes this rule stale.",
    )
    parser.add_argument("--replace", action="store_true", help="Explicitly replace the same logical rule when semantics changed.")
    parser.add_argument(
        "--mirror-agents",
        action="store_true",
        help="Also mirror an explicitly selected hard invariant into AGENTS.md.",
    )
    parser.add_argument("--write", action="store_true", help="Write the rule to its selected project-memory carrier.")
    args = parse_args_safely(parser)

    try:
        root = canonical_root(Path(args.project_root))
        normalize_args(args)
        block = rule_block(args)
        if not args.write:
            operations = prepare_memory_operations(root, args, block)
            print_memory_result(root, args, block, operations)
            if any(
                operation.status not in {"current", "legacy-current"}
                for operation in operations
            ):
                print("带上 --write 重新运行以写入上述规则块变更。")
            else:
                print("无需写入；所选规则块已是 current。")
            return 0

        with project_lock(root):
            operations = prepare_memory_operations(root, args, block)
            atomic_write_batch(
                [
                    PreparedWrite(operation.path, operation.text, operation.signature)
                    for operation in operations
                    if operation.status not in {"current", "legacy-current"}
                ],
                root=root,
            )
        print_memory_result(root, args, block, operations)
        return 0
    except (
        ConcurrentModificationError,
        OSError,
        ProjectPathError,
        RuntimeError,
        UnicodeError,
        ValueError,
    ) as exc:
        print(f"错误: {safe_error_text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
