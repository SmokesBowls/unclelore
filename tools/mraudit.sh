#!/usr/bin/env bash
set -euo pipefail

MRLORE_ROOT="$HOME/Downloads/obsidianburdenNov25/_mrlore"
AUDIT_LOG="$MRLORE_ROOT/logs/audit_MrLore_001.md"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$MRLORE_ROOT/tools/audit_mrlore_system.py" << 'PYTHON_EOF'
#!/usr/bin/env python3
"""MRLORE-AUDIT-001: System Structure & Schema Compliance Validator"""
import os, sys, json, re, pathlib, datetime
from pathlib import Path

MRLORE_ROOT = Path(os.environ.get("MRLORE_ROOT", Path.home() / "Downloads/obsidianburdenNov25/_mrlore"))
AUDIT_LOG  = MRLORE_ROOT / "logs/audit_MrLore_001.md"
EXIT_CODE  = 0

REQUIRED_DIRS = {
    "raw/chapters", "raw/notes", "raw/canon_decisions", "raw/editorial_feedback",
    "wiki/characters", "wiki/locations", "wiki/factions", "wiki/species",
    "wiki/systems", "wiki/arcs", "wiki/timelines", "wiki/themes", "wiki/terms",
    "wiki/contradictions", "wiki/unresolved", "wiki/sources", "wiki/proposals",
    "wiki/canon_decisions", "wiki/codex_candidates", "wiki/continuity",
    "schema", "tools", "logs", "cocowatch/state"
}

SCHEMA_FILES = {"MRLORE_SCHEMA.md", "TRAE_MRLORE.md", "RELATIONSHIP_PREDICATES.md", "Authority_scoring_rules.md"}
TOOLS_EXPECTED = {
    "audit_source_authority.py", "audit_vault.py", "build_registry.py",
    "continuity_audit.py", "lint_wiki.py", "mrlore_run_changed.py",
    "promote_candidate.py", "propose_corrections.py", "write_changed_manifest.py"
}

def check(name, condition, detail=""):
    global EXIT_CODE
    status = "✅ PASS" if condition else "❌ FAIL"
    if not condition:
        EXIT_CODE = 2
    return f"- [{status}] {name}: {detail if detail else 'OK'}"

def validate_index():
    idx = MRLORE_ROOT / "wiki/index.md"
    if not idx.exists():
        return check("wiki/index.md exists", False)
    content = idx.read_text(encoding="utf-8")
    required_sections = [
        "## Characters", "## Factions", "## Species", "## Locations",
        "## Systems", "## Artifacts", "## Arcs", "## Timelines",
        "## Themes", "## Terms", "## Canon Decisions", "## Contradictions",
        "## Unresolved Questions", "## Source Summaries"
    ]
    missing = [s for s in required_sections if s not in content]
    return check("wiki/index.md contract (§16)", len(missing) == 0, f"Missing sections: {missing}" if missing else "All required headers present")

def validate_log():
    log = MRLORE_ROOT / "wiki/log.md"
    if not log.exists():
        return check("wiki/log.md exists", False)
    content = log.read_text(encoding="utf-8")
    pattern = r"^## \[\d{4}-\d{2}-\d{2}\] (ingest|audit|proposal|promotion) \| .+"
    has_entries = any(re.match(pattern, line) for line in content.splitlines())
    return check("wiki/log.md append-only contract (§17)", has_entries or log.stat().st_size == 0, "No entries or empty (acceptable for new)")

def validate_raw_immutability():
    raw_chaps = MRLORE_ROOT / "raw/chapters"
    if not raw_chaps.exists():
        return check("raw/chapters exists", False)
    # Basic heuristic: ensure no .tmp, .bak, or unexpected extensions
    unexpected = [f.name for f in raw_chaps.iterdir() if not f.name.endswith(('.md', '.txt'))]
    return check("raw/ immutability (§3)", len(unexpected) == 0, f"Unexpected extensions: {unexpected}" if unexpected else "Clean")

def main():
    report_lines = [
        f"# MRLORE-AUDIT-001: System Structure & Schema Compliance",
        f"Run: {datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"Root: `{MRLORE_ROOT}`",
        "---"
    ]

    # 1. Directory structure
    report_lines.append("## 1. Directory Contract")
    for d in sorted(REQUIRED_DIRS):
        p = MRLORE_ROOT / d
        report_lines.append(check(f"`{d}`", p.is_dir()))

    # 2. Schema files
    report_lines.append("\n## 2. Schema Authority Files")
    for f in sorted(SCHEMA_FILES):
        p = MRLORE_ROOT / "schema" / f
        report_lines.append(check(f"`schema/{f}`", p.exists(), f"Size: {p.stat().st_size} bytes" if p.exists() else ""))

    # 3. Tooling inventory
    report_lines.append("\n## 3. Tooling Inventory")
    for t in sorted(TOOLS_EXPECTED):
        p = MRLORE_ROOT / "tools" / t
        report_lines.append(check(f"`tools/{t}`", p.exists()))

    # 4. Wiki contracts
    report_lines.append("\n## 4. Wiki Contract Validation")
    report_lines.append(validate_index())
    report_lines.append(validate_log())

    # 5. Raw immutability
    report_lines.append("\n## 5. Raw Source Integrity")
    report_lines.append(validate_raw_immutability())

    report_lines.append("\n---")
    report_lines.append(f"**EXIT CODE:** `{EXIT_CODE}`")
    report_lines.append(f"**Status:** {'COMPLIANT' if EXIT_CODE == 0 else 'DRIFT DETECTED — REVIEW REQUIRED'}")
    report_lines.append("")

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_LOG.write_text("\n".join(report_lines), encoding="utf-8")
    print("\n".join(report_lines))
    sys.exit(EXIT_CODE)

if __name__ == "__main__":
    main()
PYTHON_EOF

chmod +x "$MRLORE_ROOT/tools/audit_mrlore_system.py"
export MRLORE_ROOT
python3 "$MRLORE_ROOT/tools/audit_mrlore_system.py"