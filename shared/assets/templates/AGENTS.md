# AGENTS.md（精简项目宪法与地图）

This file is the short project map for AI agents. More specific folder-level instructions override it within their scope.

## Project snapshot

- Project type: [[project_type]]
- Detected stack: [[stack_markers]]
- Package manager: [[package_manager]]
- Product goal and users: [需确认]

Detected values are clues, not permission to change architecture or dependencies.

## Context map

Read only what the task needs:

- `docs/project_intake.md` — confirmed goal, users, platform, constraints;
- `docs/project_preferences.md` — durable user-confirmed rules;
- `docs/architecture.md` and `docs/source_structure.md` — structural work;
- `docs/agent_harness.md` and `docs/capability_routing.md` — only when changing agent workflow or tool routing;
- nearest folder-level `AGENTS.md` — local rules for files being changed;
- `plans/active/` — only when resuming an explicitly persisted plan;
- optional tool/task-system directories — only when the current request explicitly targets them.

Missing optional docs do not block ordinary work. Inspect relevant source, tests, and scripts before acting.

## Invariants

- Preserve existing user changes and unrelated work; do not tidy, overwrite, move, rename, or delete outside the requested scope.
- Do not read or expose real secrets. For `.env*`, check only presence and ignore coverage.
- Explain impact and obtain confirmation before destructive or hard-to-reverse actions, external/shared-state changes, installs/upgrades, migrations, permission changes, publishing, or deployment.
- Follow existing project conventions and make the smallest coherent change that satisfies the request.
- Inspect unfamiliar scripts before running them. Do not bypass protections or required checks to make a result appear successful.
- Validate the changed behavior in proportion to risk. Use relevant tests/builds and browser, simulator, or security evidence only when the changed surface calls for them.
- Report what changed, evidence gathered, unverified areas, and remaining risks. Never claim completion from assumptions.

## Durable memory

Persist only user-confirmed rules or verified reusable learnings. Record scope, source, exceptions, and validation. Keep temporary task state in the task; use a durable plan only when explicitly requested.

## Optional capabilities

Detect what the current session actually exposes and use only task-relevant capabilities. Specialized adapters are optional; do not install, initialize, disable, or require them without a matching task and authorization.
