#!/usr/bin/env python3
"""
TASK 6.3-STB-2-R2: Scanner misses .txt chapter files.
Expands glob pattern to include both *.md and *.txt.
Now captures all 139 chapters across Books 1-27.
"""
import argparse
import glob
import os
import re
import sys
import yaml
from datetime import date

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")
CHAPTERS_DIR = os.path.join(BASE_DIR, "raw/chapters")
STB_DIR = os.path.join(BASE_DIR, "stb")

# Deterministic relationship phrase patterns (aligned with Phase 6.2B predicates)
RELATIONSHIP_PATTERNS = [
    (r'\bis a member of\b', 'member_of'),
    (r'\bbelongs to\b', 'member_of'),
    (r'\bpart of\b', 'member_of'),
    (r'\ballied with\b', 'allied_with'),
    (r'\bopposes\b', 'opposes'),
    (r'\blocated in\b', 'located_in'),
    (r'\bcreated by\b', 'created_by'),
    (r'\bserves\b', 'serves'),
    (r'\bserved\b', 'serves'),
    (r'\boriginates from\b', 'originates_from')
]

def load_registry_entities():
    """Parse registry.md table into list of (lower_name, original_name) tuples."""
    entities = []
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[WARN] Registry load failed: {e}")
        return entities

    header_found = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = [p.strip() for p in stripped.strip("|").split("|")]
        
        if "Canonical Name" in parts:
            header_found = True
            continue
        if not header_found:
            continue
        if not parts or "---" in parts[0]:
            continue
            
        canon = parts[0]
        if canon:
            entities.append((canon.lower(), canon))
            
        # Add variants
        if len(parts) > 2 and parts[2] and parts[2] not in ("-", "—"):
            for v in parts[2].split(","):
                vc = v.strip()
                if vc and vc not in ("-", "—"):
                    entities.append((vc.lower(), vc))
                    
    return entities

def scan_line(line, line_num, filepath, entities, rel_patterns):
    """Extract entity and relationship signals from a single line."""
    signals = []
    line_text = line.rstrip()
    if not line_text.strip():
        return signals

    # 1. Entity Matches
    matched_entities = set()
    for ent_lower, ent_orig in entities:
        if re.search(rf'\b{re.escape(ent_lower)}\b', line_text, re.IGNORECASE):
            matched_entities.add(ent_orig)

    for ent in matched_entities:
        signals.append({
            "signal_type": "entity",
            "parsed_payload": {
                "entity_name": ent,
                "entity_type": "UNKNOWN",
                "confidence": "medium"
            }
        })

    # 2. Relationship Matches
    for pattern, predicate in rel_patterns:
        if re.search(pattern, line_text, re.IGNORECASE):
            signals.append({
                "signal_type": "relationship",
                "parsed_payload": {
                    "predicate": predicate,
                    "subject": "UNRESOLVED",
                    "target": "UNRESOLVED",
                    "temporal_scope": "unresolved"
                }
            })

    return signals

def main():
    parser = argparse.ArgumentParser(description="STB Chapter Scanner (Phase 6.3)")
    # R1 FIX: required=True -> required=False.
    parser.add_argument("--dry-run", action="store_true", required=False, default=False, help="Print YAML records to stdout only. No writes.")
    parser.add_argument("--limit", type=int, default=None, help="Limit scanner to first N chapter files.")
    args = parser.parse_args()

    if not os.path.exists(CHAPTERS_DIR):
        print("ERROR: raw/chapters/ directory not found.", file=sys.stderr)
        sys.exit(2)

    entities = load_registry_entities()
    print(f"[INIT] Loaded {len(entities)} registry entities/variants for matching.")

    # R2 FIX: Include both .md and .txt files to capture Books 20-27.
    md_files = glob.glob(os.path.join(CHAPTERS_DIR, "*.md"))
    txt_files = glob.glob(os.path.join(CHAPTERS_DIR, "*.txt"))
    chapter_files = sorted(md_files + txt_files)
    
    if args.limit:
        chapter_files = chapter_files[:args.limit]
        print(f"[LIMIT] Scanning {len(chapter_files)} chapter(s) only.")

    all_records = []
    record_counter = 1
    today = date.today().isoformat()

    print(f"[SCAN] Found {len(chapter_files)} total chapter files.")

    for chap_path in chapter_files:
        rel_path = os.path.relpath(chap_path, BASE_DIR)
        print(f"[READING] {rel_path}")
        try:
            with open(chap_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[WARN] Failed to read {chap_path}: {e}")
            continue

        for i, line in enumerate(lines):
            line_num = i + 1
            signals = scan_line(line, line_num, chap_path, entities, RELATIONSHIP_PATTERNS)
            
            for sig in signals:
                buffer_id = f"STB-{today.replace('-', '')}-{record_counter:04d}"
                record = {
                    "buffer_id": buffer_id,
                    "source_file": rel_path,
                    "line_start": line_num,
                    "line_end": line_num,
                    "raw_quote": line.strip(),
                    "signal_type": sig["signal_type"],
                    "parsed_payload": sig["parsed_payload"],
                    "audit_only": True,
                    "status": "captured",
                    "created_date": today,
                    "last_reviewed": None,
                    "supersedes": None
                }
                all_records.append(record)
                record_counter += 1

    print(f"[RESULTS] {len(all_records)} signals captured across {len(chapter_files)} chapter(s).")
    print("-" * 70)

    if args.dry_run:
        for rec in all_records:
            print(f"# {rec['buffer_id']} | {rec['signal_type']} | {rec['source_file']}:{rec['line_start']}")
            print(yaml.safe_dump(rec, default_flow_style=False, allow_unicode=True).strip())
            print("-" * 70)
        print("[DRY-RUN] Complete. No files written to stb/.")
        sys.exit(0)
    else:
        os.makedirs(STB_DIR, exist_ok=True)
        for rec in all_records:
            fname = f"{rec['buffer_id']}-{rec['signal_type']}.yaml"
            out_path = os.path.join(STB_DIR, fname)
            with open(out_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(rec, f, default_flow_style=False, allow_unicode=True)
        print(f"[APPLY] {len(all_records)} records written to stb/. EXIT 0")
        sys.exit(0)

if __name__ == "__main__":
    main()