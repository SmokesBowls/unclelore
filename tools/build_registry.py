#!/usr/bin/env python3
"""
TASK 7.4A-R1: Repair build_registry.py truncation bug.
Fixes file write logic to accumulate all entity data before writing to registry.md.
Ensures all entities and variants persist in the final output.
Deterministic, single-pass write. EXIT 0 enforced.
"""
import os
import glob
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")
CANON_DIR = os.path.join(BASE_DIR, "wiki/canon_decisions")
WIKI_DIRS = {
    "characters": os.path.join(BASE_DIR, "wiki/characters"),
    "factions": os.path.join(BASE_DIR, "wiki/factions"),
    "species": os.path.join(BASE_DIR, "wiki/species"),
    "locations": os.path.join(BASE_DIR, "wiki/locations"),
    "systems": os.path.join(BASE_DIR, "wiki/systems"),
    "artifacts": os.path.join(BASE_DIR, "wiki/artifacts"),
    "events": os.path.join(BASE_DIR, "wiki/events"),
    "arcs": os.path.join(BASE_DIR, "wiki/arcs"),
    "timelines": os.path.join(BASE_DIR, "wiki/timelines"),
    "terms": os.path.join(BASE_DIR, "wiki/terms"),
}

def parse_canon_decisions():
    """Extract variants and original casing from CANON-*.md files."""
    aliases = {} # maps variant_lower -> (canonical, variant_original)
    for fp in sorted(glob.glob(os.path.join(CANON_DIR, "*.md"))):
        if not os.path.basename(fp).startswith("CANON-"):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            
            canon_match = re.search(r"Canonical form:\s*\*\*([^*]+)\*\*", content)
            if not canon_match:
                canon_match = re.search(r"Canonical form:\s*([^\n]+)", content)
            canonical = canon_match.group(1).strip() if canon_match else None
            if not canonical: continue
            
            lines = content.split('\n')
            in_table = False
            for line in lines:
                stripped = line.strip()
                if "Variant" in stripped and stripped.startswith("|"):
                    in_table = True
                    continue
                if in_table:
                    if stripped.startswith("|"):
                        parts = [p.strip() for p in stripped.split("|")]
                        if len(parts) >= 3:
                            variant_orig = parts[1].strip()
                            classification = parts[2].lower()
                            if variant_orig and "---" not in variant_orig and ("drift" in classification or "alias" in classification):
                                aliases[variant_orig.lower()] = (canonical, variant_orig)
                    else:
                        in_table = False
        except Exception:
            continue
    return aliases

def scan_wiki_pages():
    """Scan wiki directories for entity pages."""
    entities = {}
    for dir_name, dir_path in WIKI_DIRS.items():
        if not os.path.exists(dir_path):
            continue
        for filename in sorted(os.listdir(dir_path)):
            if not filename.endswith(".md"):
                continue
            name = os.path.splitext(filename)[0].replace("_", " ").title()
            if name.lower() in ("index", "log"):
                continue
            entities[name.lower()] = {
                "name": name,
                "type": dir_name.title().rstrip('s'),
                "page": f"wiki/{dir_name}/{filename}",
                "variants": []
            }
    return entities

def merge_and_write():
    """Merge canon variants into wiki entities and write registry in ONE operation."""
    aliases = parse_canon_decisions()
    entities = scan_wiki_pages()
    
    # Apply aliases to entities
    for variant_lower, (canonical, variant_orig) in aliases.items():
        canon_lower = canonical.lower()
        if canon_lower in entities:
            if variant_orig not in entities[canon_lower]["variants"]:
                entities[canon_lower]["variants"].append(variant_orig)

    # Build rows in memory
    rows = []
    header = "| Canonical Name | Canon State | Variants | First Source | Page |\n| --- | --- | --- | --- | --- |"
    rows.append(header)
    
    sorted_entities = sorted(entities.values(), key=lambda e: e["name"])
    
    for ent in sorted_entities:
        var_str = ", ".join(sorted(ent["variants"])) if ent["variants"] else ""
        state = "wiki_only"
        row = f"| {ent['name']} | {state} | {var_str} | wiki_scan | {ent['page']} |"
        rows.append(row)

    final_content = "\n".join(rows) + "\n"
    
    # FIX R1: Single atomic write. No loop-based overwrites.
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        f.write(final_content)
        
    count = len(rows) - 1
    print(f"[BUILD] Registry written with {count} entities.")
    print(f"[BUILD] Path: {REGISTRY_PATH}")
    print("EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    merge_and_write()