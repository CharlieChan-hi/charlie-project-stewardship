#!/usr/bin/env python3
"""Project stack detection for stewardship audits."""

from __future__ import annotations

import os
from pathlib import Path

from project_steward_fs import (
    ConcurrentModificationError,
    ProjectPathError,
    canonical_root,
    open_project_regular_file,
)


def dir_exists(root: Path, rel_path: str) -> bool:
    path = root / rel_path
    return path.is_dir() and not path.is_symlink()


def read_small_text(
    path: Path,
    max_bytes: int = 500_000,
    *,
    root: Path | None = None,
) -> str:
    """Read a bounded regular file through the smallest safe descriptor root."""
    if max_bytes < 0:
        return ""
    anchored_path = path.expanduser()
    if not anchored_path.is_absolute():
        anchored_path = Path.cwd() / anchored_path
    anchored_path = Path(os.path.abspath(os.fspath(anchored_path)))
    effective_root = canonical_root(root if root is not None else anchored_path.parent)
    try:
        with open_project_regular_file(anchored_path, root=effective_root) as handle:
            if os.fstat(handle.fileno()).st_size > max_bytes:
                return ""
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            return ""
        return data.decode("utf-8", errors="ignore")
    except (OSError, ProjectPathError, ConcurrentModificationError):
        return ""


def regular_project_file_exists(path: Path, *, root: Path) -> bool:
    """Check a regular project marker without following symlinks or reading it."""
    try:
        with open_project_regular_file(path, root=root):
            return True
    except (OSError, ProjectPathError, ConcurrentModificationError):
        return False


def is_nonempty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def package_declares_workspace(package_data: dict[str, object]) -> bool:
    workspaces = package_data.get("workspaces")
    if is_nonempty_string_list(workspaces):
        return True
    if not isinstance(workspaces, dict):
        return False
    return is_nonempty_string_list(workspaces.get("packages"))


def detect_package_manager(files: set[str]) -> str:
    if "pnpm-lock.yaml" in files:
        return "pnpm"
    if "yarn.lock" in files:
        return "yarn"
    if "bun.lock" in files or "bun.lockb" in files:
        return "bun"
    if "package-lock.json" in files:
        return "npm"
    return "[需确认]"


def detect_node_markers(root: Path, files: set[str]) -> tuple[list[str], str]:
    has_package_json = "package.json" in files
    has_pnpm_workspace = (
        "pnpm-workspace.yaml" in files
        and regular_project_file_exists(root / "pnpm-workspace.yaml", root=root)
    )
    if not has_package_json and not has_pnpm_workspace:
        return [], "[需确认]"

    markers = ["Node.js / JavaScript or TypeScript"]
    if has_pnpm_workspace:
        markers.append("JavaScript workspace")
    package_manager = "pnpm" if has_pnpm_workspace else detect_package_manager(files)
    if not has_package_json:
        return markers, package_manager

    raw_text = read_small_text(root / "package.json", root=root)
    try:
        import json as _json
        pkg = _json.loads(raw_text)
    except Exception:
        return markers, package_manager

    if not isinstance(pkg, dict):
        return markers, package_manager

    if package_declares_workspace(pkg):
        markers.append("JavaScript workspace")

    # Collect dependency names only (not descriptions, author, etc.)
    dep_names: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        dependencies = pkg.get(key, {})
        if not isinstance(dependencies, dict):
            continue
        dep_names.update(name for name in dependencies if isinstance(name, str))
    dep_lower = {name.lower() for name in dep_names}

    marker_checks = {
        "next": "Next.js",
        "react": "React",
        "vue": "Vue",
        "vite": "Vite",
        "express": "Express",
        "expo": "Expo",
        "tailwindcss": "Tailwind CSS",
        "playwright": "Playwright",
        "vitest": "Vitest",
        "jest": "Jest",
    }
    markers.extend(label for key, label in marker_checks.items() if key in dep_lower)
    return markers, package_manager


def choose_project_type(root: Path, markers: list[str], files: set[str]) -> str:
    if (
        "JavaScript workspace" in markers
        or dir_exists(root, "apps") and dir_exists(root, "packages")
    ):
        return "Monorepo"
    if "Expo" in markers:
        return "Expo / React Native app"
    if {"Next.js", "React", "Vue"}.intersection(markers):
        return "Web app"
    if {"Xcode project", "Swift Package"}.intersection(markers):
        return "Apple platform project"
    if {"Python", "Go", "Rust", "JVM"}.intersection(markers):
        return "Backend or tool project [需确认]"
    return "[项目类型需确认]"


def detect_stack(root: Path) -> dict[str, object]:
    files = {path.name for path in root.iterdir()} if root.exists() else set()
    markers, package_manager = detect_node_markers(root, files)

    if "components.json" in files:
        markers.append("shadcn/ui")
    if "pyproject.toml" in files or "requirements.txt" in files:
        markers.append("Python")
    if "Package.swift" in files:
        markers.append("Swift Package")
    if root.exists() and any(
        path.suffix == ".xcodeproj" and not path.is_symlink()
        for path in root.iterdir()
    ):
        markers.append("Xcode project")
    if "Cargo.toml" in files:
        markers.append("Rust")
    if "go.mod" in files:
        markers.append("Go")
    if "pom.xml" in files or "build.gradle" in files or "settings.gradle" in files:
        markers.append("JVM")

    return {
        "project_type": choose_project_type(root, markers, files),
        "stack_markers": sorted(set(markers)),
        "package_manager": package_manager,
    }
