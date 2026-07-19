# AGENTS.md

## Project snapshot

- Project type: [[project_type]]
- Detected stack: [[stack_markers]]
- Package manager: [[package_manager]]
- Goal and users: see `docs/project_intake.md`

## Task-scoped map

Read only what the task needs:

- `docs/project_intake.md` — goal, users, platform, constraints, and validation;
- `docs/project_preferences.md` — durable confirmed rules and pending candidates;
- nearest folder-level `AGENTS.md` — rules for the files in scope;
- relevant source and tests — behavior being changed;
- architecture or harness docs — only for matching structural or agent-workflow tasks;
- `plans/active/` — only when resuming an explicitly persisted plan.

Missing optional docs do not block ordinary work.

## Invariants

- **Scope:** Preserve user changes and unrelated work; change only the requested surface.
- **Secrets:** Do not read, expose, or persist real secrets; inspect `.env*` only for presence and ignore coverage.
- **High-impact actions:** Obtain the user's confirmation before destructive or hard-to-reverse actions, external/shared-state changes, installs/upgrades, migrations, permission changes, publishing, or deployment.
- **Validation:** Inspect relevant code and scripts, run proportionate checks, and report evidence plus gaps.

## Durable memory

Persist only confirmed rules or verified reusable learnings, with scope, source, exceptions, and validation.
