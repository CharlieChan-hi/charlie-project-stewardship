# Lean Project Intake and Source Recipes

Use this reference for a new/adopted project or an explicitly requested source-layout plan.

## Minimum intake

Ask only questions whose answers change the current setup:

- product goal and target users;
- target platform/deployment constraints;
- required or forbidden technologies;
- existing UI/design system when relevant;
- architecture boundaries that already matter;
- authorization-sensitive actions;
- evidence expected for completion.

Do not require all answers before a reversible minimal bootstrap. Keep unresolved consequential fields as `[需确认]`.

Use `project_steward_intake.py` to preview or persist confirmed intake. It creates a missing file and preserves a different existing intake. Use explicit `--adoption-plan` only when one consolidated merge plan is wanted.

## Existing project adoption

Treat source, tests, scripts, current docs, and local instructions as stronger evidence than a generic template. Add context only where recurring ambiguity exists. Do not restructure an existing repository as part of onboarding.

Default to:

```bash
project_steward_scaffold.py --project-root <root> --minimal
```

If the current request explicitly authorizes creating the listed local files, add `--write` directly; otherwise preview or clarify material scope. Omit `--minimal` only for an explicitly requested extended scaffold.

## Source recipes

Available recipes are starting points, not target architectures. Inspect with:

```bash
project_steward_recipes.py --list
```

Choose a recipe only when the detected/confirmed stack matches and the proposed folders solve a current need. Use dry-run for read-only intent or unclear write scope; when the current request explicitly authorizes the recipe's safe local writes, add `--write` directly without a second preview/confirmation. Recipes create missing folders/readmes and a source-structure record while preserving differences; use `--adoption-plan` only for an explicitly requested consolidated merge plan. They do not wire targets, routes, schemas, exports, builds, or deployment.

## Optional systems

Browser tools, LSP servers, MCP servers, and output filters are outside intake. Mention one only when the user explicitly asks or a measured project need makes it a meaningful option. Intake never authorizes installation or initialization.
