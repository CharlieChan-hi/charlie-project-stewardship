# Capability Routing

This file records durable routing decisions only. It is not a list of tools every task must invoke.

## Detected project state

- Project type: [[project_type]]
- Stack markers: [[stack_markers]]
- Package manager: [[package_manager]]

## Selection rule

For the current task:

1. Verify which Skills/tools are actually exposed.
2. Prefer the project's native commands and the host's native capabilities.
3. Add one specialized capability only when it closes a real gap.
4. Continue without it when ordinary tools are sufficient.
5. Treat configuration, credentials, authorization, and successful execution as separate facts.

## Detected suggestions

[[capability_suggestions]]

These are suggestions based on repository signals, not requirements.

## Optional adapters

- Browser automation: changed Web behavior or visual/user-flow evidence.
- Simulator/device tools: changed native behavior.
- LSP/Serena: ambiguous symbol relationships or large cross-file refactors.
- Process Skills: genuinely complex planning, debugging, or review where the method adds value.
- Security tools: security-sensitive changed surfaces.
- RTK or other output filters: measured high-volume output with raw recovery.

Do not install, initialize, or globally require optional adapters from this file. Record a route only when it is stable enough to help future agents.
