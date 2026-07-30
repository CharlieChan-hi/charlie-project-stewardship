# Lean Context Update Implementation Plan

> **Status:** Historical implementation record. The update has landed; unchecked boxes below preserve the original plan and are not current task state.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a compatibility-preserving plugin update that reduces catalog and generated-project context by at least 20% without weakening routing, safety, persistence, or installation behavior.

**Architecture:** Keep the five core Skills, six compatibility entries, and all deterministic CLIs. Change only prompt-layer discovery text and minimal templates, guard the result with deterministic budgets, then select the winner through a blinded A/B before updating the canonical checkout, Codex cachebuster, installed plugin, and GitHub main.

**Tech Stack:** Markdown Skill instructions, YAML presentation metadata, Python 3.9+ standard-library tests and validators, Codex plugin CLI, Git.

## Global Constraints

- Source of truth is `$HOME/Documents/SKILL/Plugin/charlie-project-stewardship`; A is Git commit `b995afb` with the pre-change plugin content inherited from `291f0cb`.
- Preserve five core Skills and six explicit-only compatibility Skills.
- Do not change deterministic CLI interfaces or active Claude configuration.
- No new dependency, destructive cleanup, secret-file read, OpenAI directory publication, GitHub Release, or unrelated refactor.
- B must reduce both catalog frontmatter and minimal-template cost by at least 20% and pass every existing/new gate.
- Only the A/B winner may be copied into the canonical checkout and pushed.

---

### Task 1: Freeze context and metadata regression gates

**Files:**
- Create in candidate: `tests/test_context_budget_contracts.py`
- Modify in candidate: `tests/test_metadata_contracts.py`
- Modify in candidate: `shared/scripts/validate_stewardship_plugin.py`

**Interfaces:**
- Consumes: the existing `skills/*/SKILL.md`, three minimal templates, two plugin manifests, and public marketplace JSON.
- Produces: deterministic budget tests and stricter metadata errors consumed by the full validator.

- [ ] **Step 1: Write failing context-budget tests in the isolated B copy**

```python
class ContextBudgetContractTests(unittest.TestCase):
    def test_skill_catalog_frontmatter_stays_below_b_budget(self) -> None:
        total = sum(frontmatter_bytes(path) for path in SKILL_FILES)
        self.assertLessEqual(total, 3300)

    def test_minimal_templates_stay_below_b_budget(self) -> None:
        total_lines = sum(len(path.read_text().splitlines()) for path in MINIMAL_TEMPLATES)
        self.assertLessEqual(total_lines, 105)
```

- [ ] **Step 2: Run the new tests against untouched A to confirm RED**

Run: `python3 -m unittest tests.test_context_budget_contracts -v`

Expected: both budget tests fail while existing tests remain unchanged.

- [ ] **Step 3: Add strict metadata cases before changing the validator**

Cover canonical manifest name, one canonical marketplace entry, 1–3 non-empty default prompts of at most 128 characters, `skills == "./skills/"`, and package-confined icon paths that exist.

- [ ] **Step 4: Run the metadata test module to confirm only the new cases fail**

Run: `python3 -m unittest tests.test_metadata_contracts -v`

Expected: current valid metadata test passes; injected invalid fixtures fail to be rejected until the validator is updated.

- [ ] **Step 5: Implement the minimal validator checks and rerun metadata tests**

Run: `python3 -m unittest tests.test_metadata_contracts -v`

Expected: all metadata tests pass.

### Task 2: Tighten discovery and task routing

**Files:**
- Modify: `skills/*/SKILL.md` frontmatter descriptions
- Modify: `skills/task-contract/SKILL.md`
- Modify only if required for consistent UI copy: `skills/*/agents/openai.yaml`

**Interfaces:**
- Consumes: the frozen five-core/six-compatibility routing contract.
- Produces: smaller bilingual discovery metadata with unchanged Skill names and invocation policy.

- [ ] **Step 1: Shorten each description to one positive trigger and one non-trigger**

Keep Chinese and English search terms, but remove policy detail already present in the Skill body.

- [ ] **Step 2: Narrow `task-contract` discovery**

Remove generic `multi-step` and `high-impact` triggers. Keep conflicting facts/sources, unclear acceptance, batch review, and material authority/scope drift as positive triggers.

- [ ] **Step 3: Keep compatibility entries explicit-only and core entries implicit**

Run: `python3 -m unittest tests.test_metadata_contracts tests.test_context_budget_contracts -v`

Expected: routing and catalog budget tests pass.

- [ ] **Step 4: Review the Skill diff for lost unique boundaries**

Check read-only precedence, non-overwrite behavior, secret handling, durable/local synchronization, and project-native validation remain represented in their owning Skill or direct reference.

### Task 3: Reduce generated minimal context without changing file contracts

**Files:**
- Modify: `shared/assets/templates/AGENTS.md`
- Modify: `shared/assets/templates/docs-project_intake.md`
- Modify: `shared/assets/templates/docs-project_preferences.md`
- Modify: `tests/test_documentation_contracts.py`

**Interfaces:**
- Consumes: placeholder names used by `project_steward_templates.py` and memory headings used by `project_steward_memory.py`.
- Produces: the same three minimal files with less generic prose and the same script-facing placeholders/headings.

- [ ] **Step 1: Add failing assertions for required placeholders and lean output**

Assert all current placeholder names remain, `Confirmed rules`, `Structured rules`, and `Pending confirmation` remain, generic bootstrap coaching is absent, and minimal generated output is at or below the frozen budget.

- [ ] **Step 2: Run documentation and context tests to confirm RED**

Run: `python3 -m unittest tests.test_documentation_contracts tests.test_context_budget_contracts -v`

- [ ] **Step 3: Rewrite the three templates around project facts**

Keep a short snapshot, task-scoped map, four true invariant classes, project-specific intake fields, the structured memory schema, and material open questions. Remove duplicated platform, agent-personality, and optional-integration coaching.

- [ ] **Step 4: Run scaffold, memory, documentation, and context tests**

Run: `python3 -m unittest tests.test_documentation_contracts tests.test_forward_contracts tests.test_persistence_safety tests.test_context_budget_contracts -v`

Expected: all pass; generated minimal scaffold still contains exactly the expected three files and remains non-overwriting.

### Task 4: Run blinded A/B and select the winner

**Files:**
- Create temporarily: `$HOME/Desktop/Plugin-AB-Test/lane-X/`
- Create temporarily: `$HOME/Desktop/Plugin-AB-Test/lane-Y/`
- Create temporarily: blinded prompts, scores, and sanitized traces beneath that directory
- Retain only if B wins: `docs/benchmarks/2026-07-19-lean-context-ab.md`

**Interfaces:**
- Consumes: A from Git, B candidate, frozen natural-task matrix, identical permissions/tools/prompts.
- Produces: blind routing/quality/safety/context/efficiency/compatibility/recovery scores and a winner decision.

- [ ] **Step 1: Randomize A/B to opaque lanes and record artifact hashes separately**

Do not expose `current`, `candidate`, `A`, or `B` to runner or judge agents.

- [ ] **Step 2: Run negative controls, core positive routes, compatibility aliases, and authorization flips**

At minimum include routine edit, one-session plan, conflicting sources contract, bootstrap inspect/write, durable memory, durable plan, health audit/completion, all six aliases, read-only secret boundary, and local-versus-push authorization.

- [ ] **Step 3: Have independent agents score outputs without lane identity**

Use the frozen weights: routing 12, functional 15, task success 20, safety 25, context 8, efficiency 6, critical path 4, compatibility 5, recoverability 5.

- [ ] **Step 4: Enforce hard gates before computing preference**

Reject B on any validator, authorization, secret, read-only, core, alias, recoverability, or key negative-control failure.

- [ ] **Step 5: Reveal lanes and retain only the winner**

Write one compact benchmark result with artifact hashes, scenario counts, dimension scores, hard-gate results, context deltas, limitations, and winning lane. Remove the temporary A/B directory after integration.

### Task 5: Integrate and verify the winner

**Files:**
- Modify canonical checkout only with files from the winning candidate
- Modify: `docs/ai_project_context.md`
- Modify: `.codex-plugin/plugin.json` through the official cachebuster helper only

**Interfaces:**
- Consumes: winning candidate and benchmark decision.
- Produces: validated canonical source with one Codex build-metadata suffix.

- [ ] **Step 1: Apply only the winning candidate diff to the canonical checkout**

Use `apply_patch`; do not copy `.git`, caches, logs, or raw traces.

- [ ] **Step 2: Remove unverified model-name coupling from normative runtime text**

Describe compatibility through observable agent capabilities; record the actual evaluation environment only in the benchmark report.

- [ ] **Step 3: Run the complete gate before cachebuster update**

Run: `python3 shared/scripts/validate_stewardship_plugin.py`

Expected: all tests and official validators pass.

- [ ] **Step 4: Refresh one Codex cachebuster and rerun the complete gate**

Run: `python3 shared/scripts/validate_stewardship_plugin.py --update-cachebuster`

Expected: Codex version has one `+codex.*` suffix; Claude source manifest remains unchanged; all gates pass.

- [ ] **Step 5: Verify diff quality and requirements**

Run: `git diff --check`

Expected: no whitespace errors; every changed file maps to this plan.

### Task 6: Commit, push, install, and prove activation

**Files/State:**
- Git branch: `main`
- Remote: `origin` → `https://github.com/CharlieChan-hi/charlie-project-stewardship.git`
- Codex feature: `features.plugins`
- Codex Git marketplace and installed cache

**Interfaces:**
- Consumes: fully validated winner.
- Produces: remote source SHA, matching marketplace/cache SHA, and enabled installed plugin for new threads.

- [ ] **Step 1: Commit the exact validated winner**

Run: `git status --short`, inspect the diff, stage exact paths, then `git commit -m "perf: reduce stewardship context overhead"`.

- [ ] **Step 2: Push main and verify the remote SHA**

Run: `git push origin main`, then `git ls-remote origin refs/heads/main`.

Expected: remote SHA equals local `HEAD`.

- [ ] **Step 3: Persistently enable the Codex plugins feature and add or upgrade the Git marketplace**

Edit only the existing `features.plugins` value, then use `codex plugin marketplace add CharlieChan-hi/charlie-project-stewardship --ref main --json` or upgrade the already configured marketplace.

- [ ] **Step 4: Install the plugin through the official CLI**

Run: `codex plugin add charlie-project-stewardship@charlie-project-stewardship --json`.

- [ ] **Step 5: Verify installed metadata and revision with plugins enabled**

Run: `codex plugin list --enable plugins --available --json` and compare source SHA, marketplace revision, cache Git HEAD, version, installed, and enabled fields.

- [ ] **Step 6: State the new-thread boundary**

The current thread cannot prove fresh discovery. Final handoff must tell the user that a newly opened Codex thread is the last behavior-level pickup check.
