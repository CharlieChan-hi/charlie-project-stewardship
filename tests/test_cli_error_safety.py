from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import os
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

import project_steward_fs as fs
import project_steward_guard as guard
import project_steward_intake as intake
import project_steward_memory as memory
import project_steward_plan as plan
import project_steward_recipes as recipes
import project_steward_scaffold as scaffold
from project_steward_cli import parse_args_safely, safe_error_text


def run_script(name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / name), *arguments],
        cwd=str(PLUGIN_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def tree_snapshot(root: Path) -> list[tuple[str, str, bytes | None]]:
    snapshot: list[tuple[str, str, bytes | None]] = []
    if not root.exists():
        return snapshot
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_file():
            snapshot.append((relative, "file", path.read_bytes()))
        elif path.is_dir():
            snapshot.append((relative, "dir", None))
        else:
            snapshot.append((relative, "other", None))
    return snapshot


class CliArgumentSafetyTests(unittest.TestCase):
    def test_every_public_cli_prescans_secret_bearing_argv(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-cli-argv-") as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            marker = "synthetic-cli-argv-marker-48157"
            secret = f"SERVICE_API_KEY={marker}"
            cases = (
                (
                    "project_steward_plan.py",
                    ("--project-root", str(root), "--format", secret, "status"),
                ),
                (
                    "project_steward_memory.py",
                    ("--project-root", str(root), "--rule", "Keep scope narrow", "--priority", secret),
                ),
                (
                    "project_steward_audit.py",
                    ("--project-root", str(root), "--format", secret),
                ),
                (
                    "project_steward_intake.py",
                    ("--project-root", str(root), "--unknown", secret),
                ),
                (
                    "project_steward_scaffold.py",
                    ("--project-root", str(root / secret)),
                ),
                (
                    "project_steward_recipes.py",
                    ("--project-root", str(root), "--recipe", secret),
                ),
                (
                    "project_steward_guard.py",
                    ("--project-root", str(root), "--acceptance-status", secret),
                ),
                (
                    "validate_stewardship_plugin.py",
                    ("--unknown", secret),
                ),
            )

            for script, arguments in cases:
                with self.subTest(script=script):
                    before = tree_snapshot(root)
                    result = run_script(script, *arguments)
                    self.assertEqual(result.returncode, 2)
                    self.assertNotIn(marker, result.stdout)
                    self.assertNotIn(marker, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(tree_snapshot(root), before)

    def test_split_secret_assignments_are_rejected_before_argparse_echoes_tail_tokens(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-cli-split-argv-") as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            marker = "synthetic-cli-split-marker-59247"
            split_forms = (
                ("SERVICE_API_KEY", "=", marker),
                ("SERVICE_API_KEY=", marker),
                ("SERVICE_API_KEY", f"={marker}"),
            )

            for arguments in split_forms:
                with self.subTest(arguments=len(arguments)):
                    before = tree_snapshot(root)
                    result = run_script(
                        "project_steward_audit.py",
                        "--project-root",
                        str(root),
                        "--format",
                        "markdown",
                        *arguments,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertNotIn(marker, result.stdout)
                    self.assertNotIn(marker, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(tree_snapshot(root), before)

    def test_safe_sentinel_argv_and_safe_error_fallback(self) -> None:
        parser = argparse.ArgumentParser(prog="sentinel-test")
        parser.add_argument("--value")
        parsed = parse_args_safely(
            parser,
            ["--value", "SERVICE_API_KEY=redacted"],
        )
        self.assertEqual(parsed.value, "SERVICE_API_KEY=redacted")

        split_parser = argparse.ArgumentParser(prog="split-sentinel-test")
        split_parser.add_argument("parts", nargs="*")
        for safe_parts in (
            ["SERVICE_API_KEY", "=", "redacted"],
            ["SERVICE_API_KEY=", "synthetic-sentinel"],
            ["SERVICE_API_KEY", "=${SERVICE_API_KEY}"],
        ):
            with self.subTest(safe_parts=len(safe_parts)):
                split = parse_args_safely(split_parser, safe_parts)
                self.assertEqual(split.parts, safe_parts)

        marker = "synthetic-cli-error-marker-82461"
        rendered = safe_error_text(RuntimeError(f"SERVICE_API_KEY={marker}"))
        self.assertNotIn(marker, rendered)
        self.assertIn("details were withheld", rendered)


class ExternalPlanSecretBoundaryTests(unittest.TestCase):
    @staticmethod
    def plan_text(field: str, secret: str) -> str:
        title = secret if field == "title" else "Manual plan"
        plan_id = secret if field == "plan_id" else "manual-plan"
        updated_by = secret if field == "last_updated_by" else "test-machine"
        step = secret if field == "step" else "Complete validation"
        hidden = secret if field == "hidden_body" else "No hidden issue"
        return (
            "---\n"
            f"plan_id: {plan_id}\n"
            f"title: {title}\n"
            "status: active\n"
            f"last_updated_by: {updated_by}\n"
            "last_updated_at: 2026-07-17T00:00:00\n"
            "current_step: none\n"
            "---\n\n"
            f"# {title}\n\n"
            "## 步骤\n\n"
            f"- [x] [S001] {step}\n\n"
            "## 交接笔记\n\n"
            f"- {hidden}\n"
        )

    def test_all_plan_commands_reject_external_secret_carriers_without_echo_or_write(self) -> None:
        cases = (
            ("status-markdown", "title", ("status",)),
            ("status-json", "plan_id", ("--format", "json", "status")),
            (
                "check-dry-run",
                "step",
                ("check", "--plan", "manual.md", "--step", "S001", "--mark", "todo"),
            ),
            (
                "check-write",
                "last_updated_by",
                ("check", "--plan", "manual.md", "--step", "S001", "--write"),
            ),
            (
                "note-dry-run",
                "hidden_body",
                ("note", "--plan", "manual.md", "--text", "Safe note"),
            ),
            (
                "note-write",
                "title",
                ("note", "--plan", "manual.md", "--text", "Safe note", "--write"),
            ),
            (
                "finish-dry-run",
                "hidden_body",
                ("finish", "--plan", "manual.md"),
            ),
            (
                "finish-write",
                "step",
                ("finish", "--plan", "manual.md", "--write"),
            ),
        )

        for index, (label, field, command) in enumerate(cases, start=1):
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="stewardship-plan-carrier-"
            ) as temp_dir:
                root = Path(temp_dir) / "project"
                active = root / "plans" / "active"
                active.mkdir(parents=True)
                marker = f"synthetic-plan-carrier-{label}-{index:03d}"
                secret = f"SERVICE_API_KEY={marker}"
                source = active / "manual.md"
                source.write_text(self.plan_text(field, secret), encoding="utf-8")
                lock_digest = hashlib.sha256(
                    os.path.normcase(str(root.resolve())).encode("utf-8")
                ).hexdigest()[:24]
                lock_path = Path(tempfile.gettempdir()) / f"charlie-project-steward-{lock_digest}.lock"
                self.assertFalse(lock_path.exists())
                before = tree_snapshot(root)

                result = run_script(
                    "project_steward_plan.py",
                    "--project-root",
                    str(root),
                    *command,
                )

                self.assertEqual(result.returncode, 2)
                self.assertNotIn(marker, result.stdout)
                self.assertNotIn(marker, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(tree_snapshot(root), before)
                self.assertFalse(lock_path.exists())

    def test_secret_filename_and_later_invalid_plan_do_not_leak_partial_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-plan-filename-") as temp_dir:
            root = Path(temp_dir) / "project"
            active = root / "plans" / "active"
            active.mkdir(parents=True)
            (active / "a-safe.md").write_text(
                self.plan_text("safe", "unused"),
                encoding="utf-8",
            )
            marker = "synthetic-plan-filename-marker-71935"
            secret = f"SERVICE_API_KEY={marker}"
            (active / f"z-{secret}.md").write_text(
                self.plan_text("safe", "unused"),
                encoding="utf-8",
            )
            before = tree_snapshot(root)

            result = run_script(
                "project_steward_plan.py",
                "--project-root",
                str(root),
                "status",
            )

            self.assertEqual(result.returncode, 2)
            self.assertNotIn(marker, result.stdout)
            self.assertNotIn(marker, result.stderr)
            self.assertNotIn("# 活动计划状态", result.stdout)
            self.assertEqual(tree_snapshot(root), before)


class MutationCapabilityPreflightTests(unittest.TestCase):
    def invoke_main(self, module: object, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                result = module.main()
            except SystemExit as exc:
                result = int(exc.code)
        return int(result), stdout.getvalue(), stderr.getvalue()

    def test_project_lock_preflights_write_and_archive_before_temp_access(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stewardship-lock-preflight-") as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            with mock.patch.object(
                fs,
                "_secure_dirfd_available",
                return_value=False,
            ), mock.patch.object(
                fs.tempfile,
                "gettempdir",
                side_effect=AssertionError("temporary lock path was consulted"),
            ):
                with self.assertRaisesRegex(RuntimeError, "descriptor-anchored"):
                    with fs.project_lock(root):
                        self.fail("unsupported writer entered the lock")

            with mock.patch.object(
                fs,
                "_secure_archive_available",
                return_value=False,
            ), mock.patch.object(
                fs.tempfile,
                "gettempdir",
                side_effect=AssertionError("temporary archive lock path was consulted"),
            ):
                with self.assertRaisesRegex(RuntimeError, "descriptor-anchored"):
                    with fs.project_lock(root, required_capability="archive"):
                        self.fail("unsupported archiver entered the lock")

    def test_all_write_clis_fail_before_lock_artifacts_on_non_dirfd_runtime(self) -> None:
        cases = (
            (
                "scaffold",
                scaffold,
                lambda root: ["project_steward_scaffold.py", "--project-root", str(root), "--minimal", "--write"],
            ),
            (
                "intake",
                intake,
                lambda root: [
                    "project_steward_intake.py",
                    "--project-root",
                    str(root),
                    "--product-goal",
                    "Validate capability preflight",
                    "--write",
                ],
            ),
            (
                "recipe",
                recipes,
                lambda root: [
                    "project_steward_recipes.py",
                    "--project-root",
                    str(root),
                    "--recipe",
                    "backend-api",
                    "--write",
                ],
            ),
            (
                "memory",
                memory,
                lambda root: [
                    "project_steward_memory.py",
                    "--project-root",
                    str(root),
                    "--rule",
                    "Keep persistence fail-closed",
                    "--write",
                ],
            ),
            (
                "guard",
                guard,
                lambda root: [
                    "project_steward_guard.py",
                    "--project-root",
                    str(root),
                    "--acceptance-status",
                    "not-required",
                    "--write",
                ],
            ),
            (
                "plan-new",
                plan,
                lambda root: [
                    "project_steward_plan.py",
                    "--project-root",
                    str(root),
                    "new",
                    "--title",
                    "Capability preflight",
                    "--write",
                ],
            ),
        )

        for label, module, arguments in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="stewardship-write-preflight-"
            ) as temp_dir:
                root = Path(temp_dir) / "project"
                root.mkdir()
                before = tree_snapshot(root)
                with mock.patch.object(
                    fs,
                    "_secure_dirfd_available",
                    return_value=False,
                ), mock.patch.object(
                    fs.tempfile,
                    "gettempdir",
                    side_effect=AssertionError("temporary lock path was consulted"),
                ):
                    code, _stdout, stderr = self.invoke_main(module, arguments(root))
                self.assertEqual(code, 2)
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(tree_snapshot(root), before)

    def test_plan_update_and_archive_commands_share_the_same_preflight(self) -> None:
        commands = (
            ("check", ["check", "--plan", "manual.md", "--step", "S001", "--write"]),
            ("note", ["note", "--plan", "manual.md", "--text", "Safe note", "--write"]),
            ("finish", ["finish", "--plan", "manual.md", "--write"]),
        )
        safe_plan = ExternalPlanSecretBoundaryTests.plan_text("safe", "unused")

        for label, command in commands:
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="stewardship-plan-preflight-"
            ) as temp_dir:
                root = Path(temp_dir) / "project"
                source = root / "plans" / "active" / "manual.md"
                source.parent.mkdir(parents=True)
                source.write_text(safe_plan, encoding="utf-8")
                before = tree_snapshot(root)
                with mock.patch.object(
                    fs,
                    "_secure_dirfd_available",
                    return_value=False,
                ), mock.patch.object(
                    fs,
                    "_secure_archive_available",
                    return_value=False,
                ), mock.patch.object(
                    fs.tempfile,
                    "gettempdir",
                    side_effect=AssertionError("temporary lock path was consulted"),
                ):
                    code, _stdout, stderr = self.invoke_main(
                        plan,
                        [
                            "project_steward_plan.py",
                            "--project-root",
                            str(root),
                            *command,
                        ],
                    )
                self.assertEqual(code, 2)
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(tree_snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
