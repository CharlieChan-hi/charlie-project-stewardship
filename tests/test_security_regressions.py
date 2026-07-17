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
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from project_steward_audit import build_audit, is_env_file_name, is_secret_file_name
from project_steward_templates import contains_high_confidence_secret, is_placeholder_value


class SecretValueRegressionTests(unittest.TestCase):
    def test_only_pure_variable_references_are_safe_placeholders(self) -> None:
        safe_references = (
            "${SERVICE_API_KEY}",
            "{{ SERVICE_API_KEY }}",
            "{{ secrets.SERVICE_API_KEY }}",
            "${供应商_API_KEY}",
        )
        expression_like_references = (
            "${API_KEY:-synthetic-placeholder-default-101}",
            "${API_KEY:=synthetic-placeholder-assignment-102}",
            "${API_KEY-synthetic-placeholder-fallback-103}",
            "{{ API_KEY | default: 'synthetic-placeholder-filter-104' }}",
            "{{ API_KEY + 'synthetic-placeholder-expression-105' }}",
        )

        for value in safe_references:
            with self.subTest(safe=value):
                self.assertTrue(is_placeholder_value(value))
        for value in expression_like_references:
            with self.subTest(rejected=value):
                self.assertFalse(is_placeholder_value(value))

    def test_expression_like_secret_placeholders_are_rejected(self) -> None:
        sensitive_assignments = (
            "SERVICE_API_KEY=${SERVICE_API_KEY:-synthetic-default-value-201}",
            "SERVICE_SECRET_KEY=${SERVICE_SECRET_KEY:=synthetic-assignment-value-202}",
            "VENDOR_TOKEN=${VENDOR_TOKEN-synthetic-fallback-value-203}",
            'DATABASE_URL="{{ DATABASE_URL | default: \'synthetic-filter-value-204\' }}"',
            'AUTHORIZATION="{{ TOKEN + \'synthetic-expression-value-205\' }}"',
        )

        for value in sensitive_assignments:
            with self.subTest(value=value):
                self.assertTrue(contains_high_confidence_secret(value))

    def test_vendor_and_environment_prefixed_secret_assignments_are_rejected(self) -> None:
        sensitive_assignments = (
            "SERVICE_API_KEY=synthetic-regression-value-001",
            "AWS_SECRET_ACCESS_KEY=synthetic-regression-value-002",
            "PROD_SECRET_KEY: synthetic-regression-value-003",
            "services.vendor.DATABASE_URL=synthetic-regression-value-004",
            "ACME_TOKEN=synthetic-regression-value-005",
            '"VENDOR_REFRESH_TOKEN": "synthetic-regression-value-006"',
            "serviceClientSecret=synthetic-regression-value-007",
            'command="SERVICE_API_KEY=synthetic-regression-value-008 deploy"',
            "供应商_API_KEY=synthetic-regression-value-009",
        )

        for value in sensitive_assignments:
            with self.subTest(value=value):
                self.assertTrue(contains_high_confidence_secret(value))

    def test_prefixed_secret_assignments_keep_safe_sentinel_behavior(self) -> None:
        safe_assignments = (
            "SERVICE_API_KEY=${SERVICE_API_KEY}",
            "AWS_SECRET_ACCESS_KEY=synthetic-sentinel",
            "PROD_SECRET_KEY=redacted",
            "services.vendor.DATABASE_URL=placeholder",
            "ACME_TOKEN=synthetic",
            '"VENDOR_REFRESH_TOKEN": "example"',
            "SERVICE_TOKEN=github_pat_SYNTHETIC_SENTINEL_VALUE_000000000000",
            "VENDOR_AUTHORIZATION=Bearer synthetic-sentinel",
            'command="SERVICE_API_KEY=${SERVICE_API_KEY} deploy"',
            "供应商_API_KEY=${供应商_API_KEY}",
            'SERVICE_TOKEN="{{ secrets.SERVICE_TOKEN }}"',
        )

        for value in safe_assignments:
            with self.subTest(value=value):
                self.assertFalse(contains_high_confidence_secret(value))

    def test_non_secret_assignment_names_are_not_reclassified(self) -> None:
        ordinary_assignments = (
            "max_tokens=4096",
            "token_count=12",
            "database_url_template=example",
            "api_key_name=SERVICE_API_KEY",
        )

        for value in ordinary_assignments:
            with self.subTest(value=value):
                self.assertFalse(contains_high_confidence_secret(value))

    def test_fine_grained_github_pat_and_other_provider_tokens_are_rejected(self) -> None:
        high_confidence_values = (
            "github_pat_" + "A1_b" * 12,
            "glpat-" + "A1_b" * 6,
            "npm_" + "A1b2" * 9,
            "pypi-AgEIcHlwaS5vcmcC" + "A1_b" * 6,
            "AIza" + "A1_b" * 8 + "A1b",
        )

        for value in high_confidence_values:
            with self.subTest(prefix=value.split("_", 1)[0]):
                self.assertTrue(contains_high_confidence_secret(value))

    def test_provider_shaped_placeholders_and_synthetic_sentinels_are_allowed(self) -> None:
        safe_values = (
            "token=github_pat_placeholder",
            "token=github_pat_SYNTHETIC_SENTINEL_VALUE_000000000000",
            "authorization=Bearer synthetic-sentinel",
            "token=glpat-redacted",
            "token=npm_example",
            "AKIAIOSFODNN7EXAMPLE",
            "API_KEY=${API_KEY}",
        )

        for value in safe_values:
            with self.subTest(value=value):
                self.assertFalse(contains_high_confidence_secret(value))

    def test_sentinel_words_do_not_make_arbitrary_assigned_values_safe(self) -> None:
        self.assertTrue(
            contains_high_confidence_secret("API_KEY=synthetic-test-value-12345")
        )
        self.assertTrue(
            contains_high_confidence_secret("token=github_pat_not-a-placeholder-secret")
        )


class SecretPersistenceRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="stewardship-prefixed-secret-persistence-"
        )
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_script(self, name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / name), *arguments],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_marker_not_exposed(
        self,
        result: subprocess.CompletedProcess[str],
        marker: str,
    ) -> None:
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(marker, result.stdout)
        self.assertNotIn(marker, result.stderr)

    def test_memory_rejects_prefixed_secret_without_echo_or_write(self) -> None:
        marker = "synthetic-memory-credential-value-84721"
        result = self.run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "prefixed-secret-regression",
            "--rule",
            f"Use SERVICE_API_KEY={marker} for the deployment.",
            "--write",
        )

        self.assert_marker_not_exposed(result, marker)
        self.assertFalse((self.root / "docs" / "project_preferences.md").exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_plan_rejects_prefixed_secret_without_echo_or_write(self) -> None:
        marker = "synthetic-plan-credential-value-39518"
        result = self.run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "new",
            "--title",
            f"Deploy with ACME_TOKEN={marker}",
            "--step",
            "Run the deployment",
            "--write",
        )

        self.assert_marker_not_exposed(result, marker)
        self.assertFalse((self.root / "plans").exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_memory_rejects_placeholder_default_without_echo_or_write(self) -> None:
        marker = "synthetic-memory-placeholder-default-58319"
        expression = "${SERVICE_API_KEY:-" + marker + "}"
        result = self.run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "placeholder-default-regression",
            "--rule",
            f"Use SERVICE_API_KEY={expression} for the deployment.",
            "--write",
        )

        self.assert_marker_not_exposed(result, marker)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_plan_rejects_template_filter_without_echo_or_write(self) -> None:
        marker = "synthetic-plan-placeholder-filter-62407"
        expression = "{{ VENDOR_TOKEN | default: '" + marker + "' }}"
        result = self.run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "new",
            "--title",
            f'Deploy with VENDOR_TOKEN="{expression}"',
            "--step",
            "Run the deployment",
            "--write",
        )

        self.assert_marker_not_exposed(result, marker)
        self.assertEqual(list(self.root.iterdir()), [])


class SecretFilenameRegressionTests(unittest.TestCase):
    def test_secret_capable_names_are_case_insensitive(self) -> None:
        for name in (".ENV", ".Env.Local", ".NPMRC", ".PyPiRc"):
            with self.subTest(name=name):
                self.assertTrue(is_secret_file_name(name))

    def test_example_sample_and_template_suffixes_are_case_insensitive(self) -> None:
        safe_names = (
            ".ENV.EXAMPLE",
            ".env.production.Sample",
            ".Env.Staging.TEMPLATE",
            ".NPMRC.example",
            ".PYPIRC.TEMPLATE",
        )
        for name in safe_names:
            with self.subTest(name=name):
                self.assertFalse(is_secret_file_name(name))
                self.assertFalse(is_env_file_name(name))

        self.assertTrue(is_env_file_name(".ENV.EXAMPLE.SECRET"))

    def test_audit_inventories_uppercase_names_without_reading_contents(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-secret-case-") as temp_dir:
            root = Path(temp_dir)
            marker = "SYNTHETIC_SECRET_CONTENT_MUST_NOT_APPEAR"
            (root / ".ENV").write_text(marker, encoding="utf-8")
            (root / ".NPMRC").write_text(marker, encoding="utf-8")

            report = build_audit(root, max_lines=450)

            self.assertEqual(
                report["secrets"]["secret_like_files_present"],
                [".ENV", ".NPMRC"],
            )
            self.assertEqual(report["secrets"]["env_files_present"], [".ENV"])
            self.assertFalse(report["secrets"]["contents_read"])
            self.assertNotIn(marker, json.dumps(report, ensure_ascii=False))

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_git_inventory_finds_uppercase_names_in_skipped_directories(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-secret-git-") as temp_dir:
            root = Path(temp_dir)
            generated = root / "dist"
            generated.mkdir()
            (generated / ".ENV").write_text("placeholder", encoding="utf-8")
            (generated / ".NPMRC").write_text("placeholder", encoding="utf-8")
            (root / ".gitignore").write_text("dist/\n", encoding="utf-8")
            initialized = subprocess.run(
                ["git", "init", "-q", str(root)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            tracked = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "add",
                    ".gitignore",
                    "-f",
                    "dist/.ENV",
                    "dist/.NPMRC",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(tracked.returncode, 0, tracked.stderr)

            report = build_audit(root, max_lines=450)

            self.assertEqual(
                report["secrets"]["secret_like_files_present"],
                ["dist/.ENV", "dist/.NPMRC"],
            )


if __name__ == "__main__":
    unittest.main()
