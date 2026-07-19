---
name: architecture-audit
description: "显式 $architecture-audit：只读架构审查；Explicit read-only architecture audit. 不自动门禁或写重构；No automatic gates/refactor writes."
---

# Architecture Audit

This compatibility entry delegates to `$project-health` in **audit mode**.

Run the deterministic audit read-only:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_audit.py \
  --project-root <project-root>
```

Then inspect relevant source before confirming a finding. Treat line counts, generic names, root clutter, and control-flow density as signals, not defects by themselves.

Do not modify project files or save reports unless the user explicitly requests that additional action. Present confirmed findings as: verdict → evidence → impact → right-sized recommendation.

For the canonical risk model, read `<skill-dir>/../project-health/SKILL.md`.
