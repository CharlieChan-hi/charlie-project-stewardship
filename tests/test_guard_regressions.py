from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "shared" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import project_steward_guard as guard
from project_steward_templates import ConcurrentModificationError


class GuardPlanRaceRegressionTests(unittest.TestCase):
    def test_guard_and_embedded_audit_share_the_current_schema_major(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-guard-") as temp_dir:
            payload = guard.build_guard(
                Path(temp_dir),
                max_lines=450,
                acceptance_status="not-required",
            )

        self.assertEqual(payload["schema_version"], "3.0")
        self.assertEqual(payload["audit"]["schema_version"], "3.0")

    def test_disappearing_plan_is_reported_as_malformed_without_aborting_guard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-guard-") as temp_dir:
            root = Path(temp_dir)
            plan_path = root / "plans" / "active" / "vanished.md"

            with mock.patch.object(
                guard,
                "iter_active_plans",
                return_value=[plan_path],
            ), mock.patch.object(
                guard,
                "read_plan",
                side_effect=ConcurrentModificationError("plan vanished"),
            ):
                plans, malformed = guard.inspect_active_plans(root)

            self.assertEqual(plans, [])
            self.assertEqual(len(malformed), 1)
            self.assertEqual(malformed[0]["path"], "plans/active/vanished.md")
            self.assertEqual(
                malformed[0]["error_type"],
                "ConcurrentModificationError",
            )


class GuardSecretBoundaryRegressionTests(unittest.TestCase):
    def test_programmatic_inputs_reject_secrets_without_echoing_raw_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-guard-secret-") as temp_dir:
            root = Path(temp_dir)
            cases = (
                (
                    "current_plan",
                    lambda value: guard.build_guard(
                        root,
                        450,
                        current_plan=value,
                    ),
                ),
                (
                    "changed_path",
                    lambda value: guard.build_guard(
                        root,
                        450,
                        changed_paths=[value],
                    ),
                ),
                (
                    "validation_name",
                    lambda value: guard.build_guard(
                        root,
                        450,
                        validation_results={value: "pass"},
                    ),
                ),
                (
                    "validation_value",
                    lambda value: guard.build_guard(
                        root,
                        450,
                        validation_results={"tests": value},
                    ),
                ),
                (
                    "required_validation",
                    lambda value: guard.build_guard(
                        root,
                        450,
                        required_validations=[value],
                    ),
                ),
                (
                    "acceptance_status",
                    lambda value: guard.build_guard(
                        root,
                        450,
                        acceptance_status=value,
                    ),
                ),
                (
                    "validation_raw",
                    lambda value: guard.parse_validation_results([value]),
                ),
            )

            for index, (label, invoke) in enumerate(cases, start=1):
                marker = f"synthetic-guard-{label}-marker-{index:03d}"
                secret = f"SERVICE_API_KEY={marker}"
                with self.subTest(label=label):
                    with self.assertRaises(ValueError) as caught:
                        invoke(secret)
                    self.assertNotIn(marker, str(caught.exception))

    def test_active_plan_report_fields_reject_secrets_without_echo(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-guard-plan-") as temp_dir:
            root = Path(temp_dir)
            normal_path = root / "plans" / "active" / "manual.md"

            for index, field in enumerate(
                ("path", "title", "plan_id", "next_step"),
                start=1,
            ):
                marker = f"synthetic-active-plan-{field}-marker-{index:03d}"
                secret = f"SERVICE_API_KEY={marker}"
                path = (
                    root / "plans" / "active" / f"{secret}.md"
                    if field == "path"
                    else normal_path
                )
                plan = {
                    "title": secret if field == "title" else "Manual plan",
                    "plan_id": secret if field == "plan_id" else "manual-plan",
                    "summary": {"done": 0, "total": 1},
                    "next_step": {
                        "text": secret if field == "next_step" else "Run tests"
                    },
                }

                with self.subTest(field=field), mock.patch.object(
                    guard,
                    "iter_active_plans",
                    return_value=[path],
                ), mock.patch.object(
                    guard,
                    "read_plan",
                    return_value=plan,
                ):
                    with self.assertRaises(ValueError) as caught:
                        guard.inspect_active_plans(root)
                    self.assertNotIn(marker, str(caught.exception))

    def test_cli_rejects_secrets_for_json_markdown_dry_run_and_write(self) -> None:
        cases = (
            ("markdown-dry-run", "markdown", False, "--current-plan"),
            ("json-dry-run", "json", False, "--changed-path"),
            ("markdown-write", "markdown", True, "--validation-result"),
            ("json-write", "json", True, "--require-validation"),
        )

        for index, (label, output_format, write, option) in enumerate(cases, start=1):
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="stewardship-guard-cli-secret-"
            ) as temp_dir:
                root = Path(temp_dir)
                marker = f"synthetic-guard-cli-{label}-marker-{index:03d}"
                arguments = [
                    "--project-root",
                    str(root),
                    "--format",
                    output_format,
                    option,
                    f"SERVICE_API_KEY={marker}",
                ]
                if write:
                    arguments.append("--write")

                result = self.run_guard(*arguments)

                self.assert_rejected_without_report(result, root, marker)

    def test_cli_prescan_prevents_argparse_choice_error_from_echoing_secret(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-guard-choice-") as temp_dir:
            root = Path(temp_dir)
            marker = "synthetic-guard-format-choice-marker-801"
            result = self.run_guard(
                "--project-root",
                str(root),
                "--format",
                f"SERVICE_API_KEY={marker}",
                "--write",
            )

            self.assert_rejected_without_report(result, root, marker)

    def test_hand_authored_plan_with_secret_is_rejected_without_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-guard-manual-plan-") as temp_dir:
            root = Path(temp_dir)
            plan_dir = root / "plans" / "active"
            plan_dir.mkdir(parents=True)
            marker = "synthetic-guard-manual-plan-marker-902"
            plan_path = plan_dir / "manual.md"
            plan_path.write_text(
                "---\n"
                'plan_id: "manual"\n'
                f'title: "Deploy with SERVICE_API_KEY={marker}"\n'
                "status: active\n"
                "---\n\n"
                "# Manual plan\n\n"
                "## 步骤\n\n"
                "- [ ] [S001] Run tests\n",
                encoding="utf-8",
            )

            result = self.run_guard(
                "--project-root",
                str(root),
                "--format",
                "json",
                "--write",
            )

            self.assert_rejected_without_report(result, root, marker)
            self.assertTrue(plan_path.is_file())

    def test_main_converts_build_and_write_runtime_errors_to_parser_errors(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-guard-runtime-") as temp_dir:
            root = Path(temp_dir)
            cases = (
                ("build", False, "build_guard"),
                ("write", True, "atomic_write_text"),
            )

            for label, write, target in cases:
                argv = [
                    "project_steward_guard.py",
                    "--project-root",
                    str(root),
                    "--acceptance-status",
                    "not-required",
                ]
                if write:
                    argv.append("--write")
                stdout = io.StringIO()
                stderr = io.StringIO()
                with self.subTest(label=label), mock.patch.object(
                    sys,
                    "argv",
                    argv,
                ), mock.patch.object(
                    guard,
                    target,
                    side_effect=RuntimeError("synthetic unsupported runtime primitive"),
                ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as caught:
                        guard.main()

                self.assertEqual(caught.exception.code, 2)
                self.assertNotIn("Traceback", stderr.getvalue())
                self.assertFalse(self.report_path(root, "markdown").exists())

    @staticmethod
    def report_path(root: Path, output_format: str) -> Path:
        suffix = "json" if output_format == "json" else "md"
        return (
            root
            / "architecture_reports"
            / "latest"
            / f"completion_guard_report.{suffix}"
        )

    def assert_rejected_without_report(
        self,
        result: subprocess.CompletedProcess[str],
        root: Path,
        marker: str,
    ) -> None:
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(marker, result.stdout)
        self.assertNotIn(marker, result.stderr)
        self.assertFalse(self.report_path(root, "markdown").exists())
        self.assertFalse(self.report_path(root, "json").exists())

    @staticmethod
    def run_guard(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "project_steward_guard.py"),
                *arguments,
            ],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
