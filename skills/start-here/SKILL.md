---
name: start-here
description: "兼容旧入口：当用户明确调用 $start-here、第一次使用插件或不知道从哪个核心 Skill 开始时，转到最小项目开工路径。Compatibility entry for first-time use or explicit $start-here requests. Do not invoke implicitly for ordinary project work."
---

# Start Here

This is a compatibility entry, not a separate workflow.

1. Use `$project-bootstrap` in **inspect** or **minimal bootstrap** mode.
2. Start read-only and show the smallest useful file set.
3. If the current request already authorizes the scoped local files, write them without another confirmation; otherwise preview first.
4. Route later needs only when they arise:
   - ambiguity-sensitive current work → `$task-contract`;
   - durable rule → `$project-memory`;
   - health/completion evidence → `$project-health`;
   - durable handoff → `$plan-relay`.

Do not require full documentation, a fixed process Skill, or an exhaustive reading chain.

For the canonical workflow, read `<skill-dir>/../project-bootstrap/SKILL.md`.
