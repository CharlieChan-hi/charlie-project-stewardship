# Capability Routing

This file records how the plugin chooses supporting capabilities without duplicating the host's
native routing or freezing a list of fashionable tools.

## Decision Order

1. Use the repository's existing commands, conventions, and already-exposed host tools.
2. Use standard library or an already-installed dependency when it solves the problem cleanly.
3. Select a task-specific official Skill only when its instructions materially improve this task.
4. Probe optional external capabilities only when the change surface justifies them.
5. Ask before installing, enabling, authenticating, or causing external side effects.

Skill/plugin presence, tool exposure, credentials, account authorization, and a successful call are
five different facts. Report only what was actually observed.

## Optional Adapters

- Browser/Playwright/agent-browser: UI behavior, DOM, console, network, screenshots, or a real user
  journey needs evidence. Skip for non-UI work.
- LSP/Serena-style semantics: large repositories or cross-file symbol relationships make text
  search ambiguous. Skip for small, local changes.
- RTK-style compression: measured command output is large enough to justify lossy-risk controls.
  Preserve exit codes and original failures; unknown output passes through unchanged.

Do not emulate these tools in prompt prose and do not recommend installing all of them. Core
bootstrap, task-contract, memory, health, and relay workflows must degrade cleanly when none is
present.

## Domain Guidance

For plugin/Skill authoring, web, Apple, Expo, security, design, deployment, or framework-specific
work, use current official guidance when the task needs it. Preserve the target project's existing
design system and deployment constraints; platform-native is a preference with evidence, not an
automatic rewrite mandate.
