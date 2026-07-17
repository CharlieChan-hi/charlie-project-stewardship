#!/usr/bin/env python3
"""Read-only project health audit with separate governance coverage signals."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import ast
import json
import os
import re
import shutil
import stat
import subprocess

from project_steward_audit_report import print_markdown
from project_steward_capabilities import suggest_capabilities
from project_steward_cli import parse_args_safely, safe_error_text
from project_steward_stack import package_declares_workspace
from project_steward_templates import (
    ConcurrentModificationError,
    ProjectPathError,
    open_project_regular_file,
)


IGNORED_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".vercel",
    ".turbo",
    ".cache",
    "DerivedData",
    ".pytest_cache",
    "__pycache__",
    "architecture_reports",
}

SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".npmrc",
    ".pypirc",
}

ENV_EXAMPLE_SUFFIXES = {"example", "sample", "template"}

SCHEMA_VERSION = "3.0"
MAX_ANALYSIS_BYTES = 500_000

GOVERNANCE_FILES = [
    "README.md",
    "AGENTS.md",
    "docs/project_intake.md",
    "docs/architecture.md",
    "docs/source_structure.md",
    "docs/ai_project_context.md",
    "docs/project_preferences.md",
    "docs/agent_harness.md",
    "docs/capability_routing.md",
    "docs/coding_standards.md",
]

SOURCE_SUFFIXES = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".py",
    ".swift",
    ".kt",
    ".java",
    ".go",
    ".rs",
    ".vue",
    ".svelte",
}

GENERIC_SOURCE_STEMS = {
    "common",
    "helper",
    "helpers",
    "manager",
    "managers",
    "misc",
    "shared",
    "util",
    "utils",
}

DEAD_CODE_NAME_MARKERS = {
    "abandoned",
    "backup",
    "bak",
    "dead",
    "deprecated",
    "legacy",
    "old",
    "tmp",
    "unused",
}

CONTROL_FLOW_PATTERN = re.compile(
    r"\b(if|else\s+if|for|while|switch|case|catch|guard|when|except|elif)\b|&&|\|\|"
)

PYTHON_BRANCH_NODES = tuple(
    node
    for node in (
        ast.BoolOp,
        ast.If,
        ast.IfExp,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        getattr(ast, "Match", None),
    )
    if node is not None
)


def is_env_file_name(name: str) -> bool:
    normalized = name.casefold()
    if normalized == ".env":
        return True
    if not normalized.startswith(".env."):
        return False
    return normalized.rsplit(".", 1)[-1] not in ENV_EXAMPLE_SUFFIXES


def is_secret_file_name(name: str) -> bool:
    return name.casefold() in SECRET_NAMES or is_env_file_name(name)


def is_path_within_root(path: Path, root: Path) -> bool:
    """Return true only when resolving path cannot escape the project root."""
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _is_safe_regular_file(path: Path, root: Path | None = None) -> bool:
    if path.is_symlink():
        return False
    if root is not None and not is_path_within_root(path, root):
        return False
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _is_safe_directory(path: Path, root: Path | None = None) -> bool:
    if path.is_symlink():
        return False
    if root is not None and not is_path_within_root(path, root):
        return False
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def file_exists(root: Path, rel_path: str) -> bool:
    return _is_safe_regular_file(root / rel_path, root)


def safe_read_text(
    path: Path,
    max_bytes: int = MAX_ANALYSIS_BYTES,
    root: Path | None = None,
) -> str:
    """Read a bounded regular text file without following links or reading secrets."""
    if is_secret_file_name(path.name):
        return ""
    if root is None:
        if not _is_safe_regular_file(path):
            return ""
        try:
            if path.lstat().st_size > max_bytes:
                return ""
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""
    try:
        with open_project_regular_file(path, root=root) as handle:
            if os.fstat(handle.fileno()).st_size > max_bytes:
                return ""
            data = handle.read(max_bytes + 1)
            if len(data) > max_bytes:
                return ""
            return data.decode("utf-8", errors="ignore")
    except (OSError, ProjectPathError, ConcurrentModificationError):
        return ""


def stream_source_stats(path: Path, *, root: Path) -> dict[str, int] | None:
    """Count a regular source file without loading it all into memory."""
    if is_secret_file_name(path.name):
        return None
    try:
        with open_project_regular_file(path, root=root) as handle:
            size = os.fstat(handle.fileno()).st_size
            lines = 0
            nonblank_lines = 0
            for raw_line in handle:
                lines += 1
                if raw_line.strip():
                    nonblank_lines += 1
        return {
            "bytes": size,
            "lines": lines,
            "nonblank_lines": nonblank_lines,
        }
    except (OSError, ProjectPathError, ConcurrentModificationError):
        return None


def safe_file_size(path: Path, *, root: Path) -> int | None:
    """Return descriptor-derived size for one regular project file."""
    if is_secret_file_name(path.name):
        return None
    try:
        with open_project_regular_file(path, root=root) as handle:
            return os.fstat(handle.fileno()).st_size
    except (OSError, ProjectPathError, ConcurrentModificationError):
        return None


def detect_stack_safely(root: Path) -> dict[str, object]:
    """Detect common stack markers using only regular in-root entries."""
    if not _is_safe_directory(root):
        return {
            "project_type": "[项目类型需确认]",
            "stack_markers": [],
            "package_manager": "[需确认]",
        }

    entries = {
        path.name: path
        for path in root.iterdir()
        if not path.is_symlink()
        and is_path_within_root(path, root)
        and (_is_safe_regular_file(path, root) or _is_safe_directory(path, root))
    }
    files = set(entries)
    markers: list[str] = []
    package_manager = "[需确认]"
    has_pnpm_workspace = (
        "pnpm-workspace.yaml" in entries
        and _is_safe_regular_file(entries["pnpm-workspace.yaml"], root)
    )
    if has_pnpm_workspace:
        markers.extend(
            ["Node.js / JavaScript or TypeScript", "JavaScript workspace"]
        )
        package_manager = "pnpm"

    if "package.json" in files and _is_safe_regular_file(entries["package.json"], root):
        markers.append("Node.js / JavaScript or TypeScript")
        if has_pnpm_workspace or "pnpm-lock.yaml" in files:
            package_manager = "pnpm"
        elif "yarn.lock" in files:
            package_manager = "yarn"
        elif "package-lock.json" in files:
            package_manager = "npm"
        try:
            package_data = json.loads(safe_read_text(entries["package.json"], root=root))
        except (TypeError, ValueError):
            package_data = {}
        dependency_names: set[str] = set()
        if isinstance(package_data, dict):
            if package_declares_workspace(package_data):
                markers.append("JavaScript workspace")
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                dependencies = package_data.get(key, {})
                if isinstance(dependencies, dict):
                    dependency_names.update(str(name).lower() for name in dependencies)
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
        markers.extend(label for name, label in marker_checks.items() if name in dependency_names)

    if "components.json" in files:
        markers.append("shadcn/ui")
    if "pyproject.toml" in files or "requirements.txt" in files:
        markers.append("Python")
    if "Package.swift" in files:
        markers.append("Swift Package")
    if any(
        path.suffix == ".xcodeproj" and _is_safe_directory(path, root)
        for path in entries.values()
    ):
        markers.append("Xcode project")
    if "Cargo.toml" in files:
        markers.append("Rust")
    if "go.mod" in files:
        markers.append("Go")
    if {"pom.xml", "build.gradle", "settings.gradle"}.intersection(files):
        markers.append("JVM")

    marker_set = set(markers)
    if "JavaScript workspace" in marker_set or (
        "apps" in entries
        and "packages" in entries
        and _is_safe_directory(entries["apps"], root)
        and _is_safe_directory(entries["packages"], root)
    ):
        project_type = "Monorepo"
    elif "Expo" in marker_set:
        project_type = "Expo / React Native app"
    elif {"Next.js", "React", "Vue"}.intersection(marker_set):
        project_type = "Web app"
    elif {"Xcode project", "Swift Package"}.intersection(marker_set):
        project_type = "Apple platform project"
    elif {"Python", "Go", "Rust", "JVM"}.intersection(marker_set):
        project_type = "Backend or tool project [需确认]"
    else:
        project_type = "[项目类型需确认]"

    return {
        "project_type": project_type,
        "stack_markers": sorted(marker_set),
        "package_manager": package_manager,
    }


def iter_source_files(root: Path):
    """Yield regular project files deterministically without following symlinks."""
    try:
        project_root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        return
    if not _is_safe_directory(project_root):
        return

    for current, dirnames, filenames in os.walk(project_root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            candidate = current_path / dirname
            if dirname in IGNORED_DIRS or candidate.is_symlink():
                continue
            if _is_safe_directory(candidate, project_root):
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            path = current_path / filename
            if is_secret_file_name(filename):
                continue
            if _is_safe_regular_file(path, project_root):
                yield path


def find_large_files(root: Path, max_lines: int) -> list[dict[str, object]]:
    """Return size signals only; line count alone is never a defect or blocker."""
    large: list[dict[str, object]] = []
    for path in iter_source_files(root):
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        stats = stream_source_stats(path, root=root)
        if stats is None:
            continue
        line_count = stats["lines"]
        exceeds_analysis_limit = stats["bytes"] > MAX_ANALYSIS_BYTES
        if line_count > max_lines or exceeds_analysis_limit:
            large.append({
                "path": str(path.relative_to(root)),
                "lines": line_count,
                "nonblank_lines": stats["nonblank_lines"],
                "bytes": stats["bytes"],
                "threshold": max_lines,
                "severity": "info",
                "signal": "size-review",
                "complexity_analysis_limited": exceeds_analysis_limit,
                "note": "Size alone is not a quality failure; review responsibility only when relevant.",
            })
    return sorted(large, key=lambda item: item["lines"], reverse=True)


def _count_branches_without_nested_scopes(node: ast.AST) -> int:
    count = 0
    stack = list(ast.iter_child_nodes(node))
    nested_scopes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    while stack:
        child = stack.pop()
        if isinstance(child, nested_scopes):
            continue
        if isinstance(child, PYTHON_BRANCH_NODES):
            count += 1
        stack.extend(ast.iter_child_nodes(child))
    return count


def find_python_complexity_hotspots(root: Path, path: Path, text: str) -> list[dict[str, object]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    hotspots: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start_line = getattr(node, "lineno", 1)
        end_line = getattr(node, "end_lineno", start_line)
        line_count = max(end_line - start_line + 1, 1)
        branch_count = _count_branches_without_nested_scopes(node)
        density = round(branch_count / line_count * 100, 1)
        if line_count >= 80 and branch_count >= 18 and (density >= 15 or branch_count >= 30):
            hotspots.append({
                "path": f"{path.relative_to(root)}:{node.name}",
                "source_path": str(path.relative_to(root)),
                "scope": "function",
                "lines": line_count,
                "control_flow_markers": branch_count,
                "markers_per_100_lines": density,
                "severity": "review",
                "signal": "control-flow-density",
            })
    return hotspots


def find_complexity_hotspots(
    root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    hotspots: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for path in iter_source_files(root):
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        size = safe_file_size(path, root=root)
        if size is None:
            continue
        if size > MAX_ANALYSIS_BYTES:
            skipped.append({
                "path": str(path.relative_to(root)),
                "bytes": size,
                "limit_bytes": MAX_ANALYSIS_BYTES,
                "severity": "info",
                "signal": "analysis-skipped:size-limit",
                "note": "Complexity analysis was skipped because the source exceeds the bounded read limit.",
            })
            continue
        text = safe_read_text(path, root=root)
        if not text:
            continue
        if path.suffix == ".py":
            hotspots.extend(find_python_complexity_hotspots(root, path, text))
            continue
        line_count = text.count("\n") + 1
        control_count = len(CONTROL_FLOW_PATTERN.findall(text))
        density = round(control_count / max(line_count, 1) * 100, 1)
        if line_count >= 80 and control_count >= 25 and density >= 12:
            hotspots.append({
                "path": str(path.relative_to(root)),
                "source_path": str(path.relative_to(root)),
                "scope": "file",
                "lines": line_count,
                "control_flow_markers": control_count,
                "markers_per_100_lines": density,
                "severity": "review",
                "signal": "control-flow-density",
            })
    return (
        sorted(
            hotspots,
            key=lambda item: (
                item["markers_per_100_lines"],
                item["control_flow_markers"],
            ),
            reverse=True,
        )[:15],
        skipped,
    )


def find_generic_name_files(root: Path) -> list[str]:
    generic: list[str] = []
    for path in iter_source_files(root):
        if path.suffix in SOURCE_SUFFIXES and path.stem.lower() in GENERIC_SOURCE_STEMS:
            generic.append(str(path.relative_to(root)))
    return sorted(generic)


def find_dead_code_name_candidates(root: Path) -> list[str]:
    candidates: list[str] = []
    for path in iter_source_files(root):
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        # Only project-relative names are evidence. Absolute ancestors such as
        # `/tmp` must not turn every source file in a temporary checkout into a
        # dead-code candidate.
        lowered_parts = {
            part.lower() for part in path.relative_to(root).parts
        }
        lowered_stem = path.stem.lower()
        if lowered_stem in DEAD_CODE_NAME_MARKERS or lowered_parts.intersection(DEAD_CODE_NAME_MARKERS):
            candidates.append(str(path.relative_to(root)))
    return sorted(candidates)


def analyze_root_clutter(root: Path) -> dict[str, object]:
    if not _is_safe_directory(root):
        return {
            "flagged": False,
            "source_files": [],
            "source_file_count": 0,
            "severity": "info",
            "signal": "root-source-count",
        }

    source_files = sorted(
        path.name
        for path in root.iterdir()
        if _is_safe_regular_file(path, root)
        and path.suffix in SOURCE_SUFFIXES
        and not is_secret_file_name(path.name)
    )
    return {
        "flagged": len(source_files) > 8,
        "source_files": source_files[:20],
        "source_file_count": len(source_files),
        "severity": "info",
        "signal": "root-source-count",
    }


def git_repository_status(root: Path) -> str:
    """Return git, not-git, or unavailable without inspecting repository data."""
    if shutil.which("git") is None:
        return "unavailable"
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return "unavailable"
    if result.returncode == 0 and result.stdout.strip() == "true":
        return "git"
    if result.returncode in {1, 128}:
        return "not-git"
    return "unavailable"


def _git_path_probe(root: Path, arguments: list[str], rel_path: str) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments, "--", rel_path],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def classify_env_files(root: Path, env_files: list[str]) -> list[dict[str, object]]:
    """Classify env filenames through Git metadata without reading file contents."""
    repository_status = git_repository_status(root)
    classifications: list[dict[str, object]] = []
    for rel_path in env_files:
        item: dict[str, object] = {
            "path": rel_path,
            "repository_status": repository_status,
            "tracked": None,
            "ignored": None,
            "classification": "unknown",
        }
        if repository_status == "git":
            tracked = _git_path_probe(
                root,
                ["ls-files", "--error-unmatch"],
                rel_path,
            )
            ignored = _git_path_probe(
                root,
                ["check-ignore", "--no-index", "--quiet"],
                rel_path,
            )
            item["tracked"] = tracked
            item["ignored"] = ignored
            if tracked is True:
                item["classification"] = "tracked"
            elif tracked is False and ignored is True:
                item["classification"] = "ignored"
            elif tracked is False and ignored is False:
                item["classification"] = "unignored"
        classifications.append(item)
    return classifications


def gitignore_covers_env(
    root: Path,
    env_files: list[str] | None = None,
) -> bool | None:
    targets = env_files if env_files is not None else [".env", ".env.local"]
    if not targets:
        return True
    statuses = classify_env_files(root, targets)
    if any(item["classification"] == "unknown" for item in statuses):
        return None
    return all(item["classification"] == "ignored" for item in statuses)


def find_secret_like_files(root: Path) -> list[str]:
    """Inventory secret-like filenames without reading or following them."""
    if not _is_safe_directory(root):
        return []
    findings: set[str] = set()
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames[:] = [
            name
            for name in sorted(dirnames)
            if name not in IGNORED_DIRS
            and not (current_path / name).is_symlink()
            and _is_safe_directory(current_path / name, root)
        ]
        for filename in sorted(filenames):
            path = current_path / filename
            if is_secret_file_name(filename) and _is_safe_regular_file(path, root):
                findings.add(str(path.relative_to(root)))

    # Generated/vendor trees are intentionally skipped by the filesystem walk,
    # but a tracked or unignored secret-like filename inside one of them still
    # matters. Git metadata closes that blind spot without reading contents.
    if git_repository_status(root) == "git":
        secret_pathspecs = [
            ":(glob).[eE][nN][vV]",
            ":(glob).[eE][nN][vV].*",
            ":(glob).[nN][pP][mM][rR][cC]",
            ":(glob).[pP][yY][pP][iI][rR][cC]",
            ":(glob)**/.[eE][nN][vV]",
            ":(glob)**/.[eE][nN][vV].*",
            ":(glob)**/.[nN][pP][mM][rR][cC]",
            ":(glob)**/.[pP][yY][pP][iI][rR][cC]",
        ]
        try:
            tracked = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                    "-z",
                    "--",
                    *secret_pathspecs,
                ],
                capture_output=True,
                check=False,
            )
        except OSError:
            tracked = None
        if tracked is not None and tracked.returncode == 0:
            for raw_path in tracked.stdout.split(b"\0"):
                if not raw_path:
                    continue
                rel_path = Path(os.fsdecode(raw_path))
                if (
                    rel_path.is_absolute()
                    or ".." in rel_path.parts
                    or not is_secret_file_name(rel_path.name)
                ):
                    continue
                try:
                    (root / rel_path).lstat()
                except OSError:
                    continue
                findings.add(rel_path.as_posix())
    return sorted(findings)


def _finding(
    code: str,
    severity: str,
    message: str,
    evidence: list[object] | None = None,
) -> dict[str, object]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "evidence": evidence or [],
    }


def build_audit(root: Path, max_lines: int) -> dict[str, object]:
    root = root.expanduser().resolve(strict=False)
    detected = detect_stack_safely(root)
    missing = [rel_path for rel_path in GOVERNANCE_FILES if not file_exists(root, rel_path)]
    present = [rel_path for rel_path in GOVERNANCE_FILES if file_exists(root, rel_path)]
    coverage_percent = round(len(present) / len(GOVERNANCE_FILES) * 100) if GOVERNANCE_FILES else 100
    governance_coverage = {
        "artifacts": {"present": present, "missing": missing},
        "coverage_percent": coverage_percent,
        "affects_project_health": False,
        "note": "Governance artifacts are optional context and never reduce project health.",
    }

    secret_files_present = find_secret_like_files(root)
    env_files_present = [path for path in secret_files_present if is_env_file_name(Path(path).name)]
    credential_config_files_present = [
        path for path in secret_files_present if path not in env_files_present
    ]
    env_file_statuses = classify_env_files(root, env_files_present)
    credential_config_statuses = classify_env_files(
        root, credential_config_files_present
    )
    unignored_env_files = [
        str(item["path"])
        for item in env_file_statuses
        if item["classification"] in {"tracked", "unignored"}
    ]
    tracked_env_files = [
        str(item["path"])
        for item in env_file_statuses
        if item["classification"] == "tracked"
    ]
    unknown_env_files = [
        str(item["path"])
        for item in env_file_statuses
        if item["classification"] == "unknown"
    ]
    exposed_credential_config_files = [
        str(item["path"])
        for item in credential_config_statuses
        if item["classification"] in {"tracked", "unignored"}
    ]
    unknown_credential_config_files = [
        str(item["path"])
        for item in credential_config_statuses
        if item["classification"] == "unknown"
    ]
    if not env_files_present:
        env_ignore_covered: bool | None = None
        ignore_status = "not-applicable"
    elif unknown_env_files:
        env_ignore_covered = None
        ignore_status = "unknown"
    elif unignored_env_files:
        env_ignore_covered = False
        ignore_status = "risk"
    else:
        env_ignore_covered = True
        ignore_status = "covered"
    secrets = {
        "secret_like_files_present": secret_files_present,
        "env_files_present": env_files_present,
        "env_file_statuses": env_file_statuses,
        "credential_config_files_present": credential_config_files_present,
        "credential_config_statuses": credential_config_statuses,
        "exposed_credential_config_files": exposed_credential_config_files,
        "unknown_credential_config_files": unknown_credential_config_files,
        "ignore_check_required": bool(env_files_present),
        "ignore_status": ignore_status,
        "gitignore_covers_env": env_ignore_covered,
        "unignored_env_files": unignored_env_files,
        "tracked_env_files": tracked_env_files,
        "unknown_env_files": unknown_env_files,
        "risk_detected": bool(unignored_env_files),
        "contents_read": False,
        "symlinks_followed": False,
    }

    large_files = find_large_files(root, max_lines=max_lines)
    complexity_hotspots, complexity_analysis_skipped = find_complexity_hotspots(root)
    generic_name_files = find_generic_name_files(root)
    dead_code_name_candidates = find_dead_code_name_candidates(root)
    root_clutter = analyze_root_clutter(root)

    code_signals = {
        "large_files": large_files,
        "complexity_hotspots": complexity_hotspots,
        "complexity_analysis_skipped": complexity_analysis_skipped,
        "generic_name_files": generic_name_files,
        "dead_code_name_candidates": dead_code_name_candidates,
        "root_clutter": root_clutter,
    }

    serious_risks: list[dict[str, object]] = []
    review_signals: list[dict[str, object]] = []
    unknown_signals: list[dict[str, object]] = []
    informational_signals: list[dict[str, object]] = []

    if unignored_env_files:
        serious_risks.append(_finding(
            "secrets.env-not-ignored",
            "high",
            "Secret-like .env files exist without matching .gitignore coverage.",
            unignored_env_files,
        ))
    if unknown_env_files:
        unknown_signals.append(_finding(
            "secrets.env-ignore-unknown",
            "unknown",
            "Environment-file ignore and tracking status could not be established from Git metadata.",
            env_file_statuses,
        ))
    if exposed_credential_config_files:
        review_signals.append(_finding(
            "secrets.credential-config-exposed",
            "review",
            "Credential-capable config files are tracked or unignored; review their Git-safe shape without reading secret values.",
            credential_config_statuses,
        ))
    if unknown_credential_config_files:
        unknown_signals.append(_finding(
            "secrets.credential-config-unknown",
            "unknown",
            "Credential-capable config-file tracking status could not be established from Git metadata.",
            credential_config_statuses,
        ))
    if complexity_hotspots:
        review_signals.append(_finding(
            "code.control-flow-density",
            "review",
            "Control-flow density suggests a focused responsibility review.",
            [item["path"] for item in complexity_hotspots],
        ))
    if large_files:
        informational_signals.append(_finding(
            "code.large-file",
            "info",
            "Large files are size signals only; line count alone is not a quality failure.",
            [item["path"] for item in large_files],
        ))
    if complexity_analysis_skipped:
        informational_signals.append(_finding(
            "code.complexity-analysis-skipped:size-limit",
            "info",
            "Complexity analysis was skipped for source files above the bounded read limit.",
            complexity_analysis_skipped,
        ))
    if generic_name_files:
        informational_signals.append(_finding(
            "code.generic-name",
            "info",
            "Generic filenames may be intentional; review ownership only when unclear.",
            generic_name_files,
        ))
    if dead_code_name_candidates:
        informational_signals.append(_finding(
            "code.dead-name",
            "info",
            "Names suggest possible legacy code; prove usage before any deletion.",
            dead_code_name_candidates,
        ))
    if root_clutter["flagged"]:
        informational_signals.append(_finding(
            "code.root-source-count",
            "info",
            "Several source files live at project root; structure may still be appropriate.",
            root_clutter["source_files"],
        ))

    if serious_risks:
        health_status = "at-risk"
    elif unknown_signals:
        health_status = "unknown"
    elif review_signals:
        health_status = "needs-review"
    else:
        health_status = "healthy"
    evidence_counts = {
        "serious_risks": len(serious_risks),
        "review_signals": len(review_signals),
        "unknown_signals": len(unknown_signals),
        "informational_signals": len(informational_signals),
    }
    project_health = {
        "status": health_status,
        "score": None,
        "score_scale": None,
        "score_deprecated": True,
        "evidence_counts": evidence_counts,
        "serious_risks": serious_risks,
        "review_signals": review_signals,
        "unknown_signals": unknown_signals,
        "informational_signals": informational_signals,
    }

    recommendations: list[str] = []
    if missing:
        recommendations.append("Add only the governance artifacts that solve a current project need; missing optional files do not reduce health.")
    if unignored_env_files:
        recommendations.append("Remove tracked environment files from Git and add effective ignore coverage before they can be committed.")
    if unknown_env_files:
        recommendations.append("Establish the environment-file tracking and ignore policy in a Git repository before treating it as safe or risky.")
    if exposed_credential_config_files:
        recommendations.append("Review tracked or unignored .npmrc/.pypirc files for a credential-free project-safe form; keep real credentials outside version control.")
    if unknown_credential_config_files:
        recommendations.append("Establish Git tracking or ignore evidence for credential-capable config files without reading their contents.")
    if large_files:
        recommendations.append("Treat large files as review candidates only when the current change or mixed responsibilities justify it.")
    if complexity_hotspots:
        recommendations.append("Inspect the reported control-flow hotspots and change structure only when responsibilities are actually mixed.")
    if generic_name_files:
        recommendations.append("Keep conventional generic names when ownership is clear; rename only where ambiguity causes real friction.")
    if dead_code_name_candidates:
        recommendations.append("Review dead-code-like file names; prove usage before keeping or deleting them.")
    if root_clutter["flagged"]:
        recommendations.append("Review root-level source placement without assuming that a deeper folder structure is better.")

    return {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(root),
        "detected": detected,
        "project_health": project_health,
        "governance_coverage": governance_coverage,
        "secrets": secrets,
        "code_signals": code_signals,
        "capability_suggestions": suggest_capabilities(root, detected),
        "recommendations": recommendations,
        # Compatibility aliases for existing callers. They do not define health.
        "stewardship_files": governance_coverage["artifacts"],
        "large_files": large_files,
        "anti_spaghetti": {
            "complexity_hotspots": complexity_hotspots,
            "complexity_analysis_skipped": complexity_analysis_skipped,
            "generic_name_files": generic_name_files,
            "dead_code_name_candidates": dead_code_name_candidates,
            "root_clutter": root_clutter,
        },
        "readiness_score": None,
        "readiness_score_deprecated": True,
        "deprecated_aliases": {
            "readiness_score": {
                "replacement": "project_health.status and project_health.evidence_counts",
                "semantics": "Deprecated since schema 2.0 and always null; numeric readiness scoring was removed as false precision.",
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root to audit.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format.")
    parser.add_argument("--max-lines", type=int, default=450, help="Line threshold for large source file candidates.")
    args = parse_args_safely(parser)

    try:
        root = Path(args.project_root).expanduser().resolve()
        if not root.is_dir():
            parser.error(f"Project root is not a directory: {root}")
        if args.max_lines < 1:
            parser.error("--max-lines must be positive.")
        audit = build_audit(root, args.max_lines)
    except (
        ConcurrentModificationError,
        KeyError,
        OSError,
        ProjectPathError,
        RuntimeError,
        UnicodeError,
        ValueError,
    ) as exc:
        parser.error(safe_error_text(exc))

    if args.format == "json":
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        print_markdown(audit)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
