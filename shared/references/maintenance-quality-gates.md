# Maintenance Quality Gates

Use this reference only when maintaining this plugin itself. Ordinary `$project-health`
audits must not load plugin-packaging or release gates into the target project.

## Layering

- `skills/*/SKILL.md` — focused trigger, workflow, stop conditions, and direct reference links;
- `shared/references/` — detailed policy loaded only when relevant;
- `shared/scripts/` — deterministic operations and checks;
- `shared/assets/templates/` — generated project text;
- `shared/assets/recipes/` — optional source-layout data.

Assume the model is capable. Keep hard constraints narrow and explain why; leave high-freedom implementation choices to task context.

## Skill and metadata gates

For every Skill:

- frontmatter name is stable lowercase hyphen-case;
- description states what, when, and when not to use it;
- body stays concise and points directly to needed references;
- `agents/openai.yaml` has a 25–64 character short description;
- default prompt explicitly names `$skill-name`;
- implicit invocation is enabled only when safe, useful, and non-duplicative.

Compatibility entries should be thin and normally explicit-only, so old names remain usable without competing with core Skills.

## Template gates

- Preserve all placeholder names consumed by existing scripts.
- Keep `AGENTS.md` a short context map with true invariants.
- Do not generate mandatory full-document read chains, universal process Skills, arbitrary file-size stop rules, or optional-tool installation requirements.
- Read-only user intent overrides template/scaffold writing.
- Existing project files are never overwritten by adoption scaffolds.

## Version compatibility

The Claude and Codex manifests represent the same plugin release and must share the same **base SemVer**:

- Claude: `x.y.z`;
- Codex: `x.y.z` or `x.y.z+codex.<build-metadata>`.

Strip SemVer build metadata before comparing; the bases must match. Codex-only `+codex.*` metadata may be used by the official cache/update flow and does not require the Claude manifest to carry the same suffix. Do not hand-edit versions when the current task forbids manifest changes.

## Validation

Run all Skill validators and the plugin gates:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" <skill-folder>
shared/scripts/validate_stewardship_plugin.py
```

Use the plugin's official cachebuster/update flow only when the user authorized an installed-plugin refresh.

## Audit-signal interpretation

Separate invariants and direct failures from heuristics:

- secret handling, authorization, destructive actions, and failing relevant tests are actionable evidence;
- file length, generic names, optional docs, and folder shape require contextual inspection;
- missing optional capabilities are reported as evidence gaps, not installed automatically.
