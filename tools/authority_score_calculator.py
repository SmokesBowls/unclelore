#!/usr/bin/env python3
"""
TASK 6.1D-REPAIR-1: Fix undefined continuity directory reference.
Replaces legacy CONTRADICTIONS_DIR with CONTINUITY_DIR and updates scan paths.
Preserves deterministic authority scoring logic and weights.
"""
import argparse
import glob
import os
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")
SOURCES_DIR = os.path.join(BASE_DIR, "wiki/sources")
CANON_DEC_DIR = os.path.join(BASE_DIR, "wiki/canon_decisions")
CONTINUITY_DIR = os.path.join(BASE_DIR, "wiki/continuity")
AUDIT_LOGS_DIR = os.path.join(BASE_DIR, "logs")

WEIGHTS = {
    "registry_existence": 1,
    "source_mention": 5,
    "canon_resolved_active": 100,
    "continuity_resolved": 20,
    "continuity_open_high": -30,
    "continuity_open_medium_low": -10
}

def find_canon_decisions(entity):
    """Scan canon decisions for entity name or variant matches."""
    matches = []
    for fp in sorted(glob.glob(os.path.join(CANON_DEC_DIR, "*.md"))):
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        if entity.lower() in content.lower():
            status_match = re.search(r'(?:Status|status):\s*([\w/-]+)', content, re.IGNORECASE)
            status = status_match.group(1).lower() if status_match else "unknown"
            matches.append((fp, status))
    return matches

def find_continuity_findings(entity):
    """Scan continuity records and audit logs for entity matches."""
    findings = []
    # Scan continuity YAMLs
    for fp in sorted(glob.glob(os.path.join(CONTINUITY_DIR, "*.yaml")) + 
                     glob.glob(os.path.join(CONTINUITY_DIR, "*.yml"))):
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        if entity.lower() in content.lower():
            sev_match = re.search(r'(?:Severity|severity):\s*([\w/-]+)', content, re.IGNORECASE)
            status_match = re.search(r'(?:Status|status):\s*([\w/-]+)', content, re.IGNORECASE)
            findings.append((fp,
                             status_match.group(1).lower() if status_match else "unspecified",
                             sev_match.group(1).lower() if sev_match else "unspecified"))
    # Scan audit logs
    for fp in sorted(glob.glob(os.path.join(AUDIT_LOGS_DIR, "continuity_audit_*.md"))):
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        if entity.lower() in content.lower():
            sev_match = re.search(r'(?:Severity|severity):\s*([\w/-]+)', content, re.IGNORECASE)
            status_match = re.search(r'(?:Status|status):\s*([\w/-]+)', content, re.IGNORECASE)
            findings.append((fp,
                             status_match.group(1).lower() if status_match else "unspecified",
                             sev_match.group(1).lower() if sev_match else "unspecified"))
    return findings

def count_source_mentions(entity):
    """Count exact case-sensitive occurrences in source summaries."""
    count = 0
    for fp in sorted(glob.glob(os.path.join(SOURCES_DIR, "*.md"))):
        with open(fp, "r", encoding="utf-8") as f:
            count += f.read().count(entity)
    return count

def check_registry(entity):
    """Check if entity exists in registry.md column 1."""
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("|") and not line.startswith("| ---"):
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) > 0 and parts[0].lower() == entity.lower():
                    return True
    return False

def calculate_score(entity):
    """Return (total_score, explainable_breakdown_list)."""
    score = 0
    breakdown = []

    # Tier 4: Registry
    if check_registry(entity):
        score += WEIGHTS["registry_existence"]
        breakdown.append(f"[TIER 4] +{WEIGHTS['registry_existence']} | {REGISTRY_PATH} | existence baseline | Entity found in registry")
    else:
        breakdown.append(f"[TIER 4] +0 | {REGISTRY_PATH} | absence | Entity not in registry")

    # Tier 3: Source Summaries
    mentions = count_source_mentions(entity)
    if mentions > 0:
        w = mentions * WEIGHTS["source_mention"]
        score += w
        breakdown.append(f"[TIER 3] +{w} | wiki/sources/*.md | {mentions} exact mentions | Derived evidence")
    else:
        breakdown.append(f"[TIER 3] +0 | wiki/sources/*.md | 0 mentions | No source evidence")

    # Tier 1: Canon Decisions
    decisions = find_canon_decisions(entity)
    for fp, status in decisions:
        if status in ("resolved", "active"):
            w = WEIGHTS["canon_resolved_active"]
            score += w
            breakdown.append(f"[TIER 1] +{w} | {os.path.relpath(fp, BASE_DIR)} | Status: {status} | Binding decision")

    # Tier 2: Continuity Findings
    findings = find_continuity_findings(entity)
    for fp, status, sev in findings:
        if status == "resolved":
            w = WEIGHTS["continuity_resolved"]
        elif status == "open":
            if sev in ("high", "canon-breaking"):
                w = WEIGHTS["continuity_open_high"]
            else:
                w = WEIGHTS["continuity_open_medium_low"]
        else:
            w = 0
        score += w
        breakdown.append(f"[TIER 2] {w:+d} | {os.path.relpath(fp, BASE_DIR)} | Status: {status}, Severity: {sev} | Review/conflict evidence")

    return score, breakdown

def main():
    parser = argparse.ArgumentParser(description="Authority score calculator")
    parser.add_argument("--entity", required=True, help="Canonical entity name to score")
    parser.add_argument("--dry-run", action="store_true", help="Print scoring breakdown only. No mutations.")
    args = parser.parse_args()

    if not args.dry_run:
        print("ERROR: Only --dry-run is authorized at this phase.", file=sys.stderr)
        sys.exit(2)

    score, breakdown = calculate_score(args.entity)

    print(f"[DRY-RUN] Authority Score: {score}")
    print(f"[ENTITY] {args.entity}")
    print("-" * 70)
    for line in breakdown:
        print(line)
    print("-" * 70)
    print(f"[EXPLAINABLE] Score fully traceable to ingested evidence layers.")
    print("[DRY-RUN] Complete. EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()
