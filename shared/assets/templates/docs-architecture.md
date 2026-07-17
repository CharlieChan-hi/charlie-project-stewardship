# Architecture

## Current Project Type

[[project_type]]

Status: initial scaffold. Confirm uncertain assumptions before using this as a hard architecture rule.

## Structure

[Explain the real folder structure and what each major folder owns.]

Detected stack markers: [[stack_markers]]

Package manager: [[package_manager]]

Optional source structure record, when one has been selected: `docs/source_structure.md`.

## Module Boundaries

[Explain which modules may call which modules.]

## Dependency Direction

[Example: app -> features -> shared components/services -> utilities.]

## Data Flow

[Explain how data moves through the app.]

## Where New Code Goes

- New screens/pages:
- New reusable components:
- New services/API clients:
- New data models:
- New tests:
- New documentation:

If the source structure is still `[需确认]`, inspect the existing code and follow the
closest established ownership and dependency conventions. Use a source recipe only when
it solves a current structural ambiguity; a recipe is not a prerequisite for coding.

## Evolution Rules

Add structure only when the project grows enough to need it. Avoid both dumping everything into one file and creating empty enterprise folders.
