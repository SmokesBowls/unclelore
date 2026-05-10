#!/usr/bin/env python3
"""
MrLore Phase 5b — Proposal Generator
propose_corrections.py

Reads authorized continuity conflict records from wiki/continuity/*.yaml
Generates bounded patch proposals.
Presents proposals for human approval.
Writes approved proposals as Trae-executable patch tasks.

Does NOT apply patches autonomously.
Does NOT modify Tier 0 prose without explicit approval.
Does NOT resolve canon disputes.

Workflow:
  1. Scan wiki/continuity/ for status: authorized_for_5b
  2. Generate patch proposal per conflict
  3. Show diff preview to human
  4. Human approves / rejects / defers each
  5. Write approved patches to wiki/proposals/<CONT-ID>_patch.yaml
  6. Trae reads patch tasks and applies via str_replace

Usage:
  python3 tools/propose_corrections.py                    # interactive review
  python3 tools/propose_corrections.py --list             # list pending proposals
  python3 tools/propose_corrections.py --apply CONT-0001  # generate patch task only
  python3 tools/propose_corrections.py --batch            # approve all safe proposals

Exit codes:
  0  clean
  1  mechanical failure
  2  proposals pending human review
"""

import re
import sys
import yaml
from pathlib import Path
from datetime import datetime

MRLORE_ROOT    = Path(__file__).resolve().parents[1]
VAULT_ROOT     = MRLORE_ROOT.parent
WIKI_PATH      = MRLORE_ROOT / "wiki"
CONTINUITY_DIR = WIKI_PATH / "continuity"
PROPOSALS_DIR  = WIKI_PATH / "proposals"
LOGS_DIR       = MRLORE_ROOT / "logs"
LOG_PATH       = WIKI_PATH / "log.md"

PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

SOURCE_EXTS = {".md", ".txt"}


# ── CONFLICT LOADER ───────────────────────────────────────────────────────────

def load_authorized_conflicts() -> list[dict]:
    """Load all conflict records with status: authorized_for_5b."""
    conflicts = []
    if not CONTINUITY_DIR.exists():
        return conflicts
    for f in sorted(CONTINUITY_DIR.glob("CONT-*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if data and data.get("status") == "authorized_for_5b":
                data["_file"] = f
                conflicts.append(data)
        except Exception as e:
            print(f"  WARN: could not parse {f.name}: {e}")
    return conflicts


def load_all_conflicts() -> list[dict]:
    """Load all conflict records regardless of status."""
    conflicts = []
    if not CONTINUITY_DIR.exists():
        return conflicts
    for f in sorted(CONTINUITY_DIR.glob("CONT-*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if data:
                data["_file"] = f
                conflicts.append(data)
        except Exception as e:
            print(f"  WARN: could not parse {f.name}: {e}")
    return conflicts


# ── PROPOSAL GENERATORS ───────────────────────────────────────────────────────

def generate_replace_token_proposal(conflict: dict) -> dict | None:
    """
    Generate a replace_token proposal from a conflict record.
    Finds all instances in source file and builds a precise patch list.
    """
    proposal = conflict.get("proposal", {})
    if proposal.get("action") != "replace_token":
        return None

    from_token = proposal.get("from")
    to_token   = proposal.get("to")
    source_rel = conflict.get("chapter", {}).get("source")

    if not all([from_token, to_token, source_rel]):
        return None

    source_path = VAULT_ROOT / source_rel
    if not source_path.exists():
        print(f"  ERROR: source not found: {source_path}")
        return None

    text = source_path.read_text(encoding="utf-8", errors="replace")

    # Find all instances with context
    pattern = r"\b" + re.escape(from_token) + r"\b"
    matches = list(re.finditer(pattern, text))

    if not matches:
        return None

    patches = []
    for m in matches:
        start  = max(0, m.start() - 60)
        end    = min(len(text), m.end() + 60)
        before = text[start:m.start()].replace("\n", " ")
        after  = text[m.end():end].replace("\n", " ")
        patches.append({
            "offset":  m.start(),
            "from":    from_token,
            "to":      to_token,
            "context": f"...{before}[{from_token}]{after}...",
        })

    return {
        "conflict_id":   conflict.get("conflict_id"),
        "action":        "replace_token",
        "source":        source_rel,
        "from_token":    from_token,
        "to_token":      to_token,
        "instance_count": len(patches),
        "patches":       patches,
        "generated":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status":        "pending_approval",
        "approved":      False,
        "applied":       False,
    }


PROPOSAL_GENERATORS = {
    "replace_token": generate_replace_token_proposal,
}


def generate_proposal(conflict: dict) -> dict | None:
    action = conflict.get("proposal", {}).get("action")
    generator = PROPOSAL_GENERATORS.get(action)
    if not generator:
        return None
    return generator(conflict)


# ── DISPLAY ──────────────────────────────────────────────────────────────────

def display_proposal(proposal: dict) -> None:
    print()
    print(f"{'═' * 60}")
    print(f"  Proposal: {proposal['conflict_id']}")
    print(f"  Action:   {proposal['action']}")
    print(f"  Source:   {proposal['source']}")
    print(f"  Replace:  '{proposal['from_token']}' → '{proposal['to_token']}'")
    print(f"  Count:    {proposal['instance_count']} instance(s)")
    print(f"{'─' * 60}")
    print("  Instances:")
    for i, patch in enumerate(proposal["patches"][:5], 1):
        print(f"  [{i}] {patch['context']}")
    if len(proposal["patches"]) > 5:
        print(f"  ... and {proposal['instance_count'] - 5} more")
    print(f"{'═' * 60}")


# ── PROPOSAL FILE WRITER ──────────────────────────────────────────────────────

def write_proposal_file(proposal: dict) -> Path:
    """Write approved proposal as a Trae-executable patch task."""
    conflict_id = proposal["conflict_id"]
    path = PROPOSALS_DIR / f"{conflict_id}_patch.yaml"
    path.write_text(
        yaml.dump(proposal, default_flow_style=False, allow_unicode=True),
        encoding="utf-8"
    )
    return path


def update_conflict_status(conflict: dict, new_status: str) -> None:
    """Update the status field in the original conflict YAML file."""
    file_path = conflict.get("_file")
    if not file_path:
        return
    data = yaml.safe_load(Path(file_path).read_text(encoding="utf-8"))
    data["status"] = new_status
    data.setdefault("resolution_log", []).append(
        f"{datetime.now().strftime('%Y-%m-%d')}: Status updated to {new_status}"
    )
    Path(file_path).write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8"
    )


# ── TRAE PATCH TASK GENERATOR ─────────────────────────────────────────────────

def write_trae_task(proposal: dict) -> Path:
    """
    Write a Trae-executable task file for applying the approved patch.
    Trae reads this, applies str_replace operations, reports done.
    """
    task_lines = [
        f"Execute these commands in exact order. No variations.",
        f"",
        f"1. Run this command:",
        f"   sed -i 's/{proposal['from_token']}/{proposal['to_token']}/g'"
        f" '{VAULT_ROOT / proposal['source']}'",
        f"",
        f"2. Run this command:",
        f"   grep -c '{proposal['to_token']}' '{VAULT_ROOT / proposal['source']}'",
        f"",
        f"3. Report exactly: "
        f"'Patch {proposal['conflict_id']} applied.' and call task_done.",
        f"",
        f"Do not run any other commands.",
        f"Do not create placeholder files.",
    ]

    task_path = PROPOSALS_DIR / f"{proposal['conflict_id']}_trae_task.txt"
    task_path.write_text("\n".join(task_lines), encoding="utf-8")
    return task_path


# ── MODES ────────────────────────────────────────────────────────────────────

def mode_list() -> int:
    """List all pending and authorized conflicts."""
    all_conflicts = load_all_conflicts()
    if not all_conflicts:
        print("[propose] No conflict records found.")
        return 0

    print(f"\n{'═' * 60}")
    print(f"  MrLore Conflict Registry")
    print(f"{'═' * 60}")
    for c in all_conflicts:
        cid    = c.get("conflict_id", "?")
        status = c.get("status", "?")
        ctype  = c.get("type", "?")
        source = c.get("chapter", {}).get("source", "?")
        print(f"  {cid}  [{status}]  {ctype}")
        print(f"         {source}")
    print()
    return 0


def mode_interactive() -> int:
    """Interactive proposal review."""
    conflicts = load_authorized_conflicts()
    if not conflicts:
        print("[propose] No conflicts authorized for Phase 5b.")
        print("          Run continuity_audit.py first, then authorize conflicts.")
        return 0

    print(f"[propose] {len(conflicts)} conflict(s) authorized for proposal generation.")
    approved_count = 0
    rejected_count = 0

    for conflict in conflicts:
        proposal = generate_proposal(conflict)
        if not proposal:
            print(f"  SKIP: {conflict.get('conflict_id')} — no generator for "
                  f"{conflict.get('proposal', {}).get('action')}")
            continue

        display_proposal(proposal)
        print()
        print("  Options:")
        print("    [a] Approve — write patch task for Trae")
        print("    [r] Reject  — mark conflict as rejected")
        print("    [d] Defer   — leave for later review")
        print("    [s] Skip    — skip this conflict")

        while True:
            choice = input("  Choice [a/r/d/s]: ").strip().lower()
            if choice in ("a", "r", "d", "s"):
                break
            print("  Invalid choice. Enter a, r, d, or s.")

        if choice == "a":
            proposal["approved"] = True
            proposal["status"]   = "approved"
            prop_path = write_proposal_file(proposal)
            task_path = write_trae_task(proposal)
            update_conflict_status(conflict, "approved")
            approved_count += 1
            print(f"  ✓ Approved. Proposal: {prop_path.name}")
            print(f"  ✓ Trae task: {task_path.name}")

        elif choice == "r":
            update_conflict_status(conflict, "rejected")
            rejected_count += 1
            print(f"  ✗ Rejected.")

        elif choice == "d":
            update_conflict_status(conflict, "deferred")
            print(f"  ⏸ Deferred.")

        elif choice == "s":
            print(f"  → Skipped.")

    print()
    print(f"[propose] Session complete.")
    print(f"          Approved: {approved_count}  Rejected: {rejected_count}")

    if approved_count:
        print(f"\n[propose] To apply approved patches, run Trae on each task file:")
        for f in sorted(PROPOSALS_DIR.glob("*_trae_task.txt")):
            print(f"  {f.name}")
        print()
        return 2  # proposals pending Trae execution

    return 0


def mode_apply(conflict_id: str) -> int:
    """Generate patch task for a specific conflict without interactive review."""
    conflicts = load_authorized_conflicts()
    target = next((c for c in conflicts
                   if c.get("conflict_id") == conflict_id), None)
    if not target:
        print(f"[propose] ERROR: {conflict_id} not found or not authorized_for_5b")
        return 1

    proposal = generate_proposal(target)
    if not proposal:
        print(f"[propose] ERROR: no proposal generator for this conflict type")
        return 1

    proposal["approved"] = True
    proposal["status"]   = "approved"
    prop_path = write_proposal_file(proposal)
    task_path = write_trae_task(proposal)
    update_conflict_status(target, "approved")

    print(f"[propose] Proposal written: {prop_path}")
    print(f"[propose] Trae task written: {task_path}")
    return 2


def mode_batch() -> int:
    """Auto-approve all safe (replace_token) proposals without interaction."""
    conflicts = load_authorized_conflicts()
    safe = [c for c in conflicts
            if c.get("proposal", {}).get("action") == "replace_token"]

    if not safe:
        print("[propose] No safe proposals available for batch approval.")
        return 0

    print(f"[propose] Batch approving {len(safe)} replace_token proposal(s).")
    for conflict in safe:
        proposal = generate_proposal(conflict)
        if not proposal:
            continue
        proposal["approved"] = True
        proposal["status"]   = "approved"
        prop_path = write_proposal_file(proposal)
        task_path = write_trae_task(proposal)
        update_conflict_status(conflict, "approved")
        print(f"  ✓ {conflict['conflict_id']} → {task_path.name}")

    return 2  # Trae execution required


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> int:
    args = sys.argv[1:]

    if "--list" in args:
        return mode_list()

    if "--batch" in args:
        return mode_batch()

    for i, arg in enumerate(args):
        if arg == "--apply" and i + 1 < len(args):
            return mode_apply(args[i + 1])

    return mode_interactive()


if __name__ == "__main__":
    sys.exit(main())
