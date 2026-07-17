---
name: plan-relay
description: "为用户明确要求持久化、恢复或跨崩溃、会话、设备接力的多步骤计划保存仓库内状态。Use only when the user explicitly requests durable plan persistence, recovery, or cross-session/device handoff. Do not use for one-session plans, brainstorming, or ordinary task tracking."
---

# Plan Relay

Keep one repository file per explicitly persistent plan. Use the host's normal plan for work that will finish in the current session.

## Boundaries

- Read-only or planning-only intent overrides writes. An explicit request to persist or update the local plan authorizes the scoped `--write`.
- Never overwrite an existing active plan; update progress via `check` or `note`.
- `finish` archives into `plans/done/`; it does not delete history.
- Do not put secrets, credentials, or machine-specific absolute paths in plans.
- Treat Git commit/push as separate shared-state synchronization requiring authorization.
- Do not install or initialize another task system from this Skill.

## Workflow

Pass a stable machine label, and use exact plan and step IDs returned by `status`:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_plan.py \
  --project-root <project-root> --machine <label> \
  new --title "<plan title>" --plan-id "<stable-plan-id>" \
  --step "<first verifiable step>" --step "<next step>" --write

python3 <skill-dir>/../../shared/scripts/project_steward_plan.py \
  --project-root <project-root> --machine <label> status

python3 <skill-dir>/../../shared/scripts/project_steward_plan.py \
  --project-root <project-root> --machine <label> \
  check --plan <plan-id> --step <stable-step-id> \
  --mark <done|in-progress|todo> \
  --note "<evidence or resume detail>" --write

python3 <skill-dir>/../../shared/scripts/project_steward_plan.py \
  --project-root <project-root> --machine <label> \
  note --plan <plan-id> --text "<next action, evidence, blocker>" --write

python3 <skill-dir>/../../shared/scripts/project_steward_plan.py \
  --project-root <project-root> --machine <label> \
  finish --plan <plan-id> --write
```

Omit `--write` for a preview. `finish` refuses while steps remain; use `--force` only when the user intentionally closes an incomplete plan. Suggested Git commands are informational until synchronization is authorized.

## Persistence boundary

Local crash recovery is current through the last successful `--write`. Cross-machine recovery is current through the last authorized synchronization. State that boundary instead of promising recovery beyond persisted state.

Mention a task graph only when the user asks for stronger coordination and a flat plan cannot express dependencies or ownership.
