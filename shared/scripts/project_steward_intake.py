#!/usr/bin/env python3
"""Generate or plan a structured project intake for stewardship setup."""

from __future__ import annotations

from contextlib import nullcontext
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import argparse

from project_steward_audit import build_audit
from project_steward_cli import parse_args_safely, safe_error_text
from project_steward_templates import (
    ConcurrentModificationError,
    PreparedWrite,
    ProjectPathError,
    atomic_write_batch,
    canonical_root,
    content_signature,
    project_lock,
    read_text_safe,
    reject_high_confidence_secret,
    render_precise_adoption_plan,
    render_template,
    safe_project_path,
    text_is_current,
    workflow_adoption_plan_path,
)


ADOPTION_PLAN_PATH = "architecture_reports/latest/project_intake_adoption_plan.md"


def value_or_confirm(value: str | None) -> str:
    return value.strip() if value and value.strip() else "[需确认]"


def build_context(args: argparse.Namespace, root: Path) -> dict[str, str]:
    for field in (
        "project_name",
        "product_goal",
        "target_users",
        "platform",
        "ui_system",
        "architecture_preferences",
        "forbidden_patterns",
        "validation",
        "recipe",
    ):
        value = getattr(args, field)
        if value:
            reject_high_confidence_secret(value, field)
    audit = build_audit(root, max_lines=450)
    detected = audit["detected"]
    stack_markers = detected["stack_markers"]
    return {
        "project_name": value_or_confirm(args.project_name) if args.project_name else root.name,
        "project_type": str(detected["project_type"]),
        "stack_markers": ", ".join(stack_markers) if stack_markers else "[需确认]",
        "package_manager": str(detected["package_manager"]),
        "product_goal": value_or_confirm(args.product_goal),
        "target_users": value_or_confirm(args.target_users),
        "platform": value_or_confirm(args.platform),
        "ui_system": value_or_confirm(args.ui_system),
        "architecture_preferences": value_or_confirm(args.architecture_preferences),
        "forbidden_patterns": value_or_confirm(args.forbidden_patterns),
        "validation_expectations": value_or_confirm(args.validation),
        "source_structure_recipe": value_or_confirm(args.recipe),
        "capability_suggestions": "\n".join(
            f"- When {item['when']}: use `{item['use']}`. Reason: {item['why']}"
            for item in audit["capability_suggestions"]
        ),
        "stewardship_mode": "Existing project adoption / refresh",
    }


def print_questionnaire(root: Path) -> None:
    print("# 项目准入问题")
    print()
    print(f"项目根目录: `{root}`")
    print()
    print("在进行架构设计或脚手架搭建之前，请确认以下问题：")
    print()
    questions = [
        "产品目标是什么？",
        "目标用户是谁？",
        "项目平台是什么：iOS、macOS、Web、Expo、后端、还是混合？",
        "必须用或禁止用哪些框架/技术栈？",
        "已有或明确要求什么 UI / design system、可访问性或平台约束？",
        "新的页面、组件、服务、模型、测试和文档应该放在哪里？",
        "是否有已经明确禁止的实现模式或依赖？",
        "什么验证可以证明工作完成？",
    ]
    for index, question in enumerate(questions, start=1):
        print(f"{index}. {question}")
    print()
    print("回答以上问题后，带上答案参数和 --write 重新运行以创建 docs/project_intake.md。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root to inspect.")
    parser.add_argument("--project-name", help="Confirmed project name.")
    parser.add_argument("--product-goal", help="Confirmed product goal.")
    parser.add_argument("--target-users", help="Confirmed target users.")
    parser.add_argument("--platform", help="Confirmed platform or platforms.")
    parser.add_argument("--ui-system", help="Required UI system and component policy.")
    parser.add_argument("--architecture-preferences", help="Architecture preferences and module boundary rules.")
    parser.add_argument("--forbidden-patterns", help="Patterns this project should avoid.")
    parser.add_argument("--validation", help="Expected lint, test, build, simulator, or browser checks.")
    parser.add_argument("--recipe", help="Preferred source structure recipe name.")
    parser.add_argument("--write", action="store_true", help="Create a missing intake file without overwriting existing content.")
    parser.add_argument(
        "--adoption-plan",
        action="store_true",
        help="Explicitly create one precise adoption plan when the existing intake differs.",
    )
    args = parse_args_safely(parser)

    try:
        root = canonical_root(Path(args.project_root))
        has_answers = any(
            getattr(args, attr)
            for attr in [
                "product_goal",
                "target_users",
                "platform",
                "ui_system",
                "architecture_preferences",
                "forbidden_patterns",
                "validation",
                "recipe",
            ]
        )
        if not has_answers:
            if args.write:
                raise ValueError(
                    "--write requires at least one confirmed intake answer flag; "
                    "run without --write to view the questionnaire"
                )
            print_questionnaire(root)
            return 0

        mode = "WRITE" if args.write else "DRY RUN"
        lock_context = project_lock(root) if args.write else nullcontext()
        with lock_context:
            writes: list[PreparedWrite] = []
            context = build_context(args, root)
            content = render_template("docs-project_intake.md", context)
            target = safe_project_path(root, "docs/project_intake.md")
            existing, signature = read_text_safe(target, root=root)
            print(f"{mode}: project intake for {root}")
            if signature is None:
                print("- create: docs/project_intake.md")
                if args.write:
                    writes.append(PreparedWrite(target, content, None))
            elif text_is_current(existing, content):
                print("- current: docs/project_intake.md")
            else:
                print("- different, preserved: docs/project_intake.md")
                if args.adoption_plan:
                    plan = workflow_adoption_plan_path(root, "project_intake")
                    plan_content = render_precise_adoption_plan(
                        context,
                        [
                            (
                                "docs/project_intake.md",
                                signature,
                                content_signature(content.encode("utf-8")),
                            )
                        ],
                    )
                    print(f"- adoption plan: {ADOPTION_PLAN_PATH}")
                    if args.write:
                        existing_plan, plan_signature = read_text_safe(plan, root=root)
                        updated = existing_plan != plan_content
                        if updated:
                            writes.append(
                                PreparedWrite(plan, plan_content, plan_signature)
                            )
                        print(
                            f"- {'updated' if updated else 'current'}: {ADOPTION_PLAN_PATH}"
                        )
                else:
                    print("- no adoption plan written; pass --adoption-plan to request one")
            if args.write:
                atomic_write_batch(writes, root=root)
        if not args.write:
            print("\n带上 --write 重新运行以创建缺失文件；现有 intake 仍不会被覆盖。")
        return 0
    except (
        ConcurrentModificationError,
        KeyError,
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
