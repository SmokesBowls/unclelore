#!/usr/bin/env python3
"""
TASK 6.2D-SOURCE-2: Propose review-only relationship source stubs from existing entity pages.
Scans wiki entity pages for explicit relationship predicates.
Proposes normalized source stubs without inferring or inventing lore.
Dry-run only. Zero writes. EXIT 0/2 enforced.
"""
import argparse
import glob
import os
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
SCAN_DIRS = [
    os.path.join(BASE_DIR, "wiki/species"),
    os.path.join(BASE_DIR, "wiki/factions"),
    os.path.join(BASE_DIR, "wiki/characters"),
    os.path.join(BASE_DIR, "wiki/locations"),
    os.path.join(BASE_DIR, "wiki/systems")
]

# Explicit allowed relationship phrases only. No inference.
ALLOWED_PHRASES = [
    r'\bis a member of\b',
    r'\bbelongs to\b',
    r'\bpart of\b',
    r'\bserves\b',
    r'\bserved\b',
    r'\ballied with\b',
    r'\bopposes\b',
    r'\boriginates from\b',
    r'\bcreated by\b'
]

def slugify(filename):
    return os.path.splitext(filename)[0].lower().replace(" ", "_").replace("-", "_")

def scan_entity_pages():
    """Scan entity wiki pages for explicit relationship predicates."""
    proposals = []
    for dir_path in SCAN_DIRS:
        if not os.path.exists(dir_path): continue
        for fp in sorted(glob.glob(os.path.join(dir_path, "*.md"))):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception: continue
            
            entity_slug = slugify(os.path.basename(fp))
            entity_rel_lines = []
            
            for i, line in enumerate(lines):
                for phrase in ALLOWED_PHRASES:
                    if re.search(phrase, line, re.IGNORECASE):
                        entity_rel_lines.append({
                            "line": line.strip(),
                            "line_num": i + 1,
                            "phrase": phrase.strip(r'\b')
                        })
                        break
            
            if entity_rel_lines:
                proposals.append({
                    "source_file": os.path.relpath(fp, BASE_DIR),
                    "entity_slug": entity_slug,
                    "lines": entity_rel_lines
                })
    return proposals

def main():
    parser = argparse.ArgumentParser(description="Propose relationship source stubs")
    parser.add_argument("--dry-run", action="store_true", required=True, help="Print proposals only. No writes.")
    args = parser.parse_args()
    
    proposals = scan_entity_pages()
    
    print("[PROPOSAL] Relationship Source Stubs (Dry-Run)")
    print(f"[SCANNED] {len(proposals)} entity pages containing explicit relationship phrases")
    print("-" * 70)
    
    if not proposals:
        print("[INFO] Zero explicit relationship phrases found in entity wiki pages.")
        print("[NOTE] Relationship evidence must be explicitly stated in source text or entity pages before stubs can be proposed.")
    else:
        for p in proposals:
            out_path = f"wiki/sources/rel_stub_{p['entity_slug']}.md"
            fm = f"""---
type: source_summary
status: candidate
canon_state: provisional
review_only: true
source_type: relationship_stub
origin_page: {p['source_file']}
---
# Relationship Evidence: {p['entity_slug']}

## Extracted Claims
"""
            content = fm
            for l in p['lines']:
                content += f"- \"{l['line']}\" (Line {l['line_num']}, Predicate: {l['phrase']})\n"
            
            print(f"[PROPOSED FILE] {out_path}")
            print(content)
            print("-" * 70)
            
    print("[PROPOSAL] Complete. Awaiting human review.")
    print("EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()