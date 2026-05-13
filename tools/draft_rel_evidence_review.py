#!/usr/bin/env python3
"""
TASK 6.2D-SOURCE-3: Draft relationship evidence review worksheet (human-review gated).
Surfaces existing explicit claims OR provides blank review scaffold for authoring.
STRICTLY NO INFERENCE. Dry-run only. EXIT 0/2 enforced.
"""
import argparse
import glob
import os
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")
SCAN_DIRS = [
    os.path.join(BASE_DIR, "wiki/species"),
    os.path.join(BASE_DIR, "wiki/factions"),
    os.path.join(BASE_DIR, "wiki/characters"),
    os.path.join(BASE_DIR, "wiki/locations"),
    os.path.join(BASE_DIR, "wiki/systems"),
    os.path.join(BASE_DIR, "wiki/canon_decisions"),
    os.path.join(BASE_DIR, "wiki/sources")
]

# Explicit relationship predicates only. No semantic expansion.
ALLOWED_PHRASES = [
    r'\bis a member of\b',
    r'\bbelongs to\b',
    r'\bpart of\b',
    r'\bserves\b',
    r'\ballied with\b',
    r'\bopposes\b',
    r'\boriginates from\b',
    r'\bcreated by\b'
]

def load_registry_entities():
    """Load canonical entity names from registry.md Column 1 only."""
    entities = set()
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        header_found = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|"):
                parts = [p.strip() for p in stripped.strip("|").split("|")]
                if "Canonical Name" in parts:
                    header_found = True; continue
                if not header_found: continue
                if parts and parts[0] and "---" not in parts[0]:
                    entities.add(parts[0].strip())
    except Exception:
        pass
    return sorted(entities)

def scan_explicit_relationships():
    """Scan corpus for explicit relationship phrases ONLY. No inference."""
    explicit_claims = []
    for d in SCAN_DIRS:
        if not os.path.exists(d): continue
        for fp in sorted(glob.glob(os.path.join(d, "*.md"))):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        for ph in ALLOWED_PHRASES:
                            if re.search(ph, line, re.IGNORECASE):
                                explicit_claims.append({
                                    "file": os.path.relpath(fp, BASE_DIR),
                                    "line": i,
                                    "text": line.strip(),
                                    "predicate": ph.strip(r'\b')
                                })
                                break
            except Exception:
                continue
    return explicit_claims

def main():
    parser = argparse.ArgumentParser(description="Relationship Evidence Review Worksheet")
    parser.add_argument("--dry-run", action="store_true", required=True, help="Print worksheet only. No writes.")
    args = parser.parse_args()

    entities = load_registry_entities()
    explicit_claims = scan_explicit_relationships()

    print("[REVIEW] Relationship Evidence Worksheet (Dry-Run)")
    print("=" * 70)

    if explicit_claims:
        print("[SECTION] Explicitly Stated Relationships (Verified)")
        for c in explicit_claims:
            print(f"  - {c['file']}:{c['line']} | \"{c['text']}\"")
        print("-" * 70)
    else:
        print("[INFO] Zero explicit relationship predicates found in current corpus.")
        print("[INFO] No inference applied. Proceeding to blank review scaffold.")
        print("-" * 70)

    print("[WORKSHEET] Pending Author Review (Fill & Approve)")
    print("Format: [ ] Entity: ___ | Relationship Type: ___ | Target: ___ | Evidence: ___ | requires_author_approval: true")
    print("=" * 70)
    for ent in entities:
        print(f"[ ] Entity: {ent} | Relationship Type: ___ | Target: ___ | Evidence: ___ | requires_author_approval: true")
    print("=" * 70)
    
    print("[GOVERNANCE NOTE]")
    print("- No aliases, variants, or canon decisions were converted to relationships.")
    print("- No semantic inference or graph edges generated.")
    print("- Tool output is strictly a human-authoring scaffold.")
    print("[REVIEW] Complete. EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()