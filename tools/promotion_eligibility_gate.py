#!/usr/bin/env python3
"""
TASK 6.1E-REPAIR-1: Import authority_score_calculator to prevent score drift.
Removes duplicated calc_score logic. Uses single source of truth for authority calculation.
"""
import argparse
import glob
import os
import re
import sys
from datetime import date

# Ensure sibling module resolution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from authority_score_calculator import calculate_score as calc_authority_score

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
CODEX_DIR = os.path.join(BASE_DIR, "wiki/codex_candidates")
CANON_DEC_DIR = os.path.join(BASE_DIR, "wiki/canon_decisions")
CONTINUITY_DIR = os.path.join(BASE_DIR, "wiki/continuity")
AUDIT_LOGS_DIR = os.path.join(BASE_DIR, "logs")
SOURCES_DIR = os.path.join(BASE_DIR, "wiki/sources")
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")

# Deterministic v1 eligibility thresholds
THRESHOLDS = {
    "min_authority_score": 20,
    "max_open_conflicts": 0,
    "min_source_mentions": 3,
    "requires_canon_decision": False  # Set True later when canon binding is mandatory
}

def parse_candidate_frontmatter(path):
    """Extract mention_count and entity_name from candidate frontmatter."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None, None
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return None, None
    fm_text = match.group(1)
    mentions = re.search(r'mention_count:\s*(\d+)', fm_text)
    entity = re.search(r'entity_name:\s*"?([^"\n]+)"?', fm_text)
    return int(mentions.group(1)) if mentions else 0, entity.group(1).strip('"\' ') if entity else None

def check_canon_support(entity):
    """Returns True if resolved/active canon decision exists."""
    for fp in sorted(glob.glob(os.path.join(CANON_DEC_DIR, "*.md"))):
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        if entity.lower() in content.lower():
            st = re.search(r'(?:Status|status):\s*([\w/-]+)', content, re.IGNORECASE)
            if st and st.group(1).lower() in ("resolved", "active"):
                return True
    return False

def check_open_conflicts(entity):
    """Returns count of open continuity findings referencing entity."""
    count = 0
    for d in [CONTINUITY_DIR, AUDIT_LOGS_DIR]:
        for fp in sorted(glob.glob(os.path.join(d, "*"))):
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            if entity.lower() in content.lower():
                st = re.search(r'(?:Status|status):\s*([\w/-]+)', content, re.IGNORECASE)
                if st and st.group(1).lower() == "open":
                    count += 1
    return count

def evaluate_eligibility(entity, score, canon_support, open_conflicts, mentions):
    """Deterministic eligibility classification."""
    if open_conflicts > THRESHOLDS["max_open_conflicts"]:
        return "blocked_by_conflict"
    if score < THRESHOLDS["min_authority_score"] or mentions < THRESHOLDS["min_source_mentions"]:
        return "insufficient_evidence"
    if not canon_support and THRESHOLDS["requires_canon_decision"]:
        return "pending_canon_decision"
    return "eligible_for_review"

def main():
    parser = argparse.ArgumentParser(description="Promotion eligibility gate (report only)")
    parser.add_argument("--dry-run", action="store_true", required=True, help="Print eligibility report only. No promotions.")
    args = parser.parse_args()

    candidates = sorted(glob.glob(os.path.join(CODEX_DIR, "*.md")))
    if not candidates:
        print("[GATE] No candidates found. EXIT 0")
        sys.exit(0)

    print("[GATE] Promotion Eligibility Analysis (v1 Thresholds)")
    print(f"Thresholds -> min_score:{THRESHOLDS['min_authority_score']}, min_mentions:{THRESHOLDS['min_source_mentions']}, max_conflicts:{THRESHOLDS['max_open_conflicts']}, canon_required:{THRESHOLDS['requires_canon_decision']}")
    print("=" * 70)

    any_blocked = False
    for cpath in candidates:
        rel_name = os.path.basename(cpath)
        mentions, entity = parse_candidate_frontmatter(cpath)
        if not entity:
            print(f"candidate: {rel_name} | status: malformed_candidate")
            any_blocked = True
            continue

        # Import single source of truth for scoring
        score, _ = calc_authority_score(entity)
        canon_support = check_canon_support(entity)
        open_conflicts = check_open_conflicts(entity)
        status = evaluate_eligibility(entity, score, canon_support, open_conflicts, mentions)

        if "blocked" in status or "insufficient" in status:
            any_blocked = True

        canon_str = "yes" if canon_support else "no"
        print(f"candidate: {rel_name}")
        print(f"  authority_score: {score}")
        print(f"  continuity_conflicts_open: {open_conflicts}")
        print(f"  canon_decision_support: {canon_str}")
        print(f"  source_coverage: {mentions}")
        print(f"  promotion_status: {status}")
        print("-" * 70)

    print("=" * 70)
    if any_blocked:
        print("[GATE] One or more candidates do not meet promotion thresholds. EXIT 2")
        sys.exit(2)
    else:
        print("[GATE] All evaluated candidates meet eligibility thresholds. Pending human review. EXIT 0")
        sys.exit(0)

if __name__ == "__main__":
    main()