# Current Official Platform, Existing Project First

Use this reference when a task requires a consequential platform, SDK, or UI-system choice.

## Decision order

1. Preserve the project's confirmed deployment targets, design system, and conventions.
2. Check current official platform documentation when guidance is fast-moving or the choice affects compatibility.
3. Prefer native capabilities already supported by the target when they meet the requirement.
4. Introduce custom or third-party components only for a demonstrated gap and with required authorization.
5. Record durable exceptions and their validation, not a blanket “latest” rule.

“Native first” is a default heuristic for new choices, not permission to restyle an existing product or raise deployment targets.

## Apple platforms

Prefer supported SwiftUI/system components, semantic colors/type, SF Symbols, and narrow AppKit/UIKit bridges when they fit the existing project. Liquid Glass or another current design language applies only when supported by the confirmed target and desired for that product; verify official guidance rather than hard-coding a version assumption.

Use simulator/device evidence for changed runtime UI when the capability is already available. Do not install tools or change signing/deployment configuration solely for this reference.

## Android and Expo

Follow the project's current Compose/Material or React Native/Expo conventions. Prefer platform-adaptive, accessible system components where practical. Do not add a UI kit, navigation stack, or platform dependency without a demonstrated need and authorization.

## Web

Preserve the existing framework and design system. Prefer semantic HTML, accessibility, responsive behavior, and existing tokens/components. Do not add a CSS/UI framework merely to satisfy a generic baseline.

## Evidence

For a platform decision, record:

- official source and date when current guidance matters;
- deployment/runtime compatibility;
- existing project convention;
- reason for the choice or exception;
- validation surface.

Route to an exposed platform-specific Skill when it adds current domain knowledge or runtime tooling; otherwise proceed with project-native methods.
