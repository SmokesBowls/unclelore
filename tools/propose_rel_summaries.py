#!/usr/bin/env python3
"""
TASK 6.2D-SOURCE-1: Propose relationship-oriented source summaries (dry-run).
Scans existing wiki pages for explicit relationship phrases.
Proposes candidate summaries preserving original predicate and exact quotes.
No synthesis. No relationship invention. Exact phrase match only.
Dry-run only. Zero writes. EXIT 0/2 enforced.
"""
import argparse
import glob
import os
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
SCAN_DIRS = [
    os.path.join(BASE_DIR, "wiki/sources"),
    os.path.join(BASE_DIR, "wiki/canon_decisions"),
    os.path.join(BASE_DIR, "wiki/factions"),
    os.path.join(BASE_DIR, "wiki/characters"),
    os.path.join(BASE_DIR, "wiki/species"),
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

def load_aliases():
    """Load canonical names and exact-match alias map from registry & canon decisions."""
    registry_path = os.path.join(BASE_DIR, "wiki/registry.md")
    canon_dir = os.path.join(BASE_DIR, "wiki/canon_decisions")
    alias_map = {}
    display_map = {}
    registry_set = set()

    # Parse registry
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        header_found = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|"):
                parts = [p.strip() for p in stripped.strip("|").split("|")]
                if "Canonical Name" in parts:
                    header_found = True; continue
                if not header_found: continue
                if parts and parts[0]:
                    canon = parts[0].strip()
                    cl = canon.lower()
                    registry_set.add(cl)
                    display_map[cl] = canon
                    if len(parts) > 2:
                        for v in parts[2].split(","):
                            vc = v.strip()
                            if vc and vc not in ("—", "-"):
                                alias_map[vc.lower()] = cl
    except Exception:
        pass

    # Parse canon decisions for variants
    for fp in sorted(glob.glob(os.path.join(canon_dir, "*.md"))):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            canon_match = re.search(r"Canonical form:\s*\*\*([^*]+)\*\*", content)
            if canon_match:
                canon = canon_match.group(1).strip()
                cl = canon.lower()
                registry_set.add(cl)
                display_map[cl] = canon
                lines = content.split('\n')
                in_table = False
                for line in lines:
                    s = line.strip()
                    if s.startswith("| Variant"): in_table = True; continue
                    if in_table and not s.startswith("|"): in_table = False; continue
                    if in_table and s.startswith("|"):
                        parts = [p.strip() for p in s.split("|")]
                        if len(parts) >= 3:
                            v = parts[1].strip()
                            cls = parts[2].lower()
                            if v and "---" not in v and ("drift" in cls or "alias" in cls):
                                alias_map[v.lower()] = cl
        except Exception:
            pass
    return registry_set, alias_map, display_map

def resolve_aliases_in_line(line, alias_map, display_map):
    """Find exact capitalized entity mentions in line and resolve aliases."""
    entities = re.findall(r'[A-Z][a-zA-Z\s\-\'/]{2,30}', line)
    resolved_map = {}
    for ent in entities:
        clean = ent.strip()
        lower = clean.lower()
        if lower in alias_map:
            canonical_lower = alias_map[lower]
            resolved_map[clean] = display_map.get(canonical_lower, canonical_lower)
        elif lower in display_map:
            resolved_map[clean] = display_map[lower]
    return resolved_map

def main():
    parser = argparse.ArgumentParser(description="Propose relationship-oriented source summaries")
    parser.add_argument("--dry-run", action="store_true", required=True, help="Print proposals only. No writes.")
    args = parser.parse_args()

    registry_set, alias_map, display_map = load_aliases()
    proposals = []

    for dir_path in SCAN_DIRS:
        if not os.path.exists(dir_path):
            continue
        for fp in sorted(glob.glob(os.path.join(dir_path, "*.md"))):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for i, line in enumerate(lines):
                for phrase in ALLOWED_PHRASES:
                    if re.search(phrase, line, re.IGNORECASE):
                        # Strict containment: only propose if phrase actually exists in source
                        resolved = resolve_aliases_in_line(line, alias_map, display_map)
                        proposals.append({
                            "source_file": os.path.relpath(fp, BASE_DIR),
                            "line_number": i + 1,
                            "detected_phrase": phrase.strip(r'\b'),
                            "original_quote": line.strip(),
                            "normalized_entities": resolved if resolved else {}
                        })
                        break # One phrase per line

    # Deterministic sort
    proposals.sort(key=lambda x: (x["source_file"], x["line_number"]))

    print("[PROPOSAL] Relationship-Oriented Source Summaries (Dry-Run)")
    print(f"[SCANNED] {len(proposals)} lines containing explicit relationship phrases")
    print(f"[ALIASES] {len(alias_map)} variant mappings active")
    print("-" * 70)

    if not proposals:
        print("[INFO] Zero explicit relationship phrases found in current wiki surface.")
        print("[NOTE] Source normalization requires explicit phrasing before candidates can be proposed.")
    else:
        for p in proposals:
            norm_str = ", ".join([f"{k} -> {v}" for k, v in p["normalized_entities"].items()])
            print(f"candidate_summary_line: {p['detected_phrase'].replace(' ', '_')}")
            print(f"  source_file: {p['source_file']}")
            print(f"  line_number: {p['line_number']}")
            print(f"  original_quote: \"{p['original_quote']}\"")
            print(f"  detected_phrase: \"{p['detected_phrase']}\"")
            print(f"  normalized_entities: {{{norm_str}}}")
            print("-" * 70)

    print("[PROPOSAL] Complete. Awaiting human review for apply phase.")
    print("EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()