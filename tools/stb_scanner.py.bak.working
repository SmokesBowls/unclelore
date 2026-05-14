#!/usr/bin/env python3
"""
TASK 6.3-STB-3: Resolve entity_type from registry metadata.
Parses wiki/registry.md Page column to deterministically map entities to MRLORE_SCHEMA types.
Eliminates entity_type: UNKNOWN by bridging registry path -> type code.
Dry-run only. Zero mutations. Deterministic EXIT 0/2.
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

# MRLORE_SCHEMA type mapping from directory paths
TYPE_MAP_FROM_PATH = {
    "characters": "CHR",
    "factions":   "FAC",
    "species":    "SPEC",
    "locations":  "LOC",
    "systems":    "SYS",
    "artifacts":  "ART",
    "events":     "EVT",
    "arcs":       "ARC",
    "timelines":  "TML",
    "terms":      "TRM",
}

def load_registry_entities():
    """
    Parse registry.md into {lower_entity_name: (original_name, type_code)}.
    Extracts type from the Page column (index 4) using deterministic directory mapping.
    """
    entity_data = {}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[WARN] Registry load failed: {e}", file=sys.stderr)
        return entity_data

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
        # Resolve type from Page column (index 4)
        type_code = "UNKNOWN"
        if len(parts) > 4 and parts[4]:
            page_path = parts[4].lower()
            for dir_name, type_str in TYPE_MAP_FROM_PATH.items():
                if f"/{dir_name}/" in page_path:
                    type_code = type_str
                    break

        # Store canonical entry
        if canon:
            entity_data[canon.lower()] = (canon, type_code)
            
        # Store variant entries (inherit canonical type)
        if len(parts) > 2 and parts[2] and parts[2] not in ("-", "—"):
            for v in parts[2].split(","):
                vc = v.strip()
                if vc and vc not in ("-", "—"):
                    entity_data[vc.lower()] = (canon, type_code)
                    
    return entity_data

def scan_line(line, line_num, filepath, entity_data, rel_patterns):
    """Extract entity and relationship signals from a single line."""
    signals = []
    line_text = line.rstrip()
    if not line_text.strip():
        return signals

    # 1. Entity Matches
    matched_entities = set()
    for ent_lower in entity_data:
        if re.search(rf'\b{re.escape(ent_lower)}\b', line_text, re.IGNORECASE):
            matched_entities.add(ent_lower)

    for ent_lower in matched_entities:
        orig_name, type_code = entity_data[ent_lower]
        signals.append({
            "signal_type": "entity",
            "parsed_payload": {
                "entity_name": orig_name,
                "entity_type": type_code,
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
    parser.add_argument("--dry-run", action="store_true", required=False, default=True, help="Print YAML records to stdout only. No writes.")
    parser.add_argument("--limit", type=int, default=None, help="Limit scanner to first N chapter files.")
    args = parser.parse_args()

    if not os.path.exists(CHAPTERS_DIR):
        print("ERROR: raw/chapters/ directory not found.", file=sys.stderr)
        sys.exit(2)

    entity_data = load_registry_entities()
    print(f"[INIT] Loaded {len(entity_data)} registry entities/variants with type mapping.", file=sys.stderr)

    # Include both .md and .txt files to capture full corpus
    md_files = glob.glob(os.path.join(CHAPTERS_DIR, "*.md"))
    txt_files = glob.glob(os.path.join(CHAPTERS_DIR, "*.txt"))
    chapter_files = sorted(md_files + txt_files)
    
    if args.limit:
        chapter_files = chapter_files[:args.limit]
        print(f"[LIMIT] Scanning {len(chapter_files)} chapter(s) only.", file=sys.stderr)

    all_records = []
    record_counter = 1
    today = date.today().isoformat()

    print(f"[SCAN] Found {len(chapter_files)} total chapter files.", file=sys.stderr)

    for chap_path in chapter_files:
        rel_path = os.path.relpath(chap_path, BASE_DIR)
        print(f"[READING] {rel_path}", file=sys.stderr)
        try:
            with open(chap_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[WARN] Failed to read {chap_path}: {e}", file=sys.stderr)
            continue

        for i, line in enumerate(lines):
            line_num = i + 1
            signals = scan_line(line, line_num, chap_path, entity_data, RELATIONSHIP_PATTERNS)
            
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

    print(f"[RESULTS] {len(all_records)} signals captured across {len(chapter_files)} chapter(s).", file=sys.stderr)
    print("-" * 70, file=sys.stderr)

    if args.dry_run:
        for rec in all_records:
            print(f"# {rec['buffer_id']} | {rec['signal_type']} | {rec['source_file']}:{rec['line_start']}")
            print(yaml.safe_dump(rec, default_flow_style=False, allow_unicode=True).strip())
            print("-" * 70, file=sys.stderr)
        print("[DRY-RUN] Complete. No files written to stb/.", file=sys.stderr)
        sys.exit(0)
    else:
        os.makedirs(STB_DIR, exist_ok=True)
        for rec in all_records:
            fname = f"{rec['buffer_id']}-{rec['signal_type']}.yaml"
            out_path = os.path.join(STB_DIR, fname)
            with open(out_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(rec, f, default_flow_style=False, allow_unicode=True)
        print(f"[APPLY] {len(all_records)} records written to stb/. EXIT 0", file=sys.stderr)
        sys.exit(0)

if __name__ == "__main__":
    main()