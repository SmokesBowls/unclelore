#!/usr/bin/env bash
set -euo pipefail

MRLORE_ROOT="$HOME/Downloads/obsidianburdenNov25/_mrlore"
cd "$MRLORE_ROOT"

cat > tools/audit_mrlore_tools.py << 'PYEOF'
#!/usr/bin/env python3
"""MRLORE-TOOLS-001: Tooling Contract & Integrity Validator"""
import os, sys, re, py_compile
from pathlib import Path

MRLORE_ROOT = Path(os.environ.get("MRLORE_ROOT", Path.cwd()))
TOOLS_DIR   = MRLORE_ROOT / "tools"
LOG_FILE    = MRLORE_ROOT / "logs/audit_tools_001.md"
EXIT_CODE   = 0

def check(filepath, content):
    issues = []
    
    # 1. Syntax
    try:
        py_compile.compile(str(filepath), doraise=True)
    except py_compile.PyCompileError as e:
        issues.append(f"SYNTAX ERROR: {e}")

    # 2. Contract: EXIT Semantics
    has_exit = bool(re.search(r'(sys\.exit|EXIT_CODE)', content))
    if not has_exit:
        issues.append("MISSING EXIT SEMANTICS: No sys.exit or EXIT_CODE pattern found")

    # 3. Contract: Raw/ Protection
    if re.search(r'open\([^)]*["\'].*raw/.*["\']', content):
        issues.append("RAW VIOLATION RISK: File open detected on raw/ path")

    # 4. Contract: Hardcoded Paths
    if re.search(r'/home/[a-z0-9_-]+/', content, re.IGNORECASE):
        issues.append("HARDCODED PATH: Absolute home path detected (use env vars or pathlib)")

    # 5. Contract: Main Guard
    if 'if __name__ ==' not in content:
        issues.append("MISSING __main__ GUARD: Tool may execute on import")

    # 6. Artifact Flagging
    if re.match(r'Qwen_python_.*\.py', filepath.name):
        issues.append("SCRATCH ARTIFACT: Likely temporary LLM output (move to legacy/ or delete)")

    return issues

def main():
    global EXIT_CODE
    report = [
        "# MRLORE-TOOLS-001: Tooling Contract & Integrity Audit",
        f"Root: `{TOOLS_DIR}`",
        f"Run: $(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "---"
    ]

    tools = sorted([f for f in TOOLS_DIR.iterdir() if f.suffix == ".py" and f.name != "__init__.py"])
    total_issues = 0

    for t in tools:
        content = t.read_text(encoding="utf-8")
        issues = check(t, content)
        total_issues += len(issues)
        if issues:
            EXIT_CODE = 2
        
        status = "✅ PASS" if not issues else f"❌ FAIL ({len(issues)} issue(s))"
        report.append(f"## `{t.name}`")
        report.append(f"Status: {status}")
        for i in issues:
            report.append(f"- ⚠️ {i}")
        report.append("")

    report.append("---")
    report.append(f"**Total Tools Scanned:** {len(tools)}")
    report.append(f"**Total Issues Found:** {total_issues}")
    report.append(f"**EXIT CODE:** `{EXIT_CODE}`")
    report.append(f"**Status:** {'COMPLIANT' if EXIT_CODE == 0 else 'REVIEW REQUIRED'}")
    report.append("")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    sys.exit(EXIT_CODE)

if __name__ == "__main__":
    main()
PYEOF

chmod +x tools/audit_mrlore_tools.py
export MRLORE_ROOT
python3 tools/audit_mrlore_tools.py