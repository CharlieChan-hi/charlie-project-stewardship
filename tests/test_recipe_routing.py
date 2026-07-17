from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "shared" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from project_steward_recipes import (
    adapt_recipe_to_project,
    choose_recipe,
    load_recipes,
    validate_recipe_asset,
)


RECIPES = {
    name: {"name": name}
    for name in (
        "backend-api",
        "expo",
        "ios-swiftui",
        "macos-swiftui",
        "nextjs",
        "web-react",
    )
}


class RecipeRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="stewardship-recipe-")
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_package(
        self, dependencies: dict[str, str], **extra_fields: object
    ) -> None:
        (self.root / "package.json").write_text(
            json.dumps({"dependencies": dependencies, **extra_fields}),
            encoding="utf-8",
        )

    def nextjs_recipe(self) -> dict[str, object]:
        return load_recipes()["nextjs"]

    def test_all_six_bundled_recipe_assets_pass_the_full_contract(self) -> None:
        recipes = load_recipes()

        self.assertEqual(set(recipes), set(RECIPES))
        for name, recipe in recipes.items():
            with self.subTest(recipe=name):
                self.assertIsInstance(recipe["summary"], str)
                self.assertIsInstance(recipe["dependency_direction"], str)
                self.assertTrue(recipe["folders"])
                self.assertTrue(recipe["rules"])
                self.assertTrue(recipe["validation"])

    def test_recipe_contract_rejects_missing_fields_and_wrong_types(self) -> None:
        source = PLUGIN_ROOT / "shared" / "assets" / "recipes" / "nextjs.json"
        recipe = json.loads(source.read_text(encoding="utf-8"))
        del recipe["validation"]

        with self.assertRaisesRegex(ValueError, "missing required fields: validation"):
            validate_recipe_asset(recipe, source)

        recipe = json.loads(source.read_text(encoding="utf-8"))
        recipe["rules"] = "not-a-list"
        with self.assertRaisesRegex(ValueError, "field `rules` must be a non-empty list"):
            validate_recipe_asset(recipe, source)

    def test_recipe_contract_rejects_unsafe_relative_folder_paths(self) -> None:
        source = PLUGIN_ROOT / "shared" / "assets" / "recipes" / "nextjs.json"
        for unsafe_path in ("../outside", "."):
            with self.subTest(path=unsafe_path):
                recipe = json.loads(source.read_text(encoding="utf-8"))
                recipe["folders"][0]["path"] = unsafe_path

                with self.assertRaisesRegex(ValueError, "portable relative path"):
                    validate_recipe_asset(recipe, source)

    def test_clear_nextjs_project_can_be_inferred(self) -> None:
        self.write_package({"next": "1", "react": "1"})

        self.assertEqual(choose_recipe(self.root, None, RECIPES), "nextjs")

    def test_nextjs_src_app_layout_is_preserved(self) -> None:
        (self.root / "src" / "app").mkdir(parents=True)

        recipe = adapt_recipe_to_project(
            self.root, "nextjs", self.nextjs_recipe()
        )
        paths = {folder["path"] for folder in recipe["folders"]}

        self.assertIn("src/app", paths)
        self.assertIn("src/features", paths)
        self.assertNotIn("app", paths)
        self.assertIn("tests", paths)

    def test_nextjs_src_pages_layout_is_preserved(self) -> None:
        (self.root / "src" / "pages").mkdir(parents=True)

        recipe = adapt_recipe_to_project(
            self.root, "nextjs", self.nextjs_recipe()
        )
        paths = {folder["path"] for folder in recipe["folders"]}

        self.assertIn("src/pages", paths)
        self.assertNotIn("app", paths)
        self.assertNotIn("src/app", paths)

    def test_nextjs_root_app_and_pages_layout_are_both_preserved(self) -> None:
        (self.root / "app").mkdir()
        (self.root / "pages").mkdir()

        recipe = adapt_recipe_to_project(
            self.root, "nextjs", self.nextjs_recipe()
        )
        paths = [folder["path"] for folder in recipe["folders"]]

        self.assertIn("app", paths)
        self.assertIn("pages", paths)
        self.assertEqual(paths.count("app"), 1)
        self.assertEqual(paths.count("pages"), 1)

    def test_nextjs_src_app_and_pages_layout_are_both_preserved(self) -> None:
        (self.root / "src" / "app").mkdir(parents=True)
        (self.root / "src" / "pages").mkdir()

        recipe = adapt_recipe_to_project(
            self.root, "nextjs", self.nextjs_recipe()
        )
        paths = [folder["path"] for folder in recipe["folders"]]

        self.assertIn("src/app", paths)
        self.assertIn("src/pages", paths)
        self.assertEqual(paths.count("src/app"), 1)
        self.assertEqual(paths.count("src/pages"), 1)

    def test_nextjs_root_pages_with_src_components_keeps_non_routes_in_src(self) -> None:
        (self.root / "pages").mkdir()
        (self.root / "src" / "components").mkdir(parents=True)

        recipe = adapt_recipe_to_project(
            self.root, "nextjs", self.nextjs_recipe()
        )
        paths = {folder["path"] for folder in recipe["folders"]}

        self.assertIn("pages", paths)
        self.assertIn("src/components", paths)
        self.assertIn("src/features", paths)
        self.assertNotIn("components", paths)

    def test_nextjs_src_without_router_defaults_to_src_app(self) -> None:
        (self.root / "src").mkdir()

        recipe = adapt_recipe_to_project(
            self.root, "nextjs", self.nextjs_recipe()
        )
        paths = {folder["path"] for folder in recipe["folders"]}

        self.assertIn("src/app", paths)
        self.assertIn("src/components", paths)
        self.assertNotIn("app", paths)
        self.assertNotIn("components", paths)

    def test_nextjs_conflicting_root_and_src_source_boundaries_are_rejected(self) -> None:
        (self.root / "components").mkdir()
        (self.root / "src" / "features").mkdir(parents=True)

        with self.assertRaisesRegex(SystemExit, "Conflicting Next.js source layouts"):
            adapt_recipe_to_project(self.root, "nextjs", self.nextjs_recipe())

    def test_nextjs_root_and_src_router_layout_conflict_is_rejected(self) -> None:
        (self.root / "app").mkdir()
        (self.root / "src" / "app").mkdir(parents=True)

        with self.assertRaisesRegex(SystemExit, "Conflicting Next.js router layouts"):
            adapt_recipe_to_project(self.root, "nextjs", self.nextjs_recipe())

    def test_monorepo_requires_explicit_scope_and_recipe(self) -> None:
        (self.root / "apps").mkdir()
        (self.root / "packages").mkdir()
        self.write_package({"next": "1", "react": "1"})

        with self.assertRaisesRegex(SystemExit, "Monorepo detected"):
            choose_recipe(self.root, None, RECIPES)

    def test_package_workspaces_apps_root_requires_explicit_scope_and_recipe(self) -> None:
        (self.root / "apps" / "web").mkdir(parents=True)
        self.write_package(
            {"next": "1", "react": "1"},
            workspaces=["apps/*"],
        )

        with self.assertRaisesRegex(SystemExit, "Monorepo detected"):
            choose_recipe(self.root, None, RECIPES)

    def test_apple_and_python_root_is_not_inferred_as_backend(self) -> None:
        (self.root / "Package.swift").write_text("// package\n", encoding="utf-8")
        (self.root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

        with self.assertRaisesRegex(SystemExit, "Apple project detected"):
            choose_recipe(self.root, None, RECIPES)

    def test_frontend_and_backend_markers_require_explicit_recipe(self) -> None:
        self.write_package({"next": "1", "react": "1"})
        (self.root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

        with self.assertRaisesRegex(SystemExit, "Multiple source-recipe families"):
            choose_recipe(self.root, None, RECIPES)

    def test_nextjs_and_expo_markers_require_explicit_recipe(self) -> None:
        self.write_package({"next": "1", "expo": "1", "react": "1"})

        with self.assertRaisesRegex(SystemExit, "Multiple source-recipe families"):
            choose_recipe(self.root, None, RECIPES)


if __name__ == "__main__":
    unittest.main()
