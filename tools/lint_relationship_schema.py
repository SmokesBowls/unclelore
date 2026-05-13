#!/usr/bin/env python3
"""
TASK 6.2B-LINT-SCHEMA: Validate relationship predicate schema.
Deterministic lint of schema/RELATIONSHIP_PREDICATES.md before extraction.
Ensures governance structure, predicates, fields, and boundary phrases are present.
"""
import os
import sys
import re

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
SCHEMA_PATH = os.path.join(BASE_DIR, "schema", "RELATIONSHIP_PREDICATES.md")

REQUIRED_SECTIONS = [
    "Global Evidence Authority Rules",
    "Contradiction & Coexistence Policy",
    "Temporal Scope Policy",
    "Allowed Predicates",
    "Edge Storage Contract",
    "Governance Boundary"
]

REQUIRED_PREDICATES = [
    "member_of",
    "allied_with",
    "opposes",
    "located_in",
    "created_by",
    "serves",
    "originates_from"
]

REQUIRED_PREDICATE_FIELDS = [
    "Definition",
    "Directionality",
    "Required Evidence Authority",
    "Contradiction Policy",
    "Temporal Policy"
]

REQUIRED_PHRASES = [
    "No inference",
    "Source summaries may propose an edge_candidate only",
    "Continuity records may qualify/block existing edge candidates, but may not create edges",
    "Registry presence alone may not create edges"
]

def lint_schema(path):
    """Validate schema file structure, predicates, fields, and governance phrases."""
    if not os.path.exists(path):
        return False, f"File not found: {os.path.relpath(path, BASE_DIR)}"

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Check required global sections
    for section in REQUIRED_SECTIONS:
        if section.lower() not in content.lower():
            return False, f"Missing required section: {section}"

    # 2. Check required governance phrases
    for phrase in REQUIRED_PHRASES:
        if phrase not in content:
            return False, f"Missing required boundary phrase: '{phrase}'"

    # 3. Check predicates and their required fields
    for pred in REQUIRED_PREDICATES:
        # Match predicate header: ### member_of or ### `member_of`
        pred_pattern = re.compile(rf"###\s+`?{re.escape(pred)}`?\s*", re.IGNORECASE)
        match = pred_pattern.search(content)
        if not match:
            return False, f"Missing predicate definition: {pred}"

        # Isolate predicate block until next ### header or EOF
        block_start = match.end()
        next_header = re.search(r"\n###\s", content[block_start:])
        block_end = block_start + next_header.start() if next_header else len(content)
        block_content = content[block_start:block_end]

        # Check required fields within the isolated block
        for field in REQUIRED_PREDICATE_FIELDS:
            # Match field lines like "- Definition:" or "Definition:"
            field_pattern = re.compile(rf"[-*]?\s*{re.escape(field)}\s*:", re.IGNORECASE)
            if not field_pattern.search(block_content):
                return False, f"Predicate '{pred}' missing required field: {field}"

    return True, ""

def main():
    rel_path = "schema/RELATIONSHIP_PREDICATES.md"
    print(f"[LINT] Validating {rel_path}...")
    
    passed, reason = lint_schema(SCHEMA_PATH)
    
    if passed:
        print(f"[OK] {rel_path}")
        sys.exit(0)
    else:
        print(f"[FAIL] {rel_path} — {reason}")
        sys.exit(2)

if __name__ == "__main__":
    main()