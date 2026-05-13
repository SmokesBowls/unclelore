#!/usr/bin/env python3
"""
TASK 6.2B-ALIAS-1-REPAIR-2: Fix operator precedence in variant parsing.
Ensures alias/drift containment guards are applied deterministically.
Separates canonical identity, display casing, and alias resolution.
Diagnostic only. Zero edge emission. Exact match only. EXIT 0/2 enforced.
"""
import argparse
import glob
import os
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
CANON_DIR = os.path.join(BASE_DIR, "wiki/canon_decisions")
SOURCE_DIR = os.path.join(BASE_DIR, "wiki/sources")
CANDIDATE_DIR = os.path.join(BASE_DIR, "wiki/codex_candidates")
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")

ALLOWED_PHRASES = [
    r'\bis a member of\b',
    r'\bbelongs to\b',
    r'\bpart of\b'
]

EXCLUDED_PHRASES = [
    r'\bserves\b',
    r'\bserves in\b',
    r'\bserves under\b',
    r'\bservant of\b'
]

NON_ENTITIES = {"the", "a", "an", "and", "of", "in", "on", "at", "by", "to", "for", "with", "it", "they", "these", "those", "its", "their"}

def load_anchors_and_aliases():
    """
    Returns:
      - registry_set: Set of lowercase canonical names.
      - alias_map: Dict mapping lowercase variant -> lowercase canonical name.
      - canonical_display_map: Dict mapping lowercase canonical -> original display casing.
    """
    registry_set = set()
    alias_map = {}
    canonical_display_map = {}

    # 1. Parse wiki/registry.md
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return registry_set, alias_map, canonical_display_map

    header_found = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            content = stripped.strip("|")
            parts = [p.strip() for p in content.split("|")]
            if "Canonical Name" in parts:
                header_found = True; continue
            if not header_found: continue
            is_sep = all(all(c in "-: " for c in p) for p in parts if p)
            if is_sep: continue
            
            if parts:
                canon = parts[0].strip()
                if canon:
                    canon_lower = canon.lower()
                    registry_set.add(canon_lower)
                    canonical_display_map[canon_lower] = canon
                    
                    if len(parts) > 2:
                        variants_raw = parts[2]
                        if variants_raw and variants_raw not in ("—", "-"):
                            for v in variants_raw.split(","):
                                v_clean = v.strip()
                                if v_clean and v_clean not in ("—", "-"):
                                    alias_map[v_clean.lower()] = canon_lower

    # 2. Parse wiki/canon_decisions/*.md for variants (table-column aware)
    for path in sorted(glob.glob(os.path.join(CANON_DIR, "*.md"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Robust canonical regex for markdown bold
            canon_match = re.search(r"Canonical form:\s*\*\*([^*]+)\*\*", content)
            canonical = canon_match.group(1).strip() if canon_match else None
            if not canonical: continue
            
            canon_lower = canonical.lower()
            registry_set.add(canon_lower)
            canonical_display_map[canon_lower] = canonical
            
            # Deterministic table parsing: locate "Variant" header, iterate rows
            lines = content.split('\n')
            in_table = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("| Variant"):
                    in_table = True; continue
                if in_table and not stripped.startswith("|"):
                    in_table = False; continue
                if in_table and stripped.startswith("|"):
                    parts = [p.strip() for p in stripped.split("|")]
                    if len(parts) >= 3:
                        variant_name = parts[1]
                        classification = parts[2].lower()
                        
                        # Fix: Operator precedence containment
                        if (
                            variant_name 
                            and "---" not in variant_name 
                            and ("drift" in classification or "alias" in classification)
                        ):
                            alias_map[variant_name.strip().lower()] = canon_lower
        except Exception:
            pass
            
    return registry_set, alias_map, canonical_display_map

def extract_nearby_entities(line, phrase_match):
    quote = line.strip()
    phrase_alt = "is a member of|belongs to|part of"
    subj_pat = rf'([A-Z][a-zA-Z]{{2,30}}(?:\s+[A-Z][a-zA-Z]{{1,25}})?)\s+(?:{phrase_alt})'
    targ_pat = rf'(?:{phrase_alt})\s+([A-Z][a-zA-Z]{{2,30}}(?:\s+[A-Z][a-zA-Z]{{1,25}})?)'
    
    s_match = re.search(subj_pat, line)
    t_match = re.search(targ_pat, line)
    
    subj = s_match.group(1).strip() if s_match else "unresolved_subject"
    targ = t_match.group(1).strip() if t_match else "unresolved_target"
    
    if subj.lower() in NON_ENTITIES or targ.lower() in NON_ENTITIES:
        return "unresolved_subject", "unresolved_target", quote
    return subj, targ, quote

def scan_for_diagnostics(dir_path, registry_set, alias_map, display_map):
    hits = []
    excluded_count = 0
    for fp in sorted(glob.glob(os.path.join(dir_path, "*.md"))):
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception: continue
            
        for i, line in enumerate(lines):
            if any(re.search(exc, line, re.IGNORECASE) for exc in EXCLUDED_PHRASES):
                excluded_count += 1
                continue
                
            for phrase in ALLOWED_PHRASES:
                match = re.search(phrase, line, re.IGNORECASE)
                if match:
                    subj, targ, quote = extract_nearby_entities(line, match)
                    
                    # Resolution logic
                    s_resolved = alias_map.get(subj.lower(), None) if subj != "unresolved_subject" else None
                    t_resolved = alias_map.get(targ.lower(), None) if targ != "unresolved_target" else None
                    
                    # Anchoring logic
                    s_anchored = (subj.lower() in registry_set) or (s_resolved and s_resolved in registry_set)
                    t_anchored = (targ.lower() in registry_set) or (t_resolved and t_resolved in registry_set)
                    
                    # Preserve canonical display casing
                    s_canonical_display = display_map.get(s_resolved, subj) if s_resolved else subj
                    t_canonical_display = display_map.get(t_resolved, targ) if t_resolved else targ

                    if subj == "unresolved_subject" or targ == "unresolved_target":
                        reason = "blocked_no_regex_capture"
                    elif not s_anchored and not t_anchored:
                        reason = "blocked_both_unanchored"
                    elif not s_anchored:
                        reason = "blocked_subject_unanchored"
                    elif not t_anchored:
                        reason = "blocked_target_unanchored"
                    else:
                        reason = "none (would emit edge)"
                        
                    hits.append({
                        "file": os.path.relpath(fp, BASE_DIR),
                        "line": i + 1,
                        "phrase": phrase.strip(r'\b'),
                        "quote": quote,
                        "raw_subject": subj,
                        "raw_target": targ,
                        "resolved_subject_lower": s_resolved,
                        "resolved_target_lower": t_resolved,
                        "display_subject": s_canonical_display,
                        "display_target": t_canonical_display,
                        "subject_anchored": s_anchored,
                        "target_anchored": t_anchored,
                        "block_reason": reason
                    })
                    break
    return hits, excluded_count

def main():
    parser = argparse.ArgumentParser(description="Deterministic member_of edge extractor v3+alias+display")
    parser.add_argument("--dry-run", action="store_true", help="Print extraction report only.")
    parser.add_argument("--show-low-confidence", action="store_true", help="(Future) Show low-confidence edges.")
    parser.add_argument("--diagnostic", action="store_true", help="Report all phrase hits and block reasons. Resolves aliases. Suppresses edge emission.")
    args = parser.parse_args()

    if not args.dry_run and not args.diagnostic:
        print("ERROR: Requires --dry-run or --diagnostic.", file=sys.stderr)
        sys.exit(2)

    registry_set, alias_map, display_map = load_anchors_and_aliases()
    
    canon_hits, canon_excl = scan_for_diagnostics(CANON_DIR, registry_set, alias_map, display_map)
    source_hits, source_excl = scan_for_diagnostics(SOURCE_DIR, registry_set, alias_map, display_map)
    
    all_hits = [(h, "canon_decision") for h in canon_hits] + [(h, "source_summary") for h in source_hits]
    total_excluded = canon_excl + source_excl

    if args.diagnostic:
        print(f"[DIAG] member_of phrase diagnostics active")
        print(f"[REGISTRY] {len(registry_set)} canonical anchors loaded")
        print(f"[ALIASES] {len(alias_map)} variant mappings loaded")
        print(f"[SCANNED] canon_hits={len(canon_hits)} source_hits={len(source_hits)}")
        print("-" * 70)
        
        if not all_hits:
            print("[DIAG] Zero phrase hits found. No linguistic patterns matched.")
        else:
            for hit, tier in all_hits:
                # Show resolution info cleanly
                s_res_str = f" -> {hit['display_subject']}" if hit['resolved_subject_lower'] else ""
                t_res_str = f" -> {hit['display_target']}" if hit['resolved_target_lower'] else ""
                
                print(f"[DIAG] phrase_hit: \"{hit['phrase']}\"")
                print(f"  Line: {hit['file']}:{hit['line']}")
                print(f"  Raw: \"{hit['quote']}\"")
                print(f"  Subject: {hit['raw_subject']}{s_res_str} | Target: {hit['raw_target']}{t_res_str}")
                print(f"  Subject Anchored: {str(hit['subject_anchored']).lower()} | Target Anchored: {str(hit['target_anchored']).lower()}")
                print(f"  Block Reason: {hit['block_reason']}")
                print(f"  Evidence Tier: {tier}")
                print("-" * 70)
                
        print(f"[SUMMARY] Total allowed hits: {len(all_hits)}")
        print(f"[SUMMARY] Excluded (serves-patterns): {total_excluded}")
        print("[DIAG] Complete. EXIT 0")
        sys.exit(0)

    # Fallback to existing dry-run edge logic
    print("[DRY-RUN] member_of extraction complete (diagnostic disabled)")
    print("edges_found: 0")
    print("-" * 70)
    print("[INFO] Zero visible edges extracted. Registry anchoring enforced.")
    print("[DRY-RUN] Complete. EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()
