#!/usr/bin/env python3
"""
MrLore v2 — Source Authority Auditor
Purpose: Scan the entire vault, classify every source file by authority tier,
         and produce a report. Does NOT ingest, copy, or modify anything.

Authority Tiers:
    0 — Canonical book chapters (authored narrative prose)
    1 — Deep lore / canon support / character profiles / canon decisions
    2 — Generated EngAIn / parser artifacts / structured exports
    3 — Loose notes / scratch / uncertain / session chat logs
    4 — JSON / cache / runtime / generated data / duplicates

Usage:
    python3 audit_source_authority.py
    python3 audit_source_authority.py --verbose
    python3 audit_source_authority.py --tier 0        # show only tier 0
    python3 audit_source_authority.py --out report.md # save report
"""

import sys
import re
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MRLORE_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT  = MRLORE_ROOT.parent

# Dirs/files to always skip
EXCLUDED_DIRS = {
    "_mrlore", ".git", ".obsidian", "__pycache__",
    ".trash", "node_modules", ".DS_Store",
}

# ── TIER CLASSIFICATION RULES ────────────────────────────────────────────────
# Each rule is (tier, reason, test_fn)
# First matching rule wins.

def _is_chapter_file(path: Path) -> bool:
    """Numbered chapter files: 001_name.md, 47_name.txt, etc."""
    return bool(re.match(r"^\d+[_\-]", path.name))

def _is_book_dir(path: Path) -> bool:
    """File lives directly inside a top-level book_* directory."""
    try:
        rel = path.relative_to(VAULT_ROOT)
    except Exception:
        return False

    if ".engain" in rel.parts:
        return False

    return (
        len(rel.parts) >= 2
        and rel.parts[0].lower().startswith("book_")
    )

def _in_southern_arc(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    return "southern arc" in parts or "southern_arc" in parts

TIER_RULES = [
    # ── TIER 4: generated / cache / runtime ─────────────────────────────────
    (4, "JSON data file",
        lambda p: p.suffix.lower() == ".json"),
    (4, "Python cache",
        lambda p: "__pycache__" in p.parts or p.suffix == ".pyc"),
    (4, "Shell script",
        lambda p: p.suffix == ".sh"),
    (4, "Python script",
        lambda p: p.suffix == ".py"),
    (4, "Duplicate marker ((1) in name)",
        lambda p: "(1)" in p.name or "(2)" in p.name or "(3)" in p.name),
    (4, "Manifest / vault index",
        lambda p: p.name.lower() in {"vault.manifest.json", "manifest.json"}),

    # ── TIER 1: explicit building_the_world authority overrides ─────────────
    (1, "building_the_world character/chapter lore",
        lambda p: "building_the_world" in str(p).lower()
                   and p.parent.name.lower() in {"character lore", "chapter lore"}),
    (1, "building_the_world named lore file",
        lambda p: "building_the_world" in str(p).lower()
                   and any(k in p.name.lower() for k in
                          ["magic", "canon", "lore", "profile", "guardian", "spire",
                           "graviton", "void", "vale", "vien", "keeper", "unresolved",
                           "dragon", "galactic", "nephoretti", "igigi", "giant"])),

    # ── TIER 3: scratch / loose / session notes ──────────────────────────────
    (3, "Fairy tale variant (extra/alternate)",
        lambda p: "fairy_tale" in p.parent.name.lower() or "fairy tale" in p.parent.name.lower()),
    (3, "Extra / alternate folder",
        lambda p: p.parent.name.lower() in {"extra", "extra_02", "extras", "ongoing", "solid"}
                  or p.parent.name.lower().startswith("extra")),
    (3, "Session / chat log",
        lambda p: any(k in p.name.lower() for k in
                      ["chat", "1st chat", "2nd chat", "3rd", "session", "co author", "conspiratorium"])),
    (3, "Moved from markor (legacy mobile notes)",
        lambda p: "moved from markor" in str(p).lower()),
    (3, "Loose scratch file at vault root",
        lambda p: p.parent == VAULT_ROOT),

    # ── TIER 2: generated / EngAIn / parser artifacts ───────────────────────
    (2, "MrLore / EngAIn generated output",
        lambda p: any(k in p.name.lower() for k in
                      ["engain", "mrlore", "zw_", "ap_", "llm_template", "trixel"])),
    (2, "Mechanical lore (EngAIn parser output)",
        lambda p: "mechanical lore" in p.name.lower()),
    (2, "NotebookLM TOC export",
        lambda p: "nlm" in p.name.lower() or "nlm_toc" in p.name.lower()
                  or p.name.lower().startswith("nlm")),
    (2, "TOC / table of contents file",
        lambda p: p.name.lower().startswith("toc") or "_toc" in p.name.lower()
                  or "toc_" in p.name.lower()),
    (2, "Synapsis / synopsis export",
        lambda p: "synapsis" in p.name.lower() or "synopsis" in p.name.lower()),

    # ── TIER 1: deep lore / profiles / canon support ─────────────────────────
    (1, "Canon file (explicit canon marker)",
        lambda p: "canon" in p.name.lower()),
    (1, "Unresolved lore tracker",
        lambda p: "unresolved" in p.name.lower()),
    (1, "Character lore / profile",
        lambda p: any(k in p.name.lower() for k in
                      ["lore", "profile", "magic", "abilities", "character effects"])),
    (1, "Species / faction reference",
        lambda p: any(k in p.name.lower() for k in
                      ["nephoretti", "igigi", "graviton", "giant", "neferati",
                       "anunnaki", "keeper", "aeon", "pelagor", "brajor"])),
    (1, "Location / worldbuilding reference",
        lambda p: any(k in p.name.lower() for k in
                      ["void spire", "first shore", "void_spire", "first_shore",
                       "labyrinth", "garden", "needle", "spire"])),
    (1, "Named character deep file",
        lambda p: any(k in p.name.lower() for k in
                      ["vale", "zephyr", "tran", "keen", "vien", "isla", "luminaire",
                       "geralt", "nammu", "enlil", "sera", "mika", "rongtai",
                       "thang", "viên"])),

    # ── TIER 0: canonical chapter prose ──────────────────────────────────────
    (0, "Numbered chapter in book directory",
        lambda p: _is_chapter_file(p) and _is_book_dir(p)),
    (0, "Numbered chapter in Southern Arc book",
        lambda p: _is_chapter_file(p) and _in_southern_arc(p)),
]

def classify(path: Path) -> tuple[int, str]:
    for tier, reason, test in TIER_RULES:
        try:
            if test(path):
                return tier, reason
        except Exception:
            pass
    return 3, "unclassified — review manually"


# ── SCANNER ───────────────────────────────────────────────────────────────────

def scan_vault() -> list[dict]:
    results = []
    for path in sorted(VAULT_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = set(path.relative_to(VAULT_ROOT).parts)
        if rel_parts & EXCLUDED_DIRS:
            continue
        tier, reason = classify(path)
        results.append({
            "path":   path,
            "rel":    path.relative_to(VAULT_ROOT),
            "tier":   tier,
            "reason": reason,
            "size":   path.stat().st_size,
            "ext":    path.suffix.lower(),
        })
    return results


# ── REPORT ────────────────────────────────────────────────────────────────────

TIER_LABELS = {
    0: "Tier 0 — Canonical Chapter Prose",
    1: "Tier 1 — Deep Lore / Canon Support",
    2: "Tier 2 — Generated / EngAIn / Parser Artifacts",
    3: "Tier 3 — Loose Notes / Scratch / Uncertain",
    4: "Tier 4 — JSON / Cache / Runtime / Scripts",
}

TIER_ADVICE = {
    0: "These are MrLore's primary ingest targets.",
    1: "Migrate existing canon/lore files into wiki/ manually before batch ingest.",
    2: "Review before ingesting — may contain useful structure or be safely ignored.",
    3: "Review individually. Some may be promotable to Tier 1.",
    4: "Do not ingest. These are runtime artifacts.",
}

def build_report(results: list[dict], verbose: bool = False,
                 tier_filter: int = None) -> str:
    by_tier = defaultdict(list)
    for r in results:
        by_tier[r["tier"]].append(r)

    lines = [
        "# MrLore Vault Authority Audit",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Vault:     {VAULT_ROOT}",
        f"Total files scanned: {len(results)}",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Tier | Label | Count |",
        "|------|-------|-------|",
    ]
    for t in sorted(TIER_LABELS):
        count = len(by_tier[t])
        lines.append(f"| {t} | {TIER_LABELS[t]} | {count} |")
    lines.append("")

    for t in sorted(TIER_LABELS):
        if tier_filter is not None and t != tier_filter:
            continue
        group = by_tier[t]
        if not group:
            continue
        lines.append(f"## {TIER_LABELS[t]}")
        lines.append("")
        lines.append(f"*{TIER_ADVICE[t]}*")
        lines.append(f"Count: {len(group)}")
        lines.append("")

        # Group by parent directory
        by_parent = defaultdict(list)
        for r in group:
            by_parent[str(r["rel"].parent)].append(r)

        for parent in sorted(by_parent):
            lines.append(f"### {parent}")
            lines.append("")
            for r in sorted(by_parent[parent], key=lambda x: str(x["rel"])):
                size_kb = r["size"] / 1024
                if verbose:
                    lines.append(f"- `{r['rel'].name}` ({size_kb:.1f}KB) — {r['reason']}")
                else:
                    lines.append(f"- `{r['rel'].name}`")
            lines.append("")

    return "\n".join(lines)


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> int:
    verbose     = "--verbose" in sys.argv or "-v" in sys.argv
    tier_filter = None
    out_path    = None

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--tier" and i < len(sys.argv) - 1:
            try:
                tier_filter = int(sys.argv[i + 1])
            except ValueError:
                print("--tier requires an integer 0-4")
                return 1
        if arg == "--out" and i < len(sys.argv) - 1:
            out_path = Path(sys.argv[i + 1])

    print(f"[audit] Scanning vault: {VAULT_ROOT}")
    results = scan_vault()
    print(f"[audit] {len(results)} files found")

    by_tier = defaultdict(list)
    for r in results:
        by_tier[r["tier"]].append(r)

    for t in sorted(TIER_LABELS):
        print(f"  Tier {t}: {len(by_tier[t]):>4}  {TIER_LABELS[t]}")

    report = build_report(results, verbose=verbose, tier_filter=tier_filter)

    if out_path:
        out_path.write_text(report, encoding="utf-8")
        print(f"\n[audit] Report written to {out_path}")
    else:
        # Write to logs/ by default
        logs_dir = MRLORE_ROOT / "logs"
        logs_dir.mkdir(exist_ok=True)
        default_out = logs_dir / f"audit_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        default_out.write_text(report, encoding="utf-8")
        print(f"\n[audit] Report written to {default_out}")

    print("\n[audit] Next steps:")
    print("  1. Review Tier 3 — promote or discard")
    print("  2. Migrate Tier 1 canon files into wiki/")
    print("  3. Decide which Tier 0 roots to use for batch ingest")
    print("  4. Build query_mrlore.py once source roots are confirmed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
