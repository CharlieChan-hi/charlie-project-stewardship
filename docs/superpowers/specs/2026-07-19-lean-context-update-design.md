# Lean Context Update Design

## Goal

Reduce the plugin's discovery and generated-project context cost without weakening its five core outcomes, six explicit compatibility entries, deterministic safety controls, or release/install traceability.

The target is a compatibility-preserving Codex update for capable tool-using models. The package stays behavior-based rather than depending on a model ID. The user calls the current environment `5.6-sol-ultra`; official documentation endpoints were unavailable during this design pass, so that label is not treated as a public specification.

## Baseline

The source of truth is Git commit `291f0cb4f5379e48cc09e61fe9e59d15ceebd9f9`, base version `2.1.2`.

- 5 core Skills and 6 explicit-only compatibility entries.
- 4,125 bytes of Skill frontmatter, approximately 1,031 tokens at a four-byte proxy.
- 23,368 bytes / 405 lines across all Skill bodies.
- Minimal bootstrap templates total 142 lines across three files.
- 156 deterministic tests pass through the complete plugin validator.
- The installed cache and marketplace snapshot resolve to the same Git revision.

These are measurement proxies, not claims about exact host token injection or wall-clock latency.

## Options Considered

### A. Keep 2.1.2 unchanged

This preserves all behavior but leaves broad `task-contract` discovery text, eleven catalog entries with verbose bilingual descriptions, and generic generated guidance unchanged.

### B. Compatibility-preserving context reduction

Keep all eleven public names and all deterministic CLIs. Tighten discovery descriptions, narrow implicit task-contract routing, shorten only duplicated prompt guidance, and reduce the three minimal templates while retaining their existing placeholders and ownership. Add deterministic budgets and controlled model-behavior A/B checks.

This is the selected design.

### C. Five-Skill major release

Remove compatibility entries from the live catalog and move old names to an optional legacy package. This has the largest theoretical catalog reduction but breaks explicit old prompts and requires a separate major-version migration. It is outside this update.

## Design

### Catalog and routing

- Preserve all five core and six compatibility Skill identities.
- Preserve implicit invocation for core Skills and explicit-only policy for compatibility entries.
- Express each frontmatter description as the smallest useful bilingual trigger plus a concrete non-trigger.
- Remove generic `multi-step` and `high-impact` matching from `task-contract`; route it when conflicting sources, ambiguous acceptance, batch review, or an authorization boundary makes drift materially likely.
- Keep routine scoped edits, explanations, ordinary one-session plans, and routine completion handoffs outside stewardship workflows.

### Invoked Skill context

- Keep unique safety and persistence mechanics unchanged.
- Remove prose only where the same boundary is already established by the Skill's trigger or a direct reference.
- Keep references one hop away and conditional.
- Do not change deterministic script interfaces during this prompt-layer experiment.

### Generated project context

- Preserve the minimal bootstrap's three-file compatibility contract.
- Shorten the generated `AGENTS.md` to a project snapshot, task-scoped context map, a compact invariant kernel, and proportionate validation.
- Keep `docs/project_intake.md` focused on confirmed or explicitly unresolved project facts.
- Keep `docs/project_preferences.md` as the memory carrier and remove generic agent coaching that is not a durable project preference.
- Preserve every placeholder and heading consumed by existing scripts and tests.

### Regression budgets

Add deterministic tests that enforce:

- the exact five-core/six-compatibility public surface;
- compatibility entries remain explicit-only;
- Skill discovery metadata stays below the frozen B budget;
- minimal generated templates stay below the frozen B line/byte budget;
- core trigger and non-trigger phrases remain represented;
- canonical manifest identity, prompt count/length, and marketplace uniqueness remain valid.

Budgets apply only to this plugin's own prompt surface. They must not be reused as generic project file-length rules.

### Release and activation

- Do not modify active Claude configuration.
- Keep the Claude source manifest read-only in this Codex run; use one Codex cachebuster suffix after all gates pass.
- Push only the winning source to `origin/main`.
- Refresh the configured Git marketplace and install through official Codex plugin commands; never edit the cache manually.
- Because the current Codex feature gate reports `plugins = false`, persistently enable the Codex plugin feature only as the necessary activation step authorized by the user's request to make this plugin effective.
- Prove activation with source SHA, marketplace revision, cache SHA, installed version/source, and a new-thread behavior check boundary.

## A/B Protocol

A is the untouched Git baseline. B is an isolated candidate copy. The experiment freezes identical prompts, project fixtures, permission profile, available tools, and scoring before revealing the lane mapping.

The scored dimensions are:

- routing and non-trigger accuracy: 12%;
- functional quality: 15%;
- original task success: 20%;
- safety and authorization: 25%;
- context cost: 8%;
- tool and step efficiency: 6%;
- critical-path proxy: 4%;
- compatibility: 5%;
- recoverability: 5%.

B is rejected regardless of total score if any deterministic validator fails, a protected write or secret boundary regresses, a core Skill or compatibility entry fails, a negative-control task triggers stewardship, or context/critical-path cost does not improve materially.

Temporary candidate copies, blinded labels, and raw traces are task-created test artifacts and are removed after scoring. The repository retains only the compact final benchmark result and permanent regression tests.

## Success Criteria

- Complete validator passes with all existing and new tests.
- Five core Skills and six explicit compatibility entries remain usable.
- No unauthorized write, secret handling, symlink, non-overwrite, or recovery regression.
- Catalog frontmatter bytes decrease by at least 20%.
- Minimal bootstrap template bytes or lines decrease by at least 20%.
- Blinded multi-agent A/B gives B a higher weighted score with no hard-gate failure.
- Git `diff --check`, local install verification, GitHub push, and remote SHA verification pass.

## Non-goals

- No global `AGENTS.md` changes.
- No active Claude configuration, Skill, plugin, or marketplace changes.
- No new dependency, external service, hosted benchmark, OpenAI directory publication, GitHub Release, or unrelated refactor.
- No claim that a UI label or private-looking model slug is an official public model specification.
