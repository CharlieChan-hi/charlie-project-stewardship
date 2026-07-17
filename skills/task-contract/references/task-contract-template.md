# Task Contract Template

Use only the fields that materially constrain execution, but keep their names stable when a structured or persisted contract is needed.

```yaml
mode: plan | execute | review | diagnose | monitor
objective: <one observable outcome>

allowed_paths:
  - <project-relative path or explicitly scoped location>
allowed_actions:
  - <read, edit, create, run checks, or separately authorized side effect>
non_goals:
  - <adjacent work that is deliberately excluded>

source_of_truth:
  - fact: <fact class>
    source: <authoritative file, system, user decision, or observed state>
derived_outputs:
  - <report, export, generated page, cache, or other non-authoritative artifact>

acceptance_tests:
  - condition: <observable pass condition>
    evidence: <command, artifact, inspection, or user acceptance>

review_batch_size: all | <positive integer> | adaptive
stop_conditions:
  - <scope conflict, contradictory source, missing authorization, failed evidence,
    destructive risk, cost, or external side effect>
```

## Value rules

- Use project-relative paths when the project is the scope; use an absolute path only when the user explicitly placed an outside location in scope.
- Put each fact class under one authoritative source. If two sources disagree, stop and surface the conflict instead of choosing silently.
- List outputs that can be regenerated under `derived_outputs`; never edit one as though it were authoritative unless the contract explicitly changes that relationship.
- Make each acceptance condition falsifiable. “Looks good” is not a test unless the user is the designated acceptance authority.
- Use `all` for a small homogeneous review set, a positive integer when early samples can reveal systematic errors, and `adaptive` only when the contract states how the batch changes.
- Stop conditions pause the affected action, not unrelated safe work. Report what remains possible within the contract.
