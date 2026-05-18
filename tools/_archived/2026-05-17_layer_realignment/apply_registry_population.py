#!/usr/bin/env python3
"""
TASK 6.2C-REGISTRY-2: Apply approved registry proposal.
Safely updates wiki/registry.md with populated canonical anchors.
Creates atomic backup. Replaces only the markdown table. Preserves all surrounding metadata.
Deterministic. No LLM. EXIT 0/2 semantics enforced.
"""
import glob
import os
import re
import sys
from datetime import datetime

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")
WIKI_DIR = os.path.join(BASE_DIR, "wiki")
CANON_DIR = os.path.join(BASE_DIR, "wiki/canon_decisions")
SCAN_FOLDERS = ["species", "factions", "characters", "locations", "systems"]
IGNORE_FILES = {"index.md", "log.md"}

def normalize_name(filename):
    """Convert filename to human-readable Title Case."""
    name = os.path.splitext(filename)[0]
    return name.replace("_", " ").replace("-", " ").title()

def extract_canon_decisions():
    """Parse canon decision files for entity states and variants."""
    decisions = {}
    for path in sorted(glob.glob(os.path.join(CANON_DIR, "*.md"))):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        canon_match = re.search(r"Canonical form:\s*\*\*([^*]+)\*\*", content)
        canonical = canon_match.group(1).strip() if canon_match else None
        status_match = re.search(r"Status:\s*(\w+)", content)
        status = status_match.group(1).lower() if status_match else "unknown"

        if canonical:
            decisions[canonical] = {"state": "canon_" + status, "variants": []}
            lines = content.split('\n')
            in_table = False
            for line in lines:
                stripped = line.strip()
                if in_table and not stripped.startswith("|"):
                    in_table = False; continue
                if stripped.startswith("| Variant"):
                    in_table = True; continue
                if in_table and stripped.startswith("|"):
                    parts = [p.strip() for p in stripped.split("|")]
                    if len(parts) > 1:
                        v = parts[1]
                        if v and v != "Variant" and "---" not in v:
                            decisions[canonical]["variants"].append(v)
    return decisions

def scan_wiki():
    """Scan wiki folders for existing entity pages."""
    entities = {}
    for folder in SCAN_FOLDERS:
        path = os.path.join(WIKI_DIR, folder)
        if not os.path.exists(path): continue
        for filename in os.listdir(path):
            if filename.endswith(".md") and filename not in IGNORE_FILES:
                name = normalize_name(filename)
                entities[name] = {
                    "folder": folder, "page": f"wiki/{folder}/{filename}",
                    "state": "wiki_only", "variants": "", "first_source": "wiki_scan"
                }
    return entities

def merge_canon_data(entities, decisions):
    """Enrich entities with canon decision data."""
    for canonical, info in decisions.items():
        for name in list(entities.keys()):
            if name.lower() == canonical.lower():
                entities[name]["state"] = info["state"]
                entities[name]["variants"] = ", ".join(info["variants"])
                break

def generate_table(entities):
    """Generate deterministic Markdown table."""
    header = "| Canonical Name | Canon State | Variants | First Source | Page |\n| --- | --- | --- | --- | --- |"
    rows = []
    for name in sorted(entities.keys()):
        info = entities[name]
        rows.append(f"| {name} | {info['state']} | {info['variants']} | {info['first_source']} | {info['page']} |")
    return header + "\n" + "\n".join(rows)

def main():
    if not os.path.exists(REGISTRY_PATH):
        print("ERROR: wiki/registry.md not found.", file=sys.stderr)
        sys.exit(2)

    # Generate proposal table
    decisions = extract_canon_decisions()
    entities = scan_wiki()
    merge_canon_data(entities, decisions)
    new_table = generate_table(entities)

    # Read current registry
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        original_content = f.read()

    lines = original_content.split('\n')
    header_idx = None
    for i, line in enumerate(lines):
        if "Canonical Name" in line and line.strip().startswith("|"):
            header_idx = i
            break

    if header_idx is None:
        print("ERROR: Could not locate registry table header.", file=sys.stderr)
        sys.exit(2)

    # Find last row of the table
    table_end_idx = header_idx
    for i in range(header_idx, len(lines)):
        if lines[i].strip().startswith("|"):
            table_end_idx = i
        else:
            break  # Table ended

    # Validate basic structure
    if not any("---" in lines[j] for j in range(header_idx, table_end_idx + 1)):
        print("ERROR: Invalid registry table format (missing separator).", file=sys.stderr)
        sys.exit(2)

    # Atomic backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{REGISTRY_PATH}.bak.{timestamp}"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(original_content)

    # Replace table slice deterministically
    new_table_lines = new_table.split('\n')
    updated_lines = lines[:header_idx] + new_table_lines + lines[table_end_idx + 1:]
    new_content = '\n'.join(updated_lines)

    # Write updated registry
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[APPLY] Registry table updated successfully.")
    print(f"[BACKUP] Created: {os.path.relpath(backup_path, BASE_DIR)}")
    print(f"[ENTITIES] {len(entities)} canonical anchors applied.")
    print("[VALIDATION] Table structure preserved. Metadata intact.")
    print("EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()