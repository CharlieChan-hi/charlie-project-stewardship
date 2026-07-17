from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "shared" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_stewardship_plugin import (
    resolve_system_skills_dir,
    validate_metadata_contracts,
)


class MetadataContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-metadata-")
        self.root = Path(self.temp_dir.name) / "plugin"
        (self.root / ".codex-plugin").mkdir(parents=True)
        (self.root / ".claude-plugin").mkdir(parents=True)
        shutil.copy2(
            PLUGIN_ROOT / ".codex-plugin" / "plugin.json",
            self.root / ".codex-plugin" / "plugin.json",
        )
        shutil.copy2(
            PLUGIN_ROOT / ".claude-plugin" / "plugin.json",
            self.root / ".claude-plugin" / "plugin.json",
        )
        (self.root / ".agents" / "plugins").mkdir(parents=True)
        shutil.copy2(
            PLUGIN_ROOT / ".agents" / "plugins" / "marketplace.json",
            self.root / ".agents" / "plugins" / "marketplace.json",
        )
        shutil.copy2(PLUGIN_ROOT / "LICENSE", self.root / "LICENSE")
        shutil.copytree(PLUGIN_ROOT / "skills", self.root / "skills")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def manifest(self, host: str) -> tuple[Path, dict[str, object]]:
        path = self.root / f".{host}-plugin" / "plugin.json"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def write_manifest(self, host: str, payload: dict[str, object]) -> None:
        path = self.root / f".{host}-plugin" / "plugin.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_current_metadata_contracts_pass(self) -> None:
        self.assertEqual(validate_metadata_contracts(self.root), [])

    def test_validator_respects_codex_home(self) -> None:
        custom_home = self.root / "custom-codex-home"

        resolved = resolve_system_skills_dir({"CODEX_HOME": str(custom_home)})

        self.assertEqual(resolved, custom_home / "skills" / ".system")

    def test_manifest_base_version_mismatch_is_rejected(self) -> None:
        _, claude = self.manifest("claude")
        claude["version"] = "9.9.9"
        self.write_manifest("claude", claude)

        errors = validate_metadata_contracts(self.root)

        self.assertTrue(any("same base SemVer" in item for item in errors), errors)

    def test_non_codex_build_suffix_and_too_many_prompts_are_rejected(self) -> None:
        _, codex = self.manifest("codex")
        codex["version"] = "1.1.0+custom.1"
        codex["interface"]["defaultPrompt"] = ["one", "two", "three", "four"]
        self.write_manifest("codex", codex)

        errors = validate_metadata_contracts(self.root)

        self.assertTrue(any("optional +codex.* suffix" in item for item in errors), errors)
        self.assertTrue(any("at most 3 prompts" in item for item in errors), errors)

    def test_cross_manifest_identity_mismatch_is_rejected(self) -> None:
        _, claude = self.manifest("claude")
        claude["description"] = "Drifted description"
        self.write_manifest("claude", claude)

        errors = validate_metadata_contracts(self.root)

        self.assertTrue(any("field `description`" in item for item in errors), errors)

    def test_public_release_metadata_drift_is_rejected(self) -> None:
        marketplace_path = self.root / ".agents" / "plugins" / "marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["source"]["ref"] = "unreviewed-branch"
        marketplace_path.write_text(
            json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _, codex = self.manifest("codex")
        codex["license"] = "Apache-2.0"
        self.write_manifest("codex", codex)

        errors = validate_metadata_contracts(self.root)

        self.assertTrue(any("MIT license" in item for item in errors), errors)
        self.assertTrue(any("main Git repository root" in item for item in errors), errors)

    def test_openai_prompt_and_description_contracts_are_rejected(self) -> None:
        metadata = self.root / "skills" / "project-health" / "agents" / "openai.yaml"
        text = metadata.read_text(encoding="utf-8")
        text = text.replace(
            'short_description: "Audit project health and choose risk-based validation"',
            'short_description: "Too short"',
        ).replace(
            'default_prompt: "Use $project-health',
            'default_prompt: "Use this skill',
        )
        metadata.write_text(text, encoding="utf-8")

        errors = validate_metadata_contracts(self.root)

        self.assertTrue(any("short_description" in item for item in errors), errors)
        self.assertTrue(any("$project-health" in item for item in errors), errors)

    def test_implicit_routing_contract_is_enforced(self) -> None:
        core = self.root / "skills" / "task-contract" / "agents" / "openai.yaml"
        core.write_text(
            core.read_text(encoding="utf-8").replace(
                "allow_implicit_invocation: true",
                "allow_implicit_invocation: false",
            ),
            encoding="utf-8",
        )
        compatibility = (
            self.root / "skills" / "architecture-audit" / "agents" / "openai.yaml"
        )
        compatibility.write_text(
            compatibility.read_text(encoding="utf-8").replace(
                "allow_implicit_invocation: false",
                "allow_implicit_invocation: true",
            ),
            encoding="utf-8",
        )

        errors = validate_metadata_contracts(self.root)

        self.assertTrue(any("Core skill `task-contract`" in item for item in errors), errors)
        self.assertTrue(any("`architecture-audit` must be explicit-only" in item for item in errors), errors)

    def test_skill_directory_must_match_frontmatter_name(self) -> None:
        original = self.root / "skills" / "project-health"
        mismatched = self.root / "skills" / "health-shadow"
        original.rename(mismatched)

        errors = validate_metadata_contracts(self.root)

        self.assertTrue(
            any(
                "directory `health-shadow` must match frontmatter name `project-health`"
                in item
                for item in errors
            ),
            errors,
        )

    def test_duplicate_skill_frontmatter_names_are_rejected(self) -> None:
        shutil.copytree(
            self.root / "skills" / "project-health",
            self.root / "skills" / "health-shadow",
        )

        errors = validate_metadata_contracts(self.root)

        self.assertTrue(
            any(
                "Duplicate skill frontmatter name `project-health`" in item
                for item in errors
            ),
            errors,
        )

    def test_display_names_must_be_non_empty_and_case_insensitively_unique(self) -> None:
        health = self.root / "skills" / "project-health" / "agents" / "openai.yaml"
        memory = self.root / "skills" / "project-memory" / "agents" / "openai.yaml"
        health_text = health.read_text(encoding="utf-8")
        memory_text = memory.read_text(encoding="utf-8")

        with self.subTest("non-empty"):
            health.write_text(
                health_text.replace(
                    'display_name: "Project Health"',
                    'display_name: "   "',
                ),
                encoding="utf-8",
            )
            errors = validate_metadata_contracts(self.root)
            self.assertTrue(
                any(
                    "`project-health` display_name must be a non-empty string" in item
                    for item in errors
                ),
                errors,
            )

        health.write_text(health_text, encoding="utf-8")
        with self.subTest("case-insensitive uniqueness"):
            memory.write_text(
                memory_text.replace(
                    'display_name: "Project Memory"',
                    'display_name: "pRoJeCt HeAlTh"',
                ),
                encoding="utf-8",
            )
            errors = validate_metadata_contracts(self.root)
            self.assertTrue(
                any(
                    "display_name `pRoJeCt HeAlTh` duplicates skill `project-health`"
                    in item
                    for item in errors
                ),
                errors,
            )


if __name__ == "__main__":
    unittest.main()
