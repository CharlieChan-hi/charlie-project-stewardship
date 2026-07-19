---
name: completion-guard
description: "用户明确要求交付前证据检查时使用；Use for explicit pre-completion evidence checks. 不用于每次编辑后的自动检查；Do not run automatically after routine edits."
---

# Completion Guard

This compatibility entry delegates to `$project-health` in **completion mode**.

1. Classify the changed surface and risk.
2. Run project-specific tests, build, browser/simulator, or security checks only when relevant and available.
3. Optionally run the stewardship signal scan:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_guard.py \
  --project-root <project-root> \
  --changed-path <project-relative-path> \
  --require-validation <check-name> \
  --validation-result <check-name>=<status> \
  --acceptance-status <status>
```

4. Separate confirmed failures from heuristic review signals.
5. Use `--write` only for an explicitly requested report and `--fail-on-blocked` only for a project/CI policy that already adopted it.

This entry does not make optional docs, a file-length threshold, or an unavailable tool a universal blocker. Read `<skill-dir>/../project-health/SKILL.md` for the canonical workflow.
