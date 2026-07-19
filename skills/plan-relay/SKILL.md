---
name: plan-relay
description: "用户明确要求计划持久化、恢复或跨会话/设备接力时使用；Use for explicit durable plan persistence, recovery, or cross-session/device handoff. 不用于单会话计划；Do not use for one-session plans."
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

For an explicit continue or recover request, do not stop after `status`. Unless the user explicitly requests a read-only recovery, mark the recovered next step `in-progress` with current evidence, or record a blocking note when progress cannot begin. Persist only that scoped plan update.

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
