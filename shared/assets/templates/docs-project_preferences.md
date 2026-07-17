# Project Preferences

This file separates durable, confirmed project rules from provisional scaffold guidance. It is not a chat log or task tracker. Only entries backed by user confirmation or repository evidence belong in the confirmed sections.

## Confirmed rules

- [No confirmed rules recorded yet. Add only user-confirmed or evidence-verified rules here.]

## Structured rules

Use this format:

```txt
Rule ID:
Kind:
Rule:
Category:
Scope:
Priority:
Source or evidence:
Exceptions:
Detection:
Validation:
Last verified:
Expiry:
Invalidation:
```

Before adding a rule, confirm its authority and scope, then check for an equivalent entry and update or skip it instead of creating a duplicate.

## Bootstrap guidance (not user-confirmed)

The following are conservative working defaults supplied by the scaffold. They are not durable project preferences and must not be represented as user-confirmed without separate evidence.

### Architecture and platform review guidance

- Follow the project's current conventions unless the user confirms a change.
- Keep structure proportional to project size and give new code a clear owner.
- Treat file size, generic names, and folder shape as review signals, not universal limits.
- Verify fast-moving platform guidance against current official sources when it matters.

### Agent behavior guidance

- Read applicable instructions and relevant code, not every project document by default.
- Preserve existing user work and unrelated changes.
- Use the smallest coherent change and validation proportional to risk.
- Persist only confirmed rules or evidence-backed reusable learnings.

### Optional integrations

Do not mirror rules into another memory/task system or an external service unless the user explicitly requests that integration.

## Pending confirmation

- [Keep uncertain preferences here rather than enforcing them.]
- Product goal, users, deployment target, and framework conventions remain `[需确认]` until confirmed.
