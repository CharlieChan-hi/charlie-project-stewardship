---
name: project-scaffold
description: "兼容旧入口：当用户明确要求运行现有非覆盖式 scaffold、补缺失治理文件或生成全量文档计划时用。Compatibility entry for explicit deterministic scaffolding. Do not use as the default new-project path or for ordinary coding work."
---

# Project Scaffold

This compatibility entry exposes the existing non-overwriting scaffold.

- Prefer `$project-bootstrap` with `--minimal` for normal onboarding.
- Use this entry only when the user explicitly requests the extended scaffold or a deterministic missing-file plan.
- Read-only or planning-only requests override all writes.
- Never delete, move, rename, or overwrite existing project files.

Preview:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_scaffold.py \
  --project-root <project-root>
```

If the current request explicitly authorizes the scoped local scaffold, add `--write` without another confirmation; otherwise preview first. Different existing targets are preserved and reported. Add `--adoption-plan` only when the user explicitly wants one consolidated merge plan.

Read `<skill-dir>/../../shared/references/project-operating-system.md` only when the request also asks to design or evaluate the agent-facing harness; skip it when previewing or running the existing scaffold.
