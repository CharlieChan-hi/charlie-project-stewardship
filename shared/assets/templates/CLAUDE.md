# CLAUDE.md

## Project snapshot

- Project type: [[project_type]]
- Detected stack: [[stack_markers]]
- Package manager: [[package_manager]]
- Goal and users: see `docs/project_intake.md`

## Task-scoped map

Read only what the task needs:

- `docs/project_intake.md` — goal, users, platform, constraints, and validation;
- `docs/project_preferences.md` — durable confirmed rules and pending candidates;
- nearest folder-level `CLAUDE.md` — rules for the files in scope;
- relevant source and tests — behavior being changed;
- architecture or harness docs — only for matching structural or agent-workflow tasks;
- `plans/active/` — only when resuming an explicitly persisted plan.

Missing optional docs do not block ordinary work.

## Invariants

- **Scope:** Preserve user changes and unrelated work; change only the requested surface.
- **Private values:** Do not read, expose, or persist real private values. Inspect actual runtime files such as `.env`, `.env.local`, and `.env.production` only for presence and ignore coverage; placeholder-only `.env.example`, `.env.sample`, and `.env.template` may be read when relevant.
- **High-impact actions:** Obtain the user's confirmation before destructive or hard-to-reverse actions, external/shared-state changes, installs/upgrades, migrations, permission changes, publishing, or deployment.
- **Validation:** Inspect relevant code and scripts, run proportionate checks, and report evidence plus gaps.

## Durable memory

Persist only confirmed rules or verified reusable learnings, with scope, source, exceptions, and validation.

## Session start

At each session start, check `plans/active/` for any active plan. If found, surface it with current step status and offer to resume before accepting new work — this enables automatic recovery when switching from Codex or another coding agent.
