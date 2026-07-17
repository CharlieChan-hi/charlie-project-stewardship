# Coding Standards

Detected stack markers: [[stack_markers]]

Package manager: [[package_manager]]

## Naming

[Describe file, component, model, service, and test naming rules.]

## Structure

- Keep UI, business logic, API/data access, and persistence separate when the project size justifies it.
- Prefer existing framework conventions.
- Avoid vague names such as `Helper` or `Manager` unless the project already uses them clearly.
- Prefer small files with clear ownership over mixed-responsibility files.
- Remove proven dead code only when it is within the current task scope; leave unrelated cleanup alone. Obtain confirmation before deleting important files or broad generated output.
- If a file starts becoming a coordination point for unrelated concerns, create or propose a clearer module boundary.

## Comments

Add comments only when they explain non-obvious intent or constraints.

## Validation

[List safe lint, test, build, or typecheck commands after inspecting project scripts.]

## Documentation Updates

Update docs when a change affects project structure, durable preferences, module boundaries, or agent workflow.
