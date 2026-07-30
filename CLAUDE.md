# CLAUDE.md

## Purpose

This plugin is a thin project-stewardship harness. It preserves durable project facts,
offers deterministic maintenance tools, and asks for evidence before completion without
prescribing one universal development process. The host model chooses the implementation
path and available tools unless a real project invariant or approval boundary says otherwise.

## Map

- `.codex-plugin/plugin.json`: Codex package and UI metadata.
- `.claude-plugin/plugin.json`: portable package metadata; do not touch active Claude configuration.
- `skills/`: narrow workflow entry points. Core capabilities are bootstrap, task contract,
  memory, health, and plan relay; legacy names remain compatibility entry points.
- `shared/references/`: task-specific guidance loaded only when relevant.
- `shared/scripts/`: deterministic, standard-library-only project utilities.
- `shared/assets/templates/`: non-overwriting project templates including `AGENTS.md` (Codex) and `CLAUDE.md` (Claude).
- `shared/assets/recipes/`: optional source-layout recipes.
- `tests/`: behavior, security-boundary, idempotency, and regression tests.

## Stewardship capabilities

When the user invokes a capability by name, read the matching `skills/<name>/SKILL.md` in full
and follow it. Compatibility aliases route to the nearest core capability without adding process.

| Capability | When to invoke | Aliases |
|:---|:---|:---|
| `task-contract` | Explicit invocation; scope, sources, or acceptance is materially ambiguous | — |
| `project-bootstrap` | Explicit onboarding, missing-context preview, or `$start-here` | `start-here`, `project-intake`, `project-scaffold` |
| `project-memory` | Explicit request to save or enforce a durable project rule | — |
| `project-health` | Explicit read-only audit or completion-evidence check | `architecture-audit`, `completion-guard` |
| `plan-relay` | Explicit cross-session or cross-device plan persistence | — |

## Invariants

- Read this file and only the existing project material relevant to the change. Missing
  optional stewardship documents, browser tooling, or third-party adapters never
  block unrelated work.
- Prefer the host's current native capabilities. Probe before recommending an optional
  browser, semantic index, task database, or output compressor; never install one implicitly.
- Preserve user work and repository conventions. Keep changes proportional to the request;
  do not use file length, framework fashion, or template completeness as automatic blockers.
- Treat deletion, moves, dependency installation, publishing, deployment, permission changes,
  and external side effects according to the user's authorization boundary.
- Never read or emit real secret values. Do not follow symlinks outside the target project,
  and do not copy or modify active Claude configuration.
- Keep portable instructions in `SKILL.md`. Codex-only presentation belongs in
  `agents/openai.yaml`; Claude reads `SKILL.md` directly when invoked.
- Put repeated, objective checks in scripts or tests. Keep prompts focused on outcomes,
  decision boundaries, and evidence—not duplicated step-by-step micromanagement.

## Change Discipline

- Keep existing CLI behavior compatible unless a correctness or safety flaw requires a
  precise failure. Prefer stable identifiers, exact matching, atomic writes, and idempotency.
- Templates must be internally consistent in minimal mode and must not overwrite existing
  project files. A dry run describes prospective changes; explicit write intent authorizes
  safe local creation within the requested scope.
- Project health reports separate governance coverage from code risk. Optional plugin artifacts
  may be reported as context but never inflate or reduce a project's health score.
- Durable memory requires scope, provenance, evidence or detection, and a refresh/expiry rule.
  Do not promote a one-off preference into a global hard rule automatically.

## Maintenance References

- Read `shared/references/platform-native-first.md` only when changing capability routing,
  optional-tool escalation, or host-native behavior.
- Read `shared/references/maintenance-quality-gates.md` only when changing packaging,
  validation gates, release checks, or plugin maintenance policy.

## Validation

After any plugin change, run the full local gate:

```bash
python3 shared/scripts/validate_stewardship_plugin.py
```

Before reinstalling, ensure the base SemVer in both manifests matches. Codex may append one
`+codex.<cachebuster>` suffix. Refresh that suffix only after all normal gates pass:

```bash
python3 shared/scripts/validate_stewardship_plugin.py --update-cachebuster
```

Use the configured local marketplace and official `codex plugin add` command to refresh the
installed copy; never hand-edit plugin caches or marketplace state.
