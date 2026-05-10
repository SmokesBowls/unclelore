"""
MrLore Phase 4 — CocoIndex Delta Flow
coco_flow.py

Purpose:
    Detect changed vault source files and emit one flag file per change.
    Does NOT write to wiki. Does NOT validate tiers. Does NOT ingest.
    CocoIndex is a sensor only.

Output:
    cocowatch/output/changed/<slugged_path>.flag
    (one file per changed vault source, content = vault-relative path)

After this runs:
    python3 cocowatch/collect_delta.py
    → writes raw/cocoindex_delta.txt
    → feed to write_changed_manifest.py --from-file

Architecture:
    CocoIndex detects change (memo=True handles state/diff)
    ↓
    One .flag file per changed source (safe, no shared append)
    ↓
    collect_delta.py reads all .flag files
    ↓
    writes raw/cocoindex_delta.txt atomically
    ↓
    write_changed_manifest.py validates
    ↓
    mrlore_run_changed.py ingests

Usage:
    cd ~/Downloads/obsidianburdenNov25/_mrlore/cocowatch
    python3 -m cocoindex run coco_flow.py          # batch scan
    python3 -m cocoindex update coco_flow.py       # update only changed
"""

import pathlib
import cocoindex as coco
from cocoindex.resources.file import FileLike, PatternFilePathMatcher
from cocoindex.connectors import localfs

# ── PATHS ────────────────────────────────────────────────────────────────────

# Resolved relative to this file's location (_mrlore/cocowatch/)
_HERE       = pathlib.Path(__file__).resolve().parent
MRLORE_ROOT = _HERE.parent
VAULT_ROOT  = MRLORE_ROOT.parent

OUTPUT_DIR  = _HERE / "output" / "changed"
STATE_DIR   = _HERE / "state"

# Source extensions CocoIndex should watch
WATCHED_PATTERNS = [
    "**/*.md",
    "**/*.txt",
]

# Directories to exclude — CocoIndex path filter prefix
EXCLUDED_PREFIXES = [
    "_mrlore",
    ".git",
    ".obsidian",
    "__pycache__",
    ".trash",
]


# ── HELPERS ──────────────────────────────────────────────────────────────────

def _is_excluded(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    return bool(set(parts) & set(EXCLUDED_PREFIXES))


def _slug(rel_path: str) -> str:
    """Turn vault-relative path into a safe flat filename."""
    return rel_path.replace("/", "__").replace(" ", "_").replace("\\", "__")


# ── COCOINDEX TRANSFORM ───────────────────────────────────────────────────────

@coco.fn(memo=True)
async def emit_change_flag(file: FileLike) -> None:
    """
    Called by CocoIndex only when a file has changed since last run.
    memo=True means CocoIndex tracks state — unchanged files are skipped.

    Writes one .flag file per changed source.
    Uses localfs.declare_file (CocoIndex-native, safe for parallel execution).
    Does NOT append to shared files.
    """
    rel_path = str(file.file_path.path.relative_to(VAULT_ROOT))

    if _is_excluded(rel_path):
        return

    slug = _slug(rel_path)
    flag_path = OUTPUT_DIR / f"{slug}.flag"

    # Content of flag file = vault-relative path (one line)
    localfs.declare_file(
        flag_path,
        rel_path + "\n",
        create_parent_dirs=True,
    )


@coco.fn
async def app_main() -> None:
    """
    Main CocoIndex flow entry point.

    NOTE:
    localfs.walk_dir currently observes only the immediate directory level in this
    environment, so Phase 4 uses explicit source roots. This is safer anyway for
    MrLore because it prevents loose root notes from dominating deltas.
    """
    source_roots = [
        VAULT_ROOT / "book_01_book_of_genesis",
        VAULT_ROOT / "book_02_age_of_servitude",
    ]

    for source_root in source_roots:
        if not source_root.exists():
            continue

        files = localfs.walk_dir(
            source_root,
            path_matcher=PatternFilePathMatcher(
                included_patterns=WATCHED_PATTERNS,
            ),
            live=False,
        )
        await coco.mount_each(emit_change_flag, files.items())


# ── APP REGISTRATION ─────────────────────────────────────────────────────────

app = coco.App(
    coco.AppConfig(name="MrLoreWatch"),
    app_main,
)
