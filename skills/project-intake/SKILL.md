---
name: project-intake
description: "显式 $project-intake：收集影响架构的项目事实；Explicit project-intake questionnaire. 不用于一般功能发现；Not general feature discovery."
---

# Project Intake

Keep this compatibility entry narrowly scoped to confirmed intake facts.

## Workflow

1. Inspect existing project instructions and detected stack without reading secrets.
2. Run the questionnaire without writing:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_intake.py \
  --project-root <project-root>
```

3. Ask only for answers that change architecture, scope, or validation.
4. Preserve unknowns as `[需确认]`.
5. If the current request explicitly authorizes saving the confirmed intake, rerun with the confirmed answer flags and `--write` without asking again; otherwise preview or clarify first:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_intake.py \
  --project-root <project-root> \
  --product-goal "<confirmed goal>" \
  --target-users "<confirmed users>" \
  --platform "<confirmed platform>" \
  --validation "<completion evidence>" \
  --write
```

The script creates `docs/project_intake.md` when absent and preserves a different existing file. `--write` without at least one confirmed answer is rejected rather than silently doing nothing. Add `--adoption-plan` only when the user explicitly wants one precise merge plan. It does not authorize a source recipe, dependency install, or full scaffold.

For broader adoption, use `$project-bootstrap`. Read `<skill-dir>/../../shared/references/project-intake-and-recipes.md` only when the request involves adoption scope, source-layout recipes, or intake edge cases; skip it for the standard questionnaire.
