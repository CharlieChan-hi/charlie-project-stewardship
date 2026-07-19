---
name: capability-routing
description: "用户明确要求审计或更新工具/Skill 路由表时使用；Use for explicit capability-map maintenance. 不用于日常实现或自动安装工具；Do not use for routine work or automatic tool installation."
---

# Capability Routing

Keep routing capability-based and optional.

1. Inspect the current session's exposed Skills and tools; do not infer availability from a project file or product name.
2. Match only the task-relevant capability.
3. Prefer the host's native capability and ignore overlapping adapters for the current task. Disable an installed adapter only when the user explicitly requests that separate state change.
4. Continue with normal project methods when no special capability is needed.
5. Record a route in `docs/capability_routing.md` only when it is durable and the user requested the update.

Browser automation, LSP/Serena, RTK, MCP servers, and process Skills are optional. Do not install, initialize, or require them from this entry. A tool's existence does not prove credentials, permissions, or successful execution.

Read `<skill-dir>/../../shared/references/official-capability-routing.md` for the capability matrix.
