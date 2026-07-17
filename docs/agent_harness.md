# Agent Harness

## Operating Model

The harness supplies context and feedback; it does not choose every move for the model.

1. Read the nearest applicable `AGENTS.md` and inspect the files involved in the request.
2. Recover project facts from the repository before asking the user to repeat them.
3. Identify the outcome, approval boundary, true invariants, and success evidence.
4. Let the model select the smallest useful workflow and the tools actually available.
5. Validate in proportion to the changed surface and disclose anything not verified.

There is no mandatory global chain of process Skills. Planning, debugging, browser testing,
semantic indexing, multi-Agent work, and persistent task graphs are selected when their expected
value exceeds their context and coordination cost.

## Feedback Ladder

When an error repeats, improve the narrowest durable layer that would have caught it:

1. clarify a local fact or acceptance criterion;
2. add a focused regression test or lint/type check;
3. add a deterministic script or CI gate;
4. record a scoped failure memory with evidence, detection, and expiry;
5. change a global instruction only for a genuine cross-project invariant.

Do not turn one incident into a universal prompt rule. Prefer executable feedback over prose when
the condition can be checked mechanically.

## Evidence Selection

- Local logic or documentation change: focused tests/checks and diff review.
- Web behavior: browser/DOM/console evidence when a browser capability is available.
- Cross-file refactor: build/type checks and semantic reference evidence where useful.
- Security-sensitive change: threat-specific checks and explicit residual risk.
- External mutation: approval at the action boundary plus post-action verification.

## Handoff

Report the outcome, files changed, evidence collected, assumptions, and remaining risks. Refresh
the Codex cachebuster only after the complete local validation gate passes.
