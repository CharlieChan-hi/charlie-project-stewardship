# Contributing

Thanks for helping improve Charlie Project Stewardship.

## Before changing the plugin

- Read [`AGENTS.md`](AGENTS.md) and the material directly relevant to the change.
- Keep the harness thin: encode true invariants and observable evidence, while leaving implementation choices to the host Agent.
- Preserve existing CLI behavior unless a correctness or safety flaw requires a precise failure.
- Do not add runtime dependencies, external services, destructive behavior, or active Claude configuration changes without prior discussion.
- Never include real secrets, private project data, machine-specific absolute paths, or unlicensed assets.

For a substantial behavior or format change, open an issue first so compatibility and migration can be discussed.

## Validation

Run the self-contained release gate outside Codex:

```bash
python3 shared/scripts/validate_stewardship_plugin.py --portable
```

It validates public metadata, compiles the Python sources, runs the behavior and security regressions, and executes the CLI forward checks. Contributors working inside Codex should also run the complete plugin gate, which adds the official Skill and plugin validators:

```bash
python3 shared/scripts/validate_stewardship_plugin.py
```

Pull requests should explain the user-visible outcome, compatibility impact, tests run, and any surface that could not be verified.
