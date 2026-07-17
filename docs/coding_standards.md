# Coding Standards

## Python Scripts

- Use the Python standard library only unless a dependency is explicitly approved.
- Keep inspection read-only. Write commands require explicit write intent and remain confined to
  the resolved target project root.
- Reject or safely handle symlinks that escape the project. Never read `.env` or other secret
  contents; filename/policy checks are enough.
- Use stable record identifiers, exact matching, atomic replace, and a bounded lock or conflict
  check for mutable plans and memory.
- Preserve legacy input compatibility where safe; fail clearly on ambiguous or invalid input.
- Keep generated Markdown in templates and optional source layouts in recipe JSON.
- Preserve meaningful exit codes and make JSON output stable enough for tests and automation.

## Skills and Metadata

- Descriptions state the trigger, boundary, and important non-trigger cases.
- Core Skills may be implicitly invoked when the user intent is precise; compatibility and
  optional-integration Skills are explicit-only.
- `agents/openai.yaml` is quoted, concise, and names the exact `$skill-name` in its starter prompt.
- Detail belongs in a directly linked reference; do not duplicate a universal process in every
  Skill.

## Tests

- Use temporary project fixtures; never point write tests at the source plugin or user projects.
- Cover happy paths, repeat runs, malformed state, concurrency/conflict behavior, path traversal,
  symlink escape, legacy compatibility, and truthful report status.
- A validator must assert outcomes, not merely that commands exit successfully.
