# Agent Harness

This optional document explains how agents should use the project map without turning it into a fixed ceremony.

## Operating model

Use a short adaptive loop:

1. Understand the request, applicable instructions, relevant code, and current user changes.
2. Choose the smallest coherent action and the tools already available.
3. Gather evidence that can disprove the completion claim; report any remaining gap.

The amount of planning, review, and validation should follow task risk. A one-line documentation fix does not need the same process as a migration, security change, or cross-module refactor.

## Capability selection

- Prefer project-native commands and the host's already exposed tools.
- Use a specialized Skill or adapter only when it adds a missing capability or important domain knowledge.
- Avoid duplicate file/search/shell tools when the host already provides them.
- Never infer credentials or permissions from tool availability.
- Do not install browser tools, LSP servers, task trackers, MCP servers, or output filters automatically.

See `docs/capability_routing.md` only when a durable route needs documenting.

## Change discipline

- Preserve unrelated work and existing conventions.
- Ask only when missing information materially changes result, scope, or risk.
- Keep safety/authorization boundaries strict; leave implementation choices flexible where several approaches are valid.
- Update durable docs only when the change actually alters project rules, architecture, or public behavior.

## Evidence and handoff

Select evidence from the changed surface: targeted test, typecheck/lint, build, browser/simulator flow, integration check, or security review. If a check is unavailable, state the unverified area rather than adding a dependency.

Persist unfinished work in `plans/active/` only when the user explicitly wants crash-resistant or cross-machine handoff.
