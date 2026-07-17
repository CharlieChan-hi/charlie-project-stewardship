#!/usr/bin/env python3
"""Run structural validators plus independent behavior tests for the plugin."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from project_steward_cli import parse_args_safely


def resolve_system_skills_dir(
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Respect CODEX_HOME while preserving the documented ~/.codex fallback."""
    values = os.environ if environ is None else environ
    codex_home = values.get("CODEX_HOME") or str(Path.home() / ".codex")
    return Path(codex_home).expanduser() / "skills" / ".system"


SYSTEM_SKILLS_DIR = resolve_system_skills_dir()
SEMVER_BASE_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?"
)
CODEX_VERSION_PATTERN = re.compile(
    rf"(?P<base>{SEMVER_BASE_PATTERN.pattern})"
    r"(?:\+codex\.[0-9A-Za-z.-]+)?"
)
IMPLICIT_SKILLS = {
    "plan-relay",
    "project-bootstrap",
    "project-health",
    "project-memory",
    "task-contract",
}
EXPLICIT_ONLY_SKILLS = {
    "architecture-audit",
    "capability-routing",
    "completion-guard",
    "project-intake",
    "project-scaffold",
    "start-here",
}
PUBLIC_REPOSITORY = "https://github.com/CharlieChan-hi/charlie-project-stewardship"
PUBLIC_MARKETPLACE_NAME = "charlie-project-stewardship"


def system_skill_script(*parts: str) -> str:
    path = SYSTEM_SKILLS_DIR.joinpath(*parts)
    if not path.is_file():
        raise SystemExit(f"Missing validator script: {path}")
    return str(path)


def run(command: list[str], cwd: Path) -> None:
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _skill_name(skill_file: Path) -> str | None:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    closing = text.find("\n---\n", 4)
    if closing == -1:
        return None
    for line in text[4:closing].splitlines():
        if line.startswith("name:"):
            return line.partition(":")[2].strip().strip("\"'")
    return None


def _yaml_scalar(raw: str) -> object:
    value = raw.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


def _openai_yaml(path: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    section: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = len(raw_line) - len(raw_line.lstrip(" "))
        if indentation == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            result.setdefault(section, {})
            continue
        if indentation == 2 and section and ":" in stripped:
            key, _, value = stripped.partition(":")
            result[section][key.strip()] = _yaml_scalar(value)
    return result


def _read_json_object(
    path: Path, label: str, errors: list[str]
) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"Could not read {label}: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label.capitalize()} must contain a JSON object.")
        return None
    return payload


def _validate_public_marketplace(plugin_root: Path, errors: list[str]) -> None:
    marketplace_path = plugin_root / ".agents" / "plugins" / "marketplace.json"
    marketplace = _read_json_object(
        marketplace_path, "public marketplace metadata", errors
    )
    if marketplace is None:
        return

    if marketplace.get("name") != PUBLIC_MARKETPLACE_NAME:
        errors.append("Public marketplace name must match the plugin name.")
    if marketplace.get("interface") != {
        "displayName": "Charlie Project Stewardship"
    }:
        errors.append("Public marketplace display name must remain stable.")

    entries = marketplace.get("plugins")
    entry = (
        next(
            (
                item
                for item in entries
                if isinstance(item, dict)
                and item.get("name") == PUBLIC_MARKETPLACE_NAME
            ),
            None,
        )
        if isinstance(entries, list)
        else None
    )
    if entry is None:
        errors.append("Public marketplace must contain the stewardship plugin entry.")
        return

    expected_source = {
        "source": "url",
        "url": f"{PUBLIC_REPOSITORY}.git",
        "ref": "main",
    }
    if entry.get("source") != expected_source:
        errors.append(
            "Public marketplace must install the plugin from the main Git repository root."
        )
    expected_policy = {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    if entry.get("policy") != expected_policy:
        errors.append("Public marketplace policy must remain AVAILABLE/ON_INSTALL.")
    if entry.get("category") != "Developer Tools":
        errors.append("Public marketplace category must remain Developer Tools.")


def _validate_public_release_metadata(
    plugin_root: Path,
    codex: dict[str, object],
    claude: dict[str, object],
    errors: list[str],
) -> None:
    for field in (
        "name",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
    ):
        if codex.get(field) != claude.get(field):
            errors.append(f"Manifest field `{field}` must match across Codex and Claude.")

    if codex.get("repository") != PUBLIC_REPOSITORY:
        errors.append("Manifest repository must point to the canonical public GitHub repository.")
    if codex.get("homepage") != PUBLIC_REPOSITORY:
        errors.append("Manifest homepage must point to the canonical public GitHub repository.")
    if codex.get("license") != "MIT":
        errors.append("Plugin manifests must declare the repository's MIT license.")
    interface = codex.get("interface")
    if not isinstance(interface, dict) or interface.get("websiteURL") != PUBLIC_REPOSITORY:
        errors.append("Codex interface.websiteURL must match the public homepage.")

    license_path = plugin_root / "LICENSE"
    try:
        license_text = license_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Could not read LICENSE: {exc}")
    else:
        if not license_text.startswith("MIT License\n"):
            errors.append("LICENSE must contain the canonical MIT license text.")

    _validate_public_marketplace(plugin_root, errors)


def validate_metadata_contracts(plugin_root: Path) -> list[str]:
    """Validate cross-host manifests and Codex presentation contracts."""
    errors: list[str] = []
    codex_path = plugin_root / ".codex-plugin" / "plugin.json"
    claude_path = plugin_root / ".claude-plugin" / "plugin.json"
    codex = _read_json_object(codex_path, "Codex plugin manifest", errors)
    claude = _read_json_object(claude_path, "Claude plugin manifest", errors)
    if codex is None or claude is None:
        return errors

    _validate_public_release_metadata(plugin_root, codex, claude, errors)

    claude_version = claude.get("version")
    codex_version = codex.get("version")
    if not isinstance(claude_version, str) or not SEMVER_BASE_PATTERN.fullmatch(claude_version):
        errors.append("Claude manifest version must be a base SemVer without build metadata.")
    codex_match = (
        CODEX_VERSION_PATTERN.fullmatch(codex_version)
        if isinstance(codex_version, str)
        else None
    )
    if codex_match is None:
        errors.append("Codex manifest version must be base SemVer with only an optional +codex.* suffix.")
    elif isinstance(claude_version, str) and codex_match.group("base") != claude_version:
        errors.append("Codex and Claude manifests must use the same base SemVer.")

    interface = codex.get("interface")
    prompts = interface.get("defaultPrompt", []) if isinstance(interface, dict) else []
    if not isinstance(prompts, list) or not all(isinstance(item, str) for item in prompts):
        errors.append("Codex interface.defaultPrompt must be a list of strings.")
    elif len(prompts) > 3:
        errors.append("Codex interface.defaultPrompt must contain at most 3 prompts.")

    skill_dirs = sorted(
        path
        for path in (plugin_root / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )
    discovered_names: set[str] = set()
    skill_name_owners: dict[str, Path] = {}
    display_name_owners: dict[str, tuple[str, Path]] = {}
    for skill_dir in skill_dirs:
        name = _skill_name(skill_dir / "SKILL.md")
        if not name:
            errors.append(f"Missing skill name in {skill_dir / 'SKILL.md'}.")
            continue
        if skill_dir.name != name:
            errors.append(
                f"Skill directory `{skill_dir.name}` must match frontmatter name `{name}`."
            )
        previous_skill_dir = skill_name_owners.get(name)
        if previous_skill_dir is not None:
            errors.append(
                f"Duplicate skill frontmatter name `{name}` in "
                f"`{previous_skill_dir.name}` and `{skill_dir.name}`."
            )
        else:
            skill_name_owners[name] = skill_dir
        discovered_names.add(name)
        metadata_path = skill_dir / "agents" / "openai.yaml"
        if not metadata_path.is_file():
            errors.append(f"Missing Codex metadata for skill `{name}`.")
            continue
        try:
            metadata = _openai_yaml(metadata_path)
        except (OSError, ValueError) as exc:
            errors.append(f"Could not parse Codex metadata for `{name}`: {exc}")
            continue
        interface = metadata.get("interface", {})
        policy = metadata.get("policy", {})
        display_name = interface.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            errors.append(f"Skill `{name}` display_name must be a non-empty string.")
        else:
            normalized_display_name = display_name.strip().casefold()
            previous_display = display_name_owners.get(normalized_display_name)
            if previous_display is not None:
                previous_name, previous_dir = previous_display
                errors.append(
                    f"Skill `{name}` display_name `{display_name}` duplicates "
                    f"skill `{previous_name}` in `{previous_dir.name}` case-insensitively."
                )
            else:
                display_name_owners[normalized_display_name] = (name, skill_dir)
        short_description = interface.get("short_description")
        if not isinstance(short_description, str) or not 25 <= len(short_description) <= 64:
            errors.append(f"Skill `{name}` short_description must be 25-64 characters.")
        default_prompt = interface.get("default_prompt")
        if not isinstance(default_prompt, str) or f"${name}" not in default_prompt:
            errors.append(f"Skill `{name}` default_prompt must reference `${name}`.")
        implicit = policy.get("allow_implicit_invocation")
        if not isinstance(implicit, bool):
            errors.append(f"Skill `{name}` must declare boolean allow_implicit_invocation.")
        elif name in IMPLICIT_SKILLS and not implicit:
            errors.append(f"Core skill `{name}` must allow implicit invocation.")
        elif name in EXPLICIT_ONLY_SKILLS and implicit:
            errors.append(f"Compatibility/bridge skill `{name}` must be explicit-only.")
        elif name not in IMPLICIT_SKILLS | EXPLICIT_ONLY_SKILLS and implicit:
            errors.append(
                f"New skill `{name}` cannot become implicit without updating the routing contract."
            )

    missing_expected = (IMPLICIT_SKILLS | EXPLICIT_ONLY_SKILLS) - discovered_names
    for name in sorted(missing_expected):
        errors.append(f"Expected routed skill `{name}` is missing from the plugin.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-cachebuster",
        action="store_true",
        help="Update the installed plugin cachebuster after every validation gate passes.",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="Run self-contained metadata, Python, behavior, and CLI gates without Codex system validators.",
    )
    args = parse_args_safely(parser)
    if args.portable and args.update_cachebuster:
        parser.error("--portable cannot be combined with --update-cachebuster")

    shared_dir = Path(__file__).resolve().parent.parent
    plugin_root = shared_dir.parent
    tests_dir = plugin_root / "tests"

    metadata_errors = validate_metadata_contracts(plugin_root)
    if metadata_errors:
        print("Metadata contract validation failed:", file=sys.stderr)
        for error in metadata_errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    python_files = sorted(str(path) for path in (shared_dir / "scripts").glob("*.py"))
    python_files.extend(sorted(str(path) for path in tests_dir.rglob("*.py")))
    run([sys.executable, "-m", "py_compile", *python_files], plugin_root)

    run([
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(tests_dir),
        "-p",
        "test_*.py",
        "-v",
    ], plugin_root)

    if not args.portable:
        skill_dirs = sorted(
            path
            for path in (plugin_root / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        )
        for skill_dir in skill_dirs:
            run([
                sys.executable,
                system_skill_script("skill-creator", "scripts", "quick_validate.py"),
                str(skill_dir),
            ], plugin_root)

        run([
            sys.executable,
            system_skill_script("plugin-creator", "scripts", "validate_plugin.py"),
            str(plugin_root),
        ], plugin_root)

    run([
        sys.executable,
        str(shared_dir / "scripts" / "project_steward_audit.py"),
        "--project-root",
        str(plugin_root),
    ], plugin_root)
    run([
        sys.executable,
        str(shared_dir / "scripts" / "project_steward_recipes.py"),
        "--list",
    ], plugin_root)

    if args.update_cachebuster:
        run([
            sys.executable,
            system_skill_script("plugin-creator", "scripts", "update_plugin_cachebuster.py"),
            str(plugin_root),
        ], plugin_root)
        run([
            sys.executable,
            system_skill_script("plugin-creator", "scripts", "validate_plugin.py"),
            str(plugin_root),
        ], plugin_root)
        metadata_errors = validate_metadata_contracts(plugin_root)
        if metadata_errors:
            print("Metadata contract validation failed after cachebuster update:", file=sys.stderr)
            for error in metadata_errors:
                print(f"- {error}", file=sys.stderr)
            return 1

    if args.portable:
        print("Portable validation gates passed.")
    else:
        print("Validation gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
