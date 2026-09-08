#!/usr/bin/env python3
import sys
import json
from pathlib import Path

def lint_entity_passport(file_path: Path) -> int:
    print(f"[GOVERNANCE] [ENTITY_LINT] Auditing civilization passport: {file_path.name}")
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[GOVERNANCE] [ENTITY_LINT] [REJECT] Parse error: Invalid JSON formatting: {e}")
        return 2

    # 1. Structural Blueprint Constraints
    if data.get("contract_type") != "semantic_entity_contract_cut_2":
        print("[GOVERNANCE] [ENTITY_LINT] [REJECT] Structural mismatch: Not a verified Cut 2 contract.")
        return 2

    validation = data.get("validation", {})
    if not validation.get("mechanics_prose_free") or not validation.get("runtime_safe"):
        print("[GOVERNANCE] [ENTITY_LINT] [REJECT] Core violation: Passport must assert prose-free validation flags.")
        return 2

    if "entities" not in data or not isinstance(data["entities"], list) or len(data["entities"]) == 0:
        print("[GOVERNANCE] [ENTITY_LINT] [REJECT] Critical failure: No executable entity rows found inside passport.")
        return 2

    # 2. Hardcoded Architectural Primitive Vocabularies
    allowed_archetypes = ["caster", "warrior", "guardian", "civilian"]
    allowed_shells = ["humanoid", "humanoid_tall", "creature_large"]
    allowed_colors = ["blue", "red", "green", "gray"]
    allowed_capabilities = ["cast", "command", "move", "speak", "guard"]
    allowed_statuses = ["verified", "provisional"]

    # 3. Contamination Anti-Tamper Sweep
    prohibited_execution_keys = ["name", "description", "title", "story_keyword", "class_label"]

    for entity in data["entities"]:
        eid = entity.get("entity_id", "unknown_actor")
        
        # Actively catch prose leakage outside of the designated provenance envelope
        for key in prohibited_execution_keys:
            if key in entity or key in entity.get("shell", {}) or key in entity.get("resolution", {}):
                print(f"[GOVERNANCE] [ENTITY_LINT] [REJECT] Prose trace detected inside active execution block: '{key}' for {eid}!")
                return 2

        # Evaluate attributes against universal primitive sets
        arch = entity.get("archetype")
        shell_type = entity.get("shell", {}).get("placeholder_type")
        shell_color = entity.get("shell", {}).get("placeholder_color")
        status = entity.get("resolution", {}).get("ontology_status")

        if arch not in allowed_archetypes:
            print(f"[GOVERNANCE] [ENTITY_LINT] [REJECT] Invalid entity archetype: '{arch}' for {eid}")
            return 2
        if shell_type not in allowed_shells:
            print(f"[GOVERNANCE] [ENTITY_LINT] [REJECT] Invalid primitive shape: '{shell_type}' for {eid}")
            return 2
        if shell_color not in allowed_colors:
            print(f"[GOVERNANCE] [ENTITY_LINT] [REJECT] Invalid visual identifier color: '{shell_color}' for {eid}")
            return 2
        if status not in allowed_statuses:
            print(f"[GOVERNANCE] [ENTITY_LINT] [REJECT] Invalid ontology status definition: '{status}' for {eid}")
            return 2

        # Verify capability arrays
        for cap in entity.get("capabilities", []):
            if cap not in allowed_capabilities:
                print(f"[GOVERNANCE] [ENTITY_LINT] [REJECT] Unrecognized capability primitive: '{cap}' for {eid}")
                return 2

    print("[GOVERNANCE] [ENTITY_LINT] PASS: Passport matches universal structural specifications. Runtime safe.")
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.argv.append("/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore/exports/contracts/entity.proof.001.json")
    sys.exit(lint_entity_passport(Path(sys.argv[1])))