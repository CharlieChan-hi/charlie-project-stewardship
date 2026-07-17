from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "shared" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import project_steward_memory as memory
import project_steward_plan as plan
import project_steward_fs as fs
import project_steward_stack as stack
import project_steward_templates as templates


def run_script(name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / name), *arguments],
        cwd=str(PLUGIN_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


class MemoryPersistenceSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-memory-safety-")
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def verified_args(self, rule: str, *extra: str) -> tuple[str, ...]:
        return (
            "--project-root",
            str(self.root),
            "--rule-id",
            "durable-boundary",
            "--rule",
            rule,
            "--kind",
            "invariant",
            "--priority",
            "hard",
            "--category",
            "architecture",
            "--scope",
            "Whole project",
            "--source",
            "ADR-0001 owner decision",
            "--evidence",
            "tests/test_boundaries.py",
            "--detection",
            "Run the boundary regression test",
            "--validation",
            "The boundary regression test passes",
            "--last-verified",
            "2026-07-16",
            *extra,
        )

    def test_malformed_or_duplicate_markers_are_rejected_without_data_loss(self) -> None:
        preferences = self.root / "docs" / "project_preferences.md"
        preferences.parent.mkdir()
        malformed_documents = {
            "missing end": (
                "# Preferences\n\n"
                "<!-- stewardship-rule-id:durable-boundary -->\n"
                "### Old rule\n\n"
                "## Later content\nKEEP THIS\n"
            ),
            "duplicate start": (
                "# Preferences\n\n"
                "<!-- stewardship-rule-id:durable-boundary -->\n"
                "<!-- stewardship-rule-id:durable-boundary -->\n"
                "<!-- stewardship-rule-end:durable-boundary -->\n"
                "## Later content\nKEEP THIS\n"
            ),
            "reversed": (
                "# Preferences\n\n"
                "<!-- stewardship-rule-end:durable-boundary -->\n"
                "<!-- stewardship-rule-id:durable-boundary -->\n"
                "## Later content\nKEEP THIS\n"
            ),
            "duplicate pair": (
                "# Preferences\n\n"
                "<!-- stewardship-rule-id:durable-boundary -->\n"
                "<!-- stewardship-rule-end:durable-boundary -->\n"
                "<!-- stewardship-rule-id:durable-boundary -->\n"
                "<!-- stewardship-rule-end:durable-boundary -->\n"
                "## Later content\nKEEP THIS\n"
            ),
        }
        for label, original in malformed_documents.items():
            with self.subTest(label=label):
                preferences.write_text(original, encoding="utf-8")
                result = run_script(
                    "project_steward_memory.py",
                    *self.verified_args("Replacement rule.", "--replace", "--write"),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(preferences.read_text(encoding="utf-8"), original)
                self.assertNotIn("Traceback", result.stderr)

    def test_valid_replacement_preserves_all_following_content(self) -> None:
        created = run_script(
            "project_steward_memory.py",
            *self.verified_args("Original rule.", "--write"),
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        preferences = self.root / "docs" / "project_preferences.md"
        suffix = "\n## Later content\nKEEP THIS EXACTLY\n\n"
        preferences.write_text(
            preferences.read_text(encoding="utf-8") + suffix,
            encoding="utf-8",
        )

        replaced = run_script(
            "project_steward_memory.py",
            *self.verified_args("Replacement rule.", "--replace", "--write"),
        )
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        updated = preferences.read_text(encoding="utf-8")
        self.assertTrue(updated.endswith(suffix))
        self.assertEqual(updated.count("stewardship-rule-id:durable-boundary"), 1)
        self.assertEqual(updated.count("stewardship-rule-end:durable-boundary"), 1)

    def test_unverified_defaults_to_pending_and_mirror_requires_full_evidence(self) -> None:
        pending = run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule",
            "Candidate convention.",
            "--write",
        )
        self.assertEqual(pending.returncode, 0, pending.stderr)
        content = (self.root / "docs" / "project_preferences.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("- Kind: pending", content)
        self.assertIn("- Priority: pending", content)
        self.assertIn("- Source: [需确认]", content)

        rejected = run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "unsafe-hard-rule",
            "--rule",
            "Unverified hard rule.",
            "--kind",
            "invariant",
            "--priority",
            "hard",
            "--source",
            "Owner said so",
            "--mirror-agents",
            "--write",
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_non_pending_memory_requires_complete_minimum_evidence(self) -> None:
        rejected = run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "underspecified-hard-rule",
            "--rule",
            "Keep the boundary stable.",
            "--kind",
            "invariant",
            "--priority",
            "hard",
            "--source",
            "Owner decision",
            "--write",
        )

        self.assertNotEqual(rejected.returncode, 0)
        for field in ("scope", "evidence", "detection", "validation", "last_verified"):
            self.assertIn(field, rejected.stderr)
        self.assertFalse((self.root / "docs" / "project_preferences.md").exists())

    def test_preference_accepts_one_refreshable_evidence_channel(self) -> None:
        result = run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "package-manager-preference",
            "--rule",
            "Use pnpm for this repository.",
            "--kind",
            "preference",
            "--priority",
            "preference",
            "--scope",
            "Repository package-management commands",
            "--source",
            "Explicit owner preference",
            "--detection",
            "Inspect packageManager and lockfile metadata",
            "--last-verified",
            "2026-07-16",
            "--write",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        content = (self.root / "docs" / "project_preferences.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Use pnpm for this repository.", content)

    def test_failure_memory_requires_evidence_detection_and_last_verified(self) -> None:
        rejected = run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "failure-one",
            "--rule",
            "The parser failed on duplicate IDs.",
            "--kind",
            "failure",
            "--priority",
            "preference",
            "--source",
            "Observed test failure",
            "--write",
        )
        self.assertNotEqual(rejected.returncode, 0)

        accepted = run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "failure-one",
            "--rule",
            "The parser failed on duplicate IDs.",
            "--kind",
            "failure",
            "--priority",
            "preference",
            "--source",
            "Observed test failure",
            "--scope",
            "Duplicate-ID parser behavior",
            "--evidence",
            "tests/test_duplicate_ids.py",
            "--detection",
            "Run the duplicate-ID regression test",
            "--validation",
            "The duplicate-ID regression test passes",
            "--last-verified",
            "2026-07-16",
            "--write",
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_secret_sentinels_are_allowed_but_real_credentials_are_rejected(self) -> None:
        safe = run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "redacted-key",
            "--rule",
            "Document API_KEY=placeholder in the example only.",
            "--write",
        )
        self.assertEqual(safe.returncode, 0, safe.stderr)

        rejected = run_script(
            "project_steward_memory.py",
            "--project-root",
            str(self.root),
            "--rule-id",
            "real-key",
            "--rule",
            "Use API_KEY=sk-testvalue1234567890.",
            "--write",
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn("sk-testvalue1234567890", rejected.stderr)

    def test_oserror_is_reported_without_traceback(self) -> None:
        argv = [
            "project_steward_memory.py",
            *self.verified_args("Transactional rule.", "--write"),
        ]
        stderr = io.StringIO()
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
            memory, "atomic_write_batch", side_effect=OSError("injected write failure")
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            result = memory.main()
        self.assertEqual(result, 2)
        self.assertIn("injected write failure", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class PlanPersistenceSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-plan-safety-")
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_plan(self, title: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "new",
            "--title",
            title,
            "--step",
            "First step",
            *extra,
            "--write",
        )

    def test_slug_collisions_create_distinct_stable_files(self) -> None:
        first = self.create_plan("Alpha/Beta")
        second = self.create_plan("Alpha Beta")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        files = sorted((self.root / "plans" / "active").glob("*.md"))
        self.assertEqual(len(files), 2)
        self.assertEqual(len({path.name for path in files}), 2)

        status = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "--format",
            "json",
            "status",
        )
        payload = json.loads(status.stdout)
        self.assertEqual(len({item["plan_id"] for item in payload["active_plans"]}), 2)

    def test_same_plan_id_or_filename_with_different_metadata_is_an_error(self) -> None:
        first = self.create_plan("Original", "--plan-id", "shared-id")
        self.assertEqual(first.returncode, 0, first.stderr)

        dry_run_id_conflict = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "new",
            "--title",
            "Different",
            "--plan-id",
            "shared-id",
            "--step",
            "First step",
        )
        self.assertEqual(dry_run_id_conflict.returncode, 2)
        self.assertNotIn("DRY RUN: 新建计划", dry_run_id_conflict.stdout)

        dry_run_filename_conflict = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "new",
            "--title",
            "Original",
            "--plan-id",
            "different-id",
            "--step",
            "First step",
        )
        self.assertEqual(dry_run_filename_conflict.returncode, 2)
        self.assertNotIn("DRY RUN: 新建计划", dry_run_filename_conflict.stdout)

        conflict = self.create_plan("Different", "--plan-id", "shared-id")
        self.assertNotEqual(conflict.returncode, 0)

        changed_steps = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "new",
            "--title",
            "Original",
            "--plan-id",
            "shared-id",
            "--step",
            "Different step",
            "--write",
        )
        self.assertNotEqual(changed_steps.returncode, 0)

    def test_very_long_title_has_bounded_filename(self) -> None:
        title = "长期计划" * 300
        result = self.create_plan(title)
        self.assertEqual(result.returncode, 0, result.stderr)
        files = list((self.root / "plans" / "active").glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertLessEqual(len(os.fsencode(files[0].name)), 255)
        title_line = next(
            line for line in files[0].read_text(encoding="utf-8").splitlines()
            if line.startswith("title:")
        )
        self.assertEqual(json.loads(title_line.partition(":")[2].strip()), title)

    def test_multibyte_title_filename_leaves_archive_suffix_margin(self) -> None:
        title = "𠀀" * 300
        result = self.create_plan(title)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_file = next((self.root / "plans" / "active").glob("*.md"))
        self.assertLessEqual(len(os.fsencode(plan_file.name)), 231)

    def test_staging_component_is_bounded_independently_of_plan_filename(self) -> None:
        observed: list[str] = []

        def reject_open(name: str, *_args: object, **_kwargs: object) -> int:
            observed.append(name)
            raise OSError("stop after capturing the staging component")

        destination = Path(("𠀀" * 55) + "-digest.md")
        with mock.patch.object(
            fs.secrets, "token_hex", return_value="a" * 32
        ), mock.patch.object(fs.os, "open", side_effect=reject_open):
            with self.assertRaisesRegex(OSError, "capturing"):
                fs._stage_bytes(destination, b"payload", 0o600, parent_fd=-1)

        self.assertEqual(observed, [f".steward-{'a' * 32}.tmp"])
        self.assertLessEqual(len(os.fsencode(observed[0])), 255)
        self.assertNotIn("𠀀", observed[0])

    def test_frontmatter_quotes_yaml_sensitive_title_and_reads_legacy_raw_title(self) -> None:
        title = "Release: phase #1"
        created = self.create_plan(title, "--plan-id", "release-phase-one")
        self.assertEqual(created.returncode, 0, created.stderr)
        plan_file = next((self.root / "plans" / "active").glob("*.md"))
        title_line = next(
            line for line in plan_file.read_text(encoding="utf-8").splitlines()
            if line.startswith("title:")
        )
        encoded_title = title_line.partition(":")[2].strip()
        self.assertEqual(json.loads(encoded_title), title)

        legacy = self.root / "plans" / "active" / "legacy.md"
        legacy.write_text(
            "---\n"
            "plan_id: legacy-plan\n"
            "title: Legacy: phase #1\n"
            "status: active\n"
            "last_updated_by: old-machine\n"
            "last_updated_at: 2026-07-15T12:00:00\n"
            "current_step: S001\n"
            "---\n\n"
            "# Legacy plan\n\n"
            "- [ ] [S001] Continue legacy work\n",
            encoding="utf-8",
        )
        status = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "--format",
            "json",
            "status",
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        plans = {
            item["plan_id"]: item for item in json.loads(status.stdout)["active_plans"]
        }
        self.assertEqual(plans["release-phase-one"]["title"], title)
        self.assertEqual(plans["legacy-plan"]["title"], "Legacy: phase #1")

    def test_zero_step_plan_requires_force_to_finish(self) -> None:
        active = self.root / "plans" / "active"
        active.mkdir(parents=True)
        source = active / "zero-step.md"
        source.write_text(
            "---\n"
            "plan_id: zero-step\n"
            "title: Zero step\n"
            "status: active\n"
            "last_updated_by: old-machine\n"
            "last_updated_at: 2026-07-15T12:00:00\n"
            "current_step: none\n"
            "---\n\n"
            "# Zero step\n\n"
            "No checklist was recorded.\n",
            encoding="utf-8",
        )

        status = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "status",
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("无可验证步骤", status.stdout)
        self.assertIn("--force", status.stdout)
        self.assertNotIn("全部完成", status.stdout)

        rejected = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "finish",
            "--plan",
            "zero-step",
            "--write",
        )
        self.assertEqual(rejected.returncode, 1, rejected.stderr)
        self.assertTrue(source.is_file())
        self.assertFalse((self.root / "plans" / "done").exists())

        forced = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "finish",
            "--plan",
            "zero-step",
            "--force",
            "--write",
        )
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertFalse(source.exists())
        self.assertTrue((self.root / "plans" / "done" / "zero-step.md").is_file())

    def test_plan_fields_reject_real_secrets_but_allow_safe_sentinels(self) -> None:
        rejected_title = self.create_plan("Deploy API_KEY=sk-testvalue1234567890")
        self.assertNotEqual(rejected_title.returncode, 0)
        self.assertFalse((self.root / "plans").exists())

        safe = self.create_plan("Deploy API_KEY=redacted")
        self.assertEqual(safe.returncode, 0, safe.stderr)
        plan_file = next((self.root / "plans" / "active").glob("*.md"))
        before = plan_file.read_text(encoding="utf-8")
        plan_id = json.loads(
            run_script(
                "project_steward_plan.py",
                "--project-root",
                str(self.root),
                "--format",
                "json",
                "status",
            ).stdout
        )["active_plans"][0]["plan_id"]
        rejected_note = run_script(
            "project_steward_plan.py",
            "--project-root",
            str(self.root),
            "note",
            "--plan",
            plan_id,
            "--text",
            "token=ghp_abcdefghijklmnopqrstuvwxyz",
            "--write",
        )
        self.assertNotEqual(rejected_note.returncode, 0)
        self.assertEqual(plan_file.read_text(encoding="utf-8"), before)


class StackReadSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-stack-safety-")
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_stack_detection_degrades_for_unexpected_package_json_shapes(self) -> None:
        package_json = self.root / "package.json"
        (self.root / "package-lock.json").write_text("{}\n", encoding="utf-8")
        framework_markers = {
            "Next.js",
            "React",
            "Vue",
            "Vite",
            "Express",
            "Expo",
            "Tailwind CSS",
            "Playwright",
            "Vitest",
            "Jest",
        }
        cases = {
            "top-level list": ([{"dependencies": {"react": "latest"}}], set()),
            "top-level null": (None, set()),
            "top-level scalar": ("react", set()),
            "dependencies list": (
                {
                    "dependencies": ["react"],
                    "devDependencies": {"vite": "latest"},
                },
                {"Vite"},
            ),
            "devDependencies string": (
                {
                    "dependencies": {"react": "latest"},
                    "devDependencies": "vite",
                },
                {"React"},
            ),
            "null and numeric sections": (
                {
                    "dependencies": None,
                    "devDependencies": 7,
                    "peerDependencies": False,
                },
                set(),
            ),
            "unusual dependency values": (
                {
                    "dependencies": {"react": None},
                    "devDependencies": {"vitest": {"workspace": "*"}},
                },
                {"React", "Vitest"},
            ),
        }

        for label, (payload, expected) in cases.items():
            with self.subTest(label=label):
                package_json.write_text(json.dumps(payload), encoding="utf-8")

                detected = stack.detect_stack(self.root)

                self.assertIn(
                    "Node.js / JavaScript or TypeScript",
                    detected["stack_markers"],
                )
                self.assertEqual(detected["package_manager"], "npm")
                self.assertEqual(
                    framework_markers.intersection(detected["stack_markers"]),
                    expected,
                )

    def test_detect_stack_recognizes_package_workspace_forms(self) -> None:
        package_json = self.root / "package.json"
        workspace_forms = [
            ["packages/*"],
            {"packages": ["apps/*", "packages/*"], "nohoist": []},
        ]

        for workspaces in workspace_forms:
            with self.subTest(workspaces=workspaces):
                package_json.write_text(
                    json.dumps({"workspaces": workspaces}),
                    encoding="utf-8",
                )

                detected = stack.detect_stack(self.root)

                self.assertEqual(detected["project_type"], "Monorepo")
                self.assertIn("JavaScript workspace", detected["stack_markers"])
                self.assertIn(
                    "Node.js / JavaScript or TypeScript",
                    detected["stack_markers"],
                )

    def test_detect_stack_ignores_invalid_package_workspace_shapes(self) -> None:
        package_json = self.root / "package.json"
        invalid_workspaces = [
            None,
            7,
            "packages/*",
            [],
            [""],
            ["packages/*", 7],
            {},
            {"packages": None},
            {"packages": []},
            {"packages": "packages/*"},
            {"packages": ["packages/*", " "]},
        ]

        for workspaces in invalid_workspaces:
            with self.subTest(workspaces=workspaces):
                package_json.write_text(
                    json.dumps({"workspaces": workspaces}),
                    encoding="utf-8",
                )

                detected = stack.detect_stack(self.root)

                self.assertNotEqual(detected["project_type"], "Monorepo")
                self.assertNotIn("JavaScript workspace", detected["stack_markers"])

    def test_detect_stack_recognizes_only_regular_pnpm_workspace_marker(self) -> None:
        marker = self.root / "pnpm-workspace.yaml"
        marker.write_text("packages:\n  - 'packages/*'\n", encoding="utf-8")

        detected = stack.detect_stack(self.root)

        self.assertEqual(detected["project_type"], "Monorepo")
        self.assertEqual(detected["package_manager"], "pnpm")
        self.assertIn("JavaScript workspace", detected["stack_markers"])

        marker.unlink()
        outside = self.base / "outside-pnpm-workspace.yaml"
        outside.write_text("packages:\n  - 'outside/*'\n", encoding="utf-8")
        try:
            marker.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable on this platform")

        symlinked = stack.detect_stack(self.root)

        self.assertNotEqual(symlinked["project_type"], "Monorepo")
        self.assertNotIn("JavaScript workspace", symlinked["stack_markers"])

    def test_stack_reader_supports_direct_calls_without_explicit_root(self) -> None:
        package_json = self.root / "package.json"
        content = '{"dependencies": {"react": "latest"}}\n'
        package_json.write_text(content, encoding="utf-8")

        self.assertEqual(
            stack.read_small_text(package_json, max_bytes=len(content.encode("utf-8"))),
            content,
        )
        self.assertEqual(
            stack.read_small_text(package_json, len(content.encode("utf-8"))),
            content,
        )
        self.assertEqual(
            stack.read_small_text(package_json, max_bytes=len(content.encode("utf-8")) - 1),
            "",
        )
        with mock.patch.object(stack.Path, "cwd", return_value=self.root):
            self.assertEqual(
                stack.read_small_text(Path("package.json"), max_bytes=500_000),
                content,
            )

    def test_stack_reader_refuses_final_component_symlink(self) -> None:
        marker = "outside-package-must-not-be-read"
        outside = self.base / "outside-package.json"
        outside.write_text(
            json.dumps({"dependencies": {"react": marker}}),
            encoding="utf-8",
        )
        link = self.root / "package.json"
        try:
            link.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable on this platform")

        text = stack.read_small_text(link, root=self.root)
        direct_text = stack.read_small_text(link, max_bytes=500_000)
        with mock.patch.object(stack.Path, "cwd", return_value=self.root):
            relative_text = stack.read_small_text(
                Path("package.json"),
                max_bytes=500_000,
            )
        detected = stack.detect_stack(self.root)

        self.assertEqual(text, "")
        self.assertEqual(direct_text, "")
        self.assertEqual(relative_text, "")
        self.assertNotIn(marker, text)
        self.assertNotIn("React", detected["stack_markers"])

    def test_fallback_reader_rejects_final_component_identity_swap_before_read(self) -> None:
        source = self.root / "package.json"
        source.write_text('{"dependencies": {}}\n', encoding="utf-8")
        replacement = self.base / "replacement-package.json"
        marker = "REPLACEMENT_MUST_NOT_BE_READ"
        replacement.write_text(marker, encoding="utf-8")
        canonical_source = source.resolve()
        real_open = fs.os.open
        observed_fd: int | None = None
        swapped = False

        def swap_after_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            nonlocal observed_fd, swapped
            fd = real_open(path, flags, *args, **kwargs)
            if not swapped and Path(path) == canonical_source:
                observed_fd = os.dup(fd)
                os.replace(replacement, canonical_source)
                swapped = True
            return fd

        try:
            with mock.patch.object(
                fs,
                "_secure_dirfd_available",
                return_value=False,
            ), mock.patch.object(fs.os, "open", side_effect=swap_after_open):
                with self.assertRaises(fs.ConcurrentModificationError):
                    fs.read_text_safe(source, root=self.root)

            self.assertTrue(swapped)
            self.assertIsNotNone(observed_fd)
            self.assertEqual(os.lseek(observed_fd, 0, os.SEEK_CUR), 0)
            self.assertEqual(source.read_text(encoding="utf-8"), marker)
        finally:
            if observed_fd is not None:
                os.close(observed_fd)

    @unittest.skipUnless(fs._secure_dirfd_available(), "secure dirfd support required")
    def test_stack_reader_fails_closed_when_ancestor_is_swapped(self) -> None:
        nested = self.root / "config"
        nested.mkdir()
        source = nested / "package.json"
        source.write_text('{"dependencies": {}}\n', encoding="utf-8")
        outside = self.base / "outside-config"
        outside.mkdir()
        marker = "OUTSIDE_ANCESTOR_MUST_NOT_BE_READ"
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
            if not swapped and relative == Path("config"):
                nested.rename(self.root / "config.saved")
                nested.symlink_to(outside, target_is_directory=True)
                swapped = True
            return fd, created

        with mock.patch.object(
            fs,
            "_open_relative_directory",
            side_effect=swap_after_open,
        ):
            text = stack.read_small_text(source, root=self.root)

        self.assertTrue(swapped)
        self.assertEqual(text, "")
        self.assertNotIn(marker, text)


class TransactionAndAdoptionPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-transaction-")
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_batch_write_rolls_back_first_commit_when_second_commit_fails(self) -> None:
        first = self.root / "first.txt"
        second = self.root / "second.txt"
        first.write_text("original\n", encoding="utf-8")
        signature = fs.file_signature(first)
        real_commit = fs._commit_staged
        calls = 0

        def fail_second(stage: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second commit failure")
            real_commit(stage)

        writes = [
            fs.PreparedWrite(first, "updated\n", signature),
            fs.PreparedWrite(second, "created\n", None),
        ]
        with mock.patch.object(fs, "_commit_staged", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "second commit"):
                fs.atomic_write_batch(writes, root=self.root)

        self.assertEqual(first.read_text(encoding="utf-8"), "original\n")
        self.assertFalse(second.exists())
        self.assertFalse(list(self.root.rglob(".*.tmp")))

    def test_unanchored_batch_write_fails_before_staging_or_directory_creation(self) -> None:
        target = self.root / "target.txt"
        target.write_text("original\n", encoding="utf-8")
        nested_target = self.root / "new" / "nested" / "created.txt"
        writes = [
            fs.PreparedWrite(target, "updated\n", fs.file_signature(target)),
            fs.PreparedWrite(nested_target, "created\n", None),
        ]

        with mock.patch.object(fs, "_secure_dirfd_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "descriptor-anchored"):
                fs.atomic_write_batch(writes, root=self.root)

        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")
        self.assertFalse(nested_target.parent.exists())
        self.assertFalse(list(self.root.rglob(".*.tmp")))

    def test_unanchored_batch_write_does_not_create_a_missing_project_root(self) -> None:
        missing_root = Path(self.temp_dir.name) / "missing-project"
        target = missing_root / "nested" / "target.txt"

        with mock.patch.object(fs, "_secure_dirfd_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "descriptor-anchored"):
                fs.atomic_write_batch(
                    [fs.PreparedWrite(target, "created\n", None)],
                    root=missing_root,
                )

        self.assertFalse(missing_root.exists())

    def test_unanchored_project_deletion_fails_closed(self) -> None:
        target = self.root / "keep.txt"
        target.write_text("keep\n", encoding="utf-8")

        with mock.patch.object(fs, "_secure_dirfd_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "descriptor-anchored"):
                fs.unlink_project_file_safe(
                    target,
                    root=self.root,
                    expected_signature=fs.file_signature(target),
                )

        self.assertEqual(target.read_text(encoding="utf-8"), "keep\n")

    @unittest.skipUnless(fs._secure_dirfd_available(), "secure dirfd support required")
    def test_finish_destination_replacement_restores_original_source(self) -> None:
        active = self.root / "plans" / "active"
        active.mkdir(parents=True)
        source = active / "archive-race.md"
        original = (
            "---\n"
            "plan_id: archive-race\n"
            "title: Archive race\n"
            "status: active\n"
            "last_updated_by: test\n"
            "last_updated_at: 2026-07-16T00:00:00\n"
            "current_step: none\n"
            "---\n\n"
            "# Archive race\n\n"
            "- [x] [S001] Complete\n"
        ).encode("utf-8")
        source.write_bytes(original)
        destination = self.root / "plans" / "done" / source.name
        real_unlink = fs._unlink_at
        replaced = False

        def replace_destination_before_source_unlink(
            parent_fd: int,
            name: str,
            *,
            expected_identity: tuple[int, int] | None = None,
        ) -> bool:
            nonlocal replaced
            if not replaced and name == source.name and destination.is_file():
                attacker = destination.with_name(".attacker-replacement.tmp")
                attacker.write_text("CONCURRENT REPLACEMENT\n", encoding="utf-8")
                os.replace(attacker, destination)
                replaced = True
            return real_unlink(
                parent_fd,
                name,
                expected_identity=expected_identity,
            )

        args = SimpleNamespace(
            write=True,
            plan="archive-race",
            force=False,
            machine="test-machine",
        )
        with mock.patch.object(
            fs,
            "_unlink_at",
            side_effect=replace_destination_before_source_unlink,
        ), redirect_stdout(io.StringIO()):
            with self.assertRaises(fs.ConcurrentModificationError):
                plan.cmd_finish(fs.canonical_root(self.root), args)

        self.assertTrue(replaced)
        self.assertTrue(source.is_file(), "archive failure removed the only source copy")
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(
            destination.read_text(encoding="utf-8"),
            "CONCURRENT REPLACEMENT\n",
        )
        self.assertFalse(list(self.root.rglob(".*.tmp")))

    def test_unanchored_archive_fails_before_source_or_destination_changes(self) -> None:
        source = self.root / "plans" / "active" / "fallback-race.md"
        destination = self.root / "plans" / "done" / source.name
        source.parent.mkdir(parents=True)
        original = b"fallback original\n"
        source.write_bytes(original)

        with mock.patch.object(fs, "_secure_archive_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "descriptor-anchored"):
                fs.archive_project_file_safe(
                    source,
                    destination,
                    "fallback archived\n",
                    root=self.root,
                    expected_source_signature=fs.content_signature(original),
                )

        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.rglob(".*.tmp")))

    @unittest.skipUnless(fs._secure_dirfd_available(), "secure dirfd support required")
    def test_intermediate_symlink_swap_cannot_redirect_atomic_write(self) -> None:
        active = self.root / "plans" / "active"
        active.mkdir(parents=True)
        outside = Path(self.temp_dir.name) / "outside"
        (outside / "active").mkdir(parents=True)
        target = active / "race.md"
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
            if not swapped and relative == Path("plans/active"):
                (self.root / "plans").rename(self.root / "plans.saved")
                (self.root / "plans").symlink_to(outside, target_is_directory=True)
                swapped = True
            return fd, created

        with mock.patch.object(
            fs,
            "_open_relative_directory",
            side_effect=swap_after_open,
        ):
            with self.assertRaises(
                (fs.ConcurrentModificationError, fs.ProjectPathError)
            ):
                fs.atomic_write_text(
                    target,
                    "must stay inside\n",
                    root=self.root,
                    expected_signature=None,
                )

        self.assertTrue(swapped)
        self.assertFalse((outside / "active" / "race.md").exists())
        self.assertFalse(list((self.root / "plans.saved").rglob(".*.tmp")))

    @unittest.skipUnless(fs._secure_dirfd_available(), "secure dirfd support required")
    def test_finish_intermediate_symlink_swap_cannot_delete_outside_source(self) -> None:
        active = self.root / "plans" / "active"
        active.mkdir(parents=True)
        source = active / "delete-race.md"
        source.write_text(
            "---\n"
            "plan_id: delete-race\n"
            "title: Delete race\n"
            "status: active\n"
            "last_updated_by: test\n"
            "last_updated_at: 2026-07-16T00:00:00\n"
            "current_step: none\n"
            "---\n\n"
            "# Delete race\n\n"
            "- [x] [S001] Complete\n",
            encoding="utf-8",
        )
        outside = Path(self.temp_dir.name) / "outside-plans"
        (outside / "active").mkdir(parents=True)
        (outside / "done").mkdir()
        outside_source = outside / "active" / source.name
        outside_source.write_text("OUTSIDE SOURCE MUST SURVIVE\n", encoding="utf-8")

        real_open = fs._open_relative_directory
        real_archive = plan.archive_project_file_safe
        armed = False
        swapped = False

        def arm_archive(*args: object, **kwargs: object) -> None:
            nonlocal armed
            armed = True
            real_archive(*args, **kwargs)

        def swap_after_open(
            root_fd: int,
            relative: Path,
            *,
            create: bool,
        ) -> tuple[int, list[Path]]:
            nonlocal swapped
            fd, created = real_open(root_fd, relative, create=create)
            if armed and not swapped and relative == Path("plans/active"):
                (self.root / "plans").rename(self.root / "plans.saved")
                (self.root / "plans").symlink_to(outside, target_is_directory=True)
                swapped = True
            return fd, created

        args = SimpleNamespace(
            write=True,
            plan="delete-race",
            force=False,
            machine="test-machine",
        )
        with mock.patch.object(plan, "archive_project_file_safe", side_effect=arm_archive), mock.patch.object(
            fs,
            "_open_relative_directory",
            side_effect=swap_after_open,
        ), redirect_stdout(io.StringIO()):
            with self.assertRaises(
                (fs.ConcurrentModificationError, fs.ProjectPathError)
            ):
                plan.cmd_finish(fs.canonical_root(self.root), args)

        self.assertTrue(swapped)
        self.assertEqual(
            outside_source.read_text(encoding="utf-8"),
            "OUTSIDE SOURCE MUST SURVIVE\n",
        )
        self.assertTrue((self.root / "plans.saved" / "active" / source.name).is_file())

    def test_safe_read_and_write_refuse_final_component_symlink(self) -> None:
        outside = Path(self.temp_dir.name) / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        link = self.root / "link.txt"
        try:
            link.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable on this platform")

        with self.assertRaises(templates.ProjectPathError):
            templates.read_text_safe(link, root=self.root)
        with self.assertRaises(templates.ProjectPathError):
            templates.atomic_write_text(
                link,
                "replacement\n",
                root=self.root,
                expected_signature=None,
            )
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")

    def test_workflows_keep_independent_adoption_plans(self) -> None:
        (self.root / "docs").mkdir()
        (self.root / "AGENTS.md").write_text("# Existing agents\n", encoding="utf-8")
        (self.root / "docs" / "project_intake.md").write_text(
            "# Existing intake\n", encoding="utf-8"
        )
        (self.root / "docs" / "source_structure.md").write_text(
            "# Existing structure\n", encoding="utf-8"
        )

        scaffold = run_script(
            "project_steward_scaffold.py",
            "--project-root",
            str(self.root),
            "--minimal",
            "--adoption-plan",
            "--write",
        )
        self.assertEqual(scaffold.returncode, 0, scaffold.stderr)
        scaffold_plan = (
            self.root
            / "architecture_reports"
            / "latest"
            / "stewardship_scaffold_adoption_plan.md"
        )
        self.assertTrue(scaffold_plan.is_file())
        scaffold_before = scaffold_plan.read_text(encoding="utf-8")

        intake = run_script(
            "project_steward_intake.py",
            "--project-root",
            str(self.root),
            "--product-goal",
            "Ship the product",
            "--adoption-plan",
            "--write",
        )
        self.assertEqual(intake.returncode, 0, intake.stderr)
        intake_plan = (
            self.root
            / "architecture_reports"
            / "latest"
            / "project_intake_adoption_plan.md"
        )
        self.assertTrue(intake_plan.is_file())
        intake_before = intake_plan.read_text(encoding="utf-8")

        recipe = run_script(
            "project_steward_recipes.py",
            "--project-root",
            str(self.root),
            "--recipe",
            "backend-api",
            "--adoption-plan",
            "--write",
        )
        self.assertEqual(recipe.returncode, 0, recipe.stderr)
        recipe_plan = (
            self.root
            / "architecture_reports"
            / "latest"
            / "source_recipe_backend-api_adoption_plan.md"
        )
        self.assertTrue(recipe_plan.is_file())
        self.assertEqual(scaffold_plan.read_text(encoding="utf-8"), scaffold_before)
        self.assertEqual(intake_plan.read_text(encoding="utf-8"), intake_before)


if __name__ == "__main__":
    unittest.main()
