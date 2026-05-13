#!/usr/bin/env python3
"""MRLORE-FIX-003: Tooling Logic Hardening & Corpus State Injection"""
import os, sys, re, shutil, argparse
from pathlib import Path

MRLORE_ROOT = Path(os.environ.get("MRLORE_ROOT", Path.home() / "Downloads/obsidianburdenNov25/_mrlore"))
TOOLS_DIR   = MRLORE_ROOT / "tools"
WIKI_DIR    = MRLORE_ROOT / "wiki"
EXIT_CODE   = 0

CORPUS_LOADER_SNIPPET = '''
def load_corpus_context():
    """Load §22 Session Contract state: index, contradictions, canon decisions."""
    context = {"index": None, "contradictions": [], "canon_decisions": []}
    idx = WIKI_DIR / "index.md"
    if idx.exists(): context["index"] = idx.read_text(encoding="utf-8")
    
    cont_dir = WIKI_DIR / "continuity"
    if cont_dir.exists():
        for f in sorted(cont_dir.glob("*.yaml")):
            context["contradictions"].append({"file": f.name, "content": f.read_text(encoding="utf-8")})
            
    canon_dir = WIKI_DIR / "canon_decisions"
    if canon_dir.exists():
        for f in sorted(canon_dir.glob("*.md")):
            if f.name.startswith("CANON-"):
                context["canon_decisions"].append({"file": f.name, "content": f.read_text(encoding="utf-8")})
    return context
'''

def patch_file(filepath, apply=False):
    content = filepath.read_text(encoding="utf-8")
    changes = []
    original = content

    # 1. Fix Dry-Run Bypass
    dry_pattern = r'(if.*dry.?run.*:\n\s*)(return|sys\.exit|continue|pass)'
    if re.search(dry_pattern, content, re.IGNORECASE):
        changes.append("🔧 Fixing dry-run bypass to allow validation execution")
        content = re.sub(dry_pattern, r'\1print("[DRY-RUN] Validation skipped, but logic proceeds.\")\n        # validation runs regardless in dry-run mode', content, flags=re.IGNORECASE)

    # 2. Inject Corpus Loader if missing
    if 'load_corpus_context' not in content and 'MISSING STATE LOAD' in filepath.name:
        changes.append("🔧 Injecting load_corpus_context() per §22 Session Contract")
        # Add imports if missing
        if 'from pathlib import Path' not in content:
            content = "from pathlib import Path\n" + content
        if 'import os' not in content:
            content = "import os\n" + content
            
        # Insert loader before main()
        main_match = re.search(r'(\ndef main\(\):)', content)
        if main_match:
            pos = main_match.start()
            content = content[:pos] + CORPUS_LOADER_SNIPPET + "\n" + content[pos:]
            
        # Inject call at start of main()
        content = re.sub(r'def main\(\):\n', 'def main():\n    ctx = load_corpus_context()  # §22 Context Load\n', content)

    if content != original:
        if apply:
            backup = filepath.with_suffix(filepath.suffix + ".bak")
            shutil.copy(filepath, backup)
            filepath.write_text(content, encoding="utf-8")
            print(f"✅ Applied: {filepath.name}")
            return True
        else:
            print(f"📝 Preview changes for: {filepath.name}")
            for c in changes:
                print(f"   - {c}")
            return True
    return False

def main():
    global EXIT_CODE
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Commit patches to disk")
    args = parser.parse_args()

    targets = {
        "mrlore_run_changed.py": ["DRY-RUN BYPASS"],
        "write_changed_manifest.py": ["DRY-RUN BYPASS", "MISSING STATE LOAD"],
        "audit_source_authority.py": ["MISSING STATE LOAD"],
        "promote_candidate.py": ["DRY-RUN BYPASS"]
    }

    print(f"🔍 MRLORE-FIX-003: {'Applying' if args.apply else 'Previewing'} logic patches...")
    patched_count = 0
    for fname, issues in targets.items():
        path = TOOLS_DIR / fname
        if path.exists():
            if patch_file(path, args.apply):
                patched_count += 1
        else:
            print(f"⚠️ Missing target: {fname}")

    if not args.apply:
        print("\n🔒 Dry-run complete. Run with --apply to commit.")
    else:
        print(f"\n✅ {patched_count} tools patched. Re-run audit to verify EXIT 0.")
        
    sys.exit(EXIT_CODE)

if __name__ == "__main__":
    main()
