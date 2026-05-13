#!/usr/bin/env python3
"""
TASK 6.3-STB-4-R1: Fix stb_lint.py --stdin parser to ignore scanner log lines.
Splits input on '# STB-' headers to isolate YAML records and strip separator lines.
Deterministic. Read-only. EXIT 0/2 semantics.
"""
import sys
import os
import yaml
import argparse
import glob
import re

# Schema Constraints from SEMANTIC_BUFFER_SCHEMA.md
REQUIRED_FIELDS = {
    'buffer_id', 'source_file', 'line_start', 'line_end', 
    'raw_quote', 'signal_type', 'parsed_payload', 'audit_only', 'status'
}

ALLOWED_SIGNAL_TYPES = {
    'entity', 'relationship', 'descriptor', 'timeline', 'terminology_placeholder'
}

ALLOWED_STATUS = {
    'captured', 'validated', 'promoted', 'archived'
}

def validate_record(rec):
    """Validates a single record against schema constraints. Returns list of errors."""
    errors = []
    
    # 1. Required Fields Check
    missing = REQUIRED_FIELDS - set(rec.keys())
    if missing:
        errors.append(f"Missing required fields: {', '.join(sorted(missing))}")

    # 2. Enum Checks
    st = rec.get('signal_type')
    if st not in ALLOWED_SIGNAL_TYPES:
        errors.append(f"Invalid signal_type: '{st}'")

    status = rec.get('status')
    if status not in ALLOWED_STATUS:
        errors.append(f"Invalid status: '{status}'")

    # 3. Type Checks
    if not isinstance(rec.get('line_start'), int) or not isinstance(rec.get('line_end'), int):
        errors.append("line_start and line_end must be integers")
    
    if rec.get('audit_only') is not True:
        errors.append("audit_only must be boolean True")

    return errors

def load_from_stdin():
    """Load YAML records from stdin, handling scanner formatting."""
    records = []
    try:
        input_text = sys.stdin.read()
        
        # R1 FIX: Split input based on the scanner's YAML block headers: "# STB-..."
        # This consumes the header line and separates the records, effectively skipping log lines.
        blocks = re.split(r'^# STB-.*$', input_text, flags=re.MULTILINE)
        
        for block in blocks:
            if not block.strip():
                continue
            
            # Remove separator lines (e.g. "-------------------") which are not valid YAML
            # and would cause parsing errors if left in the block.
            clean_lines = [line for line in block.split('\n') if not re.match(r'^[-=]{10,}$', line.strip())]
            clean_block = '\n'.join(clean_lines)
            
            if not clean_block.strip():
                continue

            # Attempt to parse block
            doc = yaml.safe_load(clean_block)
            
            # Only accept valid record dicts; ignore logs/preamble that parse as None/str
            if isinstance(doc, dict):
                records.append(doc)
                
    except yaml.YAMLError as e:
        print(f"[FATAL] YAML Parse Error on STDIN: {e}", file=sys.stderr)
        sys.exit(2)
    return records

def load_from_dir(path):
    """Load YAML records from a directory."""
    records = []
    if not os.path.isdir(path):
        print(f"[INFO] Directory {path} does not exist or is not a directory.")
        return records
        
    yaml_files = sorted(glob.glob(os.path.join(path, '*.yaml')))
    if not yaml_files:
        print(f"[INFO] No YAML files found in {path}.")
        return records

    for fp in yaml_files:
        try:
            with open(fp, 'r') as f:
                doc = yaml.safe_load(f)
            if isinstance(doc, dict):
                records.append(doc)
        except yaml.YAMLError as e:
            print(f"[WARN] Skipping invalid YAML file {fp}: {e}", file=sys.stderr)
    return records

def main():
    parser = argparse.ArgumentParser(description="STB Lint & Deduplication Validator")
    parser.add_argument('--stdin', action='store_true', help="Read YAML stream from stdin (pipe mode)")
    parser.add_argument('--dir', type=str, default='stb/', help="Directory containing STB YAML files (default: stb/)")
    args = parser.parse_args()

    records = []
    
    # Loading Phase
    if args.stdin:
        records = load_from_stdin()
    else:
        records = load_from_dir(args.dir)

    if not records:
        print("[STB] Nothing to lint. EXIT 0")
        sys.exit(0)

    # Analysis Phase
    all_errors = []
    unknown_type_count = 0
    
    # Deduplication Set: (source_file, line_start, raw_quote, signal_type)
    seen_keys = set()
    duplicates = 0
    
    # Counters
    valid_unique = 0
    unique_invalid = 0
    
    for rec in records:
        # 1. Dedup Check
        key = (
            rec.get('source_file'), 
            rec.get('line_start'), 
            rec.get('raw_quote'), 
            rec.get('signal_type')
        )
        
        if key in seen_keys:
            duplicates += 1
            continue # Count duplicate and skip further processing for this record
            
        seen_keys.add(key)
        
        # 2. Validation Check (Only for unique records)
        rec_errors = validate_record(rec)
        if rec_errors:
            unique_invalid += 1
            bid = rec.get('buffer_id', 'unknown_id')
            for err in rec_errors:
                all_errors.append(f"[REC {bid}] {err}")
        else:
            valid_unique += 1
            
            # 3. Stats: Unknown Types (Only for valid unique records)
            payload = rec.get('parsed_payload', {})
            if isinstance(payload, dict) and payload.get('entity_type') == 'UNKNOWN':
                unknown_type_count += 1

    # Reporting Phase
    total_scanned = len(records)
    
    print("[STB LINT REPORT]")
    print(f"[INFO] Total records scanned: {total_scanned}")
    print(f"[OK] records_passed: {valid_unique} | [WARN] duplicates: {duplicates} | [FAIL] schema_violations: {unique_invalid}")
    print(f"[INFO] Entities with UNKNOWN type: {unknown_type_count}")
    
    if all_errors:
        print("\n[DETAILS] Schema Violations:")
        for err in all_errors:
            print(f"  {err}")

    if duplicates > 0:
        print(f"\n[WARN] {duplicates} duplicate records detected. Deduplication key: (source_file, line_start, raw_quote, signal_type).")

    if unique_invalid > 0:
        print("\n[RESULT] Lint FAILED due to schema violations. EXIT 2")
        sys.exit(2)
    else:
        print("\n[RESULT] Lint CLEAN. EXIT 0")
        sys.exit(0)

if __name__ == '__main__':
    main()