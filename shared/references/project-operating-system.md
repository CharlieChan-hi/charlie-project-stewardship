# Lean Project Meta-Harness

Use this reference when designing or evaluating the project's agent-facing context.

## Purpose

A modern harness should make the repository legible, preserve true constraints, expose useful capabilities, and turn verified failures into durable improvements. It should not prescribe every reasoning step to a capable model.

Keep three layers separate:

1. **Invariant kernel** — safety, authorization, secrets, preservation of existing work, and truthful evidence.
2. **Project map** — where relevant context, code, tests, decisions, and durable rules live.
3. **Optional adapters** — specialized Skills/tools selected only when the current task needs them.

## Context on demand

`AGENTS.md` is a short map, not a mandatory reading syllabus. Read the closest applicable instructions, relevant source/tests, and only the docs needed for the decision.

Typical roles:

- `docs/project_intake.md` — confirmed product/platform constraints;
- `docs/project_preferences.md` — durable rules and verified learnings;
- `docs/architecture.md` / `docs/source_structure.md` — structural work;
- `docs/decisions/` — rationale worth preserving;
- `plans/active/` — explicitly persisted unfinished work;
- `architecture_reports/latest/` — audit artifacts, not startup context;

Missing optional files do not block ordinary work.

## Harness-engineering feedback loop

Use repository evidence to improve the environment:

```text
observe failure or friction
  → identify the missing constraint, tool, test, or context
  → fix the smallest root cause
  → verify the result
  → encode only reusable learning
  → periodically refresh or remove stale guidance
```

Prefer executable checks, tests, clear tool errors, and discoverable project maps over more prompt prose. Do not turn a one-off mistake into a global rule.

## Escalation ladder

1. Use project-native commands and the host's native tools.
2. Add one exposed specialist capability when it closes a real gap.
3. Persist a plan or learning only when continuity or reuse is explicit.
4. Introduce an external system only after measured need and authorization.

Each step should add observable value. Capability presence, configuration, credentials, authorization, and successful execution are separate facts.

## Design basis and source ranking

Use sources according to authority; inspiration is not a mandate.

### Official OpenAI guidance

- [OpenAI Harness Engineering](https://openai.com/zh-Hans-CN/index/harness-engineering/)
- [GPT-5.6 Prompting Guidance](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6)
- [GPT-5.6 latest model guide](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6)
- [Codex: Build Skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex: Build Plugins](https://learn.chatgpt.com/docs/build-plugins)

These define the primary model, Skill, plugin, and harness expectations.

### Community-created reference

- [GitHub awesome-copilot harness-engineering Skill](https://github.com/github/awesome-copilot/blob/main/skills/harness-engineering/SKILL.md) is community-created material in GitHub's repository. Treat it as a useful implementation pattern, not official OpenAI policy.

### External inspiration

- [Ponytail](https://github.com/DietrichGebert/ponytail) and [Karpathy guideline compilation](https://github.com/multica-ai/andrej-karpathy-skills): assumption clarity, scope control, reuse, and goal-based verification.
- [Compound Engineering](https://github.com/EveryInc/compound-engineering-plugin) and [gstack](https://github.com/garrytan/gstack): feedback loops, review/QA routing, and reusable learning; their full role/process systems are not defaults here.
- [Serena](https://github.com/oraios/serena) and [RTK](https://github.com/rtk-ai/rtk): optional semantic navigation and output compression.
- [agent-browser](https://github.com/vercel-labs/agent-browser) and [Playwright MCP](https://github.com/microsoft/playwright-mcp): optional browser observability and verification.

External claims and metrics require independent validation before they influence project policy.
