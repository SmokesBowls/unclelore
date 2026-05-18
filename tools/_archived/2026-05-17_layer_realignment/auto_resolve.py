#!/usr/bin/env python3
"""
TASK 7.1B-R1: Unify alias lookup logic between --dry-run and --apply paths.
Extracts shared resolve_term() function to ensure identical punctuation stripping
and resolution behavior. Eliminates 311/225 count divergence.
Deterministic, provenance-tracked, zero Tier 0 mutation.
"""
import argparse
import glob
import os
import re
import sys
import yaml

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
CANON_DIR = os.path.join(BASE_DIR, "wiki/canon_decisions")
CONTINUITY_DIR = os.path.join(BASE_DIR, "wiki/continuity")
LOG_PATH = os.path.join(CONTINUITY_DIR, "auto_resolved_log.md")

def parse_canon_decisions():
    """Extract canonical forms and known aliases from CANON-*.md files."""
    aliases = {}
    for fp in sorted(glob.glob(os.path.join(CANON_DIR, "CANON-*.md"))):
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
                        variant = parts[1]
                        classification = parts[2].lower()
                        if variant and "---" not in variant and ("drift" in classification or "alias" in classification):
                            aliases[variant.lower()] = canonical
                else:
                    in_table = False
    return aliases

def resolve_term(term, aliases):
    """Clean punctuation/regex artifacts and perform deterministic alias lookup.
    Used by both --dry-run and --apply paths to guarantee identical resolution counts."""
    if not term:
        return None
    # Strip non-alphanumeric/spaces to handle '?', '[^i]', etc.
    term_clean = re.sub(r"[^a-zA-Z0-9 ]", "", str(term)).strip()
    term_lower = term_clean.lower()
    return aliases.get(term_lower)

def process_continuity_files(aliases, apply_mode):
    """Unified scanner for both dry-run and apply modes."""
    resolved_log = []
    unresolved_log = []
    applied_count = 0
    
    pattern = os.path.join(CONTINUITY_DIR, "CONT-*.yaml")
    files = glob.glob(pattern)
    print(f"[SCAN] Found {len(files)} continuity files.")

    for fp in sorted(files):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
            modified = False

            for item in items:
                status = item.get("status", "open").lower()
                if status in ("resolved", "auto_resolved"):
                    continue

                # Extract term from standardized YAML fields
                detected = item.get("detected", {})
                term = detected.get("token") or item.get("proposal", {}).get("from")

                # Shared resolution logic
                canonical = resolve_term(term, aliases)
                
                if canonical:
                    item["status"] = "auto_resolved"
                    modified = True
                    applied_count += 1
                    resolved_log.append(
                        f"- [AUTO_RESOLVED] {os.path.basename(fp)}: '{term}' -> '{canonical}'"
                    )
                elif term:
                    unresolved_log.append(
                        f"- [UNRESOLVED] {os.path.basename(fp)}: '{term}' (No canon backing)"
                    )

            # Apply mutation only in --apply mode
            if modified and apply_mode:
                with open(fp, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)

        except yaml.YAMLError as e:
            print(f"[WARN] Parse error in {fp}: {e}")
            continue

    return resolved_log, unresolved_log, applied_count, len(files)

def main():
    parser = argparse.ArgumentParser(description="Auto-resolve Alias Drift (Phase 7)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Report only. No writes.")
    group.add_argument("--apply", action="store_true", help="Apply status updates and write log.")
    args = parser.parse_args()

    aliases = parse_canon_decisions()
    print(f"[AUTHORITY] Loaded {len(aliases)} alias mappings from canon decisions.")

    # Unified processing path ensures identical counts regardless of mode
    apply_mode = args.apply
    resolved_log, unresolved_log, applied_count, file_count = process_continuity_files(aliases, apply_mode)

    print(f"[RESOLVED] {applied_count} conflicts auto-resolved.")
    print(f"[UNRESOLVED] {len(unresolved_log)} conflicts require human review.")

    # Generate Log Content
    report = []
    report.append("# Auto-Resolution Log")
    report.append(f"Date: 2026-05-13")
    report.append(f"Files Scanned: {file_count}")
    report.append(f"Conflicts Auto-Resolved: {applied_count}")
    report.append(f"Conflicts Unresolved: {len(unresolved_log)}")
    report.append("")
    if resolved_log:
        report.append("## Resolved Entries")
        report.extend(resolved_log)
    if unresolved_log:
        report.append("## Unresolved Entries")
        report.extend(unresolved_log)
    report.append("")

    log_content = "\n".join(report)

    if apply_mode:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(log_content)
        print(f"[WRITE] Log updated: {os.path.relpath(LOG_PATH, BASE_DIR)}")
    else:
        print("\n" + log_content)
        print("[DRY-RUN] No files mutated.")

    if unresolved_log:
        print("\nEXIT 2: Unresolved conflicts detected. Manual review required.")
        sys.exit(2)
    else:
        print(f"\nEXIT 0: {applied_count} conflicts auto-resolved. All scanned conflicts have canon backing.")
        sys.exit(0)

if __name__ == "__main__":
    main()