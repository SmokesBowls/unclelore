#!/usr/bin/env python3
import sys
import json
from pathlib import Path

def lint_proof_contract(file_path: Path) -> int:
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[OKARCHITECT] [REJECT] Invalid JSON formatting: {e}")
        return 2

    # Strict structural identity requirements
    if data.get("contract_type") != "semantic_scene_contract_cut_1":
        print("[OKARCHITECT] [REJECT] Missing/Incorrect contract_type identity!")
        return 2

    validation = data.get("validation", {})
    if not validation.get("mechanics_prose_free") or not validation.get("runtime_safe"):
        print("[OKARCHITECT] [REJECT] Contract must explicitly enforce prose-free flags.")
        return 2

    if "regions" not in data or not isinstance(data["regions"], list) or len(data["regions"]) == 0:
        print("[OKARCHITECT] [REJECT] Critical failure: No executable regions found.")
        return 2

    # THE CONSTITUTIONAL FIREWALL
    # Prose may exist upstream, but runtime execution fields must be blind to it
    prohibited_keys = ["label", "story_keyword", "description", "text", "biome_name", "author_term"]
    allowed_forms = ["depression", "elevation_spike", "flat_plain"]
    allowed_materials = ["ash", "sand", "rock", "water", "grass"]

    for region in data["regions"]:
        for key in prohibited_keys:
            if key in region or key in region.get("topology", {}) or key in region.get("surface", {}):
                print(f"[OKARCHITECT] [REJECT] Prose trace detected inside key: '{key}'!")
                return 2

        form = region.get("topology", {}).get("form")
        material = region.get("surface", {}).get("material")

        if form not in allowed_forms:
            print(f"[OKARCHITECT] [REJECT] Unauthorized topology form primitive: '{form}'")
            return 2
        if material not in allowed_materials:
            print(f"[OKARCHITECT] [REJECT] Unauthorized material primitive: '{material}'")
            return 2

    print("[OKARCHITECT] [VALIDATOR] PASS: Contract is completely clean and prose-free.")
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 lint_scene_contract.py <path_to_json>")
        # Default to the pristine Treaty Output location
        sys.argv.append("/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore/exports/contracts/scene.proof.001.json")
    sys.exit(lint_proof_contract(Path(sys.argv[1])))