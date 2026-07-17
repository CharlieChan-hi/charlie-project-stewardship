---
name: project-bootstrap
description: "为用户明确要求的新项目初始化、现有仓库接手或最小 Agent 上下文建设建立非覆盖式项目地图。Use only when the user explicitly asks to bootstrap, onboard, or adopt a repository, or to create its minimal project context. Do not trigger for ordinary implementation, merely because governance files are absent, or for architecture/tool setup."
---

# Project Bootstrap

Create the smallest useful project map for an explicit bootstrap or adoption request. Leave implementation choices and ordinary project work to the host model.

## Boundaries

- Read-only, proposal-only, or planning-only intent overrides all writes.
- Read the applicable project and folder instructions before proposing changes.
- Preserve existing files and user changes; scaffolding creates missing files and reports differences without overwriting.
- Do not read secret-file contents, install dependencies, or change shared/external state.

## Select the smallest mode

1. **Inspect only** when the request is read-only or the repository already explains itself.
2. **Minimal bootstrap** for an authorized bootstrap: `AGENTS.md`, `docs/project_intake.md`, and `docs/project_preferences.md`.
3. **Full scaffold** only when the user explicitly requests the extended set.
4. **Source recipe** only when requested or when a confirmed stack has a real unresolved layout need.

Do not block ordinary work merely because optional stewardship files are absent.

## Workflow

Inspect relevant conventions. If the request is read-only or write scope is unclear, preview the minimal result; the scaffold performs its own project scan:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_scaffold.py \
  --project-root <project-root> --minimal
```

Ask only for missing facts that change scope, architecture, authorization, or validation. Run the intake questionnaire only when those facts are needed; keep consequential unknowns as `[需确认]`.

If the request already authorizes the listed local files, run the write form directly rather than scanning once for preview and again for write. Otherwise keep the preview. Use `--adoption-plan` only when the user wants one precise merge plan for preserved differences.

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_scaffold.py \
  --project-root <project-root> --minimal --write
```

## Handoff

Report facts, assumptions, proposed or created files, preserved files, and unresolved material decisions. Route subsequent ambiguity-sensitive work to `$task-contract` only when a bounded execution envelope would materially reduce drift; route to another core Skill only when that separate need is explicit.

## Read references only when needed

- Read `<skill-dir>/../../shared/references/project-operating-system.md` only when deciding context layers for an existing or growing repository.
- Read `<skill-dir>/../../shared/references/project-intake-and-recipes.md` only for an intake questionnaire, existing-project adoption details, or an explicitly relevant source recipe.
