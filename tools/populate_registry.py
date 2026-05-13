#!/usr/bin/env python3
"""
TASK 6.2C-REGISTRY-1-REPAIR: Harden registry population tool.
Fixes: canonical form regex, variant table bleed, removes --write flag.
Strictly proposal/dry-run only. No autonomous mutation. Proposal != Approval != Mutation.
"""
import argparse
import glob
import os
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
WIKI_DIR = os.path.join(BASE_DIR, "wiki")
CANON_DIR = os.path.join(BASE_DIR, "wiki/canon_decisions")

SCAN_FOLDERS = ["species", "factions", "characters", "locations", "systems"]
IGNORE_FILES = {"index.md", "log.md"}

def normalize_name(filename):
    """Convert filename to human-readable Title Case."""
    name = os.path.splitext(filename)[0]
    name = name.replace("_", " ").replace("-", " ")
    return name.title()

def extract_canon_decisions():
    """Parse canon decision files for entity states and variants."""
    decisions = {}
    for path in sorted(glob.glob(os.path.join(CANON_DIR, "*.md"))):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Fix 1: Robust canonical form regex (handles **bold** markdown)
        canon_match = re.search(r"Canonical form:\s*\*\*([^*]+)\*\*", content)
        canonical = canon_match.group(1).strip() if canon_match else None

        status_match = re.search(r"Status:\s*(\w+)", content)
        status = status_match.group(1).lower() if status_match else "unknown"

        if canonical:
            decisions[canonical] = {
                "state": "canon_" + status,
                "variants": []
            }

            lines = content.split('\n')
            in_table = False
            for line in lines:
                stripped = line.strip()

                # Fix 2: Explicit table termination to prevent variant bleed
                if in_table and not stripped.startswith("|"):
                    in_table = False
                    continue

                if stripped.startswith("| Variant"):
                    in_table = True
                    continue

                if in_table and stripped.startswith("|"):
                    parts = [p.strip() for p in stripped.split("|")]
                    if len(parts) > 1:
                        variant = parts[1]
                        if variant and variant != "Variant" and "---" not in variant:
                            decisions[canonical]["variants"].append(variant)
    return decisions

def scan_wiki():
    """Scan wiki folders for existing entity pages."""
    entities = {}
    for folder in SCAN_FOLDERS:
        path = os.path.join(WIKI_DIR, folder)
        if not os.path.exists(path):
            continue
        
        for filename in os.listdir(path):
            if filename.endswith(".md") and filename not in IGNORE_FILES:
                name = normalize_name(filename)
                rel_page = f"wiki/{folder}/{filename}"
                entities[name] = {
                    "folder": folder,
                    "page": rel_page,
                    "state": "wiki_only",
                    "variants": "",
                    "first_source": "wiki_scan"
                }
    return entities

def merge_canon_data(entities, decisions):
    """Enrich entities with canon decision data (case-insensitive matching)."""
    for canonical, info in decisions.items():
        for name in list(entities.keys()):
            if name.lower() == canonical.lower():
                entities[name]["state"] = info["state"]
                entities[name]["variants"] = ", ".join(info["variants"])
                break

def generate_table(entities):
    """Generate Markdown table rows."""
    rows = []
    for name in sorted(entities.keys()):
        info = entities[name]
        rows.append(f"| {name} | {info['state']} | {info['variants']} | {info['first_source']} | {info['page']} |")
    return "\n".join(rows)

def main():
    # Fix 3: --write flag removed entirely. Strict separation of proposal vs mutation.
    parser = argparse.ArgumentParser(description="Registry Population Tool (Proposal Only)")
    parser.add_argument("--dry-run", action="store_true", required=True, help="Output proposed registry content. No writes.")
    args = parser.parse_args()

    decisions = extract_canon_decisions()
    entities = scan_wiki()
    merge_canon_data(entities, decisions)
    
    table_content = generate_table(entities)
    header = """| Canonical Name | Canon State | Variants | First Source | Page |
| --- | --- | --- | --- | --- |"""
    
    output = header + "\n" + table_content
    
    print("[DRY-RUN] Proposed registry.md content:")
    print("-" * 70)
    print(output)
    print("-" * 70)
    print(f"[STATS] Found {len(entities)} entities in wiki scan.")
    print(f"[STATS] Found {len(decisions)} active canon decisions.")
    print("[NOTE] This is a proposal tool. No write path exists in this executable.")
    print("[DRY-RUN] Complete. EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()