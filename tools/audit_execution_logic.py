#!/usr/bin/env python3
"""MRLORE-TOOLS-002: Execution Logic & Corpus-Scoped Validation Audit"""
import os, sys, re, ast, textwrap
from pathlib import Path

MRLORE_ROOT = Path(os.environ.get("MRLORE_ROOT", Path.cwd()))
TOOLS_DIR   = MRLORE_ROOT / "tools"
COCOWATCH   = MRLORE_ROOT / "cocowatch"
LOG_FILE    = MRLORE_ROOT / "logs/audit_tools_002.md"
EXIT_CODE   = 0

CORE_TOOLS = [
    "mrlore_run_changed.py", "write_changed_manifest.py",
    "continuity_audit.py", "audit_source_authority.py",
    "build_registry.py", "promote_candidate.py"
]

def analyze_tool(filepath):
    issues = []
    if not filepath.exists():
        return ["MISSING: Core tool not found in tools/"]

    content = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ["SYNTAX ERROR: Cannot parse AST"]

    # 1. Dry-run gating that skips validation
    has_dryrun_bypass = bool(re.search(r'if.*dry.?run.*:.*\n\s*(return|sys\.exit|continue)', content, re.DOTALL))
    if has_dryrun_bypass:
        issues.append("DRY-RUN BYPASS: Validation/mutation skipped when dry-run flag is active")

    # 2. Single-file vs multi-file iteration
    has_manifest_loop = bool(re.search(r'for\s+\w+\s+in\s+.*manifest', content))
    has_hardcoded_single = bool(re.search(r'open\([^)]*["\'].*(chapter|book).*["\']', content))
    if not has_manifest_loop and has_hardcoded_single:
        issues.append("SCOPE LIMIT: Hardcoded single-file path detected; no manifest iteration")

    # 3. State/Context Loading
    loads_registry = bool(re.search(r'(registry|index\.md|canon_decision|contradiction)', content, re.IGNORECASE))
    if not loads_registry:
        issues.append("MISSING STATE LOAD: No loading of wiki/registry.md, contradictions, or canon decisions")

    # 4. Assertion/Validation Presence
    has_assertions = bool(re.search(r'(assert|validate|check_|detect_|find_|compare_|scan_)', content))
    has_exit_0_early = bool(re.search(r'sys\.exit\(0\)', content))
    if not has_assertions and has_exit_0_early:
        issues.append("RUBBER-STAMP RISK: Exits 0 without explicit validation or assertion logic")

    # 5. Cross-Reference Capability
    loads_wiki_content = bool(re.search(r'(wiki/|read_text|parse_yaml|load_json|open.*wiki)', content))
    if not loads_wiki_content:
        issues.append("ISOLATED PROCESSING: Does not load existing wiki state for cross-chapter comparison")

    return issues

def main():
    global EXIT_CODE
    report = [
        "# MRLORE-TOOLS-002: Execution Logic & Corpus-Scoped Validation Audit",
        f"Root: `{TOOLS_DIR}`",
        f"Run: 2026-05-11T$(date -u +%H:%M:%S)Z",
        "---"
    ]

    for tool in CORE_TOOLS:
        path = TOOLS_DIR / tool
        issues = analyze_tool(path)
        if issues:
            EXIT_CODE = 2
        status = "✅ PASS" if not issues else f"❌ FAIL ({len(issues)} issue(s))"
        report.append(f"## `{tool}`")
        report.append(f"Status: {status}")
        for i in issues:
            report.append(f"- ⚠️ {i}")
        report.append("")

    # Check cocowatch delta collector for multi-file support
    delta_path = COCOWATCH / "collect_delta.py"
    if delta_path.exists():
        d_content = delta_path.read_text(encoding="utf-8")
        if not re.search(r'for|walk|glob|listdir', d_content):
            report.append("## `cocowatch/collect_delta.py`")
            report.append("Status: ❌ FAIL")
            report.append("- ⚠️ DELTA COLLECTION: No iteration logic detected; may only capture single file")
            EXIT_CODE = 2

    report.append("---")
    report.append(f"**Total Tools Analyzed:** {len(CORE_TOOLS)+1}")
    report.append(f"**Total Issues Found:** {sum(1 for t in CORE_TOOLS+[delta_path] if Path(t).exists())}")
    report.append(f"**EXIT CODE:** `{EXIT_CODE}`")
    report.append(f"**Status:** {'CORPUS-READY' if EXIT_CODE == 0 else 'SINGLE-CHAPTER/DRY-RUN LIMITED'}")
    report.append("")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    sys.exit(EXIT_CODE)

if __name__ == "__main__":
    main()
