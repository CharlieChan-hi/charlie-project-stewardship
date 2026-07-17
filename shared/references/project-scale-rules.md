# Project Scale and Risk Signals

Use these signals to keep structure and validation proportional. They guide judgment; they are not fixed gates.

## Task topology first

Classify the current task before the whole repository:

| Task shape | Typical response |
|:---|:---|
| Local, reversible, low-impact | Inspect relevant files, make the focused change, run a targeted check |
| Multi-file or behavior-changing | Small plan, affected-callers review, relevant tests |
| Cross-module, stateful, UI/integration | Explicit impact map and integration/browser/simulator evidence |
| Security, permissions, migration, deploy, shared state | Stronger review, recovery path, and required authorization |

A large repository can still contain a low-risk edit; a tiny repository can contain a high-risk migration.

## Project growth signals

Add structure only when evidence shows a need:

- a file repeatedly receives unrelated changes;
- several features duplicate the same logic;
- agents or contributors repeatedly cannot find ownership;
- module boundaries or dependency direction are ambiguous;
- validation setup is routinely rediscovered;
- decisions keep reopening because their rationale is absent;
- concurrent work needs explicit dependencies or ownership.

File length, generic names, folder count, and control-flow density are prompts to inspect responsibility. None is a defect or stop condition by itself.

## Right-sized context

### Prototype or small app

Usually sufficient:

- short `AGENTS.md`;
- confirmed intake/preference notes when needed;
- existing source/tests;
- project-native run and validation commands.

Avoid empty enterprise folders, long policy docs, and external task systems.

### Growing project

Consider architecture/source maps, decision records, and local folder instructions only where ambiguity has recurred. Add deterministic checks for repeated failures.

### Multi-package or concurrent project

Document public boundaries and ownership. Consider a durable dependency graph only when several agents, machines, or long-running work items make a flat plan insufficient.

## Evolution rule

Evolve after observed friction, not because a template or ecosystem project offers a larger structure. Remove or refresh guidance when the project no longer matches it.
