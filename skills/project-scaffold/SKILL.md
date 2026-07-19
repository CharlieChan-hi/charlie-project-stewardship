---
name: project-scaffold
description: "用户明确调用 $project-scaffold 预览非覆盖式 scaffold 或缺失文件时，转到 project-bootstrap minimal；Use for explicit legacy scaffold previews routed to project-bootstrap minimal. 不用于普通编码；Do not use for routine coding."
---

# Project Scaffold

This compatibility entry delegates ordinary missing-context previews to the
`$project-bootstrap` minimal path while preserving the extended scaffold on explicit request.

- Use `$project-bootstrap` semantics with `--minimal` for normal onboarding or a general missing-file preview.
- Use this entry only when the user explicitly requests the extended scaffold or a deterministic missing-file plan.
- Read-only or planning-only requests override all writes.
- Never read secret-capable file contents; inspect only presence and ignore/tracking metadata.
- Never delete, move, rename, or overwrite existing project files.

Preview:

```bash
python3 <skill-dir>/../../shared/scripts/project_steward_scaffold.py \
  --project-root <project-root> \
  --minimal
```

Omit `--minimal` only when the user explicitly requests the extended scaffold. If the current request explicitly authorizes the scoped local scaffold, add `--write` without another confirmation; otherwise preview first. Different existing targets are preserved and reported. Add `--adoption-plan` only when the user explicitly wants one consolidated merge plan.

Read `<skill-dir>/../../shared/references/project-operating-system.md` only when the request also asks to design or evaluate the agent-facing harness; skip it when previewing or running the existing scaffold.
