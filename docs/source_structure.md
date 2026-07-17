# Source Structure

## Selected Recipe

This package uses a custom plugin structure. It separates user-intent routing, detailed guidance,
deterministic mechanics, generated content, optional layout data, and verification.

## Folders

- `.codex-plugin/`: Codex manifest and UI surface.
- `.claude-plugin/`: portable package metadata for the multi-host source package.
- `skills/`: focused core capabilities plus thin compatibility entry points.
- `shared/references/`: detailed guidance loaded only when relevant.
- `shared/scripts/`: deterministic standard-library CLIs.
- `shared/assets/templates/`: non-overwriting project-document templates.
- `shared/assets/recipes/`: optional, data-driven source-layout recipes.
- `tests/`: independent behavior and regression tests.
- `docs/`: maintainer context and design decisions.

## Dependency Direction

`manifest -> matching Skill -> relevant reference/script -> template or recipe -> target-project
evidence`. Scripts may share small utility modules but must not depend on a host-specific runtime.

## Rules

- Core Skills own user outcomes; legacy Skills only preserve discoverability and compatibility.
- References stay one hop from the Skill that needs them. Avoid reference chains that force broad
  context loading.
- Generated prose stays in templates and optional source trees stay in recipe JSON.
- Mutable project state uses stable IDs, exact parsing, safe paths, atomic writes, and conflict
  protection.
- Platform-specific implementation stays in the target repository or current official capability.

## Validation

Run the single full validation entry point in `AGENTS.md`; it owns test discovery, CLI forward
scenarios, official Skill/plugin validation, manifest drift checks, and cachebuster preconditions.
