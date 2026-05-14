#!/usr/bin/env python3
"""
TASK 6.4A-R1: Add compound noun extraction and smarter exclusion logic.
Filters standalone colors/ordinals, extracts bigram/trigram proper noun phrases,
and supports --output flag for deterministic logging.
Deterministic. Dry-run only. Zero mutations. EXIT 0/2 enforced.
"""
import argparse
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
CHAPTERS_DIR = os.path.join(BASE_DIR, "raw/chapters")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")

# Curated deterministic exclusion set
COMMON_WORDS = {
    "The", "A", "An", "And", "Or", "But", "In", "On", "At", "To", "For",
    "With", "By", "From", "Up", "About", "Into", "Over", "After", "I", "Me",
    "My", "We", "Us", "Our", "You", "Your", "He", "Him", "His", "She", "Her",
    "It", "Its", "They", "Them", "Their", "What", "Which", "Who", "Whom",
    "This", "That", "These", "Those", "Is", "Are", "Was", "Were", "Be",
    "Been", "Being", "Have", "Has", "Had", "Do", "Does", "Did", "Will",
    "Would", "Could", "Should", "May", "Might", "Must", "Shall", "Can",
    "Need", "Dare", "Ought", "Used", "Of", "If", "So", "As", "No", "Not"
}
COLORS = {"Red", "Blue", "Green", "White", "Crimson", "Violet", "Golden", "Silver", "Black", "Purple", "Dark", "Light", "Yellow", "Orange", "Pink"}
ORDINALS = {"First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth", "Last", "Next", "Final"}
METADATA = {"ACT", "ARC", "STATUS", "TIME", "FOCUS", "THREADS", "POV", "PERIOD", "REGION", "MOVEMENT", "NOTE", "CHAPTER", "BOOK", "PART", "SECTION", "VOLUME", "PAGE", "FILE"}

EXCLUSIONS = set(COMMON_WORDS) | set(COLORS) | set(ORDINALS) | set(METADATA)
# Normalize for case-insensitive matching
_EXCASING = {w.lower() for w in EXCLUSIONS} | EXCLUSIONS | {w.upper() for w in EXCLUSIONS}
EXCLUSIONS.update(_EXCASING)

def load_registry_entities():
    """Load canonical names and variants from registry.md."""
    known = set()
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return known

    header_found = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"): continue
        parts = [p.strip() for p in stripped.strip("|").split("|")]
        if "Canonical Name" in parts:
            header_found = True; continue
        if not header_found: continue
        if not parts or "---" in parts[0]: continue
        
        canon = parts[0].strip()
        if canon: known.add(canon.lower())
        
        if len(parts) > 2 and parts[2] and parts[2] not in ("-", "—"):
            for v in parts[2].split(","):
                vc = v.strip()
                if vc and vc not in ("-", "—"): known.add(vc.lower())
    return known

def process_sentence(sent, registry_known):
    """Extract valid single tokens and adjacent bigrams/trigrams from a sentence."""
    singles = set()
    phrases = set()
    
    # Find all capitalized words (min 3 chars)
    capitalized = [(m.group(0), m.start()) for m in re.finditer(r'\b[A-Z][a-zA-Z\']{2,}\b', sent)]
    
    # Filter exclusions & registry
    valid = [(w, pos) for w, pos in capitalized 
             if w not in EXCLUSIONS 
             and w.lower() not in EXCLUSIONS 
             and w.lower() not in registry_known]
             
    # Singles
    for w, _ in valid:
        singles.add(w)
        
    # Bigrams & Trigrams (adjacent in valid list = effectively adjacent in text)
    for i in range(len(valid)):
        # Bigram
        if i + 1 < len(valid):
            # Check if truly adjacent in raw text (gap <= 20 chars)
            gap = valid[i+1][1] - valid[i][1] - len(valid[i][0])
            if gap <= 25:
                bigram = f"{valid[i][0]} {valid[i+1][0]}"
                phrases.add(bigram)
        # Trigram
        if i + 2 < len(valid):
            gap1 = valid[i+1][1] - valid[i][1] - len(valid[i][0])
            gap2 = valid[i+2][1] - valid[i+1][1] - len(valid[i+1][0])
            if gap1 <= 25 and gap2 <= 25:
                trigram = f"{valid[i][0]} {valid[i+1][0]} {valid[i+2][0]}"
                phrases.add(trigram)
                
    return singles, phrases

def main():
    parser = argparse.ArgumentParser(description="Extract recurring proper noun candidates (R1)")
    parser.add_argument("--dry-run", action="store_true", required=True, help="Process candidates. No wiki mutations.")
    parser.add_argument("--output", action="store_true", help="Write full results to logs/candidates_TIMESTAMP.txt. Stdout shows summary only.")
    args = parser.parse_args()

    if not os.path.exists(CHAPTERS_DIR):
        print("ERROR: raw/chapters/ directory not found.", file=sys.stderr)
        sys.exit(2)

    registry_known = load_registry_entities()
    print(f"[INIT] Loaded {len(registry_known)} registry anchors for exclusion.", file=sys.stderr)

    chapter_files = sorted(
        glob.glob(os.path.join(CHAPTERS_DIR, "*.md")) +
        glob.glob(os.path.join(CHAPTERS_DIR, "*.txt"))
    )
    print(f"[SCAN] Processing {len(chapter_files)} chapter files.", file=sys.stderr)

    # candidate_name -> set of chapter filenames
    cross_chapter = defaultdict(set)
    is_phrase = {} # track which are phrases vs tokens

    for fpath in chapter_files:
        fname = os.path.basename(fpath)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue

        sentences = re.split(r'(?<=[.!?])\s+', text)
        file_candidates = set()

        for sent in sentences:
            if not sent.strip(): continue
            
            # Identify sentence starter to skip it
            first_match = re.search(r'\b[A-Z][a-zA-Z]+\b', sent)
            first_word = first_match.group(0) if first_match else ""
            
            sent_singles, sent_phrases = process_sentence(sent, registry_known)
            
            # Remove sentence-starting single tokens to avoid false positives
            if first_word and first_word not in EXCLUSIONS:
                sent_singles.discard(first_word)
                
            for s in sent_singles:
                file_candidates.add(s)
                is_phrase[s] = False
                
            for p in sent_phrases:
                file_candidates.add(p)
                is_phrase[p] = True

        for cand in file_candidates:
            cross_chapter[cand].add(fname)

    # Filter & Sort
    threshold = 3
    results = []
    for cand, chapters in cross_chapter.items():
        if len(chapters) >= threshold:
            results.append((cand, len(chapters), sorted(list(chapters)), is_phrase.get(cand, False)))

    # Primary: frequency desc. Secondary: phrases first. Tertiary: alphabetical.
    results.sort(key=lambda x: (-x[1], not x[3], x[0]))

    # Formatting
    output_lines = []
    for cand, freq, files, phrase_flag in results:
        tag = "[PHRASE]" if phrase_flag else "[TOKEN]"
        output_lines.append(f"{tag:<10} {cand:<30} | {freq:>3} files | e.g., {files[0]}")
        
    log_content = f"CANDIDATE PROPER NOUNS (>= {threshold} chapters | registry excluded)\n{'='*80}\n" + "\n".join(output_lines) + f"\n{'='*80}\nTotal candidates: {len(results)}\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

    if args.output:
        os.makedirs(LOGS_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_path = os.path.join(LOGS_DIR, f"candidates_{ts}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(log_content)
        print(f"[SUMMARY] {len(results)} candidates surfaced. Results written to {out_path}")
    else:
        print("\n" + log_content)
        print("[DRY-RUN] Complete. No files written. wiki/proposals/ untouched.")
        
    print("EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()