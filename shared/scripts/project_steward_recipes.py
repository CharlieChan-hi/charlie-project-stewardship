#!/usr/bin/env python3
"""Plan or create a source structure recipe for a project."""

from __future__ import annotations

from contextlib import nullcontext
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import json

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


SKILL_DIR = Path(__file__).resolve().parent.parent
RECIPE_DIR = SKILL_DIR / "assets" / "recipes"

REQUIRED_RECIPE_FIELDS = {
    "name",
    "summary",
    "dependency_direction",
    "folders",
    "rules",
    "validation",
}
REQUIRED_FOLDER_FIELDS = {"path", "responsibility", "allowed", "avoid"}


def _require_non_empty_text(
    payload: dict[str, object], field: str, source: Path
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Recipe `{source.name}` field `{field}` must be a non-empty string"
        )
    return value


def _require_text_list(
    payload: dict[str, object], field: str, source: Path
) -> list[str]:
    value = payload.get(field)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ValueError(
            f"Recipe `{source.name}` field `{field}` must be a non-empty list "
            "of non-empty strings"
        )
    return value


def _validate_recipe_relative_path(raw_path: object, source: Path, index: int) -> str:
    label = f"Recipe `{source.name}` folder #{index + 1} path"
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{label} must be a non-empty string")

    posix_path = PurePosixPath(raw_path)
    windows_path = PureWindowsPath(raw_path)
    if (
        raw_path != raw_path.strip()
        or not posix_path.parts
        or "\\" in raw_path
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or posix_path.as_posix() != raw_path
        or any(part in {"", ".", ".."} for part in posix_path.parts)
    ):
        raise ValueError(
            f"{label} must be a normalized, portable relative path without `.` or `..`"
        )
    return raw_path


def validate_recipe_asset(data: object, source: Path) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ValueError(f"Recipe `{source.name}` must contain a JSON object")

    missing = sorted(REQUIRED_RECIPE_FIELDS - set(data))
    if missing:
        raise ValueError(
            f"Recipe `{source.name}` is missing required fields: {', '.join(missing)}"
        )

    name = _require_non_empty_text(data, "name", source)
    if name != source.stem:
        raise ValueError(
            f"Recipe `{source.name}` field `name` must match filename stem `{source.stem}`"
        )
    _require_non_empty_text(data, "summary", source)
    _require_non_empty_text(data, "dependency_direction", source)
    _require_text_list(data, "rules", source)
    _require_text_list(data, "validation", source)

    folders = data.get("folders")
    if not isinstance(folders, list) or not folders:
        raise ValueError(
            f"Recipe `{source.name}` field `folders` must be a non-empty list"
        )

    seen_paths: set[str] = set()
    for index, folder in enumerate(folders):
        if not isinstance(folder, dict):
            raise ValueError(
                f"Recipe `{source.name}` folder #{index + 1} must be an object"
            )
        missing_folder_fields = sorted(REQUIRED_FOLDER_FIELDS - set(folder))
        if missing_folder_fields:
            raise ValueError(
                f"Recipe `{source.name}` folder #{index + 1} is missing fields: "
                f"{', '.join(missing_folder_fields)}"
            )
        folder_path = _validate_recipe_relative_path(folder.get("path"), source, index)
        portable_key = folder_path.casefold()
        if portable_key in seen_paths:
            raise ValueError(
                f"Recipe `{source.name}` contains duplicate folder path `{folder_path}`"
            )
        seen_paths.add(portable_key)
        for field in ("responsibility", "allowed", "avoid"):
            _require_non_empty_text(folder, field, source)
    return data


def load_recipes() -> dict[str, dict[str, object]]:
    recipes: dict[str, dict[str, object]] = {}
    recipe_root = RECIPE_DIR.resolve()
    for path in sorted(RECIPE_DIR.glob("*.json")):
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(recipe_root)
        except ValueError as exc:
            raise ProjectPathError(f"Recipe escapes recipe directory: {path}") from exc
        if path.is_symlink() or not path.is_file():
            raise ProjectPathError(f"Unsafe recipe asset: {path}")
        data = validate_recipe_asset(
            json.loads(path.read_text(encoding="utf-8")), path
        )
        name = str(data["name"])
        if name in recipes:
            raise ValueError(f"Duplicate recipe name `{name}`")
        recipes[name] = data
    return recipes


def choose_recipe(root: Path, requested: str | None, recipes: dict[str, dict[str, object]]) -> str:
    if requested:
        reject_high_confidence_secret(requested, "recipe name")
        if requested not in recipes:
            raise SystemExit(f"Unknown recipe `{requested}`. Available: {', '.join(sorted(recipes))}")
        return requested

    detected = build_audit(root, max_lines=450)["detected"]
    markers = set(detected["stack_markers"])
    project_type = str(detected["project_type"])
    if project_type == "Monorepo":
        raise SystemExit(
            "Monorepo detected; one root recipe may not fit every package. "
            "Inspect the relevant package, then pass an explicit `--recipe`."
        )
    if {"Xcode project", "Swift Package"}.intersection(markers):
        raise SystemExit(
            "Apple project detected but iOS vs macOS is ambiguous. Choose "
            "`--recipe ios-swiftui` or `--recipe macos-swiftui`; mixed-stack "
            "roots also require an explicit scope."
        )

    candidates: list[str] = []
    has_next = "Next.js" in markers
    has_expo = project_type == "Expo / React Native app" or "Expo" in markers
    if has_next:
        candidates.append("nextjs")
    if has_expo:
        candidates.append("expo")
    if (
        not has_next
        and not has_expo
        and {"React", "Vue", "Vite", "Tailwind CSS"}.intersection(markers)
    ):
        candidates.append("web-react")
    if {"Express", "Python", "Go", "Rust", "JVM"}.intersection(markers) or "Backend" in project_type:
        candidates.append("backend-api")

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise SystemExit(
            "Multiple source-recipe families match this root "
            f"({', '.join(candidates)}). Pass an explicit `--recipe` after "
            "choosing the relevant project scope."
        )
    raise SystemExit("Could not infer a safe source recipe. Run with `--list`, then pass `--recipe <name>`.")


def adapt_recipe_to_project(
    root: Path, recipe_name: str, recipe: dict[str, object]
) -> dict[str, object]:
    """Preserve an existing Next.js root/src and App/Pages Router layout."""
    if recipe_name != "nextjs":
        return recipe

    root_routes = [name for name in ("app", "pages") if (root / name).is_dir()]
    src_routes = [
        name for name in ("app", "pages") if (root / "src" / name).is_dir()
    ]
    if root_routes and src_routes:
        raise SystemExit(
            "Conflicting Next.js router layouts detected at both project root and `src/`. "
            "Resolve the layout ambiguity before applying a source recipe."
        )

    source_folder_names = [
        str(folder["path"])
        for folder in recipe["folders"]
        if str(folder["path"]) not in {"app", "tests"}
    ]
    root_source_folders = [
        name for name in source_folder_names if (root / name).is_dir()
    ]
    src_source_folders = [
        name for name in source_folder_names if (root / "src" / name).is_dir()
    ]
    if root_source_folders and src_source_folders:
        raise SystemExit(
            "Conflicting Next.js source layouts detected at both project root and `src/` "
            f"({', '.join(root_source_folders)} vs "
            f"{', '.join(f'src/{name}' for name in src_source_folders)}). "
            "Choose the intended source boundary before applying a source recipe."
        )

    if src_source_folders:
        source_prefix = "src"
    elif root_source_folders:
        source_prefix = ""
    elif (root / "src").is_dir() or src_routes:
        source_prefix = "src"
    else:
        source_prefix = ""

    if src_routes:
        route_paths = [f"src/{name}" for name in src_routes]
    elif root_routes:
        route_paths = root_routes
    else:
        route_paths = [f"{source_prefix}/app" if source_prefix else "app"]

    adapted_folders: list[dict[str, object]] = []
    for raw_folder in recipe["folders"]:
        original_path = str(raw_folder["path"])
        if original_path == "app":
            for route_path in route_paths:
                folder = dict(raw_folder)
                folder["path"] = route_path
                if route_path.endswith("pages"):
                    folder["responsibility"] = (
                        "Next.js Pages Router pages, API routes when used, and routing entry points."
                    )
                    folder["allowed"] = (
                        "Page files, Pages Router API routes, and routing composition."
                    )
                    folder["avoid"] = "Large business logic directly inside page files."
                adapted_folders.append(folder)
            continue

        folder = dict(raw_folder)
        if source_prefix and original_path != "tests":
            folder["path"] = f"{source_prefix}/{original_path}"
        adapted_folders.append(folder)

    adapted = dict(recipe)
    adapted["folders"] = adapted_folders
    return adapted


def folder_readme(recipe: dict[str, object], folder: dict[str, str]) -> str:
    context = {
        "recipe_name": str(recipe["name"]),
        "folder_path": folder["path"],
        "folder_responsibility": folder["responsibility"],
        "folder_allowed": folder.get("allowed", "[需确认]"),
        "folder_avoid": folder.get("avoid", "[需确认]"),
    }
    return render_template("recipe-folder-readme.md", context)


def recipe_context(root: Path, recipe: dict[str, object]) -> dict[str, str]:
    audit = build_audit(root, max_lines=450)
    detected = audit["detected"]
    stack_markers = detected["stack_markers"]
    folders = recipe["folders"]
    return {
        "project_name": root.name,
        "project_type": str(detected["project_type"]),
        "stack_markers": ", ".join(stack_markers) if stack_markers else "[需确认]",
        "package_manager": str(detected["package_manager"]),
        "recipe_name": str(recipe["name"]),
        "recipe_summary": str(recipe["summary"]),
        "recipe_folders": "\n".join(
            f"- `{folder['path']}`: {folder['responsibility']}" for folder in folders
        ),
        "dependency_direction": str(recipe["dependency_direction"]),
        "recipe_rules": "\n".join(f"- {item}" for item in recipe["rules"]),
        "recipe_validation": "\n".join(f"- {item}" for item in recipe["validation"]),
        "capability_suggestions": "\n".join(
            f"- When {item['when']}: use `{item['use']}`. Reason: {item['why']}"
            for item in audit["capability_suggestions"]
        ),
        "stewardship_mode": "Existing project adoption / refresh",
    }


def list_recipes(recipes: dict[str, dict[str, object]]) -> None:
    print("# 可用的源码结构配方")
    print()
    for name, recipe in sorted(recipes.items()):
        print(f"- `{name}`: {recipe['summary']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root to inspect or update.")
    parser.add_argument("--recipe", help="Recipe name. Omit to infer from detected stack.")
    parser.add_argument("--list", action="store_true", help="List available recipes.")
    parser.add_argument("--write", action="store_true", help="Create missing recipe folders and docs.")
    parser.add_argument(
        "--adoption-plan",
        action="store_true",
        help="Explicitly create one precise adoption plan for preserved files that differ.",
    )
    args = parse_args_safely(parser)

    try:
        root = canonical_root(Path(args.project_root))
        recipes = load_recipes()
        if args.list:
            list_recipes(recipes)
            return 0

        recipe_name = choose_recipe(root, args.recipe, recipes)
        recipe = adapt_recipe_to_project(root, recipe_name, recipes[recipe_name])
        mode = "WRITE" if args.write else "DRY RUN"
        lock_context = project_lock(root) if args.write else nullcontext()
        with lock_context:
            writes: list[PreparedWrite] = []
            context = recipe_context(root, recipe)
            print(f"{mode}: source structure recipe `{recipe_name}` for {root}\n")
            print(f"Summary: {recipe['summary']}")
            print(f"Dependency direction: {recipe['dependency_direction']}\n")
            differences: list[tuple[str, str, str]] = []

            for folder in recipe["folders"]:
                folder_rel = str(folder["path"])
                folder_path = safe_project_path(root, folder_rel)
                if folder_path.exists() and not folder_path.is_dir():
                    raise ProjectPathError(f"Recipe folder path is not a directory: {folder_rel}")
                print(f"- {'current' if folder_path.is_dir() else 'create'}: {folder_rel}/")

                readme_rel = str(Path(folder_rel) / "README.md")
                readme_path = safe_project_path(root, readme_rel)
                readme_content = folder_readme(recipe, folder)
                existing, signature = read_text_safe(readme_path, root=root)
                if signature is None:
                    print(f"  - create: {readme_rel}")
                    if args.write:
                        writes.append(PreparedWrite(readme_path, readme_content, None))
                elif text_is_current(existing, readme_content):
                    print(f"  - current: {readme_rel}")
                else:
                    print(f"  - different, preserved: {readme_rel}")
                    differences.append(
                        (
                            readme_rel,
                            signature,
                            content_signature(readme_content.encode("utf-8")),
                        )
                    )

            structure_rel = "docs/source_structure.md"
            structure_doc = safe_project_path(root, structure_rel)
            content = render_template("docs-source_structure.md", context)
            existing, signature = read_text_safe(structure_doc, root=root)
            if signature is None:
                print(f"- create: {structure_rel}")
                if args.write:
                    writes.append(PreparedWrite(structure_doc, content, None))
            elif text_is_current(existing, content):
                print(f"- current: {structure_rel}")
            else:
                print(f"- different, preserved: {structure_rel}")
                differences.append(
                    (
                        structure_rel,
                        signature,
                        content_signature(content.encode("utf-8")),
                    )
                )

            if differences and args.adoption_plan:
                plan = workflow_adoption_plan_path(
                    root, "source_recipe", recipe_name
                )
                adoption_plan_path = str(plan.relative_to(root))
                plan_content = render_precise_adoption_plan(context, differences)
                print(f"- adoption plan: {adoption_plan_path}")
                if args.write:
                    existing_plan, plan_signature = read_text_safe(plan, root=root)
                    updated = existing_plan != plan_content
                    if updated:
                        writes.append(
                            PreparedWrite(plan, plan_content, plan_signature)
                        )
                    print(
                        f"- {'updated' if updated else 'current'}: {adoption_plan_path}"
                    )
            elif differences:
                print("- no adoption plan written; pass --adoption-plan to request one")
            elif args.adoption_plan:
                print("- no adoption plan needed: no substantive differences")

            if args.write:
                atomic_write_batch(writes, root=root)

        if not args.write:
            print("\n带上 --write 重新运行以创建缺失目录和文件；现有内容仍不会被覆盖。")
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
