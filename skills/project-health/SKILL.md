---
name: project-health
description: "为用户明确要求的项目健康或架构审计、交付前完成证据检查提供只读扫描和风险相称的验证选择。Use when the user explicitly asks for a project or architecture health audit, or for completion verification before handoff. Do not invoke automatically after edits, for routine handoffs, or instead of project-native runtime or security checks."
---

# Project Health

Gather evidence without imposing a universal development process. Deterministic signals point to review areas; they do not prove defects.

## Boundaries

- Read-only intent overrides report writing; save a report only when explicitly requested.
- Never read secret-file contents; only check presence and ignore coverage.
- Use **audit mode** for a requested project/architecture assessment and **completion mode** for a requested finished-change check.
- Project-native tests and runtime/security checks remain the primary evidence.

## Audit mode

Run the deterministic scan:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_audit.py \
  --project-root <project-root>
```

Use JSON only when structured output helps. Confirm material findings against relevant source; file length, names, and control-flow density are review signals, not failures.

## Completion mode

Classify the changed surface, then run the narrowest project-native checks that can disprove completion. Escalate from static/local evidence to integration, user-surface, or dedicated high-impact checks only when the change crosses that boundary.

When the current conversation contains a task contract, use its acceptance tests as outcome evidence without treating the contract as a substitute for project-native runtime, integration, or security checks.

Use the stewardship guard only when a structured project-map signal adds value:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_guard.py \
  --project-root <project-root> \
  --changed-path <project-relative-path> \
  --require-validation <check-name> \
  --validation-result <check-name>=<pass|fail|not-run|skipped> \
  --acceptance-status <pass|fail|not-run|not-required>
```

Pass actual changed paths and observed validation results. Use `--write` only for a requested saved report and `--fail-on-blocked` only for an adopted project/CI policy.

## Capability escalation

Use an already exposed browser, simulator, semantic, or security capability only when it closes a concrete evidence gap. Do not install a tool or dependency to satisfy this Skill; state the unverified surface instead.

## Output

Lead with the verdict. Separate confirmed findings from heuristics, cite commands/evidence, and identify unverified surfaces and remaining risk.

## Read references only when needed

- Read `<skill-dir>/../../shared/references/memory-and-completion-guard.md` only when the completion evidence ladder or Guard status semantics need clarification.
- Read `<skill-dir>/../../shared/references/project-scale-rules.md` only when task topology, repository scale, or structural signals make proportionality ambiguous.
