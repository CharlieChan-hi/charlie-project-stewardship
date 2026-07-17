from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "shared" / "scripts"


def run_script(name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / name), *arguments],
        cwd=str(PLUGIN_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


class PlanForwardContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-plan-contract-")
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_plan_uses_stable_step_ids_without_git_hints_outside_work_tree(self) -> None:
        created = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "--machine",
            "test-machine",
            "new",
            "--title",
            "Stable Plan",
            "--step",
            "First step",
            "--step",
            "Second step",
            "--write",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertFalse(
            any(line.strip().startswith("git push") for line in created.stdout.splitlines())
        )
        self.assertNotIn("Git 同步步骤", created.stdout)
        self.assertNotIn("git add --", created.stdout)

        plan_files = list((self.root / "plans" / "active").glob("*.md"))
        self.assertEqual(len(plan_files), 1)
        plan_text = plan_files[0].read_text(encoding="utf-8")
        self.assertIn("- [ ] [S001] First step", plan_text)
        self.assertIn("- [ ] [S002] Second step", plan_text)

        status = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "--format",
            "json",
            "status",
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["active_plans"][0]["next_step"]["id"], "S001")

        markdown_status = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "status",
        )
        self.assertEqual(markdown_status.returncode, 0, markdown_status.stderr)
        self.assertNotIn("push", markdown_status.stdout)

        checked = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "--machine",
            "test-machine",
            "check",
            "--plan",
            "Stable Plan",
            "--step",
            "S001",
            "--mark",
            "done",
            "--write",
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertFalse(
            any(line.strip().startswith("git push") for line in checked.stdout.splitlines())
        )
        self.assertNotIn("Git 同步步骤", checked.stdout)
        self.assertNotIn("git add --", checked.stdout)
        self.assertIn("- [x] [S001] First step", plan_files[0].read_text(encoding="utf-8"))
        self.assertIn("current_step: S002", plan_files[0].read_text(encoding="utf-8"))

    def test_plan_prints_git_hints_inside_work_tree(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is unavailable")
        initialized = subprocess.run(
            ["git", "init", "--quiet"],
            cwd=str(self.root),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

        created = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "--machine",
            "test-machine",
            "new",
            "--title",
            "Git Plan",
            "--step",
            "First step",
            "--write",
        )

        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("可选的本地 Git 同步步骤", created.stdout)
        self.assertIn("push", created.stdout)
        self.assertIn("授权", created.stdout)

        status = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "status",
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("push", status.stdout)

    def test_plan_selector_rejects_fuzzy_or_ambiguous_matches(self) -> None:
        for title in ("Alpha Plan", "Alpha Extension"):
            created = run_script(
                "project_steward_plan.py",
                "--project-root",
                str(self.root),
                "new",
                "--title",
                title,
                "--step",
                "Step",
                "--write",
            )
            self.assertEqual(created.returncode, 0, created.stderr)

        fuzzy = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "check",
            "--plan",
            "Alpha",
            "--step",
            "S001",
            "--write",
        )
        self.assertNotEqual(fuzzy.returncode, 0)


class MemoryForwardContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-memory-contract-")
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def memory_command(self, rule: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "architecture-boundary",
            "--rule",
            rule,
            "--category",
            "architecture",
            "--scope",
            "Whole project",
            "--kind",
            "invariant",
            "--priority",
            "hard",
            "--evidence",
            "Explicit owner decision",
            "--source",
            "Explicit owner decision in ADR-0001",
            "--detection",
            "Review the architecture boundary test",
            "--validation",
            "Run targeted tests",
            "--last-verified",
            "2026-07-16",
            *extra,
        )

    def test_memory_defaults_to_one_destination(self) -> None:
        written = self.memory_command("Keep boundaries clear.", "--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        self.assertIn(
            "rule block created: docs/project_preferences.md",
            written.stdout,
        )
        self.assertNotIn("- created: docs/project_preferences.md", written.stdout)
        self.assertTrue((self.root / "docs" / "project_preferences.md").is_file())
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / "architecture_reports").exists())
        before = (self.root / "docs" / "project_preferences.md").read_text(encoding="utf-8")

        current_preview = self.memory_command("Keep boundaries clear.")
        self.assertEqual(current_preview.returncode, 0, current_preview.stderr)
        self.assertIn(
            "rule block current: docs/project_preferences.md",
            current_preview.stdout,
        )
        self.assertNotIn("带上 --write", current_preview.stdout)

        repeated = self.memory_command("Keep boundaries clear.", "--write")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn(
            "rule block current: docs/project_preferences.md",
            repeated.stdout,
        )
        after = (self.root / "docs" / "project_preferences.md").read_text(encoding="utf-8")
        self.assertEqual(after, before)

    def test_memory_reuses_bootstrap_structured_rules_heading_case_insensitively(self) -> None:
        scaffolded = run_script(
            "project_steward_scaffold.py",
            "--project-root",
            str(self.root),
            "--minimal",
            "--write",
        )
        self.assertEqual(scaffolded.returncode, 0, scaffolded.stderr)

        written = self.memory_command("Keep boundaries clear.", "--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        preferences = (self.root / "docs" / "project_preferences.md").read_text(
            encoding="utf-8"
        )
        headings = [
            line
            for line in preferences.splitlines()
            if line.strip().casefold() == "## structured rules"
        ]
        self.assertEqual(headings, ["## Structured rules"])

    def test_memory_reuses_legacy_heading_capitalization(self) -> None:
        preferences = self.root / "docs" / "project_preferences.md"
        preferences.parent.mkdir()
        preferences.write_text(
            "# Project Preferences\n\n## Structured Rules\n",
            encoding="utf-8",
        )

        written = self.memory_command("Keep boundaries clear.", "--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        headings = [
            line
            for line in preferences.read_text(encoding="utf-8").splitlines()
            if line.strip().casefold() == "## structured rules"
        ]
        self.assertEqual(headings, ["## Structured Rules"])

    def test_memory_mirrors_agents_only_with_explicit_flag(self) -> None:
        mirrored = self.memory_command(
            "Keep boundaries clear.",
            "--mirror-agents",
            "--write",
        )
        self.assertEqual(mirrored.returncode, 0, mirrored.stderr)
        self.assertIn(
            "Keep boundaries clear.",
            (self.root / "AGENTS.md").read_text(encoding="utf-8"),
        )

    def test_rule_id_conflict_requires_explicit_replace(self) -> None:
        initial = self.memory_command("Version one.", "--write")
        self.assertEqual(initial.returncode, 0, initial.stderr)

        dry_run_conflict = self.memory_command("Version two.")
        self.assertEqual(dry_run_conflict.returncode, 2)
        self.assertNotIn("带上 --write", dry_run_conflict.stdout)

        dry_run_replace = self.memory_command("Version two.", "--replace")
        self.assertEqual(dry_run_replace.returncode, 0, dry_run_replace.stderr)
        self.assertIn(
            "rule block updated: docs/project_preferences.md",
            dry_run_replace.stdout,
        )
        self.assertIn("带上 --write", dry_run_replace.stdout)
        preferences = (self.root / "docs" / "project_preferences.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Version one.", preferences)
        self.assertNotIn("Version two.", preferences)

        conflict = self.memory_command("Version two.", "--write")
        self.assertNotEqual(conflict.returncode, 0)

        replaced = self.memory_command("Version two.", "--replace", "--write")
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertIn(
            "rule block updated: docs/project_preferences.md",
            replaced.stdout,
        )
        preferences = (self.root / "docs" / "project_preferences.md").read_text(encoding="utf-8")
        self.assertIn("Version two.", preferences)
        self.assertNotIn("Version one.", preferences)


class ScaffoldForwardContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-scaffold-contract-")
        self.root = Path(self.temp_dir.name) / "project"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_minimal_scaffold_is_idempotent_and_does_not_require_missing_docs(self) -> None:
        first = run_script(
            "project_steward_scaffold.py",
            "--project-root",
            str(self.root),
            "--minimal",
            "--write",
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        agents_text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Read only what the task needs", agents_text)
        self.assertIn("Missing optional docs do not block ordinary work", agents_text)
        self.assertNotIn("读不到就停下", agents_text)

        second = run_script(
            "project_steward_scaffold.py",
            "--project-root",
            str(self.root),
            "--minimal",
            "--write",
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("current", second.stdout.lower())
        self.assertFalse((self.root / "architecture_reports").exists())

    def test_existing_files_are_preserved_without_per_file_update_plans(self) -> None:
        self.root.mkdir()
        original = "# Existing project rules\n"
        (self.root / "AGENTS.md").write_text(original, encoding="utf-8")

        result = run_script(
            "project_steward_scaffold.py",
            "--project-root",
            str(self.root),
            "--minimal",
            "--write",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), original)
        reports = self.root / "architecture_reports"
        self.assertFalse(reports.exists())


if __name__ == "__main__":
    unittest.main()
