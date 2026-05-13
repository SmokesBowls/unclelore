#!/usr/bin/env python3
"""
TASK 6.2B-EXTRACT-2-REPAIR: Harden registry column parsing.
Replaces fragile registry loading with robust table parser that strips pipes,
skips separator rows, and correctly identifies Column 1.
Deterministic dry-run only. Zero file writes.
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

# Strict allowed phrases for member_of (case-insensitive matching)
ALLOWED_PHRASES = [
    r'\bis a member of\b',
    r'\bbelongs to\b',
    r'\bpart of\b'
]

# Explicit exclusion guard: these belong to the `serves` predicate
EXCLUDED_PHRASES = [
    r'\bserves\b',
    r'\bserves in\b',
    r'\bserves under\b',
    r'\bservant of\b'
]

NON_ENTITIES = {"the", "a", "an", "and", "of", "in", "on", "at", "by", "to", "for", "with", "it", "they", "these", "those", "its", "their"}

def load_registry(path):
    """Load canonical entity names from registry.md Column 1 into a deterministic set."""
    registry_set = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return registry_set

    header_found = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
            
        # Strip outer pipes and split
        # Handles "| A | B |" -> ["A", "B"]
        content = stripped.strip("|")
        if not content:
            continue
            
        parts = [p.strip() for p in content.split("|")]
        
        # Detect header
        if "Canonical Name" in parts:
            header_found = True
            continue
            
        if not header_found:
            continue
            
        # Skip separator rows (contain only dashes, colons, spaces)
        is_separator = True
        for p in parts:
            if p and not all(c in "-: " for c in p):
                is_separator = False
                break
        if is_separator:
            continue
            
        # Extract Column 1 (index 0 after pipe stripping)
        if len(parts) > 0 and parts[0]:
            registry_set.add(parts[0].lower())
            
    return registry_set

def extract_nearby_entities(line, phrase_match):
    """Conservatively extract subject/target and capture exact provenance quote."""
    quote = line.strip()
    
    phrase_alternatives = "is a member of|belongs to|part of"
    
    # Enforce strict capitalization: [A-Z] required. Case-sensitive.
    subject_pattern = rf'([A-Z][a-zA-Z]{{2,30}}(?:\s+[A-Z][a-zA-Z]{{1,25}})?)\s+(?:{phrase_alternatives})'
    target_pattern = rf'(?:{phrase_alternatives})\s+([A-Z][a-zA-Z]{{2,30}}(?:\s+[A-Z][a-zA-Z]{{1,25}})?)'
    
    subject_match = re.search(subject_pattern, line)
    target_match = re.search(target_pattern, line)
    
    subject = subject_match.group(1).strip() if subject_match else "unresolved_subject"
    target = target_match.group(1).strip() if target_match else "unresolved_target"
    
    if subject.lower() in NON_ENTITIES or target.lower() in NON_ENTITIES:
        return "unresolved_subject", "unresolved_target", quote
        
    return subject, target, quote

def evaluate_confidence(subject, target, tier_base, registry_set):
    """Assign deterministic confidence tier based on anchoring and evidence tier."""
    s_lower = subject.lower()
    t_lower = target.lower()
    is_anchored = (s_lower in registry_set) and (t_lower in registry_set)
    
    if is_anchored:
        if tier_base == "canon_decision":
            return "high", True
        else:
            return "medium", True
    else:
        return "low", False

def scan_file(filepath, tier_base, registry_set):
    """Scan a single markdown file for explicit member_of phrases."""
    edges = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return edges

    for i, line in enumerate(lines):
        if any(re.search(exc, line, re.IGNORECASE) for exc in EXCLUDED_PHRASES):
            continue

        for phrase in ALLOWED_PHRASES:
            match = re.search(phrase, line, re.IGNORECASE)
            if match:
                subject, target, quote = extract_nearby_entities(line, match)
                if subject != "unresolved_subject" and target != "unresolved_target":
                    confidence, anchored = evaluate_confidence(subject, target, tier_base, registry_set)
                    edges.append({
                        "subject": subject,
                        "target": target,
                        "status": "edge_candidate" if tier_base != "canon_decision" else "provisional_edge",
                        "confidence": confidence,
                        "anchored": anchored,
                        "tier": tier_base,
                        "file": filepath,
                        "line": i + 1,
                        "quote": quote
                    })
                break
    return edges

def scan_canon_decisions(registry_set):
    edges = []
    for fp in sorted(glob.glob(os.path.join(CANON_DIR, "*.md"))):
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        status_match = re.search(r'(?i)Status:\s*(\w+)', content)
        if status_match and status_match.group(1).lower() in ('resolved', 'active'):
            found = scan_file(fp, "canon_decision", registry_set)
            edges.extend(found)
    return edges

def scan_sources(registry_set):
    edges = []
    for fp in sorted(glob.glob(os.path.join(SOURCE_DIR, "*.md"))):
        edges.extend(scan_file(fp, "source_summary", registry_set))
    return edges

def scan_candidates():
    return []

def main():
    parser = argparse.ArgumentParser(description="Deterministic member_of edge extractor v2")
    parser.add_argument("--dry-run", action="store_true", required=True, help="Print extraction report only. No writes.")
    parser.add_argument("--show-low-confidence", action="store_true", help="Show edges with low confidence/anchoring.")
    args = parser.parse_args()

    registry_set = load_registry(REGISTRY_PATH)
    
    all_edges = []
    all_edges.extend(scan_canon_decisions(registry_set))
    all_edges.extend(scan_sources(registry_set))
    all_edges.extend(scan_candidates())

    seen = set()
    unique_edges = []
    for e in all_edges:
        key = (e["subject"].lower(), e["target"].lower(), os.path.relpath(e["file"], BASE_DIR))
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)
    unique_edges.sort(key=lambda x: (x["status"], x["confidence"], x["subject"], x["target"]))

    # Filter low confidence unless explicitly requested
    visible_edges = [e for e in unique_edges if e["confidence"] != "low" or args.show_low_confidence]

    print(f"[DRY-RUN] member_of extraction complete")
    print(f"edges_found: {len(visible_edges)}")
    if len(unique_edges) > len(visible_edges):
        print(f"[FILTERED] {len(unique_edges) - len(visible_edges)} low-confidence edges hidden (use --show-low-confidence)")
    print("-" * 70)
    
    if not visible_edges:
        print("[INFO] Zero visible edges extracted. Registry anchoring and confidence filtering enforced.")
        
    for e in visible_edges:
        print(f"[PREDICATE] member_of")
        print(f"Subject: {e['subject']} | Target: {e['target']} | Status: {e['status']} | Confidence: {e['confidence']}")
        print(f"Anchored: {str(e['anchored']).lower()} | Evidence Tier: {e['tier']}")
        print(f"Provenance: {os.path.relpath(e['file'], BASE_DIR)}:{e['line']}")
        print(f"Quote: \"{e['quote']}\"")
        print("-" * 70)

    print("[DRY-RUN] Complete. EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()