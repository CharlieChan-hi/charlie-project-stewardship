---
name: project-memory
description: "用户明确要求跨会话保存项目规则、已验证经验或待确认候选时使用；Use for explicit durable project memory. 不用于当前任务状态或 secrets；Do not use for temporary task state or secrets."
---

# Project Memory

Persist only information that should change future project behavior and has trustworthy authority. Keep implementation choices free unless a confirmed rule actually constrains them.

## Capture gate

Evaluate five checks before treating a memory as confirmed:

1. **Durability** — the rule or learning should matter beyond the current task.
2. **Authority** — it was explicitly confirmed by the user, already documented, or verified against source/tests.
3. **Scope** — where it applies and where it does not.
4. **Evidence** — how a future agent can validate it.
5. **Novelty** — update or skip an equivalent rule instead of duplicating it.

If authority or scope is unclear, keep it in conversation or record it as pending only when requested.

## Destination

- Write one default carrier: `docs/project_preferences.md`.
- Mirror into `AGENTS.md` only for an explicitly requested hard invariant using `--mirror-agents --priority hard --kind invariant`.
- Treat a formal decision record or durable task plan as a separate explicitly scoped action.

## Persist safely

Use a dry run for drafts or unresolved scope/evidence:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_memory.py \
  --project-root <project-root> \
  --rule "<confirmed rule or explicitly pending candidate>" \
  --rule-id "<stable-logical-id>" \
  --kind <invariant|preference|decision|failure|pending> \
  --category <category> \
  --scope "<where it applies>" \
  --priority <hard|preference|pending> \
  --source "<user confirmation, source path, test, or decision>" \
  --evidence "<non-secret issue, ADR, test, log, or path>" \
  --detection "<check that detects drift or recurrence>" \
  --validation "<how future agents verify it>" \
  --last-verified "<date or revision>" \
  --invalidation "<condition that makes this stale>"
```

Add evidence, detection, exceptions, expiry, and invalidation fields when applicable; the script enforces stronger evidence for hard invariants and verified failures.

An explicit request to persist the confirmed rule or explicitly pending candidate authorizes `--write` to the default carrier. Reusing an unchanged `rule-id` is idempotent; changed semantics require review and explicit `--replace`.

## Output

Report the rule, authority/evidence, scope, destination, duplicate/update outcome, and refresh condition. Never present an inferred convention as confirmed.

## Read the reference only when needed

- Read `<skill-dir>/../../shared/references/memory-and-completion-guard.md` only when classifying a candidate as pending, confirmed, hard, or stale, or when choosing validation for the stored rule.
