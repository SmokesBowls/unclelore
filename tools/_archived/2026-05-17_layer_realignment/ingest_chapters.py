#!/usr/bin/env python3
"""
TASK 7.3A-R1: Repair ingest_chapters.py --dry-run flag blocking --apply mode.
Changes required=True to required=False.
When --dry-run is not passed, executes the file copies.
Deterministic. No other logic altered. Zero mutations on dry-run.
"""
import argparse
import glob
import os
import re
import shutil
import sys

VAULT_ROOT = "/home/mytruelove/Downloads/obsidianburdenNov25"
MRLORE_ROOT = os.path.join(VAULT_ROOT, "_mrlore")
CHAPTERS_DIR = os.path.join(MRLORE_ROOT, "raw", "chapters")

EXCLUDE_KEYWORDS = {"fairy_tale", "synapsis", "toc", "nlm"}
ALLOWED_EXTS = {".md", ".txt"}

def is_chapter_file(filename):
    """Check if filename matches a basic chapter number pattern."""
    basename = os.path.basename(filename).lower()
    return bool(re.match(r'^(?:\d+|ch\.?|chapter)', basename))

def normalize_filename(src_path, book_dir):
    """Map source filename to book_NN_bookname_NNN_chaptername.ext"""
    basename = os.path.basename(src_path)
    name_part, ext = os.path.splitext(basename)

    # Extract book number/name from directory
    dir_name = os.path.basename(book_dir)
    book_match = re.match(r'book_(\d+)(?:[_\- ]+(.*))?', dir_name, re.IGNORECASE)
    book_num = f"{int(book_match.group(1)):02d}" if book_match else "00"
    book_name = re.sub(r'[^a-zA-Z0-9_]', '_', (book_match.group(2) or dir_name)).strip('_').lower()

    # Extract chapter number/name from filename
    chap_match = re.match(r'^(?:ch(?:apter)?\.?\s*)?(\d+)(?:[_\- ]+(.*))?', name_part, re.IGNORECASE)
    chap_num = f"{int(chap_match.group(1)):03d}" if chap_match else "000"
    chap_name = re.sub(r'[^a-zA-Z0-9_]', '_', (chap_match.group(2) or name_part)).strip('_').lower()

    return f"book_{book_num}_{book_name}_{chap_num}_{chap_name}{ext}"

def main():
    parser = argparse.ArgumentParser(description="Chapter Ingest Tool")
    # R1 FIX: required=True -> required=False. Apply is default when --dry-run is absent.
    parser.add_argument("--dry-run", action="store_true", required=False, default=False, help="Print mapping only. No copies.")
    args = parser.parse_args()

    if not os.path.exists(CHAPTERS_DIR):
        if not args.dry_run:
            os.makedirs(CHAPTERS_DIR, exist_ok=True)
        else:
            print(f"[INFO] {CHAPTERS_DIR} does not exist. Creating it would be part of apply mode.")

    existing_files = set(os.listdir(CHAPTERS_DIR)) if os.path.exists(CHAPTERS_DIR) else set()
    book_dirs = sorted(glob.glob(os.path.join(VAULT_ROOT, "book_*")))
    
    print(f"[DISCOVERY] Found {len(book_dirs)} book directories at vault root.")
    candidates = []

    for bdir in book_dirs:
        bdir_name = os.path.basename(bdir).lower()
        # Skip extra_* directories at root level
        if bdir_name.startswith("extra_"):
            continue

        for root, dirs, files in os.walk(bdir):
            # Prune extra_* subdirectories during walk
            dirs[:] = [d for d in dirs if "extra_" not in d.lower()]

            for fname in files:
                _, ext = os.path.splitext(fname)
                if ext.lower() not in ALLOWED_EXTS:
                    continue
                # Keyword exclusion
                fname_lower = fname.lower()
                if any(kw in fname_lower for kw in EXCLUDE_KEYWORDS):
                    continue
                if not is_chapter_file(fname):
                    continue

                dest_name = normalize_filename(os.path.join(root, fname), bdir)
                
                # Skip if already present in raw/chapters/
                if dest_name in existing_files:
                    continue

                candidates.append((os.path.join(root, fname), os.path.join(CHAPTERS_DIR, dest_name)))

    print(f"[FILTERING] Identified {len(candidates)} new chapter candidates.")
    print("=" * 90)
    print(f"{'SOURCE PATH':<65} | DESTINATION FILE")
    print("-" * 90)
    
    for src, dst in candidates:
        src_rel = os.path.relpath(src, VAULT_ROOT)
        dst_name = os.path.basename(dst)
        print(f"{src_rel:<65} -> {dst_name}")
        
    print("=" * 90)
    print(f"[SUMMARY] {len(candidates)} files ready for ingest.")

    if args.dry_run:
        print("[DRY-RUN] No files copied. Originals untouched.")
        sys.exit(0)
    else:
        if not os.path.exists(CHAPTERS_DIR):
            os.makedirs(CHAPTERS_DIR, exist_ok=True)
        
        for src, dst in candidates:
            try:
                shutil.copy2(src, dst)
                print(f"[COPIED] {src_rel:<65} -> {dst_name}")
            except Exception as e:
                print(f"[ERROR] Failed to copy {src}: {e}")
                sys.exit(1)
        
        print(f"[APPLY] {len(candidates)} files copied to raw/chapters/. EXIT 0")
        sys.exit(0)

if __name__ == "__main__":
    main()