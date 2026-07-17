---
name: completion-guard
description: "兼容旧入口：当用户明确调用旧 completion guard 或要求在重要改动交付前检查证据时，转到 project-health 的 completion 模式。Compatibility entry for explicit pre-completion evidence checks. Do not run automatically after every edit."
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
