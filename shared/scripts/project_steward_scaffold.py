#!/usr/bin/env python3
"""Create missing project stewardship files without overwriting existing files."""

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
    render_precise_adoption_plan,
    render_template,
    safe_project_path,
    text_is_current,
    workflow_adoption_plan_path,
)


BASE_TEMPLATE_FILES = {
    ".gitignore": "gitignore.md",
    "README.md": "README.md",
    "AGENTS.md": "AGENTS.md",
    "docs/project_intake.md": "docs-project_intake.md",
    "docs/architecture.md": "docs-architecture.md",
    "docs/source_structure.md": "docs-source_structure.md",
    "docs/ai_project_context.md": "docs-ai_project_context.md",
    "docs/project_preferences.md": "docs-project_preferences.md",
    "docs/agent_harness.md": "docs-agent_harness.md",
    "docs/capability_routing.md": "docs-capability_routing.md",
    "docs/coding_standards.md": "docs-coding_standards.md",
    "docs/decisions/0001-project-stewardship.md": "docs-decisions-0001-project-stewardship.md",
    "architecture_reports/latest/architecture_current_map.md": "architecture-current-map.md",
    "architecture_reports/latest/architecture_target_plan.md": "architecture-target-plan.md",
    "architecture_reports/latest/ai_project_context.md": "architecture-ai-project-context.md",
    "architecture_reports/latest/architecture_refactor_plan.md": "architecture-refactor-plan.md",
}

MINIMAL_TEMPLATE_FILES = {
    "AGENTS.md": "AGENTS.md",
    "docs/project_intake.md": "docs-project_intake.md",
    "docs/project_preferences.md": "docs-project_preferences.md",
}

ADOPTION_PLAN_PATH = "architecture_reports/latest/stewardship_scaffold_adoption_plan.md"


def build_template_context(root: Path) -> dict[str, str]:
    audit = build_audit(root, max_lines=450)
    detected = audit["detected"]
    stack_markers = detected["stack_markers"]
    stack_text = ", ".join(stack_markers) if stack_markers else "[需确认]"
    capability_suggestions = "\n".join(
        f"- When {item['when']}: use `{item['use']}`. Reason: {item['why']}"
        for item in audit["capability_suggestions"]
    )
    has_project_files = root.exists() and any(
        (root / item).exists()
        for item in ["README.md", "AGENTS.md", "package.json", "Package.swift", "pyproject.toml"]
    )
    stewardship_mode = "Existing project adoption / refresh" if has_project_files else "New project bootstrap"
    return {
        "project_name": root.name,
        "project_type": str(detected["project_type"]),
        "stack_markers": stack_text,
        "package_manager": str(detected["package_manager"]),
        "capability_suggestions": capability_suggestions,
        "stewardship_mode": stewardship_mode,
        "product_goal": "[需确认]",
        "target_users": "[需确认]",
        "platform": str(detected["project_type"]),
        "ui_system": "[需确认]",
        "architecture_preferences": "[需确认]",
        "forbidden_patterns": "[需确认]",
        "validation_expectations": "[需确认]",
        "source_structure_recipe": "[需确认]",
        "recipe_name": "[需确认]",
        "recipe_summary": "Run `project_steward_recipes.py --list` and choose a source structure recipe after stack confirmation.",
        "recipe_folders": "- [需确认]",
        "dependency_direction": "[需确认]",
        "recipe_rules": "- Confirm project type before applying a source recipe.",
        "recipe_validation": "- Inspect project scripts before running validation.",
    }


def scaffold_files(minimal: bool = False) -> dict[str, str]:
    return dict(MINIMAL_TEMPLATE_FILES if minimal else BASE_TEMPLATE_FILES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root to inspect or scaffold.")
    parser.add_argument("--write", action="store_true", help="Create missing files. Existing files are never overwritten.")
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="只生成 3 个核心治理文件（AGENTS.md + docs/project_intake.md + docs/project_preferences.md），适合刚开工。",
    )
    parser.add_argument(
        "--adoption-plan",
        action="store_true",
        help="When existing files differ materially, explicitly create one precise adoption plan.",
    )
    args = parse_args_safely(parser)

    mode = "WRITE" if args.write else "DRY RUN"
    actions: list[str] = []
    differences: list[tuple[str, str, str]] = []
    writes: list[PreparedWrite] = []

    try:
        root = canonical_root(Path(args.project_root))
        lock_context = project_lock(root) if args.write else nullcontext()
        with lock_context:
            context = build_template_context(root)
            for rel_path, template_name in scaffold_files(args.minimal).items():
                target = safe_project_path(root, rel_path)
                content = render_template(template_name, context)
                existing, signature = read_text_safe(target, root=root)
                if signature is None:
                    actions.append(f"create: {rel_path}")
                    if args.write:
                        writes.append(PreparedWrite(target, content, None))
                    continue
                if text_is_current(existing, content):
                    actions.append(f"current: {rel_path}")
                    continue
                actions.append(f"different, preserved: {rel_path}")
                differences.append(
                    (
                        rel_path,
                        signature,
                        content_signature(content.encode("utf-8")),
                    )
                )

            if differences and args.adoption_plan:
                plan = workflow_adoption_plan_path(root, "stewardship_scaffold")
                plan_content = render_precise_adoption_plan(context, differences)
                actions.append(f"adoption plan: {ADOPTION_PLAN_PATH}")
                if args.write:
                    existing_plan, plan_signature = read_text_safe(plan, root=root)
                    updated = existing_plan != plan_content
                    if updated:
                        writes.append(
                            PreparedWrite(plan, plan_content, plan_signature)
                        )
                    actions.append(
                        f"  → {'updated' if updated else 'current'}: {ADOPTION_PLAN_PATH}"
                    )
            elif differences:
                actions.append(
                    "no adoption plan written; rerun with --adoption-plan only if the preserved differences need a merge plan"
                )
            elif args.adoption_plan:
                actions.append("no adoption plan needed: no substantive differences")

            if args.write:
                atomic_write_batch(writes, root=root)

        print(f"{mode}: project stewardship scaffold for {root}")
        for action in actions:
            print(f"- {action}")
        if not args.write:
            print("\n带上 --write 重新运行以创建缺失文件；现有文件仍不会被覆盖。")
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
