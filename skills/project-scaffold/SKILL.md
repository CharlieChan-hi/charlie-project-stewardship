---
name: project-scaffold
description: "用户明确要求非覆盖式 scaffold 或缺失文件计划时使用；Use for explicit non-overwriting scaffolding or missing-file plans. 不用于普通编码；Do not use for routine coding."
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
