#!/usr/bin/env python3
"""Change-surface capability suggestions for project stewardship reports.

The script cannot observe a host session's live tool inventory. Suggestions therefore describe
capability classes and always remain conditional on the capability actually being exposed.
"""

from __future__ import annotations

from pathlib import Path


def suggest_capabilities(root: Path, detected: dict[str, object]) -> list[dict[str, str]]:
    markers = set(detected["stack_markers"])
    project_type = str(detected["project_type"])
    suggestions: list[dict[str, str]] = []

    if project_type == "Web app" or markers.intersection({"Next.js", "React", "Vue", "Vite", "Tailwind CSS"}):
        suggestions.append({
            "when": "Building or redesigning frontend UI",
            "use": "A currently exposed web implementation capability, if repository guidance is insufficient",
            "why": "Use task-specific official guidance without making a second process stack mandatory.",
        })
        suggestions.append({
            "when": "Testing or debugging rendered web UI",
            "use": "A currently exposed browser or web-testing capability",
            "why": "Rendered behavior needs DOM, interaction, console, network, or screenshot evidence.",
        })

    if markers.intersection({"React", "Next.js"}):
        suggestions.append({
            "when": "Writing or refactoring React/Next.js code",
            "use": "Current React/Next guidance after repository-native checks",
            "why": "Use specialized guidance only when the change reaches framework semantics.",
        })

    if "shadcn/ui" in markers:
        suggestions.append({
            "when": "Working with shadcn/ui components",
            "use": "The exposed shadcn registry/project capability",
            "why": "Prefer the project's component registry over assumptions when that capability exists.",
        })

    if project_type == "Expo / React Native app" or "Expo" in markers:
        suggestions.append({
            "when": "Building Expo native UI or navigation",
            "use": "A currently exposed Expo capability relevant to the changed subsystem",
            "why": "Expo-specific native behavior benefits from current platform guidance.",
        })
        suggestions.append({
            "when": "Expo API/data fetching, native modules, deployment, or run actions",
            "use": "Repository-native Expo commands, then an exposed subsystem-specific capability if needed",
            "why": "Choose one capability for the actual subsystem instead of loading a fixed bundle.",
        })

    if markers.intersection({"Xcode project", "Swift Package"}):
        suggestions.append({
            "when": "iOS or iPadOS SwiftUI app work",
            "use": "The exposed iOS build, UI, debugger, or simulator capability that matches the task",
            "why": "Select from deployment-target evidence; do not impose a UI style or every Apple workflow.",
        })
        suggestions.append({
            "when": "macOS SwiftUI/AppKit work",
            "use": "The exposed macOS build, SwiftUI, AppKit, or windowing capability that matches the task",
            "why": "Use specialized macOS guidance only for the affected subsystem.",
        })

    if project_type == "Monorepo":
        suggestions.append({
            "when": "Cross-package architecture or shared code changes",
            "use": "Repository-native workspace tools; add a semantic index only if text search is ambiguous",
            "why": "Cross-package work needs dependency evidence, not a mandatory planning persona.",
        })

    if markers.intersection({"Express", "Python", "Go", "Rust", "JVM"}) or "Backend" in project_type:
        suggestions.append({
            "when": "Backend API, service, data, or auth changes",
            "use": "An exposed security or provider capability only when the changed surface requires it",
            "why": "Auth, data, and deployment changes need focused evidence; ordinary backend edits may not.",
        })

    return suggestions
