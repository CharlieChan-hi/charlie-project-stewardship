from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "shared" / "scripts"
TEMPLATES_DIR = PLUGIN_ROOT / "shared" / "assets" / "templates"


class DocumentationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-doc-contract-")
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def intake(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "project_steward_intake.py"),
                "--project-root",
                str(self.root),
                *args,
            ],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_intake_write_without_answers_is_rejected(self) -> None:
        result = self.intake("--write")

        self.assertEqual(result.returncode, 2)
        self.assertIn("requires at least one confirmed intake answer", result.stderr)
        self.assertFalse((self.root / "docs" / "project_intake.md").exists())

    def test_default_questionnaire_does_not_inject_optional_tools(self) -> None:
        result = self.intake()

        self.assertEqual(result.returncode, 0, result.stderr)
        for product_name in ("Beads", "Serena", "RTK"):
            self.assertNotIn(product_name, result.stdout)

    def test_capability_routing_requires_explicit_disable_authority(self) -> None:
        text = (PLUGIN_ROOT / "skills" / "capability-routing" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Disable an installed adapter only when the user explicitly requests", text)
        self.assertNotIn("disable or ignore overlapping adapters", text)

    def test_compatibility_references_are_loaded_conditionally(self) -> None:
        cases = {
            "project-intake": "project-intake-and-recipes.md",
            "project-scaffold": "project-operating-system.md",
        }

        for skill_name, reference_name in cases.items():
            with self.subTest(skill=skill_name):
                text = (
                    PLUGIN_ROOT / "skills" / skill_name / "SKILL.md"
                ).read_text(encoding="utf-8")
                reference_line = next(
                    line for line in text.splitlines() if reference_name in line
                )
                self.assertIn("only when", reference_line)
                self.assertIn("skip it", reference_line)

    def test_readme_uses_portable_checkout_and_marketplace_discovery(self) -> None:
        text = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("$HOME/Desktop/SKILL", text)
        self.assertNotIn("charlie-project-stewardship@personal", text)
        self.assertIn("read_marketplace_name.py", text)
        self.assertIn("--marketplace-path", text)
        self.assertIn("codex plugin list --json", text)
        self.assertIn(
            "codex plugin marketplace add CharlieChan-hi/charlie-project-stewardship",
            text,
        )
        self.assertIn("$task-contract", text)
        self.assertIn("不是工作流引擎、项目操作系统或任务管理器", text)

    def test_maintenance_references_are_one_hop_from_agents_map(self) -> None:
        text = (PLUGIN_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("shared/references/platform-native-first.md", text)
        self.assertIn("shared/references/maintenance-quality-gates.md", text)

    def test_task_contract_is_conversation_first_and_has_stable_fields(self) -> None:
        skill_text = (
            PLUGIN_ROOT / "skills" / "task-contract" / "SKILL.md"
        ).read_text(encoding="utf-8")
        template_text = (
            PLUGIN_ROOT
            / "skills"
            / "task-contract"
            / "references"
            / "task-contract-template.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Return the contract in conversation by default", skill_text)
        self.assertIn("Persist it only when the user explicitly requests", skill_text)
        for field in (
            "mode:",
            "objective:",
            "allowed_paths:",
            "allowed_actions:",
            "non_goals:",
            "source_of_truth:",
            "derived_outputs:",
            "acceptance_tests:",
            "review_batch_size:",
            "stop_conditions:",
        ):
            self.assertIn(field, template_text)

    def test_plan_relay_continue_persists_recovery_state(self) -> None:
        text = (
            PLUGIN_ROOT / "skills" / "plan-relay" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("explicit continue or recover request", text)
        self.assertIn("do not stop after `status`", text)
        self.assertIn("mark the recovered next step `in-progress`", text)
        self.assertIn("record a blocking note", text)
        self.assertIn("explicitly requests a read-only recovery", text)

    def test_planning_templates_do_not_claim_audit_writes(self) -> None:
        for name in ("architecture-refactor-plan.md", "architecture-target-plan.md"):
            text = (
                PLUGIN_ROOT / "shared" / "assets" / "templates" / name
            ).read_text(encoding="utf-8")
            self.assertIn("project health audit remains read-only", text)
            self.assertNotIn("Generated or updated by architecture audit", text)

    def test_legacy_update_pointer_has_no_fake_global_path(self) -> None:
        text = (
            PLUGIN_ROOT
            / "shared"
            / "assets"
            / "templates"
            / "update-plan.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("stewardship_adoption_plan.md", text)
        self.assertIn("workflow-specific", text)

    def test_scaffolded_adr_is_explicitly_proposed_and_unconfirmed(self) -> None:
        text = (
            PLUGIN_ROOT
            / "shared"
            / "assets"
            / "templates"
            / "docs-decisions-0001-project-stewardship.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Status: Proposed", text)
        self.assertIn("Authority: Unconfirmed", text)
        self.assertIn("## Proposed decision", text)
        self.assertNotIn("\n## Decision\n", text)

    def test_minimal_templates_do_not_inject_optional_tools_or_forbidden_patterns(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "project_steward_scaffold.py"),
                "--project-root",
                str(self.root),
                "--minimal",
                "--write",
            ],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        intake = (self.root / "docs" / "project_intake.md").read_text(
            encoding="utf-8"
        )
        preferences = (self.root / "docs" / "project_preferences.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((agents, intake, preferences))
        self.assertEqual(
            sorted(
                path.relative_to(self.root).as_posix()
                for path in self.root.rglob("*")
                if path.is_file()
            ),
            ["AGENTS.md", "docs/project_intake.md", "docs/project_preferences.md"],
        )
        for product_name in ("Beads", "Serena", "RTK"):
            self.assertNotIn(product_name, combined)
        self.assertIn("## Forbidden patterns\n\n[需确认]", intake)
        confirmed = preferences.split("## Confirmed rules", 1)[1].split(
            "## Structured rules", 1
        )[0]
        self.assertIn("No confirmed rules recorded yet", confirmed)
        self.assertNotIn("## Bootstrap guidance (not user-confirmed)", preferences)
        self.assertNotIn("Follow the project's current conventions", confirmed)

    def test_minimal_template_contracts_preserve_project_facts_only(self) -> None:
        agents = (TEMPLATES_DIR / "AGENTS.md").read_text(encoding="utf-8")
        intake = (TEMPLATES_DIR / "docs-project_intake.md").read_text(
            encoding="utf-8"
        )
        preferences = (TEMPLATES_DIR / "docs-project_preferences.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((agents, intake, preferences))

        expected_placeholders = {
            "AGENTS.md": ("project_type", "stack_markers", "package_manager"),
            "docs-project_intake.md": (
                "project_name",
                "product_goal",
                "target_users",
                "platform",
                "project_type",
                "stack_markers",
                "package_manager",
                "source_structure_recipe",
                "ui_system",
                "architecture_preferences",
                "forbidden_patterns",
                "validation_expectations",
                "capability_suggestions",
            ),
        }
        template_text = {
            "AGENTS.md": agents,
            "docs-project_intake.md": intake,
        }
        for template_name, placeholders in expected_placeholders.items():
            with self.subTest(template=template_name):
                for placeholder in placeholders:
                    self.assertIn(f"[[{placeholder}]]", template_text[template_name])

        self.assertIn("## Project snapshot", agents)
        self.assertIn("## Task-scoped map", agents)
        invariants = agents.split("## Invariants", 1)[1].split("\n## ", 1)[0]
        for invariant_class in (
            "**Scope:**",
            "**Secrets:**",
            "**High-impact actions:**",
            "**Validation:**",
        ):
            self.assertIn(invariant_class, invariants)
        self.assertEqual(
            sum(line.startswith("- **") for line in invariants.splitlines()),
            4,
        )
        self.assertIn(
            "- **High-impact actions:** Obtain the user's confirmation before "
            "destructive or hard-to-reverse actions, external/shared-state changes, "
            "installs/upgrades, migrations, permission changes, publishing, or "
            "deployment.",
            invariants.splitlines(),
        )
        high_impact = next(
            line
            for line in invariants.splitlines()
            if line.startswith("- **High-impact actions:**")
        )
        for protected_boundary in (
            "hard-to-reverse",
            "external/shared-state",
            "installs/upgrades",
            "migrations",
            "permission changes",
            "publishing",
            "deployment",
        ):
            self.assertIn(protected_boundary, high_impact)

        self.assertIn("## Open questions", intake)
        preference_lines = preferences.splitlines()
        for heading in (
            "## Confirmed rules",
            "## Structured rules",
            "## Pending confirmation",
        ):
            self.assertEqual(preference_lines.count(heading), 1)
        for field in (
            "Rule ID:",
            "Kind:",
            "Rule:",
            "Category:",
            "Scope:",
            "Priority:",
            "Source or evidence:",
            "Exceptions:",
            "Detection:",
            "Validation:",
            "Last verified:",
            "Expiry:",
            "Invalidation:",
        ):
            self.assertIn(field, preferences)

        for generic_coaching in (
            "## Bootstrap guidance (not user-confirmed)",
            "### Agent behavior guidance",
            "### Optional integrations",
            "## Optional capabilities",
            "Follow the project's current conventions",
            "current official guidance",
            "Never claim completion from assumptions",
            "Suggestions are optional",
        ):
            self.assertNotIn(generic_coaching, combined)


if __name__ == "__main__":
    unittest.main()
