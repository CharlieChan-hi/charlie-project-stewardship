from __future__ import annotations

import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL_FILES = tuple(sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md")))
MINIMAL_TEMPLATES = tuple(
    PLUGIN_ROOT / "shared" / "assets" / "templates" / name
    for name in (
        "AGENTS.md",
        "docs-project_intake.md",
        "docs-project_preferences.md",
    )
)
FROZEN_SKILL_FRONTMATTER_BYTES = 4125
FROZEN_MINIMAL_TEMPLATE_LINES = 142


def frontmatter_bytes(path: Path) -> int:
    content = path.read_bytes()
    closing_marker = b"\n---\n"
    if not content.startswith(b"---\n"):
        raise ValueError(f"Missing frontmatter opener in {path}")
    closing = content.find(closing_marker, len(b"---\n"))
    if closing == -1:
        raise ValueError(f"Missing frontmatter closer in {path}")
    return closing + len(closing_marker)


class ContextBudgetContractTests(unittest.TestCase):
    def test_skill_catalog_frontmatter_matches_frozen_a_baseline(self) -> None:
        total = sum(frontmatter_bytes(path) for path in SKILL_FILES)
        self.assertEqual(total, FROZEN_SKILL_FRONTMATTER_BYTES)

    def test_minimal_templates_match_frozen_a_baseline(self) -> None:
        total_lines = sum(
            len(path.read_text(encoding="utf-8").splitlines())
            for path in MINIMAL_TEMPLATES
        )
        self.assertEqual(total_lines, FROZEN_MINIMAL_TEMPLATE_LINES)


if __name__ == "__main__":
    unittest.main()
