#!/usr/bin/env python3
"""Markdown reporting for project health audits."""

from __future__ import annotations


def print_governance_coverage(coverage: dict[str, object]) -> None:
    print("## 治理覆盖（不影响项目健康）")
    artifacts = coverage["artifacts"]
    missing = artifacts["missing"]
    print(f"- Coverage: {coverage['coverage_percent']}%")
    print("- Missing artifacts are optional and do not change project health status.")
    if not missing:
        print("- Missing: None")
        return
    print("- Missing:")
    for rel_path in missing:
        print(f"  - `{rel_path}`")


def print_large_files(large_files: list[dict[str, object]]) -> None:
    print("## 大文件信号（仅供复核）")
    if not large_files:
        print("- None")
        return
    for item in large_files:
        print(
            f"- `{item['path']}`: {item['lines']} lines "
            f"(threshold {item['threshold']}; size alone is not a failure)"
        )


def print_complexity_hotspots(items: list[dict[str, object]]) -> None:
    if not items:
        return
    print("- Complexity hotspots:")
    for item in items:
        print(
            f"  - `{item['path']}`: {item['control_flow_markers']} control-flow markers, "
            f"{item['markers_per_100_lines']} per 100 lines"
        )


def print_complexity_skips(items: list[dict[str, object]]) -> None:
    if not items:
        return
    print("- Complexity analysis skipped:")
    for item in items:
        print(
            f"  - `{item['path']}`: `{item['signal']}` "
            f"({item['bytes']} bytes; limit {item['limit_bytes']})"
        )


def print_named_paths(title: str, paths: list[str]) -> None:
    if not paths:
        return
    print(f"- {title}:")
    for rel_path in paths:
        print(f"  - `{rel_path}`")


def print_root_clutter(root_clutter: dict[str, object]) -> None:
    if not root_clutter["flagged"]:
        return
    sample = ", ".join(f"`{name}`" for name in root_clutter["source_files"][:8])
    suffix = f" ({sample})" if sample else ""
    print(f"- Root source clutter: {root_clutter['source_file_count']} source files in project root{suffix}")


def print_anti_spaghetti(anti_spaghetti: dict[str, object]) -> None:
    print("## 代码健康信号")
    complexity_hotspots = anti_spaghetti["complexity_hotspots"]
    complexity_analysis_skipped = anti_spaghetti.get("complexity_analysis_skipped", [])
    generic_name_files = anti_spaghetti["generic_name_files"]
    dead_code_name_candidates = anti_spaghetti["dead_code_name_candidates"]
    root_clutter = anti_spaghetti["root_clutter"]
    if (
        not complexity_hotspots
        and not complexity_analysis_skipped
        and not generic_name_files
        and not dead_code_name_candidates
        and not root_clutter["flagged"]
    ):
        print("- None")
        return
    print_complexity_hotspots(complexity_hotspots)
    print_complexity_skips(complexity_analysis_skipped)
    print_named_paths("Generic source names", generic_name_files)
    print_named_paths("Dead-code-like source names", dead_code_name_candidates)
    print_root_clutter(root_clutter)


def print_recommendations(recommendations: list[str]) -> None:
    print("## 建议")
    if not recommendations:
        print("- No immediate evidence-based health action.")
        return
    for recommendation in recommendations:
        print(f"- {recommendation}")


def print_capability_suggestions(suggestions: list[dict[str, str]]) -> None:
    print("## 可选能力建议")
    if not suggestions:
        print("- None")
        return
    for item in suggestions:
        print(f"- When {item['when']}: use `{item['use']}`. Reason: {item['why']}")


def print_markdown(audit: dict[str, object]) -> None:
    detected = audit["detected"]
    health = audit["project_health"]
    secrets = audit["secrets"]

    print("# 项目健康审计报告")
    print()
    print(f"- Project root: `{audit['project_root']}`")
    print(f"- Schema: `{audit['schema_version']}`")
    print(f"- Project type: `{detected['project_type']}`")
    print(f"- Stack markers: `{', '.join(detected['stack_markers']) or '[需确认]'}`")
    print(f"- Package manager: `{detected['package_manager']}`")
    print(f"- Health status: `{health['status']}`")
    counts = health["evidence_counts"]
    print(
        "- Evidence counts: "
        f"serious={counts['serious_risks']}, "
        f"review={counts['review_signals']}, "
        f"unknown={counts['unknown_signals']}, "
        f"info={counts['informational_signals']}"
    )
    print("- Numeric health scoring is deprecated; status follows the evidence categories above.")
    if secrets["ignore_check_required"]:
        print(f"- `.env` ignore coverage: `{secrets['ignore_status']}`")
    else:
        print("- `.env` ignore coverage: not applicable (no real .env file detected)")
    credential_configs = secrets.get("credential_config_statuses", [])
    if credential_configs:
        summary = ", ".join(
            f"{item['path']}={item['classification']}"
            for item in credential_configs
        )
        print(f"- Credential-capable config inventory (names/Git metadata only): `{summary}`")
    else:
        print("- Credential-capable config inventory: none")
    print("- Secret contents read: `False`")
    print()
    print("## 有证据的严重风险")
    if health["serious_risks"]:
        for item in health["serious_risks"]:
            print(f"- [{item['code']}] {item['message']}")
    else:
        print("- None")
    print()
    print("## 需复核信号")
    if health["review_signals"]:
        for item in health["review_signals"]:
            print(f"- [{item['code']}] {item['message']}")
    else:
        print("- None")
    print()
    print("## 不可判定信号")
    if health["unknown_signals"]:
        for item in health["unknown_signals"]:
            print(f"- [{item['code']}] {item['message']}")
    else:
        print("- None")
    print()
    print_large_files(audit["code_signals"]["large_files"])
    print()
    print_anti_spaghetti(audit["anti_spaghetti"])
    print()
    print_governance_coverage(audit["governance_coverage"])
    print()
    print_recommendations(audit["recommendations"])
    print()
    print_capability_suggestions(audit["capability_suggestions"])
