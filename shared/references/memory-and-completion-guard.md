# Evidence-Based Memory and Validation

Use this reference for durable project memory and risk-driven completion evidence.

## Memory evidence ladder

| Level | Evidence | Treatment |
|:---|:---|:---|
| Candidate | Conversation inference or one observed pattern | Keep in the task; do not enforce |
| Pending | User wants to revisit it, but scope/evidence is incomplete | Record as pending only if requested |
| Confirmed | Explicit user rule, existing authoritative doc, or verified source/test behavior | Persist with scope and validation |
| Hard invariant | Confirmed rule every future agent must see immediately | Keep the default record in `docs/project_preferences.md`; mirror only on explicit request |
| Stale/conflicting | Code or user intent no longer matches the record | Refresh, demote, or remove after review |

A reusable learning should include a stable rule id, kind, failure/symptom, root cause, successful evidence, applicable scope, detection, exceptions, validation, last-verified point, and expiry/invalidation condition. Check for overlap before creating a second record.

Use dry-run for a draft or unresolved scope. An explicit request to persist a confirmed rule authorizes `--write` to the single default carrier, `docs/project_preferences.md`; do not ask again for the same scoped local write. Changed semantics under the same `--rule-id` require explicit `--replace`. Mirror a hard invariant into `AGENTS.md` only with explicit `--mirror-agents --priority hard --kind invariant`.

## Risk-driven validation ladder

Choose evidence that can falsify the completion claim:

1. **Static/local** — parse, diff review, lint/typecheck, focused unit test.
2. **Behavioral** — relevant integration test or direct runtime exercise.
3. **User surface** — browser/simulator/device flow plus visible and console/runtime evidence.
4. **High impact** — security, migration, permissions, deploy, or shared-state checks with authorization and recovery considerations.

Run the narrowest sufficient layer, escalating when the changed surface or failure mode crosses a boundary. More checks are not automatically better.

## Stewardship signals

`project_steward_audit.py` identifies structural review signals. `project_steward_guard.py` combines changed paths, required validations, validation results, and acceptance status into completion evidence; pass these explicitly rather than inferring success from repository shape.

Interpretation:

- secret exposure or unauthorized action is a real boundary;
- a failing project test/build is direct evidence;
- missing optional docs, line count, generic names, or folder shape need contextual review;
- an unavailable optional tool is an evidence gap, not permission to install it.

## Completion record

Report:

- claim being verified;
- relevant commands and observed results;
- confirmed failures versus heuristic signals;
- unverified surfaces and why;
- remaining risks or follow-up.

Do not mark a goal complete because the checklist is long, the context is ending, or a heuristic score is high.
