#!/usr/bin/env python3
"""
MrLore v2 — Run Changed Sources
Stable entry point for external drivers (Trae Agent, CocoIndex, manual).

Reads a list of changed vault files, runs MrLore ingest workflow on each,
rebuilds the registry, lints the wiki, and writes a run report.

Usage:
    python3 mrlore_run_changed.py --changed changed_files.txt
    python3 mrlore_run_changed.py --file book_01/001_the_ethereal_vigil.md
    python3 mrlore_run_changed.py --all          # process all Tier 0 sources
    python3 mrlore_run_changed.py --dry-run      # report what would run, no changes

Exit codes:
    0  clean run — no issues
    1  lint failed — structural problem in wiki
    2  canon conflicts flagged — human review required before next run
"""

import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

MRLORE_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT  = MRLORE_ROOT.parent
TOOLS_DIR   = MRLORE_ROOT / "tools"
LOGS_DIR    = MRLORE_ROOT / "logs"
WIKI_PATH   = MRLORE_ROOT / "wiki"
LOG_PATH    = WIKI_PATH / "log.md"

LOGS_DIR.mkdir(exist_ok=True)

# Authority tier for auto-ingest (Tier 0 = canonical chapters)
SAFE_INGEST_TIER = 0

# ── SOURCE AUTHORITY CLASSIFIER (inline, no import needed) ──────────────────

import re
from collections import defaultdict

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


# ── INGEST STUB (inline call to existing tool) ───────────────────────────────

def run_ingest_stub(vault_rel: str, dry_run: bool = False) -> dict:
    """Call ingest_source_stub.py for one file. Returns result dict."""
    stub_script = TOOLS_DIR / "ingest_source_stub.py"
    if not stub_script.exists():
        return {"status": "error", "message": "ingest_source_stub.py not found"}

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
    if dry_run:
        return True
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "build_registry.py")],
        capture_output=True, text=True, cwd=str(MRLORE_ROOT)
    )
    return result.returncode == 0


def run_lint(dry_run: bool = False) -> bool:
    if dry_run:
        return True
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "lint_wiki.py")],
        capture_output=True, text=True, cwd=str(MRLORE_ROOT)
    )
    return result.returncode == 0


def check_open_conflicts() -> list[str]:
    """Return list of open contradiction files requiring human review."""
    conflicts_dir = WIKI_PATH / "contradictions"
    if not conflicts_dir.exists():
        return []
    open_conflicts = []
    for f in conflicts_dir.glob("*.md"):
        text = f.read_text(encoding="utf-8", errors="replace")[:400]
        if "status: open" in text.lower():
            open_conflicts.append(f.name)
    return open_conflicts


# ── CHANGED FILE SOURCES ─────────────────────────────────────────────────────

def load_changed_files(changed_path: Path) -> list[str]:
    """Read vault-relative paths from a changed_files.txt manifest."""
    if not changed_path.exists():
        print(f"[run_changed] ERROR: changed file manifest not found: {changed_path}")
        return []
    lines = changed_path.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def discover_all_tier0() -> list[str]:
    """Return all Tier 0 sources in the vault."""
    sources = []
    for path in sorted(VAULT_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SOURCE_EXTS:
            continue
        rel_parts = set(path.relative_to(VAULT_ROOT).parts)
        if rel_parts & EXCLUDED_DIRS:
            continue
        if classify_tier(path) == SAFE_INGEST_TIER:
            sources.append(str(path.relative_to(VAULT_ROOT)))
    return sources


def filter_to_safe_tier(paths: list[str]) -> tuple[list[str], list[str]]:
    """Split paths into safe-to-ingest and skipped-by-tier."""
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
    open_conflicts: list[str],
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
        f"- Open conflicts:     {len(open_conflicts)}",
        "",
    ]

    if open_conflicts:
        lines += ["## ⚠ Canon Conflicts — Human Review Required", ""]
        for c in open_conflicts:
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

    lines += [
        "## Exit Code",
        "",
        "0 = clean" if lint_ok and not open_conflicts else
        ("2 = canon conflicts" if open_conflicts else "1 = lint failed"),
        "",
    ]

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
            changed_manifest = Path(args[i + 1])
        if arg == "--file" and i + 1 < len(args):
            single_file = args[i + 1]

    if not any([run_all, changed_manifest, single_file]):
        print(__doc__)
        return 0

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    if dry_run:
        run_id += "_dryrun"
    print(f"[run_changed] MrLore v2 — run {run_id}")
    print(f"[run_changed] Vault: {VAULT_ROOT}")
    if dry_run:
        print("[run_changed] DRY RUN — no changes will be made")

    # 1. Collect sources
    if run_all:
        candidates = discover_all_tier0()
        print(f"[run_changed] --all: {len(candidates)} Tier 0 sources found")
    elif changed_manifest:
        candidates = load_changed_files(changed_manifest)
        print(f"[run_changed] --changed: {len(candidates)} paths loaded")
    else:
        candidates = [single_file]
        print(f"[run_changed] --file: {single_file}")

    # 2. Filter to safe tier
    safe_sources, skipped = filter_to_safe_tier(candidates)
    print(f"[run_changed] Safe to ingest: {len(safe_sources)}  Skipped: {len(skipped)}")

    # 3. Ingest each source
    results = []
    for i, rel in enumerate(safe_sources, 1):
        print(f"[run_changed] [{i}/{len(safe_sources)}] {rel}")
        result = run_ingest_stub(rel, dry_run=dry_run)
        results.append(result)
        if result["status"] == "error":
            print(f"  ERROR: {result.get('stderr', '')[:120]}")
        else:
            print(f"  {result['status'].upper()}")

    # 4. Rebuild registry
    print("[run_changed] Rebuilding registry...")
    registry_ok = run_build_registry(dry_run=dry_run)
    print(f"[run_changed] Registry: {'OK' if registry_ok else 'FAILED'}")

    # 5. Lint
    print("[run_changed] Running lint...")
    lint_ok = run_lint(dry_run=dry_run)
    print(f"[run_changed] Lint: {'OK' if lint_ok else 'FAILED'}")

    # 6. Check open conflicts
    open_conflicts = check_open_conflicts()
    if open_conflicts:
        print(f"[run_changed] ⚠ {len(open_conflicts)} open conflict(s) require human review")

    # 7. Append to wiki log
    if not dry_run:
        log_entry = (
            f"\n## [{datetime.now().strftime('%Y-%m-%d')}] run | {run_id}\n\n"
            f"Sources ingested: {len([r for r in results if r['status'] == 'ok'])}\n"
            f"Skipped: {len(skipped)}\n"
            f"Lint: {'OK' if lint_ok else 'FAILED'}\n"
            f"Open conflicts: {len(open_conflicts)}\n"
        )
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry)

    # 8. Write run report
    report_path = write_run_report(
        run_id, safe_sources, results, skipped,
        registry_ok, lint_ok, open_conflicts, dry_run
    )
    print(f"[run_changed] Report: {report_path}")

    # 9. Exit code
    if not lint_ok:
        print("[run_changed] EXIT 1 — lint failed")
        return 1
    if open_conflicts:
        print("[run_changed] EXIT 2 — canon conflicts require human review")
        return 2
    print("[run_changed] EXIT 0 — clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
