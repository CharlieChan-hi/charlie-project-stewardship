---
name: architecture-audit
description: "兼容旧入口：当用户明确要求只读架构审计、面条代码排查或结构体检时，转到 project-health 的 audit 模式。Compatibility entry for explicit read-only architecture audits. Do not use as an automatic gate or to write refactors."
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
