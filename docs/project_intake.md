# Project Intake

## Confirmed Summary

- Project name: Charlie Project Stewardship
- Product goal: Provide a lightweight stewardship harness that improves project continuity and
  verification without suppressing a capable model's judgment.
- Target users: Individual developers and small teams using coding Agents across projects,
  sessions, or machines.
- Platform: local multi-Skill plugin, with Codex presentation metadata and portable Skill bodies.
- Preferred source structure recipe: custom plugin structure.

## Acceptance Criteria

- A safe local fix can proceed without being blocked by absent optional governance files.
- Existing repositories are inspected before questions or scaffolding; only material gaps are
  proposed.
- Durable rules are scoped, evidenced, deduplicated, and refreshable.
- Plan steps keep stable identity across edits and concurrent writers cannot silently overwrite.
- Audit and completion status reflect real risk and validation, not template adoption.
- Optional integrations are capability-detected and never installed implicitly.
- All write paths are non-overwriting or explicit, atomic, and project-root confined.

## Product Boundaries

No application UI is generated. The plugin does not impose a framework, design language, source
tree, CI provider, browser stack, LSP, or task database. It can recommend a current official
domain capability when repository evidence and the requested outcome make that useful.

Review requests remain read-only. Explicit create/fix/update requests authorize safe local writes
within scope, but installation, deployment, publishing, push, permissions, and destructive changes
retain their own approval boundaries.

## Forbidden Patterns

- Mandatory full-document read chains or one fixed process Skill stack.
- Treating file length, missing `AGENTS.md`, or placeholders as universal blockers.
- Project-health scores that reward the plugin's own generated files.
- Automatic promotion of a preference into a global hard rule.
- Shell snippets that interpolate untrusted paths or messages without safe quoting.
- Silent fuzzy matching, line-number record identity, non-atomic writes, or symlink escape.
