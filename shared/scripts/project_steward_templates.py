#!/usr/bin/env python3
"""Secret validation, template rendering, and adoption-plan helpers."""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent

# Keep these imports as compatibility re-exports for existing stewardship scripts.
from project_steward_fs import (
    ConcurrentModificationError,
    PreparedWrite,
    ProjectPathError,
    atomic_write_batch,
    atomic_write_text,
    canonical_root,
    content_signature,
    file_signature,
    open_project_regular_file,
    project_lock,
    read_text_safe,
    safe_project_path,
    unlink_project_file_safe,
)


SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "assets" / "templates"
PLACEHOLDER_PATTERN = re.compile(r"\[\[([A-Za-z_][A-Za-z0-9_]*)\]\]")
_PURE_VARIABLE_REFERENCE_PATTERN = re.compile(
    r"(?:\$\{(?!\d)\w+\}|"
    r"\{\{[ \t]*(?!\d)\w+(?:\.(?!\d)\w+)*[ \t]*\}\})"
)
_SECRET_ASSIGNMENT_NAME_PATTERN = (
    r"(?:[\w][\w.-]*?)?"
    r"(?:secret[_-]?access[_-]?key|secret[_-]?key|refresh[_-]?token|"
    r"access[_-]?token|api[_-]?key|client[_-]?secret|connection[_-]?string|"
    r"database[_-]?url|authorization|password|passwd|secret|token)"
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    rf"(?i)(?<![\w.-])(?P<quote>[\"']?)"
    rf"(?P<name>{_SECRET_ASSIGNMENT_NAME_PATTERN})(?P=quote)"
    r"\s*[:=]\s*(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;\"']+)"
)
_CREDENTIAL_URL_PATTERN = re.compile(
    r"(?i)[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:(?P<value>[^@\s]+)@"
)
_HIGH_CONFIDENCE_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+(?P<value>[A-Za-z0-9._~+/-]{12,})"),
    re.compile(r"(?P<value>sk-[A-Za-z0-9_-]{12,})"),
    re.compile(r"(?P<value>gh[pousr]_[A-Za-z0-9]{12,})"),
    re.compile(r"(?P<value>github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"(?P<value>AKIA[0-9A-Z]{16})"),
    re.compile(r"(?P<value>xox[baprs]-[A-Za-z0-9-]{12,})"),
    re.compile(r"(?P<value>glpat-[A-Za-z0-9_-]{20,})"),
    re.compile(r"(?P<value>npm_[A-Za-z0-9]{36})"),
    re.compile(
        r"(?P<value>pypi-AgEIcHlwaS5vcmcC[A-Za-z0-9_-]{20,})"
    ),
    re.compile(r"(?P<value>AIza[A-Za-z0-9_-]{35})"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_SAFE_SECRET_SENTINELS = {
    "required",
    "redacted",
    "example",
    "placeholder",
    "none",
    "unset",
    "not-set",
    "not_set",
    "not-required",
    "not_required",
    "not-applicable",
    "not_applicable",
    "missing",
    "unknown",
    "masked",
    "omitted",
    "synthetic",
    "synthetic-sentinel",
    "n/a",
    "na",
    "tbd",
    "todo",
    "需确认",
    "未提供",
    "未设置",
    "已脱敏",
    "示例",
}
_SAFE_SECRET_EXAMPLES = {
    # AWS's public documentation example access-key ID is not a usable credential.
    "akiaiosfodnn7example",
}
_PROVIDER_SECRET_PREFIX_PATTERN = re.compile(
    r"(?i)^(?:bearer\s+|sk-(?:(?:live|test|proj)[_-])?|gh[pousr]_|"
    r"github_pat_|AKIA|xox[baprs]-|glpat-|npm_|pypi-|AIza)(?P<payload>.+)$"
)
_PROVIDER_EXAMPLE_PAYLOAD_PATTERN = re.compile(
    r"(?i)^(?:placeholder|redacted|example|synthetic(?:[_-]sentinel)?|dummy|fake)"
    r"(?:[_-](?:value|token|key|secret|only|[0-9]+))*$"
)


def _sentinel_text(value: str) -> str:
    """Trim presentation wrappers without accepting unbalanced quoting."""
    cleaned = value.strip().rstrip(".,;")
    if (
        len(cleaned) >= 2
        and cleaned[0] == cleaned[-1]
        and cleaned[0] in {"\"", "'"}
    ):
        cleaned = cleaned[1:-1].strip().rstrip(".,;")
    return cleaned


def _is_pure_variable_reference(value: str) -> bool:
    """Allow only a variable name or dotted template path, never expressions."""
    return _PURE_VARIABLE_REFERENCE_PATTERN.fullmatch(_sentinel_text(value)) is not None


def _normalized_sentinel(value: str) -> str:
    cleaned = _sentinel_text(value)
    if _PURE_VARIABLE_REFERENCE_PATTERN.fullmatch(cleaned) is not None:
        return "placeholder"
    if (
        len(cleaned) >= 2
        and (cleaned[0], cleaned[-1]) in {("[", "]"), ("<", ">"), ("{", "}")}
    ):
        inner = cleaned[1:-1].strip()
        cleaned = inner
    return cleaned.lower().replace(" ", "-")


def _is_safe_secret_sentinel(value: str) -> bool:
    """Recognize explicit non-secret values, including provider-shaped test sentinels."""
    normalized = _normalized_sentinel(value)
    if normalized in _SAFE_SECRET_SENTINELS or normalized in _SAFE_SECRET_EXAMPLES:
        return True
    provider_match = _PROVIDER_SECRET_PREFIX_PATTERN.fullmatch(
        _sentinel_text(value)
    )
    if provider_match is None:
        return False
    payload = _normalized_sentinel(provider_match.group("payload"))
    return _PROVIDER_EXAMPLE_PAYLOAD_PATTERN.fullmatch(payload) is not None


def is_placeholder_value(value: str) -> bool:
    """Return whether a value explicitly represents missing/unverified evidence."""
    cleaned = value.strip()
    if _is_pure_variable_reference(cleaned):
        return True
    if cleaned.startswith("<") and cleaned.endswith(">"):
        return True
    return _is_safe_secret_sentinel(value) or value.strip() in {"[需确认]", "[未验证]"}


def contains_high_confidence_secret(value: str) -> bool:
    """Detect likely real credentials while allowing explicit safe sentinels."""
    for match in _SECRET_ASSIGNMENT_PATTERN.finditer(value):
        candidate = match.group("value")
        normalized = _normalized_sentinel(candidate)
        if normalized == "bearer":
            remainder = value[match.end():].lstrip()
            candidate = remainder.split(None, 1)[0] if remainder else ""
        if not _is_safe_secret_sentinel(candidate):
            return True
    for match in _CREDENTIAL_URL_PATTERN.finditer(value):
        if not _is_safe_secret_sentinel(match.group("value")):
            return True
    for pattern in _HIGH_CONFIDENCE_SECRET_PATTERNS:
        for match in pattern.finditer(value):
            matched_value = match.groupdict().get("value")
            if matched_value is None or not _is_safe_secret_sentinel(matched_value):
                return True
    return False


def reject_high_confidence_secret(value: str, label: str) -> None:
    if contains_high_confidence_secret(value):
        raise ValueError(
            f"{label} appears to contain a real secret; use a redacted/example/placeholder "
            "sentinel or store only an evidence reference"
        )


def workflow_adoption_plan_path(
    root: Path,
    workflow: str,
    qualifier: str | None = None,
) -> Path:
    """Return an isolated adoption-plan carrier for one generating workflow."""
    parts = [workflow, qualifier or ""]
    safe_name = "_".join(
        item
        for item in (
            re.sub(r"[^A-Za-z0-9_-]+", "_", part.strip()).strip("_").lower()
            for part in parts
        )
        if item
    )
    if not safe_name:
        raise ValueError("Adoption-plan workflow name must not be empty")
    return safe_project_path(
        root,
        f"architecture_reports/latest/{safe_name}_adoption_plan.md",
    )


def load_template(template_name: str) -> str:
    relative = Path(template_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProjectPathError(f"Unsafe template path: {template_name}")
    path = TEMPLATE_DIR / relative
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(TEMPLATE_DIR.resolve())
    except ValueError as exc:
        raise ProjectPathError(f"Template escapes template directory: {template_name}") from exc
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f"Missing scaffold template: {path}")
    return path.read_text(encoding="utf-8")


def render_template(template_name: str, context: dict[str, str]) -> str:
    template = dedent(load_template(template_name)).strip()
    missing_keys = sorted({
        match.group(1)
        for match in PLACEHOLDER_PATTERN.finditer(template)
        if match.group(1) not in context
    })
    if missing_keys:
        raise KeyError(f"Missing template context keys: {', '.join(missing_keys)}")
    return PLACEHOLDER_PATTERN.sub(lambda match: context[match.group(1)], template) + "\n"


def render_precise_adoption_plan(
    context: dict[str, str], differences: list[tuple[str, str, str]]
) -> str:
    """Render one evidence-backed plan for preserved files that differ."""
    base = render_template("stewardship-adoption-plan.md", context).rstrip()
    rows = [
        "",
        "## Exact files requiring review",
        "",
        "The tool preserved these existing files. Review and merge only the missing stewardship content:",
        "",
    ]
    rows.extend(
        f"- `{rel_path}` — current sha256 `{current_hash}`; generated reference sha256 `{expected_hash}`"
        for rel_path, current_hash, expected_hash in differences
    )
    return base + "\n" + "\n".join(rows) + "\n"


def normalized_markdown(text: str) -> str:
    """Ignore line-ending and trailing-space drift without hiding content changes."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip() + "\n"


def text_is_current(existing: str, expected: str) -> bool:
    return normalized_markdown(existing) == normalized_markdown(expected)
