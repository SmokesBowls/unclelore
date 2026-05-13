#!/usr/bin/env python3
"""MRLORE-TOOLS-002 v2: Execution Logic & Corpus-Scoped Validation Audit (Repaired)"""
import os, sys, re, ast, datetime
from pathlib import Path

MRLORE_ROOT = Path(os.environ.get("MRLORE_ROOT", Path.home() / "Downloads/obsidianburdenNov25/_mrlore"))
TOOLS_DIR   = MRLORE_ROOT / "tools"
COCOWATCH   = MRLORE_ROOT / "cocowatch"
LOG_FILE    = MRLORE_ROOT / "logs/audit_tools_002_v2.md"
EXIT_CODE   = 0

CORE_TOOLS = [
    "mrlore_run_changed.py", "write_changed_manifest.py",
    "continuity_audit.py", "audit_source_authority.py",
    "build_registry.py", "promote_candidate.py"
]

# Tools that genuinely require corpus/wiki state for their primary function
REQUIRES_STATE = {"continuity_audit.py", "build_codex_candidates.py", "propose_corrections.py"}

def analyze_tool(filepath):
    issues = []
    if not filepath.exists():
        return ["MISSING: Core tool not found in tools/"]

    content = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ["SYNTAX ERROR: Cannot parse AST"]

    # 1. Dry-run gating analysis
    # Only flag if dry-run exits BEFORE any validation/analysis logic.
    # Dry-run should skip writes/mutations, but must still calculate eligibility & report.
    has_early_dryrun_exit = bool(re.search(
        r'def main.*?if\s+(args\.?dry_run|dry_run).*?:\s*(return|sys\.exit\(0\))',
        content, re.DOTALL | re.IGNORECASE
    ))
    if has_early_dryrun_exit:
        issues.append("DRY-RUN BYPASS: Early exit/return skips validation logic. Dry-run should only skip mutation.")

    # 2. State/Context Loading (Contextualized per tool purpose)
    if filepath.name in REQUIRES_STATE:
        loads_wiki = bool(re.search(r'(registry|index\.md|canon_decision|contradiction|wiki/)', content, re.IGNORECASE))
        if not loads_wiki:
            issues.append("MISSING STATE LOAD: Tool requires wiki/corpus context but does not load it")

    # 3. Assertion/Validation Presence (Rubber-stamp check)
    has_validation = bool(re.search(r'(validate|check_|detect_|assert|eligibility|calculate|score)', content))
    has_early_exit_0 = bool(re.search(r'sys\.exit\(0\)', content))
    if not has_validation and has_early_exit_0:
        issues.append("RUBBER-STAMP RISK: Exits 0 without explicit validation or calculation logic")

    # 4. Scope: Single-file vs Multi-file iteration
    has_manifest_loop = bool(re.search(r'for\s+\w+\s+in\s+.*manifest|readlines|load_json.*files', content))
    if not has_manifest_loop and 'batch' in filepath.name.lower():
        issues.append("SCOPE NOTE: Batch-named tool lacks manifest iteration logic")

    return issues

def main():
    global EXIT_CODE
    total_issues = 0
    run_time = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    report = [
        "# MRLORE-TOOLS-002 v2: Execution Logic & Corpus-Scoped Validation Audit",
        f"Root: `{TOOLS_DIR}`",
        f"Run: {run_time}",
        "---"
    ]

    for tool in CORE_TOOLS:
        path = TOOLS_DIR / tool
        issues = analyze_tool(path)
        if issues:
            EXIT_CODE = 2
            total_issues += len(issues)
        status = "✅ PASS" if not issues else f"❌ FAIL ({len(issues)} issue(s))"
        report.append(f"## `{tool}`")
        report.append(f"Status: {status}")
        for i in issues:
            report.append(f"- ⚠️ {i}")
        report.append("")

    # Cocowatch delta collector check
    delta_path = COCOWATCH / "collect_delta.py"
    if delta_path.exists():
        d_content = delta_path.read_text(encoding="utf-8")
        if not re.search(r'for|walk|glob|listdir|iterdir', d_content):
            report.append("## `cocowatch/collect_delta.py`")
            report.append("Status: ❌ FAIL")
            report.append("- ⚠️ DELTA COLLECTION: No iteration logic detected; may only capture single file")
            EXIT_CODE = 2
            total_issues += 1
        else:
            report.append("## `cocowatch/collect_delta.py`")
            report.append("Status: ✅ PASS")
            report.append("")

    report.append("---")
    report.append(f"**Total Tools Analyzed:** {len(CORE_TOOLS)+1}")
    report.append(f"**Total Issues Found:** {total_issues}")
    report.append(f"**EXIT CODE:** `{EXIT_CODE}`")
    report.append(f"**Status:** {'CORPUS-READY' if EXIT_CODE == 0 else 'REVIEW RECOMMENDED'}")
    report.append("")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    sys.exit(EXIT_CODE)

if __name__ == "__main__":
    main()
