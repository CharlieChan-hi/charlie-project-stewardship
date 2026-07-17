---
name: task-contract
description: "把复杂、跨载体、高影响或边界容易漂移的请求转成可执行的任务契约，明确目标、授权范围、事实源、非目标、验收证据、分批策略与停止条件。Use when work is multi-step, high-impact, ambiguity-sensitive, batch-reviewed, or spans multiple sources of truth and a bounded execution envelope would materially reduce rework. Do not use for simple scoped edits, ordinary answers, durable cross-session plans, or as permission to expand the user's authority."
---

# Task Contract

Create the smallest execution envelope that prevents scope drift and makes completion observable. Treat the contract as a current-task boundary, not a durable plan or added authorization.

## Boundaries

- Let read-only, diagnosis-only, or planning-only intent override every write or external action.
- Return the contract in conversation by default. Persist it only when the user explicitly requests persistence and authorizes the destination.
- Preserve the user's authority boundary: recording an action in the contract does not authorize it.
- Skip the full form for a simple, already-scoped request; restate only the material boundary if useful.
- Specify outcomes and evidence. Constrain implementation choices only when a real invariant, dependency, or user decision requires it.

## Choose the contract depth

Use a full contract when multiple sources must agree, the work is high-impact, acceptance is ambiguous, review must happen in batches, or several agents/steps could drift. Use a compact contract for one or two material ambiguities. Do not create process overhead for an ordinary local edit or direct answer.

## Build the contract

1. Separate confirmed facts from reversible assumptions and unresolved decisions. Ask only when an unresolved choice would materially change the outcome, authorization, or risk.
2. Select the mode: `plan`, `execute`, `review`, `diagnose`, or `monitor`.
3. State one observable objective. Bound allowed paths and actions, and name consequential non-goals.
4. Assign each fact class one source of truth. Mark reports, exports, generated pages, and caches as derived outputs so they cannot silently override the source.
5. Define acceptance tests as observable pass conditions with expected evidence. For repeated review, choose a batch size that exposes pattern errors early without fragmenting a small homogeneous set.
6. Define stop conditions for scope conflict, contradictory sources, missing authorization, failed evidence, destructive risk, cost, or external side effects.
7. Present the contract before action when the user asked for a contract/plan or confirmation is genuinely required. If scoped execution is already authorized, state the compact contract and proceed.

Read [task-contract-template.md](references/task-contract-template.md) when the contract is complex, must be persisted, coordinates several agents, or needs a reusable structured form.

## Maintain and hand off

Update the contract when the user changes the objective, scope, source of truth, or acceptance standard; never expand it silently. Report the resulting evidence against the acceptance tests and distinguish incomplete work from a failed contract.

Route to `$plan-relay` only for explicitly requested cross-session persistence, `$project-bootstrap` for explicit repository onboarding, and `$project-health` for a separately requested audit or completion-evidence check.
