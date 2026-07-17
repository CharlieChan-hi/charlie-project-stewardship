# Charlie Project Stewardship Architecture

## Purpose

Keep high-value project context and feedback durable without wrapping a capable model in a rigid
workflow. The architecture favors a small public surface, progressive disclosure, deterministic
utilities, and compatibility with existing entry points.

## Public Capability Surface

- `project-bootstrap`: inspect, infer, and scaffold only justified project context.
- `task-contract`: bound ambiguity-sensitive work with scope, authority, sources, and acceptance evidence.
- `project-memory`: persist verified, future-relevant knowledge and maintain its lifecycle.
- `project-health`: read-only audit or change-aware completion verification.
- `plan-relay`: durable, crash-resistant handoff for genuinely long-running work.

Former intake, scaffold, audit, guard, start, and routing names remain thin compatibility entry
points. They route to the focused capability without imposing a second process stack.

## Layers

- Manifests expose the package and Codex presentation metadata.
- `SKILL.md` files provide narrow triggers, autonomy boundaries, and workflow selection.
- References hold detailed policy that is loaded only for the relevant branch.
- Standard-library scripts implement exact parsing, safe paths, atomic writes, reports, and checks.
- Templates and recipe JSON keep generated content and optional layout data out of script logic.
- Tests exercise behavior, safety boundaries, idempotency, compatibility, and drift.

## Dependency Direction

```txt
user outcome + repository state
  -> matching focused skill
  -> only relevant reference branch
  -> deterministic script when exact behavior is useful
  -> repository-local evidence or durable memory
  -> proportionate validation and handoff
```

Optional browser, LSP/semantic, and output-compression tools sit outside this graph.
They are adapters selected after a real capability probe; the plugin stays functional without them.

## Extension Boundary

- Add prose only when it resolves a repeated decision that cannot be made from the repository.
- Add a script or test when a repeatable condition can be checked mechanically.
- Add a Skill only for a distinct user intent with a precise trigger and independent output.
- Keep write tools non-overwriting or explicitly updating, project-root confined, symlink-safe,
  atomic, and idempotent.
- Never make an optional adapter a prerequisite for core stewardship behavior.

## Validation

The full gate compiles scripts, runs independent unit/behavior tests, validates every Skill and the
plugin manifest, exercises CLI forward scenarios, and checks cross-manifest base-version drift.
