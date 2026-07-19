---
name: architecture-audit
description: "用户明确要求只读架构审计或结构体检时使用；Use for explicit read-only architecture audits. 不用于自动门禁或写重构；Do not use for automatic gates or refactor writes."
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
