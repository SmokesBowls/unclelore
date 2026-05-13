#!/usr/bin/env python3
"""
TASK 6.2A-REPAIR-1: Remove duplicated authority scoring from promote_candidate.py.
Imports calculate_score from authority_score_calculator.py to enforce single source of truth.
Preserves governed promotion workflow, eligibility gates, and provenance tracking.
"""
import argparse
import os
import re
import sys
from datetime import date

# Ensure sibling module resolution for tools/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from authority_score_calculator import calculate_score as calc_authority_score

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
CANDIDATE_DIR = os.path.join(BASE_DIR, "wiki/codex_candidates")
CODEX_DIR = os.path.join(BASE_DIR, "wiki/codex")
CANON_DEC_DIR = os.path.join(BASE_DIR, "wiki/canon_decisions")
CONTINUITY_DIR = os.path.join(BASE_DIR, "wiki/continuity")
AUDIT_LOGS_DIR = os.path.join(BASE_DIR, "logs")

THRESHOLDS = {
    "min_authority_score": 20,
    "max_open_conflicts": 0,
    "min_source_mentions": 3,
    "requires_canon_decision": False
}

def parse_fm(content):
    """Return (frontmatter_dict, body_str, full_content)."""
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not m:
        return None, content, content
    fm = {}
    for line in m.group(1).split('\n'):
        if ':' in line:
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, content[m.end():], content

def update_fm(content, updates):
    """Apply key-value updates to YAML frontmatter block."""
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not m:
        return content
    lines = m.group(1).split('\n')
    new_lines = []
    applied = set()
    for line in lines:
        if ':' in line:
            k = line.split(':', 1)[0].strip()
            if k in updates:
                new_lines.append(f"{k}: {updates[k]}")
                applied.add(k)
                continue
        new_lines.append(line)
    for k, v in updates.items():
        if k not in applied:
            new_lines.append(f"{k}: {v}")
    return "---\n" + "\n".join(new_lines) + "\n---\n" + content[m.end():]

def check_canon(entity):
    """Returns True if resolved/active canon decision exists."""
    for fp in sorted(os.listdir(CANON_DEC_DIR)):
        if not fp.endswith(".md"):
            continue
        fpath = os.path.join(CANON_DEC_DIR, fp)
        with open(fpath, "r", encoding="utf-8") as f:
            c = f.read()
        if entity.lower() in c.lower():
            st = re.search(r'(?:Status|status):\s*([\w/-]+)', c, re.IGNORECASE)
            if st and st.group(1).lower() in ("resolved", "active"):
                return True
    return False

def check_conflicts(entity):
    """Returns count of open continuity findings referencing entity."""
    count = 0
    for d in [CONTINUITY_DIR, AUDIT_LOGS_DIR]:
        if not os.path.isdir(d):
            continue
        for fp in sorted(os.listdir(d)):
            fpath = os.path.join(d, fp)
            if not os.path.isfile(fpath):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                c = f.read()
            if entity.lower() in c.lower():
                st = re.search(r'(?:Status|status):\s*([\w/-]+)', c, re.IGNORECASE)
                if st and st.group(1).lower() == "open":
                    count += 1
    return count

def evaluate_eligibility(entity, mentions):
    """Deterministic eligibility classification using shared authority score."""
    score, _ = calc_authority_score(entity)
    canon = check_canon(entity)
    conflicts = check_conflicts(entity)
    
    if conflicts > THRESHOLDS["max_open_conflicts"]:
        return "blocked_by_conflict", score
    if score < THRESHOLDS["min_authority_score"] or mentions < THRESHOLDS["min_source_mentions"]:
        return "insufficient_evidence", score
    if not canon and THRESHOLDS["requires_canon_decision"]:
        return "pending_canon_decision", score
    return "eligible_for_review", score

def main():
    parser = argparse.ArgumentParser(description="Human-Gated Candidate Promotion Workflow")
    parser.add_argument("--candidate", required=True, help="Slug of the candidate to evaluate/promote")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate eligibility and show intended destination. No writes.")
    parser.add_argument("--approve", action="store_true", help="Execute promotion to official codex. Requires explicit flag.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing official codex file if present.")
    args = parser.parse_args()

    cand_path = os.path.join(CANDIDATE_DIR, f"{args.candidate}.md")
    if not os.path.exists(cand_path):
        print(f"ERROR: Candidate file not found: {cand_path}", file=sys.stderr)
        sys.exit(2)

    with open(cand_path, "r", encoding="utf-8") as f:
        raw = f.read()

    fm, body, full = parse_fm(raw)
    if not fm or "entity_name" not in fm:
        print("ERROR: Candidate malformed or missing required frontmatter.", file=sys.stderr)
        sys.exit(2)

    entity = fm.get("entity_name")
    mentions = int(fm.get("mention_count", 0))
    status, score = evaluate_eligibility(entity, mentions)

    if status != "eligible_for_review":
        print(f"ERROR: Eligibility gate failed. Status: {status} (Score: {score})", file=sys.stderr)
        sys.exit(2)

    dest_rel = os.path.join("wiki", "codex", f"{args.candidate}.md")
    dest_path = os.path.join(CODEX_DIR, f"{args.candidate}.md")

    if args.dry_run:
        print("[PROMOTION DRY-RUN]")
        print(f"  Candidate Path: {cand_path}")
        print(f"  Authority Score: {score}")
        print(f"  Promotion Eligibility: {status}")
        print(f"  Intended Destination: {dest_rel}")
        print("-" * 70)
        print("[DRY-RUN] Complete. EXIT 0")
        sys.exit(0)

    if not args.approve:
        print("ERROR: Promotion requires explicit --approve flag. Use --dry-run for evaluation.", file=sys.stderr)
        sys.exit(2)

    # APPROVE MODE
    if os.path.exists(dest_path) and not args.force:
        print(f"ERROR: Destination exists: {dest_rel} (use --force to overwrite)", file=sys.stderr)
        sys.exit(2)

    os.makedirs(CODEX_DIR, exist_ok=True)
    today = date.today().isoformat()
    updates = {
        "promoted_from_candidate": "true",
        "promotion_date": today,
        "promotion_review_required": "false"
    }
    updated_content = update_fm(full, updates)
    updated_content += f"\n<!-- PROMOTED: Promoted via governed workflow from review-only candidate. Date: {today} -->\n"

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print("[PROMOTION APPROVED]")
    print(f"  Candidate: {args.candidate}")
    print(f"  Destination: {dest_rel}")
    print(f"  Preserved Candidate: {cand_path}")
    print("-" * 70)
    print("[PROMOTION] Complete. EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()