# Lean v2 Natural Task Scenario Matrix

This matrix is a model-free acceptance contract. It can be checked through static
instructions and public CLI behavior without calling an external model or API.

| Scenario | Authorized behavior | Must not happen | Evidence |
|---|---|---|---|
| Small local fix in a repo with optional docs missing | Inspect relevant files, declare the changed path or explicit acceptance scope, make the scoped fix, run relevant non-destructive validation | Stop solely because optional stewardship docs or tools are absent | Empty/minimal health tests; Guard passes only after scope/evidence is declared |
| Review or diagnosis request | Read and report evidence | Mutate project files | Audit and guard are read-only unless explicit `--write` is passed |
| Explicit fix/build request | Make in-scope local changes and validate | Ask again merely because the action is a safe local edit | Skill/static contract plus CLI dry-run/write boundary tests |
| Complex or drift-prone request | State a compact current-task contract with scope, fact authority, non-goals, evidence, and stop conditions; proceed when already authorized | Persist it by default, turn it into a second approval ceremony, or treat listed actions as new authority | Task-contract documentation and metadata contract tests |
| Push, deploy, package install, or other external/system action | Stop for explicit authorization; Git hints appear only inside a real work tree | Emit an executable/unqualified `git push`, deploy, or install step, or print unusable Git commands outside Git | Plan Git-work-tree forward tests |
| Small edit in a 500-line file | Complete the scoped edit; report size only if relevant | Force a refactor or mark completion high-risk based on line count alone | `test_five_hundred_line_file_is_info_only_and_guard_passes` |
| Existing design system | Preserve the existing system and current task intent | Replace it with a universal platform aesthetic doctrine | Static skill/reference review owned by the prompt-layer tests |
| Durable memory update | Write one structured rule to one default destination; mirror only by explicit flag | Duplicate the rule or automatically fan it out to AGENTS or another destination | Memory forward contract tests |
| Durable memory evidence | Require complete evidence for hard invariants; allow a scoped preference to use one refreshable evidence/detection channel | Promote placeholders into hard policy or force every preference through invariant-level ceremony | Memory persistence safety tests |
| Failed relevant validation or failed acceptance | Return `blocked` with concrete evidence | Claim completion | Guard validation and acceptance tests |
| Declared validation is not run/skipped, or duplicate results conflict | Return `needs-review`, or reject contradictory duplicate evidence | Let a later `pass` overwrite an earlier `fail`, or report `pass` from non-passing evidence | Validation evidence boundary tests |
| No declared scope, validation, acceptance, or current plan | Return `needs-review` with `evidence.unspecified` | Claim completion from an empty evidence envelope | Empty-project Guard test |
| Incomplete durable plan | Return `needs-review` only when selected by exact `--current-plan`; keep other plans as signals | Let an unrelated or malformed plan decide the current outcome or crash Guard | Exact-current-plan and malformed-plan tests |
| Plan create/update/archive | Use YAML-safe metadata, bounded UTF-8 filenames, identical dry-run/write conflict checks, and require `--force` for zero-step plans | Emit invalid frontmatter, exceed common filename limits, or let dry-run promise an impossible write | Plan persistence and forward-contract tests |
| Secret-name fixture in Git | Use `git check-ignore` and `git ls-files`; block tracked or confirmed-unignored env files | Approximate Git ignore rules or read secret contents | Directory/nested-ignore and tracked-env tests |
| Secret-like file inside a skipped build/vendor tree | Use bounded Git pathspecs to find tracked and untracked-unignored `.env*`; treat `.npmrc/.pypirc` as review evidence | Let scanner performance exclusions hide Git-visible secret carriers | Skipped-tree and credential-config tests |
| Secret-name fixture outside Git or with unavailable Git | Return unknown review evidence without reading contents | Treat unknown as safe or as a confirmed blocker | Non-Git env test |
| Secret-bearing argument to any public CLI | Scan every argv token and assignment-shaped adjacent-token reconstruction before argparse or business selection can quote it; safely withhold secret-bearing downstream exceptions | Echo a rejected choice, split assignment, unknown argument, path, text value, or recipe selector | Public-CLI error-safety matrix and Guard programmatic regressions |
| Secret-bearing hand-authored active plan | Validate filename, full carrier, and parsed fields before any partial status, lock, update, report, or archive | Echo plan-derived text, leave a lock/report behind, or copy the secret into an updated/archived carrier | Plan-carrier command matrix and Guard hand-authored-plan regression |
| Source above the bounded complexity-read limit | Stream size/line evidence and emit `analysis-skipped:size-limit` | Silently omit the largest source files or infer complexity | Large-source limit test |
| Final or intermediate symlink/ancestor swap | On POSIX, anchor reads, staged writes, commit, rollback, cleanup, and archive deletion to root/parent dirfds; fail closed on weaker platforms | Read, replace, or delete through a swapped ancestor outside the project | Deterministic read/write/stream/finish swap tests |
| Windows or other non-dirfd runtime | Permit identity-checked read-only audit; refuse every plugin persistence write, deletion, or archive before project directories, staging, or system lock creation | Present path-only mutation as safe, create any temporary artifact, or partially change a target before refusing | Primitive and all-write-CLI capability-preflight tests plus README platform boundary |
| Mixed or ambiguous stack recipe | Require explicit scope/recipe for monorepos, Apple platform ambiguity, Next+backend, or Next+Expo | Treat one marker as authority to impose a root architecture | Recipe-routing tests |
| Minimal bootstrap or intake | Create only the three core files, preserve unknowns, and keep optional systems out unless explicitly requested or evidenced | Inject optional tool products, invented forbidden patterns, or silently accept `--write` without answers | Documentation-contract and scaffold forward tests |
| Alternate `CODEX_HOME` | Resolve official validators below the configured Codex home | Hard-code `~/.codex` and validate against the wrong installation | Metadata contract test |

## Pass criteria

- `pass`: explicit outcome scope/evidence exists, with no blocker and no outcome-relevant review evidence.
- `needs-review`: evidence is incomplete or a relevant code/plan signal needs judgment.
- `blocked`: evidenced serious secret risk, failed relevant validation, or failed acceptance.
- Audit health uses `healthy / needs-review / at-risk / unknown` plus evidence counts;
  numeric health/readiness scores are deprecated and `null`.
- Governance coverage, unavailable optional tools, placeholders, generic names, and file length alone
  never produce `blocked`.
