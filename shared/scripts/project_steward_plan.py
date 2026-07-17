#!/usr/bin/env python3
"""Durable plan relay for resumable, cross-machine project work."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from project_steward_cli import parse_args_safely, safe_error_text
from project_steward_templates import (
    ConcurrentModificationError,
    ProjectPathError,
    atomic_write_text,
    canonical_root,
    file_signature,
    project_lock,
    read_text_safe,
    reject_high_confidence_secret,
    safe_project_path,
    unlink_project_file_safe,
)
from project_steward_fs import archive_project_file_safe


ACTIVE_DIR = "plans/active"
DONE_DIR = "plans/done"
STEP_ID_PATTERN = re.compile(r"S[0-9]{3,6}")
STEP_PATTERN = re.compile(
    r"^\s*-\s*\[(?P<mark>[ xX~])\]\s*"
    r"(?:(?:\[(?P<id>S[0-9]{3,6})\])|(?:(?P<legacy_number>[0-9]+)[.)]))?"
    r"\s*(?P<text>.+?)\s*$"
)
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
STEP_SECTION_HEADING_PATTERN = re.compile(
    r"^##[ \t]+步骤(?:[ \t]+#+)?[ \t]*$"
)
LEGACY_STEP_SECTION_HEADING_PATTERN = re.compile(
    r"^##[ \t]+steps?(?:[ \t]+#+)?[ \t]*$",
    re.IGNORECASE,
)
SECTION_BOUNDARY_PATTERN = re.compile(r"^#{1,2}(?:[ \t]+|$)")
HANDOFF_SECTION_HEADING_PATTERN = re.compile(
    r"^##[ \t]+(?:交接笔记|handoff(?:[ \t]+notes?)?)(?:[ \t]+#+)?[ \t]*$",
    re.IGNORECASE,
)
PLAN_ID_PATTERN = re.compile(r"[\w][\w.-]{0,127}", re.UNICODE)
COMMON_FILENAME_LIMIT_BYTES = 255
ARCHIVE_SUFFIX_RESERVE_BYTES = 32
QUOTED_FRONTMATTER_FIELDS = {"plan_id", "title", "created_by", "last_updated_by"}


class PlanLookupError(ValueError):
    """Raised when a plan or step selector is missing or ambiguous."""


class PlanSecretError(ValueError):
    """Raised when an external plan carrier violates the secret boundary."""


def now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def single_line(value: str, label: str, *, allow_empty: bool = False) -> str:
    cleaned = value.strip()
    if (not cleaned and not allow_empty) or "\n" in cleaned or "\r" in cleaned or "\0" in cleaned:
        raise ValueError(f"{label} must be a non-empty single line")
    reject_high_confidence_secret(cleaned, label)
    return cleaned


def slugify(title: str, *, max_length: int | None = 72) -> str:
    cleaned = re.sub(r"[^\w一-鿿-]+", "-", title.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if max_length is not None:
        cleaned = cleaned[:max_length].rstrip("-")
    return cleaned or "plan"


def title_digest(title: str) -> str:
    return hashlib.sha256(title.encode("utf-8")).hexdigest()[:10]


def default_plan_id(title: str) -> str:
    return (
        f"{datetime.now().strftime('%Y-%m-%d')}-{slugify(title)}-{title_digest(title)}"
    )


def plan_filename(title: str) -> str:
    suffix = f"-{title_digest(title)}.md"
    slug_budget = (
        COMMON_FILENAME_LIMIT_BYTES
        - ARCHIVE_SUFFIX_RESERVE_BYTES
        - len(suffix.encode("utf-8"))
    )
    slug = truncate_utf8(slugify(title, max_length=None), slug_budget).rstrip("-")
    return f"{slug or 'plan'}{suffix}"


def truncate_utf8(value: str, max_bytes: int) -> str:
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    return data[:max_bytes].decode("utf-8", errors="ignore")


def encode_frontmatter_value(value: str) -> str:
    """Use a JSON string scalar, which is also valid YAML."""
    return json.dumps(value, ensure_ascii=False)


def decode_frontmatter_value(value: str) -> str:
    """Read new quoted scalars while preserving legacy raw frontmatter values."""
    cleaned = value.strip()
    if cleaned.startswith('"') and cleaned.endswith('"'):
        try:
            decoded = json.loads(cleaned)
        except (TypeError, ValueError):
            return cleaned
        if isinstance(decoded, str):
            return decoded
    return cleaned


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        normalized_key = key.strip()
        if normalized_key in fields:
            raise ValueError(
                f"Duplicate frontmatter field `{normalized_key}` in plan"
            )
        fields[normalized_key] = decode_frontmatter_value(value)
    return fields


def step_section_lines(text: str) -> list[tuple[int, str]]:
    """Return step-section lines while retaining old heading-less plan support."""
    lines = text.splitlines()
    frontmatter = FRONTMATTER_PATTERN.match(text)
    body_start = text[:frontmatter.end()].count("\n") if frontmatter else 0
    canonical_headings = [
        index
        for index in range(body_start, len(lines))
        if STEP_SECTION_HEADING_PATTERN.fullmatch(lines[index])
    ]
    legacy_headings = [
        index
        for index in range(body_start, len(lines))
        if LEGACY_STEP_SECTION_HEADING_PATTERN.fullmatch(lines[index])
    ]
    if len(canonical_headings) > 1:
        raise ValueError("Duplicate `## 步骤` sections in plan")
    if len(legacy_headings) > 1:
        raise ValueError("Duplicate legacy `## Steps` sections in plan")
    if canonical_headings and legacy_headings:
        raise ValueError("Plan contains both `## 步骤` and `## Steps` sections")

    if canonical_headings:
        start = canonical_headings[0] + 1
        end = next(
            (
                index
                for index in range(start, len(lines))
                if SECTION_BOUNDARY_PATTERN.match(lines[index])
            ),
            len(lines),
        )
    else:
        if legacy_headings:
            start = legacy_headings[0] + 1
            end = next(
                (
                    index
                    for index in range(start, len(lines))
                    if SECTION_BOUNDARY_PATTERN.match(lines[index])
                ),
                len(lines),
            )
        else:
            # Plans created before the sectioned format stored their checklist in
            # the document body. Preserve that format, but never interpret a
            # handoff-note checkbox as a step.
            start = body_start
            end = next(
                (
                    index
                    for index in range(body_start, len(lines))
                    if HANDOFF_SECTION_HEADING_PATTERN.fullmatch(lines[index])
                ),
                len(lines),
            )

    return [(index + 1, lines[index]) for index in range(start, end)]


def parse_steps(text: str) -> list[dict[str, object]]:
    """Parse the steps section and map legacy numbered checkboxes without rewrites."""
    steps: list[dict[str, object]] = []
    used_ids: set[str] = set()
    for line_number, line in step_section_lines(text):
        match = STEP_PATTERN.match(line)
        if not match:
            continue
        ordinal = len(steps) + 1
        explicit_id = match.group("id")
        legacy_number = match.group("legacy_number")
        numeric_id = int(legacy_number) if legacy_number else ordinal
        step_id = explicit_id or f"S{numeric_id:03d}"
        if step_id in used_ids:
            raise ValueError(f"Duplicate step ID `{step_id}` in plan")
        used_ids.add(step_id)
        mark = match.group("mark").lower()
        status = {"x": "done", "~": "in-progress", " ": "todo"}[mark]
        steps.append(
            {
                "id": step_id,
                "line": line_number,
                "status": status,
                "text": match.group("text"),
                "legacy": explicit_id is None,
            }
        )
    return steps


def step_summary(steps: list[dict[str, object]]) -> dict[str, int]:
    summary = {"total": len(steps), "done": 0, "in_progress": 0, "todo": 0}
    for step in steps:
        if step["status"] == "done":
            summary["done"] += 1
        elif step["status"] == "in-progress":
            summary["in_progress"] += 1
        else:
            summary["todo"] += 1
    return summary


def first_open_step(steps: list[dict[str, object]]) -> dict[str, object] | None:
    for status in ("in-progress", "todo"):
        for step in steps:
            if step["status"] == status:
                return step
    return None


def active_dir(root: Path) -> Path:
    return safe_project_path(root, ACTIVE_DIR)


def done_dir(root: Path) -> Path:
    return safe_project_path(root, DONE_DIR)


def iter_active_plans(root: Path) -> list[Path]:
    canonical = canonical_root(root)
    directory = active_dir(canonical)
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise ProjectPathError(f"Unsafe active plan directory: {directory}")
    plans: list[Path] = []
    for path in sorted(directory.iterdir()):
        if path.suffix != ".md":
            continue
        reject_plan_carrier(path)
        safe_project_path(canonical, path.relative_to(canonical))
        if path.is_symlink() or not path.is_file():
            raise ProjectPathError(f"Unsafe active plan entry: {path}")
        plans.append(path)
    return plans


def reject_plan_value(value: object, label: str = "plan data") -> None:
    """Apply the secret boundary recursively to parsed plan values."""
    if isinstance(value, str):
        try:
            reject_high_confidence_secret(value, label)
        except ValueError:
            raise PlanSecretError(
                "Plan data contains a high-confidence secret; the value was withheld."
            ) from None
    elif isinstance(value, dict):
        for key, item in value.items():
            reject_plan_value(key, label)
            reject_plan_value(item, label)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            reject_plan_value(item, label)


def reject_plan_carrier(path: Path, text: str | None = None) -> None:
    """Reject an external plan carrier before it can be rendered or persisted."""
    try:
        reject_high_confidence_secret(path.name, "plan filename")
        if text is not None:
            reject_high_confidence_secret(text, "plan content")
    except ValueError:
        raise PlanSecretError(
            "Plan data contains a high-confidence secret; the value was withheld."
        ) from None


def read_plan(path: Path, root: Path | None = None) -> dict[str, object]:
    canonical = canonical_root(root or path.parents[2])
    reject_plan_carrier(path)
    text, signature = read_text_safe(path, root=canonical)
    if signature is None:
        raise ConcurrentModificationError(
            "活动计划在读取前已不存在；请重试。"
        )
    reject_plan_carrier(path, text)
    fields = parse_frontmatter(text)
    steps = parse_steps(text)
    summary = step_summary(steps)
    plan = {
        "path": path,
        "title": fields.get("title", path.stem),
        "plan_id": fields.get("plan_id", path.stem),
        "status": fields.get("status", "active"),
        "last_updated_by": fields.get("last_updated_by", "[需确认]"),
        "last_updated_at": fields.get("last_updated_at", "[需确认]"),
        "steps": steps,
        "summary": summary,
        "next_step": first_open_step(steps),
        "text": text,
        "signature": signature,
    }
    reject_plan_value(
        {
            "title": plan["title"],
            "plan_id": plan["plan_id"],
            "status": plan["status"],
            "last_updated_by": plan["last_updated_by"],
            "last_updated_at": plan["last_updated_at"],
            "steps": plan["steps"],
            "next_step": plan["next_step"],
        }
    )
    return plan


def git_hint(root: Path, rel_paths: str | list[str], message: str) -> list[str]:
    paths = [rel_paths] if isinstance(rel_paths, str) else rel_paths
    if os.name == "nt":
        return [
            "# Shell: Windows；以下仅为步骤摘要，需按 PowerShell/CMD 重新转义，不保证可直接复制。",
            f"# Project: {root}",
            f"# Stage paths: {', '.join(paths)}",
            f"# Commit message: {message}",
            "# Push 会修改远端状态；仅在用户明确授权后再运行 git push。",
        ]
    quoted_paths = " ".join(shlex.quote(path) for path in paths)
    return [
        "# Shell: POSIX sh；请先审阅，再逐条运行。",
        f"cd {shlex.quote(str(root))}",
        f"git add -- {quoted_paths}",
        f"git commit -m {shlex.quote(message)} -- {quoted_paths}",
        "# Push 会修改远端状态；仅在用户明确授权后再运行: git push",
    ]


def is_git_work_tree(root: Path) -> bool:
    git = shutil.which("git")
    if git is None:
        return False
    try:
        result = subprocess.run(
            [git, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def print_git_sync_hint(
    root: Path,
    rel_paths: str | list[str],
    message: str,
) -> None:
    if not is_git_work_tree(root):
        return
    print("可选的本地 Git 同步步骤（push 仍需单独授权）：")
    for line in git_hint(root, rel_paths, message):
        print(f"  {line}")


def render_plan_markdown(plan_id: str, title: str, machine: str, steps: list[str]) -> str:
    stamp = now_stamp()
    normalized_steps = steps or ["[需确认] 第一步"]
    step_lines = "\n".join(
        f"- [ ] [S{index:03d}] {step}" for index, step in enumerate(normalized_steps, start=1)
    )
    return (
        "---\n"
        f"plan_id: {encode_frontmatter_value(plan_id)}\n"
        f"title: {encode_frontmatter_value(title)}\n"
        "status: active\n"
        f"created_by: {encode_frontmatter_value(machine)}\n"
        f"last_updated_by: {encode_frontmatter_value(machine)}\n"
        f"last_updated_at: {stamp}\n"
        "current_step: S001\n"
        "---\n\n"
        f"# {title}\n\n"
        "## 步骤\n\n"
        f"{step_lines}\n\n"
        "## 交接笔记\n\n"
        f"{machine} {stamp}: 计划已创建，等待执行。\n"
    )


def set_field(text: str, key: str, value: str) -> str:
    safe_value = single_line(value, key)
    rendered_value = (
        encode_frontmatter_value(safe_value)
        if key in QUOTED_FRONTMATTER_FIELDS
        else safe_value
    )
    frontmatter = FRONTMATTER_PATTERN.match(text)
    if frontmatter is None:
        return text
    body = frontmatter.group("body")
    pattern = re.compile(
        rf"^[ \t]*{re.escape(key)}[ \t]*:.*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(body))
    if len(matches) > 1:
        raise ValueError(f"Duplicate frontmatter field `{key}` in plan")
    if matches:
        updated_body = pattern.sub(
            lambda _match: f"{key}: {rendered_value}",
            body,
            count=1,
        )
        start, end = frontmatter.span("body")
        return text[:start] + updated_body + text[end:]
    closing = frontmatter.end("body")
    return text[:closing] + f"\n{key}: {rendered_value}" + text[closing:]


def append_note(text: str, note_line: str) -> str:
    safe_note = single_line(note_line, "note")
    if not text.endswith("\n"):
        text += "\n"
    if "## 交接笔记" not in text:
        text += "\n## 交接笔记\n\n"
    return text + safe_note + "\n"


def load_active_plans(root: Path) -> list[dict[str, object]]:
    """Validate every active plan before any command renders partial output."""
    return [read_plan(path, root) for path in iter_active_plans(root)]


def resolve_plan(
    root: Path,
    identifier: str | None,
    *,
    plans: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    plans = load_active_plans(root) if plans is None else plans
    if not plans:
        raise PlanLookupError("当前没有活动计划。")
    if identifier is None:
        if len(plans) == 1:
            return plans[0]
        raise PlanLookupError("存在多个活动计划；请用 --plan 提供精确 plan_id、标题或文件名。")
    needle = single_line(identifier, "plan identifier")
    matches = [
        plan
        for plan in plans
        if needle
        in {
            str(plan["plan_id"]),
            str(plan["title"]),
            plan["path"].stem,
            plan["path"].name,
        }
    ]
    if not matches:
        raise PlanLookupError(f"未找到精确匹配 `{needle}` 的活动计划。")
    if len(matches) > 1:
        raise PlanLookupError(f"`{needle}` 同时匹配多个活动计划；请使用唯一 plan_id。")
    return matches[0]


@contextmanager
def selected_plan(
    root: Path,
    identifier: str | None,
    *,
    write: bool,
    required_capability: str = "write",
):
    """Validate before locking, then re-read under the lock before a mutation."""
    plan = resolve_plan(root, identifier)
    if not write:
        yield plan
        return
    with project_lock(root, required_capability=required_capability):
        yield resolve_plan(root, identifier)


def resolve_step(steps: list[dict[str, object]], selector: str) -> dict[str, object]:
    cleaned = single_line(selector, "step selector")
    if STEP_ID_PATTERN.fullmatch(cleaned):
        matches = [step for step in steps if step["id"] == cleaned]
    elif cleaned.isdigit() and steps and all(bool(step["legacy"]) for step in steps):
        # Compatibility for old plans whose CLI used Markdown line numbers.
        matches = [step for step in steps if step["line"] == int(cleaned)]
    else:
        raise PlanLookupError(
            "步骤必须使用 status 显示的精确稳定 ID（例如 S001）；仅旧格式计划兼容旧行号。"
        )
    if len(matches) != 1:
        raise PlanLookupError(f"未找到唯一步骤 `{cleaned}`；请运行 status 查看稳定步骤 ID。")
    return matches[0]


def write_plan(root: Path, plan: dict[str, object], text: str) -> None:
    signature = plan.get("signature")
    if not isinstance(signature, str):
        raise ConcurrentModificationError(
            "活动计划没有可验证的读取签名；拒绝创建或覆盖计划文件。"
        )
    reject_plan_carrier(plan["path"], text)
    atomic_write_text(
        plan["path"],
        text,
        root=root,
        expected_signature=signature,
    )


def preflight_new_plan(
    root: Path,
    target: Path,
    plan_id: str,
    title: str,
    normalized_steps: list[str],
) -> bool:
    """Return whether the exact plan is current; raise on any conflict."""
    for existing_path in iter_active_plans(root):
        existing = read_plan(existing_path, root)
        same_metadata = (
            existing["plan_id"] == plan_id
            and existing["title"] == title
            and [str(step["text"]) for step in existing["steps"]] == normalized_steps
        )
        if existing["plan_id"] == plan_id or existing_path == target:
            if existing_path == target and same_metadata:
                return True
            raise PlanLookupError(
                f"计划标识或文件名冲突：`{plan_id}` / {existing_path.name} "
                "已存在且 metadata 不同。"
            )
    if file_signature(target, root=root) is not None:
        raise PlanLookupError(f"计划文件 `{target.relative_to(root)}` 已存在但无法匹配 metadata。")
    return False


def print_new_plan_summary(
    mode: str,
    title: str,
    rel_path: str,
    plan_id: str,
    step_count: int,
) -> None:
    print(f"{mode}: 新建计划 `{title}`")
    print(f"- 路径: {rel_path}")
    print(f"- plan_id: {plan_id}")
    print(f"- 步骤数: {step_count}")


def cmd_new(root: Path, args: argparse.Namespace) -> int:
    title = single_line(args.title, "title")
    machine = single_line(args.machine, "machine")
    plan_id = args.plan_id or default_plan_id(title)
    plan_id = single_line(plan_id, "plan_id")
    if not PLAN_ID_PATTERN.fullmatch(plan_id):
        raise ValueError("plan_id must contain only Unicode letters/numbers, dots, underscores, and hyphens")
    steps = [single_line(step, "step") for step in (args.step or []) if step.strip()]
    normalized_steps = steps or ["[需确认] 第一步"]
    rel_path = f"{ACTIVE_DIR}/{plan_filename(title)}"
    target = safe_project_path(root, rel_path)
    content = render_plan_markdown(plan_id, title, machine, steps)

    mode = "WRITE" if args.write else "DRY RUN"
    current = preflight_new_plan(root, target, plan_id, title, normalized_steps)
    if not args.write:
        print_new_plan_summary(mode, title, rel_path, plan_id, len(normalized_steps))
        if current:
            print(f"- current: {rel_path}")
            print("  如需更新进度，请使用 `check` 或 `note` 子命令。")
            return 0
        print(f"\n{content}\n带上 --write 重新运行以写入计划文件。")
        return 0

    with project_lock(root):
        current = preflight_new_plan(root, target, plan_id, title, normalized_steps)
        if not current:
            reject_plan_carrier(target, content)
            atomic_write_text(target, content, root=root, expected_signature=None)
    print_new_plan_summary(mode, title, rel_path, plan_id, len(normalized_steps))
    if current:
        print(f"- current: {rel_path}")
        print("  如需更新进度，请使用 `check` 或 `note` 子命令。")
        return 0
    print(f"- created: {rel_path}\n")
    print_git_sync_hint(root, rel_path, f"plan: start {title}")
    return 0


def cmd_status(root: Path, args: argparse.Namespace) -> int:
    plans = load_active_plans(root)
    print("# 活动计划状态\n")
    print(f"- Project root: `{root}`")
    if not plans:
        print("- 当前没有活动计划（plans/active/ 为空或不存在）。")
        return 0
    for plan in plans:
        path = plan["path"]
        summary = plan["summary"]
        nxt = plan["next_step"]
        print(f"\n## {plan['title']}")
        print(f"- plan_id: {plan['plan_id']}")
        print(f"- 文件: {path.relative_to(root)}")
        print(
            f"- 进度: {summary['done']}/{summary['total']} 完成"
            f"（进行中 {summary['in_progress']}，待办 {summary['todo']}）"
        )
        print(f"- 最后更新: {plan['last_updated_by']} @ {plan['last_updated_at']}")
        if summary["total"] == 0:
            print("- 下一步: 无可验证步骤；请修复计划，或确认有意关闭后使用 `finish --force`。")
        elif nxt:
            print(f"- 下一步: {nxt['id']} → {nxt['text']}")
        else:
            print("- 下一步: 全部完成，可运行 `finish` 归档。")
    if is_git_work_tree(root):
        print("\n跨机器接手前先自行确认远端同步状态；push 属于外部写入，必须先获授权。")
    return 0


def cmd_check(root: Path, args: argparse.Namespace) -> int:
    machine = single_line(args.machine, "machine")
    with selected_plan(root, args.plan, write=args.write) as plan:
        target_step = resolve_step(plan["steps"], args.step)
        text = plan["text"]
        new_mark = {"done": "x", "in-progress": "~", "todo": " "}[args.mark]
        lines = text.splitlines()
        index = int(target_step["line"]) - 1
        original = lines[index]
        updated_line = original.replace(
            f"[{STEP_PATTERN.match(original).group('mark')}]", f"[{new_mark}]", 1
        )
        lines[index] = updated_line
        new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        new_text = set_field(new_text, "last_updated_by", machine)
        new_text = set_field(new_text, "last_updated_at", now_stamp())
        next_step = first_open_step(parse_steps(new_text))
        new_text = set_field(
            new_text,
            "current_step",
            str(next_step["id"]) if next_step else "none",
        )
        if args.note:
            new_text = append_note(
                new_text,
                f"{machine} {now_stamp()}: "
                f"{single_line(args.note, 'note')}",
            )

        rel_path = plan["path"].relative_to(root)
        mode = "WRITE" if args.write else "DRY RUN"
        print(f"{mode}: 更新 `{plan['title']}` {target_step['id']} → {args.mark}")
        print(f"- 旧: {original.strip()}\n- 新: {updated_line.strip()}")
        if not args.write:
            print("\n带上 --write 重新运行以保存进度。")
            return 0
        write_plan(root, plan, new_text)
    print(f"- updated: {rel_path}\n")
    print_git_sync_hint(
        root,
        str(rel_path),
        f"plan: step {target_step['id']} -> {args.mark}",
    )
    return 0


def cmd_note(root: Path, args: argparse.Namespace) -> int:
    machine = single_line(args.machine, "machine")
    note_text = single_line(args.text, "note")
    with selected_plan(root, args.plan, write=args.write) as plan:
        note_line = f"{machine} {now_stamp()}: {note_text}"
        new_text = append_note(plan["text"], note_line)
        new_text = set_field(new_text, "last_updated_by", machine)
        new_text = set_field(new_text, "last_updated_at", now_stamp())
        rel_path = plan["path"].relative_to(root)
        mode = "WRITE" if args.write else "DRY RUN"
        print(f"{mode}: 追加交接笔记到 `{plan['title']}`\n- {note_line}")
        if not args.write:
            print("\n带上 --write 重新运行以保存笔记。")
            return 0
        write_plan(root, plan, new_text)
    print(f"- updated: {rel_path}\n")
    print_git_sync_hint(root, str(rel_path), "plan: handoff note")
    return 0


def cmd_finish(root: Path, args: argparse.Namespace) -> int:
    machine = single_line(args.machine, "machine")
    with selected_plan(
        root,
        args.plan,
        write=args.write,
        required_capability="archive",
    ) as plan:
        summary = plan["summary"]
        if summary["total"] == 0 and not args.force:
            print(f"计划 `{plan['title']}` 没有可验证步骤，未归档。")
            print("补充步骤后再完成，或确认有意关闭后带上 --force --write 再运行。")
            return 1
        unfinished = summary["total"] - summary["done"]
        if unfinished > 0 and not args.force:
            print(f"计划 `{plan['title']}` 还有 {unfinished} 步未完成，未归档。")
            print("确认全部完成后，带上 --force --write 再运行。")
            return 1

        source = plan["path"]
        rel_source = source.relative_to(root)
        target = done_dir(root) / source.name
        if file_signature(target, root=root) is not None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            counter = 0
            while file_signature(target, root=root) is not None:
                suffix = f"__{stamp}" if counter == 0 else f"__{stamp}-{counter}"
                target = safe_project_path(root, f"{DONE_DIR}/{source.stem}{suffix}{source.suffix}")
                counter += 1
        rel_target = target.relative_to(root)
        new_text = set_field(plan["text"], "status", "done")
        new_text = set_field(new_text, "last_updated_by", machine)
        new_text = set_field(new_text, "last_updated_at", now_stamp())

        mode = "WRITE" if args.write else "DRY RUN"
        print(f"{mode}: 归档计划 `{plan['title']}`")
        print(f"- 从: {rel_source}\n- 到: {rel_target}")
        if target.name != source.name:
            print("- 注意: plans/done/ 已有同名文件，使用唯一名称归档，未覆盖旧计划。")
        if not args.write:
            print("\n带上 --write 重新运行以归档；不会覆盖任何已有计划。")
            return 0

        reject_plan_carrier(target, new_text)
        archive_project_file_safe(
            source,
            target,
            new_text,
            root=root,
            expected_source_signature=str(plan["signature"]),
        )
    print(f"- archived: {rel_target}\n")
    print_git_sync_hint(
        root,
        [str(rel_source), str(rel_target)],
        f"plan: finish {plan['title']}",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root.")
    parser.add_argument("--machine", default="this-machine", help="Machine label, e.g. home-mac or office-mac.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="Create a new active plan file.")
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--plan-id", dest="plan_id")
    p_new.add_argument("--step", action="append", help="A step description. Repeatable.")
    p_new.add_argument("--write", action="store_true")

    sub.add_parser("status", help="Show active plans and the next open stable step ID.")

    p_check = sub.add_parser("check", help="Update a step by exact stable ID.")
    p_check.add_argument("--plan", help="Exact plan id, title, or filename.")
    p_check.add_argument("--step", required=True, help="Stable step ID from status, e.g. S001.")
    p_check.add_argument("--mark", choices=["done", "in-progress", "todo"], default="done")
    p_check.add_argument("--note", help="Optional one-line handoff note to append.")
    p_check.add_argument("--write", action="store_true")

    p_note = sub.add_parser("note", help="Append a handoff note to a plan.")
    p_note.add_argument("--plan", help="Exact plan id, title, or filename.")
    p_note.add_argument("--text", required=True)
    p_note.add_argument("--write", action="store_true")

    p_finish = sub.add_parser("finish", help="Archive a completed plan into plans/done/.")
    p_finish.add_argument("--plan", help="Exact plan id, title, or filename.")
    p_finish.add_argument("--force", action="store_true", help="Archive even if steps remain.")
    p_finish.add_argument("--write", action="store_true")

    args = parse_args_safely(parser)

    try:
        root = canonical_root(Path(args.project_root))
        if args.command == "status" and args.format == "json":
            plans = [
                {
                    "title": p["title"],
                    "plan_id": p["plan_id"],
                    "path": str(p["path"].relative_to(root)),
                    "summary": p["summary"],
                    "last_updated_by": p["last_updated_by"],
                    "last_updated_at": p["last_updated_at"],
                    "next_step": p["next_step"],
                }
                for p in load_active_plans(root)
            ]
            print(json.dumps({"project_root": str(root), "active_plans": plans}, ensure_ascii=False, indent=2))
            return 0

        handlers = {
            "new": cmd_new,
            "status": cmd_status,
            "check": cmd_check,
            "note": cmd_note,
            "finish": cmd_finish,
        }
        handler = handlers.get(args.command)
        if handler is None:
            parser.print_help()
            return 0
        return handler(root, args)
    except (
        ConcurrentModificationError,
        OSError,
        PlanLookupError,
        ProjectPathError,
        RuntimeError,
        UnicodeError,
        ValueError,
    ) as exc:
        print(f"错误: {safe_error_text(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
