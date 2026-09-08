#!/usr/bin/env python3
"""
MrLore v2 — Run Changed Sources (Phase 5c Integrated)
Stable entry point for external drivers (Trae Agent, CocoIndex, manual).

Reads a list of changed vault files, runs MrLore ingest workflow on each,
rebuilds the registry, lints the wiki, runs the continuity audit,
and writes a run report.

Usage:
    python3 mrlore_run_changed.py --changed changed_files.txt
    python3 mrlore_run_changed.py --file book_01/001_the_ethereal_vigil.md
    python3 mrlore_run_changed.py --all          # process all Tier 0 sources
    python3 mrlore_run_changed.py --dry-run      # report what would run, no changes

Exit codes:
    0  clean run — no structural issues or open continuity findings
    1  lint failed — structural problem in wiki
    2  canon conflicts flagged — open CONT-*.yaml requires human review
"""

import sys
import re
import yaml
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MRLORE_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT  = MRLORE_ROOT.parent
TOOLS_DIR   = MRLORE_ROOT / "tools"
LOGS_DIR    = MRLORE_ROOT / "logs"
WIKI_PATH   = MRLORE_ROOT / "wiki"
LOG_PATH    = WIKI_PATH / "log.md"

LOGS_DIR.mkdir(exist_ok=True)

# Authority tier for auto-ingest (Tier 0 = canonical chapters)
SAFE_INGEST_TIER = 0

# ── SOURCE AUTHORITY CLASSIFIER ─────────────────────────────────────────────

EXCLUDED_DIRS = {
    "_mrlore", ".git", ".obsidian", "__pycache__",
    ".trash", "node_modules",
}

SOURCE_EXTS = {".md", ".txt"}

def _is_chapter_file(path: Path) -> bool:
    return bool(re.match(r"^\d+[_\-]", path.name))

def _is_book_dir(path: Path) -> bool:
    parent = path.parent.name.lower()
    return parent.startswith("book") or parent.startswith("book_")

def _in_southern_arc(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    return "southern arc" in parts or "southern_arc" in parts

def classify_tier(path: Path) -> int:
    """Return authority tier 0-4 for a vault file."""
    if path.suffix.lower() == ".json":            return 4
    if path.suffix in {".sh", ".py", ".pyc"}:     return 4
    if any(x in path.name for x in ["(1)", "(2)", "(3)"]): return 4

    if "fairy_tale" in path.parent.name.lower():  return 3
    if path.parent.name.lower() in {"extra", "extras", "ongoing", "solid"} \
            or path.parent.name.lower().startswith("extra"): return 3
    if path.parent == VAULT_ROOT:                 return 3

    if "canon" in path.name.lower():              return 1
    if "unresolved" in path.name.lower():         return 1
    if any(k in path.name.lower() for k in
           ["lore", "profile", "magic", "graviton", "nephoretti",
            "igigi", "vale", "zephyr", "keeper"]):  return 1

    if _is_chapter_file(path) and (_is_book_dir(path) or _in_southern_arc(path)):
        return 0
    if _is_chapter_file(path):                    return 0

    return 3

# ── INGEST STUB ──────────────────────────────────────────────────────────────

def run_ingest_stub(vault_rel: str, dry_run: bool = False) -> dict:
    """Call ingest_source_stub.py for one file. Returns result dict."""
    stub_script = TOOLS_DIR / "ingest_source_stub.py"
    if not stub_script.exists():
        return {
            "status": "error",
            "path": vault_rel,
            "message": "ingest_source_stub.py not found",
            "code": 1,
        }

    if dry_run:
        return {"status": "dry-run", "path": vault_rel}

    result = subprocess.run(
        [sys.executable, str(stub_script), vault_rel],
        capture_output=True, text=True,
        cwd=str(MRLORE_ROOT)
    )
    return {
        "status": "ok" if result.returncode == 0 else "error",
        "path":   vault_rel,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "code":   result.returncode,
    }

def run_build_registry(dry_run: bool = False) -> bool:
    if dry_run: return True
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "build_registry.py")],
        capture_output=True, text=True, cwd=str(MRLORE_ROOT)
    )
    return result.returncode == 0

def run_lint(dry_run: bool = False) -> bool:
    if dry_run: return True
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "lint_wiki.py")],
        capture_output=True, text=True, cwd=str(MRLORE_ROOT)
    )
    return result.returncode == 0

# ── PHASE 5c: CONTINUITY AUDIT RUNNER & STATE CHECKER ────────────────────────

def run_continuity_audit(sources: list[str], dry_run: bool = False) -> int:
    """Run continuity_audit.py scoped to exactly the given sources.

    Passes one --source flag per file so only the just-ingested files are
    audited — faster and safer than --all-sources (which is not implemented).

    Returns the audit exit code:
        0  clean
        1  mechanical failure
        2  continuity conflicts found
    """
    if dry_run or not sources:
        return 0
    audit_script = TOOLS_DIR / "continuity_audit.py"
    if not audit_script.exists():
        print("[run_changed] WARNING: continuity_audit.py not found, skipping audit")
        return 0
    audit_cmd = [sys.executable, str(audit_script)]
    for src in sources:
        audit_cmd.extend(["--source", src])
    result = subprocess.run(
        audit_cmd,
        capture_output=False,   # stream output live so progress is visible
        cwd=str(MRLORE_ROOT),
    )
    return result.returncode

def check_open_continuity_findings() -> list[str]:
    """Return list of open CONT-*.yaml files requiring human review."""
    continuity_dir = WIKI_PATH / "continuity"
    if not continuity_dir.exists():
        return []
    open_findings = []
    for f in sorted(continuity_dir.glob("CONT-*.yaml")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict) and data.get("status", "").lower() == "open":
                open_findings.append(f.name)
        except Exception:
            continue  # skip malformed or empty files
    return open_findings

# ── CHANGED FILE SOURCES ─────────────────────────────────────────────────────

def load_changed_files(changed_path: Path) -> list[str]:
    if not changed_path.exists():
        print(f"[run_changed] ERROR: changed file manifest not found: {changed_path}")
        return []
    lines = changed_path.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]

def discover_all_tier0() -> list[str]:
    sources = []
    for path in sorted(VAULT_ROOT.rglob("*")):
        if not path.is_file(): continue
        if path.suffix.lower() not in SOURCE_EXTS: continue
        rel_parts = set(path.relative_to(VAULT_ROOT).parts)
        if rel_parts & EXCLUDED_DIRS: continue
        if classify_tier(path) == SAFE_INGEST_TIER:
            sources.append(str(path.relative_to(VAULT_ROOT)))
    return sources

def filter_to_safe_tier(paths: list[str]) -> tuple[list[str], list[str]]:
    safe, skipped = [], []
    for rel in paths:
        full = VAULT_ROOT / rel
        if not full.exists():
            skipped.append(f"{rel}  [NOT FOUND]")
            continue
        tier = classify_tier(full)
        if tier == 0:
            safe.append(rel)
        else:
            skipped.append(f"{rel}  [Tier {tier} — skipped]")
    return safe, skipped

# ── REPORT ───────────────────────────────────────────────────────────────────

def write_run_report(
    run_id: str,
    sources_attempted: list[str],
    results: list[dict],
    skipped: list[str],
    registry_ok: bool,
    lint_ok: bool,
    audit_rc: int,
    open_continuity: list[str],
    dry_run: bool,
) -> Path:
    lines = [
        f"# MrLore Run Report — {run_id}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Dry run: {'yes' if dry_run else 'no'}",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- Sources attempted:  {len(sources_attempted)}",
        f"- Ingested OK:        {sum(1 for r in results if r['status'] in ('ok','dry-run'))}",
        f"- Ingest errors:      {sum(1 for r in results if r['status'] == 'error')}",
        f"- Skipped by tier:    {len(skipped)}",
        f"- Registry rebuild:   {'OK' if registry_ok else 'FAILED'}",
        f"- Lint:               {'OK' if lint_ok else 'FAILED'}",
        f"- Continuity audit:   {'CLEAN' if audit_rc == 0 else f'FLAGGED (rc={audit_rc})'}",
        f"- Open CONT-*.yaml:   {len(open_continuity)}",
        "",
    ]

    if open_continuity:
        lines += ["## ⚠ Continuity Findings — Human Review Required", ""]
        for c in open_continuity:
            lines.append(f"- {c}")
        lines.append("")

    lines += ["## Ingested Sources", ""]
    for r in results:
        status = r["status"].upper()
        lines.append(f"- [{status}] {r.get('path', '?')}")
        if r["status"] == "error" and r.get("stderr"):
            lines.append(f"  Error: {r['stderr'][:200]}")
    lines.append("")

    if skipped:
        lines += ["## Skipped Sources", ""]
        for s in skipped:
            lines.append(f"- {s}")
        lines.append("")

    # Determine final status text
    if lint_ok and audit_rc == 0 and not open_continuity:
        exit_text = "0 = clean run"
    elif open_continuity or audit_rc == 2:
        exit_text = "2 = canon conflicts flagged — human review required"
    else:
        exit_text = "1 = lint failed"

    lines += ["## Exit Code", "", exit_text, ""]

    report_path = LOGS_DIR / f"run_{run_id}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path

# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> int:
    args = sys.argv[1:]
    dry_run   = "--dry-run" in args
    run_all   = "--all" in args
    changed_manifest = None
    single_file = None

    for i, arg in enumerate(args):
        if arg == "--changed" and i + 1 < len(args):
            changed_manifest = args[i + 1]
        if arg == "--file" and i + 1 < len(args):
            single_file = args[i + 1]

    # ── Resolve source list ────────────────────────────────────────────────
    if run_all:
        raw_sources = discover_all_tier0()
    elif changed_manifest:
        raw_sources = load_changed_files(Path(changed_manifest))
    elif single_file:
        raw_sources = [single_file]
    else:
        print("[run_changed] No --all, --changed, or --file provided.")
        print(__doc__)
        return 1

    safe_sources, skipped = filter_to_safe_tier(raw_sources)
    if not safe_sources:
        print("[run_changed] No Tier 0 sources to process.")
        return 0

    print(f"[run_changed] Processing {len(safe_sources)} Tier 0 source(s)...")

    # ── Execute Pipeline ───────────────────────────────────────────────────
    results = []
    for src in safe_sources:
        res = run_ingest_stub(src, dry_run)
        results.append(res)
        if res["status"] == "error" and not dry_run:
            print(f"  [ERROR] {src} → {res.get('stderr', 'unknown')[:120]}")

    registry_ok = run_build_registry(dry_run)
    lint_ok     = run_lint(dry_run)

    # Phase 5c: Run continuity audit & gather open review queue
    ingested_sources = [r["path"] for r in results if r["status"] == "ok"]
    audit_rc        = run_continuity_audit(ingested_sources, dry_run)
    open_continuity = check_open_continuity_findings() if not dry_run else []

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = write_run_report(
        run_id, safe_sources, results, skipped,
        registry_ok, lint_ok, audit_rc, open_continuity, dry_run
    )
    print(f"[run_changed] Report: {report}")

    # ── Exit Code Routing ──────────────────────────────────────────────────
    ingest_errors = sum(1 for r in results if r["status"] == "error")

    if ingest_errors > 0:
        print(f"[run_changed] EXIT 1 — ingest failed for {ingest_errors} source(s)")
        sys.exit(1)

    if not lint_ok:
        print("[run_changed] EXIT 1 — lint failed")
        return 1
    if audit_rc == 2 or open_continuity:
        print("[run_changed] EXIT 2 — continuity conflicts require human review")
        return 2
    print("[run_changed] EXIT 0 — clean run")
    return 0

if __name__ == "__main__":
    sys.exit(main())