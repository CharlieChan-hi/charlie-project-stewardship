from __future__ import annotations

import json
import shutil
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

import project_steward_audit as audit_module
import project_steward_fs as fs
import project_steward_templates as templates
from project_steward_audit import build_audit
from project_steward_guard import build_guard, parse_validation_results


class ProjectHealthMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-health-")
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def init_git(self) -> None:
        result = subprocess.run(
            ["git", "init", "-q", str(self.root)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_empty_project_is_healthy_despite_zero_governance_coverage(self) -> None:
        audit = build_audit(self.root, max_lines=450)

        self.assertEqual(audit["schema_version"], "3.0")
        self.assertEqual(audit["project_health"]["status"], "healthy")
        self.assertIsNone(audit["project_health"]["score"])
        self.assertIsNone(audit["readiness_score"])
        self.assertEqual(audit["governance_coverage"]["coverage_percent"], 0)
        self.assertFalse(audit["governance_coverage"]["affects_project_health"])
        guard = build_guard(self.root, 450)
        self.assertEqual(guard["status"], "needs-review")
        self.assertIn("evidence.unspecified", {item["code"] for item in guard["review_items"]})
        self.assertEqual(
            build_guard(self.root, 450, acceptance_status="not-required")["status"],
            "pass",
        )

    def test_minimal_project_missing_docs_and_placeholders_do_not_block(self) -> None:
        (self.root / "docs").mkdir()
        (self.root / "AGENTS.md").write_text("# Rules\n\n[需确认]\n", encoding="utf-8")
        (self.root / "docs" / "project_intake.md").write_text(
            "# Intake\n\n[需确认]\n", encoding="utf-8"
        )
        (self.root / "docs" / "project_preferences.md").write_text(
            "# Preferences\n", encoding="utf-8"
        )

        guard = build_guard(self.root, 450, acceptance_status="not-required")

        self.assertEqual(guard["status"], "pass")
        self.assertTrue(guard["unresolved_docs"])
        self.assertFalse(guard["blockers"])
        self.assertFalse(guard["review_items"])

    def test_existing_repo_stack_detection_does_not_require_governance_docs(self) -> None:
        (self.root / "package.json").write_text(
            json.dumps({"dependencies": {"react": "latest"}}),
            encoding="utf-8",
        )
        (self.root / "package-lock.json").write_text("{}\n", encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)

        self.assertEqual(audit["detected"]["project_type"], "Web app")
        self.assertIn("React", audit["detected"]["stack_markers"])
        self.assertEqual(audit["detected"]["package_manager"], "npm")
        self.assertIsNone(audit["project_health"]["score"])

    def test_audit_cli_emits_package_workspace_monorepo_evidence(self) -> None:
        package_json = self.root / "package.json"
        workspace_forms = [
            ["apps/*", "packages/*"],
            {"packages": ["apps/*", "packages/*"], "nohoist": []},
        ]

        for workspaces in workspace_forms:
            with self.subTest(workspaces=workspaces):
                package_json.write_text(
                    json.dumps({"workspaces": workspaces}),
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS_DIR / "project_steward_audit.py"),
                        "--project-root",
                        str(self.root),
                        "--format",
                        "json",
                    ],
                    cwd=str(PLUGIN_ROOT),
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                detected = json.loads(result.stdout)["detected"]
                self.assertEqual(detected["project_type"], "Monorepo")
                self.assertIn("JavaScript workspace", detected["stack_markers"])

    def test_audit_ignores_invalid_package_workspace_shapes(self) -> None:
        package_json = self.root / "package.json"
        invalid_workspaces = [
            None,
            7,
            "packages/*",
            [],
            ["packages/*", 7],
            {"packages": None},
            {"packages": "packages/*"},
            {"packages": ["packages/*", " "]},
        ]

        for workspaces in invalid_workspaces:
            with self.subTest(workspaces=workspaces):
                package_json.write_text(
                    json.dumps({"workspaces": workspaces}),
                    encoding="utf-8",
                )

                detected = audit_module.detect_stack_safely(self.root)

                self.assertNotEqual(detected["project_type"], "Monorepo")
                self.assertNotIn("JavaScript workspace", detected["stack_markers"])

    def test_audit_accepts_only_regular_pnpm_workspace_marker(self) -> None:
        marker = self.root / "pnpm-workspace.yaml"
        marker.write_text("packages:\n  - 'packages/*'\n", encoding="utf-8")

        detected = audit_module.detect_stack_safely(self.root)

        self.assertEqual(detected["project_type"], "Monorepo")
        self.assertEqual(detected["package_manager"], "pnpm")
        self.assertIn("JavaScript workspace", detected["stack_markers"])

        marker.unlink()
        outside = self.base / "outside-pnpm-workspace.yaml"
        outside.write_text("OUTSIDE_WORKSPACE_MARKER_MUST_NOT_BE_READ", encoding="utf-8")
        try:
            marker.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable on this platform")

        symlinked = audit_module.detect_stack_safely(self.root)

        self.assertNotEqual(symlinked["project_type"], "Monorepo")
        self.assertNotIn("JavaScript workspace", symlinked["stack_markers"])

    def test_five_hundred_line_file_is_info_only_and_guard_passes(self) -> None:
        (self.root / "local.py").write_text("value = 1\n" * 500, encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)
        guard = build_guard(self.root, max_lines=450, changed_paths=["local.py"])

        self.assertIsNone(audit["project_health"]["score"])
        self.assertEqual(audit["project_health"]["status"], "healthy")
        self.assertEqual(audit["code_signals"]["large_files"][0]["severity"], "info")
        self.assertEqual(guard["status"], "pass")
        self.assertIn("code.large-file", {item["code"] for item in guard["signals"]})

    def test_source_above_read_limit_is_reported_and_complexity_skip_is_explicit(self) -> None:
        path = self.root / "huge.py"
        path.write_text("value = 1\n" * 70_000, encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)
        guard = build_guard(self.root, 450, changed_paths=["huge.py"])

        self.assertGreater(path.stat().st_size, 500_000)
        self.assertEqual(audit["code_signals"]["large_files"][0]["path"], "huge.py")
        skipped = audit["code_signals"]["complexity_analysis_skipped"]
        self.assertEqual(skipped[0]["signal"], "analysis-skipped:size-limit")
        self.assertIn(
            "code.complexity-analysis-skipped:size-limit",
            {item["code"] for item in guard["signals"]},
        )
        self.assertEqual(guard["status"], "pass")

    def test_complexity_signal_is_scoped_to_changed_paths(self) -> None:
        lines = ["def complicated(value):", "    result = 0"]
        for index in range(30):
            lines.extend([
                f"    if value == {index}:",
                f"        result += {index}",
            ])
        lines.extend(["    result += 0"] * 30)
        lines.append("    return result")
        (self.root / "complex.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (self.root / "small.py").write_text("value = 1\n", encoding="utf-8")

        whole_project = build_guard(
            self.root,
            450,
            acceptance_status="not-required",
        )
        unrelated_change = build_guard(self.root, 450, changed_paths=["small.py"])

        self.assertEqual(whole_project["status"], "pass")
        self.assertEqual(unrelated_change["status"], "pass")
        self.assertIn(
            "code.control-flow-density",
            {item["code"] for item in whole_project["signals"]},
        )
        self.assertIn(
            "code.control-flow-density",
            {item["code"] for item in unrelated_change["signals"]},
        )

    def test_project_root_changed_path_scopes_all_complexity_signals(self) -> None:
        lines = ["def complicated(value):", "    result = 0"]
        for index in range(30):
            lines.extend([
                f"    if value == {index}:",
                f"        result += {index}",
            ])
        lines.extend(["    result += 0"] * 30)
        lines.append("    return result")
        (self.root / "complex.py").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

        guard = build_guard(self.root, 450, changed_paths=["."])

        self.assertEqual(guard["status"], "needs-review")
        self.assertIn(
            "code.control-flow-density",
            {item["code"] for item in guard["review_items"]},
        )

    def test_absolute_tmp_ancestor_is_not_a_dead_code_name(self) -> None:
        nested_root = self.base / "tmp" / "project"
        nested_root.mkdir(parents=True)
        (nested_root / "main.py").write_text("value = 1\n", encoding="utf-8")

        audit = build_audit(nested_root, max_lines=450)

        self.assertEqual(audit["code_signals"]["dead_code_name_candidates"], [])

    def test_symlink_escape_is_not_followed_or_reported(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        secret_marker = "DO_NOT_READ_SYMLINK_TARGET"
        (outside / "escape.py").write_text(
            secret_marker + "\n" + ("if True:\n    pass\n" * 200),
            encoding="utf-8",
        )
        (outside / ".env").write_text(secret_marker, encoding="utf-8")
        (self.root / "escape.py").symlink_to(outside / "escape.py")
        (self.root / "linked-dir").symlink_to(outside, target_is_directory=True)
        (self.root / ".env").symlink_to(outside / ".env")

        audit = build_audit(self.root, max_lines=20)
        rendered = json.dumps(audit, ensure_ascii=False)

        self.assertNotIn(secret_marker, rendered)
        self.assertFalse(audit["code_signals"]["large_files"])
        self.assertFalse(audit["secrets"]["secret_like_files_present"])
        self.assertFalse(audit["secrets"]["symlinks_followed"])

    @unittest.skipUnless(fs._secure_dirfd_available(), "secure dirfd support required")
    def test_safe_read_fails_closed_when_intermediate_directory_is_swapped(self) -> None:
        source_dir = self.root / "src"
        source_dir.mkdir()
        source = source_dir / "race.py"
        source.write_text("inside = True\n", encoding="utf-8")
        outside = self.base / "outside-read"
        outside.mkdir()
        marker = "OUTSIDE_READ_MUST_NOT_ESCAPE"
        (outside / source.name).write_text(marker, encoding="utf-8")
        real_open = fs._open_relative_directory
        swapped = False

        def swap_after_open(
            root_fd: int,
            relative: Path,
            *,
            create: bool,
        ) -> tuple[int, list[Path]]:
            nonlocal swapped
            fd, created = real_open(root_fd, relative, create=create)
            if not swapped and relative == Path("src"):
                source_dir.rename(self.root / "src.saved")
                source_dir.symlink_to(outside, target_is_directory=True)
                swapped = True
            return fd, created

        with mock.patch.object(
            fs,
            "_open_relative_directory",
            side_effect=swap_after_open,
        ):
            text = audit_module.safe_read_text(source, root=self.root)

        self.assertTrue(swapped)
        self.assertEqual(text, "")
        self.assertNotIn(marker, text)

    @unittest.skipUnless(fs._secure_dirfd_available(), "secure dirfd support required")
    def test_stream_stats_fail_closed_when_intermediate_directory_is_swapped(self) -> None:
        source_dir = self.root / "lib"
        source_dir.mkdir()
        source = source_dir / "race.py"
        source.write_text("inside = True\n", encoding="utf-8")
        outside = self.base / "outside-stream"
        outside.mkdir()
        (outside / source.name).write_text("outside\n" * 100, encoding="utf-8")
        real_open = fs._open_relative_directory
        swapped = False

        def swap_after_open(
            root_fd: int,
            relative: Path,
            *,
            create: bool,
        ) -> tuple[int, list[Path]]:
            nonlocal swapped
            fd, created = real_open(root_fd, relative, create=create)
            if not swapped and relative == Path("lib"):
                source_dir.rename(self.root / "lib.saved")
                source_dir.symlink_to(outside, target_is_directory=True)
                swapped = True
            return fd, created

        with mock.patch.object(
            fs,
            "_open_relative_directory",
            side_effect=swap_after_open,
        ):
            stats = audit_module.stream_source_stats(source, root=self.root)

        self.assertTrue(swapped)
        self.assertIsNone(stats)

    def test_non_git_env_is_unknown_without_reading_contents(self) -> None:
        secret_marker = "TOP_SECRET_MUST_NOT_APPEAR"
        (self.root / ".env").write_text(secret_marker, encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)
        guard = build_guard(
            self.root,
            max_lines=450,
            acceptance_status="not-required",
        )

        self.assertEqual(audit["secrets"]["env_files_present"], [".env"])
        self.assertEqual(audit["secrets"]["unignored_env_files"], [])
        self.assertEqual(audit["secrets"]["unknown_env_files"], [".env"])
        self.assertEqual(audit["secrets"]["ignore_status"], "unknown")
        self.assertEqual(audit["project_health"]["status"], "unknown")
        self.assertFalse(audit["secrets"]["contents_read"])
        self.assertNotIn(secret_marker, json.dumps(audit, ensure_ascii=False))
        self.assertEqual(guard["status"], "needs-review")
        self.assertFalse(guard["blockers"])
        self.assertIn(
            "secrets.env-ignore-unknown",
            {item["code"] for item in guard["review_items"]},
        )

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_git_directory_and_nested_ignore_rules_are_authoritative(self) -> None:
        self.init_git()
        (self.root / ".gitignore").write_text("secrets/\n", encoding="utf-8")
        (self.root / "secrets").mkdir()
        (self.root / "secrets" / ".env").write_text("placeholder", encoding="utf-8")
        (self.root / "config").mkdir()
        (self.root / "config" / ".gitignore").write_text(".env\n", encoding="utf-8")
        (self.root / "config" / ".env").write_text("placeholder", encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)

        self.assertTrue(audit["secrets"]["gitignore_covers_env"])
        self.assertEqual(audit["secrets"]["ignore_status"], "covered")
        self.assertFalse(audit["secrets"]["risk_detected"])
        self.assertEqual(
            build_guard(
                self.root,
                450,
                acceptance_status="not-required",
            )["status"],
            "pass",
        )

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_unignored_or_tracked_env_is_a_confirmed_blocker(self) -> None:
        self.init_git()
        (self.root / ".env").write_text("placeholder", encoding="utf-8")

        unignored = build_audit(self.root, max_lines=450)
        self.assertEqual(unignored["project_health"]["status"], "at-risk")
        self.assertEqual(unignored["secrets"]["unignored_env_files"], [".env"])

        (self.root / ".gitignore").write_text(".env\n", encoding="utf-8")
        added = subprocess.run(
            ["git", "-C", str(self.root), "add", "-f", ".env"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        tracked = build_audit(self.root, max_lines=450)
        guard = build_guard(
            self.root,
            450,
            acceptance_status="not-required",
        )

        self.assertEqual(tracked["secrets"]["tracked_env_files"], [".env"])
        self.assertEqual(tracked["secrets"]["unignored_env_files"], [".env"])
        self.assertEqual(guard["status"], "blocked")
        self.assertTrue(guard["high"])

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_tracked_env_inside_skipped_build_tree_is_still_detected(self) -> None:
        self.init_git()
        generated = self.root / "dist"
        generated.mkdir()
        (generated / ".env").write_text("placeholder", encoding="utf-8")
        added = subprocess.run(
            ["git", "-C", str(self.root), "add", "dist/.env"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(added.returncode, 0, added.stderr)

        audit = build_audit(self.root, max_lines=450)
        guard = build_guard(
            self.root,
            450,
            acceptance_status="not-required",
        )

        self.assertEqual(audit["secrets"]["tracked_env_files"], ["dist/.env"])
        self.assertEqual(audit["project_health"]["status"], "at-risk")
        self.assertEqual(guard["status"], "blocked")

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_untracked_unignored_env_inside_skipped_build_tree_is_detected(self) -> None:
        self.init_git()
        generated = self.root / "dist"
        generated.mkdir()
        (generated / ".env").write_text("placeholder", encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)
        guard = build_guard(
            self.root,
            450,
            acceptance_status="not-required",
        )

        self.assertEqual(audit["secrets"]["unignored_env_files"], ["dist/.env"])
        self.assertEqual(audit["project_health"]["status"], "at-risk")
        self.assertEqual(guard["status"], "blocked")

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_secret_git_inventory_uses_bounded_pathspecs(self) -> None:
        self.init_git()
        generated = self.root / "dist"
        generated.mkdir()
        (generated / ".env").write_text("placeholder", encoding="utf-8")
        real_run = subprocess.run
        inventory_commands: list[list[str]] = []

        def capture_run(command: list[str], *args: object, **kwargs: object):
            if "ls-files" in command and "--others" in command:
                inventory_commands.append(command)
            return real_run(command, *args, **kwargs)

        with mock.patch.object(
            audit_module.subprocess,
            "run",
            side_effect=capture_run,
        ):
            audit = build_audit(self.root, max_lines=450)

        self.assertEqual(audit["secrets"]["unignored_env_files"], ["dist/.env"])
        self.assertEqual(len(inventory_commands), 1)
        command = inventory_commands[0]
        separator = command.index("--")
        self.assertTrue(command[separator + 1 :])
        self.assertTrue(all(item.startswith(":(glob)") for item in command[separator + 1 :]))

    def test_env_example_is_not_a_real_secret_signal(self) -> None:
        (self.root / ".env.example").write_text("API_KEY=placeholder\n", encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)

        self.assertFalse(audit["secrets"]["ignore_check_required"])
        self.assertFalse(audit["secrets"]["risk_detected"])

    def test_env_example_suffixes_are_exempt_but_ambiguous_suffixes_are_not(self) -> None:
        for name in (
            ".env.production.example",
            ".env.local.sample",
            ".env.staging.template",
        ):
            (self.root / name).write_text("API_KEY=placeholder\n", encoding="utf-8")
        ambiguous = ".env.example.secret"
        (self.root / ambiguous).write_text("API_KEY=placeholder\n", encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)

        self.assertEqual(audit["secrets"]["secret_like_files_present"], [ambiguous])
        self.assertEqual(audit["secrets"]["env_files_present"], [ambiguous])

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_credential_capable_config_is_reviewed_without_reading_contents(self) -> None:
        self.init_git()
        secret_marker = "SYNTHETIC_NPMRC_VALUE_MUST_NOT_APPEAR"
        (self.root / ".npmrc").write_text(secret_marker, encoding="utf-8")

        audit = build_audit(self.root, max_lines=450)
        guard = build_guard(
            self.root,
            max_lines=450,
            acceptance_status="not-required",
        )

        self.assertEqual(audit["project_health"]["status"], "needs-review")
        self.assertEqual(
            audit["secrets"]["exposed_credential_config_files"], [".npmrc"]
        )
        self.assertFalse(audit["secrets"]["contents_read"])
        self.assertNotIn(secret_marker, json.dumps(audit, ensure_ascii=False))
        self.assertEqual(guard["status"], "needs-review")
        self.assertIn(
            "secrets.credential-config-exposed",
            {item["code"] for item in guard["review_items"]},
        )

    def test_only_exact_current_plan_affects_review_status(self) -> None:
        active = self.root / "plans" / "active"
        active.mkdir(parents=True)
        (active / "demo.md").write_text(
            "---\n"
            "plan_id: demo\n"
            "title: Demo\n"
            "status: active\n"
            "---\n\n"
            "- [ ] 1. unfinished\n",
            encoding="utf-8",
        )

        unrelated = build_guard(
            self.root,
            max_lines=450,
            acceptance_status="not-required",
        )
        selected = build_guard(
            self.root,
            max_lines=450,
            current_plan="demo",
        )

        self.assertEqual(unrelated["status"], "pass")
        self.assertIn(
            "plan.incomplete-unrelated",
            {item["code"] for item in unrelated["signals"]},
        )
        self.assertEqual(selected["status"], "needs-review")
        self.assertIn(
            "plan.incomplete",
            {item["code"] for item in selected["review_items"]},
        )
        self.assertFalse(selected["blockers"])

    def test_malformed_plan_is_a_signal_or_current_plan_review(self) -> None:
        active = self.root / "plans" / "active"
        active.mkdir(parents=True)
        (active / "broken.md").write_text(
            "- [ ] [S001] first\n- [ ] [S001] duplicate\n",
            encoding="utf-8",
        )

        unrelated = build_guard(
            self.root,
            450,
            acceptance_status="not-required",
        )
        selected = build_guard(self.root, 450, current_plan="broken")

        self.assertEqual(unrelated["status"], "pass")
        self.assertIn(
            "plan.malformed-unrelated",
            {item["code"] for item in unrelated["signals"]},
        )
        self.assertEqual(selected["status"], "needs-review")
        self.assertIn(
            "plan.malformed",
            {item["code"] for item in selected["review_items"]},
        )
        self.assertEqual(selected["malformed_plans"][0]["path"], "plans/active/broken.md")

    def test_missing_exact_current_plan_needs_review(self) -> None:
        guard = build_guard(self.root, 450, current_plan="missing")

        self.assertEqual(guard["status"], "needs-review")
        self.assertIn(
            "plan.current-not-found",
            {item["code"] for item in guard["review_items"]},
        )

    def test_validation_and_acceptance_evidence_drive_blocking(self) -> None:
        validation_failure = build_guard(
            self.root,
            450,
            validation_results={"tests": "fail"},
        )
        missing_required = build_guard(
            self.root,
            450,
            validation_results={},
            required_validations=["tests"],
        )
        acceptance_failure = build_guard(
            self.root,
            450,
            acceptance_status="fail",
        )

        self.assertEqual(validation_failure["status"], "blocked")
        self.assertEqual(missing_required["status"], "needs-review")
        self.assertEqual(acceptance_failure["status"], "blocked")

    def test_declared_nonpassing_validation_needs_review(self) -> None:
        for validation_status in ("not-run", "skipped"):
            with self.subTest(validation_status=validation_status):
                guard = build_guard(
                    self.root,
                    450,
                    validation_results={"tests": validation_status},
                )
                self.assertEqual(guard["status"], "needs-review")
                self.assertIn(
                    "validation.not-passed",
                    {item["code"] for item in guard["review_items"]},
                )

    def test_conflicting_duplicate_validation_results_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Conflicting validation results"):
            parse_validation_results(["tests=fail", "tests=pass"])

    def test_intake_rejects_high_confidence_secret_input(self) -> None:
        synthetic_secret = "API_KEY=synthetic-test-value-12345"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "project_steward_intake.py"),
                "--project-root",
                str(self.root),
                "--product-goal",
                synthetic_secret,
                "--write",
            ],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "docs" / "project_intake.md").exists())
        self.assertNotIn(synthetic_secret, result.stdout)
        self.assertNotIn(synthetic_secret, result.stderr)

    def test_audit_cli_emits_machine_readable_json(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "project_steward_audit.py"),
                "--project-root",
                str(self.root),
                "--format",
                "json",
            ],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], "3.0")
        self.assertIn("project_health", payload)
        self.assertIn("governance_coverage", payload)
        self.assertIn("code_signals", payload)
        self.assertIsNone(payload["project_health"]["score"])
        self.assertIn("evidence_counts", payload["project_health"])

    def test_guard_json_write_keeps_stdout_machine_readable(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "project_steward_guard.py"),
                "--project-root",
                str(self.root),
                "--format",
                "json",
                "--acceptance-status",
                "not-required",
                "--write",
            ],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "pass")
        report = (
            self.root
            / "architecture_reports"
            / "latest"
            / "completion_guard_report.json"
        )
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "pass")
        self.assertIn("Report saved:", result.stderr)

    def test_fail_on_blocked_cli_uses_evidence_status(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required")
        self.init_git()
        (self.root / ".env").write_text("NEVER_ECHO_THIS", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "project_steward_guard.py"),
                "--project-root",
                str(self.root),
                "--format",
                "json",
                "--fail-on-blocked",
            ],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(payload["high"])
        self.assertEqual(payload["high"], payload["critical"])
        self.assertIn("fail-on-high", payload["deprecated_aliases"])
        self.assertNotIn("NEVER_ECHO_THIS", result.stdout)

    def test_guard_refuses_report_symlink_escape(self) -> None:
        outside = self.base / "outside-reports"
        outside.mkdir()
        (self.root / "architecture_reports").symlink_to(outside, target_is_directory=True)

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "project_steward_guard.py"),
                "--project-root",
                str(self.root),
                "--write",
            ],
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((outside / "latest" / "completion_guard_report.md").exists())


if __name__ == "__main__":
    unittest.main()
