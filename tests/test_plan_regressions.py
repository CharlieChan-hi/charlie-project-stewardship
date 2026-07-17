from __future__ import annotations

from contextlib import redirect_stdout
import io
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

import project_steward_plan as plan


class PlanRelayRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-plan-regression-")
        self.root = plan.canonical_root(Path(self.temp_dir.name) / "project")
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_active_plan(self, name: str, body: str) -> Path:
        path = self.root / "plans" / "active" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def plan_text(*, duplicate_title: bool = False) -> str:
        duplicate = "title: Duplicate title\n" if duplicate_title else ""
        return (
            "---\n"
            "plan_id: regression-plan\n"
            "title: Regression plan\n"
            f"{duplicate}"
            "status: active\n"
            "last_updated_by: test-machine\n"
            "last_updated_at: 2026-07-17T00:00:00\n"
            "current_step: S001\n"
            "---\n\n"
            "# Regression plan\n\n"
            "## 步骤\n\n"
            "- [ ] [S001] Complete the real step\n\n"
            "## 交接笔记\n\n"
            "- [ ] [S999] This checkbox is note content, not a plan step\n"
        )

    def test_enumerated_then_removed_plan_fails_closed_for_all_commands(self) -> None:
        source = self.write_active_plan("vanished.md", self.plan_text())
        enumerated = plan.iter_active_plans(self.root)
        source.unlink()

        operations = {
            "status": lambda: plan.cmd_status(self.root, SimpleNamespace()),
            "check": lambda: plan.cmd_check(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    step="S001",
                    mark="done",
                    note=None,
                    machine="test-machine",
                ),
            ),
            "note": lambda: plan.cmd_note(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    text="Do not recreate a vanished plan",
                    machine="test-machine",
                ),
            ),
            "finish": lambda: plan.cmd_finish(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    force=True,
                    machine="test-machine",
                ),
            ),
        }

        for label, operation in operations.items():
            with self.subTest(command=label), mock.patch.object(
                plan,
                "iter_active_plans",
                return_value=enumerated,
            ), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(
                    plan.ConcurrentModificationError,
                    "在读取前已不存在",
                ):
                    operation()
            self.assertFalse(source.exists())
            self.assertFalse((self.root / "plans" / "done" / source.name).exists())

    def test_only_canonical_steps_section_drives_progress_and_archive(self) -> None:
        source = self.write_active_plan("sectioned.md", self.plan_text())

        parsed = plan.read_plan(source, self.root)
        self.assertEqual([step["id"] for step in parsed["steps"]], ["S001"])
        self.assertEqual(parsed["summary"]["total"], 1)

        with redirect_stdout(io.StringIO()):
            result = plan.cmd_check(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    step="S001",
                    mark="done",
                    note=None,
                    machine="test-machine",
                ),
            )
        self.assertEqual(result, 0)
        updated = source.read_text(encoding="utf-8")
        self.assertIn("- [x] [S001] Complete the real step", updated)
        self.assertIn("- [ ] [S999] This checkbox is note content", updated)

        with redirect_stdout(io.StringIO()):
            result = plan.cmd_finish(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    force=False,
                    machine="test-machine",
                ),
            )
        self.assertEqual(result, 0)
        self.assertFalse(source.exists())
        archived = self.root / "plans" / "done" / source.name
        self.assertTrue(archived.is_file())
        self.assertIn(
            "- [ ] [S999] This checkbox is note content",
            archived.read_text(encoding="utf-8"),
        )

    def test_headingless_legacy_plan_stops_before_handoff_notes(self) -> None:
        legacy = (
            "---\n"
            "plan_id: legacy-plan\n"
            "title: Legacy plan\n"
            "status: active\n"
            "current_step: S001\n"
            "---\n\n"
            "# Legacy plan\n\n"
            "- [ ] 1. Legacy step\n\n"
            "## Handoff Notes\n\n"
            "- [ ] 2. Note checkbox\n"
        )

        steps = plan.parse_steps(legacy)

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["id"], "S001")
        self.assertEqual(steps[0]["text"], "Legacy step")
        self.assertTrue(steps[0]["legacy"])

    def test_duplicate_frontmatter_fields_fail_before_any_command_mutates(self) -> None:
        source = self.write_active_plan(
            "duplicate-frontmatter.md",
            self.plan_text(duplicate_title=True),
        )
        original = source.read_text(encoding="utf-8")
        operations = {
            "status": lambda: plan.cmd_status(self.root, SimpleNamespace()),
            "check": lambda: plan.cmd_check(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    step="S001",
                    mark="done",
                    note=None,
                    machine="test-machine",
                ),
            ),
            "note": lambda: plan.cmd_note(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    text="Must not be appended",
                    machine="test-machine",
                ),
            ),
            "finish": lambda: plan.cmd_finish(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    force=True,
                    machine="test-machine",
                ),
            ),
        }

        for label, operation in operations.items():
            with self.subTest(command=label), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(
                    ValueError,
                    "Duplicate frontmatter field `title`",
                ):
                    operation()
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertFalse((self.root / "plans" / "done").exists())

    def test_duplicate_unknown_frontmatter_field_also_fails_exactly(self) -> None:
        text = (
            "---\n"
            "custom: first\n"
            " custom : second\n"
            "---\n\n"
            "## 步骤\n\n"
            "- [ ] [S001] Work\n"
        )

        with self.assertRaisesRegex(
            ValueError,
            "Duplicate frontmatter field `custom`",
        ):
            plan.parse_frontmatter(text)

    def test_mixed_canonical_and_legacy_step_sections_are_rejected(self) -> None:
        text = (
            "## Steps\n\n"
            "- [ ] [S001] English section\n\n"
            "## 步骤\n\n"
            "- [ ] [S002] Chinese section\n"
        )

        with self.assertRaisesRegex(ValueError, "contains both"):
            plan.parse_steps(text)

    def test_spaced_legacy_frontmatter_is_updated_without_duplicate_fields(self) -> None:
        machine = r"new\name"
        source = self.write_active_plan(
            "spaced-frontmatter.md",
            self.plan_text()
            .replace("status: active", "status : active")
            .replace("last_updated_by: test-machine", "last_updated_by : old-machine")
            .replace("last_updated_at: 2026-07-17T00:00:00", "last_updated_at : old")
            .replace("current_step: S001", "current_step : S001"),
        )

        with redirect_stdout(io.StringIO()):
            checked = plan.cmd_check(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    step="S001",
                    mark="done",
                    note=None,
                    machine=machine,
                ),
            )
            finished = plan.cmd_finish(
                self.root,
                SimpleNamespace(
                    write=True,
                    plan="regression-plan",
                    force=False,
                    machine=machine,
                ),
            )

        self.assertEqual((checked, finished), (0, 0))
        self.assertFalse(source.exists())
        archived = self.root / "plans" / "done" / source.name
        text = archived.read_text(encoding="utf-8")
        fields = plan.parse_frontmatter(text)
        self.assertEqual(fields["status"], "done")
        self.assertEqual(fields["last_updated_by"], machine)
        for key in ("status", "last_updated_by", "last_updated_at", "current_step"):
            self.assertEqual(
                sum(
                    1
                    for line in text.splitlines()
                    if ":" in line and line.partition(":")[0].strip() == key
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
