#!/usr/bin/env python3
"""
TASK 6.1C: Deterministic codex candidate lint.
Validates structure, frontmatter, and sections of generated candidate pages.
"""
import glob
import os
import re
import sys

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
CODEX_DIR = os.path.join(BASE_DIR, "wiki/codex_candidates")
CODEX_PATTERN = os.path.join(CODEX_DIR, "*.md")

REQUIRED_FIELDS = {
    "status": "candidate",
    "canon_state": "provisional",
    "review_only": "true"
}
REQUIRED_SECTION_HEADINGS = [
    "Source Mention Count",
    "Source References",
    "Unresolved Questions",
    "Human Review Checklist"
]

def parse_frontmatter(content):
    """Extract frontmatter dict and body from markdown content."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return None, content
    fm_text = match.group(1)
    body = content[match.end():]
    fm = {}
    for line in fm_text.split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, body

def lint_candidate(filepath):
    """Return (is_valid, reason_string)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, f"Read error: {e}"

    fm, body = parse_frontmatter(content)
    if fm is None:
        return False, "Missing frontmatter"

    # Check required fields
    for key, expected_val in REQUIRED_FIELDS.items():
        if key not in fm:
            return False, f"Missing frontmatter field: {key}"
        if fm[key].lower() != str(expected_val).lower():
            return False, f"Field '{key}' expected '{expected_val}', got '{fm[key]}'"

    if 'entity_name' not in fm:
        return False, "Missing frontmatter field: entity_name"

    if 'mention_count' in fm:
        try:
            int(fm['mention_count'])
        except ValueError:
            return False, f"mention_count is not an integer: {fm['mention_count']}"
    else:
        return False, "Missing frontmatter field: mention_count"

    # Check sections
    for section in REQUIRED_SECTION_HEADINGS:
        if f"## {section}" not in body:
            return False, f"Missing section: {section}"

    return True, ""

def main():
    candidates = sorted(glob.glob(CODEX_PATTERN))
    if not candidates:
        print("WARNING: No candidate files found in", CODEX_DIR)
        sys.exit(0)

    all_pass = True
    for fp in candidates:
        rel_path = os.path.relpath(fp, BASE_DIR)
        valid, reason = lint_candidate(fp)
        if valid:
            print(f"[OK] {rel_path}")
        else:
            print(f"[FAIL] {rel_path} — {reason}")
            all_pass = False

    if all_pass:
        print("\n[Lint] All candidates passed. EXIT 0")
        sys.exit(0)
    else:
        print("\n[Lint] Failures detected. EXIT 2")
        sys.exit(2)

if __name__ == "__main__":
    main()