#!/usr/bin/env python3
"""
TASK 6.1A-REPAIR-3: Slugify intended codex candidate filenames.
Reads registry.md, extracts canonical names from column 1, scans source summaries,
and reports mention counts + intended slugified output paths in --dry-run mode.
"""
import argparse
import glob
import os
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")
SOURCES_DIR = os.path.join(BASE_DIR, "wiki/sources")

EXPECTED_HEADER_COLS = ["Canonical Name", "Canon State", "Variants", "First Source", "Page"]

def slugify_filename(name):
    """Deterministically convert canonical name to safe filename."""
    s = name.lower()
    s = s.replace(" ", "_").replace("/", "_").replace("'", "_").replace(":", "_")
    s = re.sub(r'[^a-z0-9_-]', '', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip('_')
    if not s:
        s = "unnamed_entity"
    return s

def parse_registry(path):
    """Parse markdown table and extract unique canonical names from column 1."""
    canonical_names = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"ERROR: Registry not found at {path}", file=sys.stderr)
        sys.exit(1)

    header_index = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = [p.strip() for p in stripped.split("|")[1:-1]]
        if len(parts) >= 2 and parts[0] == EXPECTED_HEADER_COLS[0] and parts[1] == EXPECTED_HEADER_COLS[1]:
            header_index = i
            break

    if header_index is None:
        print("ERROR: Expected registry table header not found.", file=sys.stderr)
        sys.exit(1)

    for line in lines[header_index + 1:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if all("---" in part or not part.strip() for part in stripped.split("|")[1:-1]):
            continue

        parts = [p.strip() for p in stripped.split("|")[1:-1]]
        if len(parts) > 0 and parts[0]:
            canonical_names.append(parts[0])

    seen = set()
    unique = []
    for name in canonical_names:
        if name not in seen:
            seen.add(name)
            unique.append(name)

    return sorted(unique)


def count_mentions(entity_name, sources_dir):
    """Count exact case-sensitive occurrences of entity_name in source summaries."""
    count = 0
    pattern = os.path.join(sources_dir, "*.md")
    for src_path in sorted(glob.glob(pattern)):
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.read()
        count += content.count(entity_name)
    return count


def main():
    parser = argparse.ArgumentParser(description="Codex candidate enumerator")
    parser.add_argument("--dry-run", action="store_true", help="Print candidate info only. No files created.")
    args = parser.parse_args()

    entities = parse_registry(REGISTRY_PATH)

    if not args.dry_run:
        print("ERROR: Only --dry-run is authorized at this phase.", file=sys.stderr)
        sys.exit(2)

    print(f"[DRY-RUN] Total entities to process: {len(entities)}")
    print("-" * 60)
    for name in entities:
        mention_count = count_mentions(name, SOURCES_DIR)
        slug = slugify_filename(name)
        rel_path = os.path.join("wiki", "codex_candidates", f"{slug}.md")
        print(f"Canonical Name: {name}")
        print(f"  Mention Count: {mention_count}")
        print(f"  Intended Output Path (relative to _mrlore): {rel_path}")
        print("-" * 60)

    print("[DRY-RUN] Complete. EXIT 0")
    sys.exit(0)


if __name__ == "__main__":
    main()