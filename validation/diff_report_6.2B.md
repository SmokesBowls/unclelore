# MrLore 6.2B — Surgical Pipeline Fix Diff Report

**Generated:** 2026-05-17  
**Status:** EXIT 0 — all three fixes applied, syntax clean, full run complete  
**Tools patched:** artifact_extractor.py, pass2_math.py, identity_signal_math.py  
**Validation dataset:** validation/target_7_query.jsonl (7 targets)

---

## Summary

| Fix | Tool | Mechanism | Verified Impact |
|---|---|---|---|
| Fix 1 | artifact_extractor.py | Expanded stop-word set + all-caps filter | −2,069 artifacts (−4.1%), 50,437 tokens dropped |
| Fix 2 | pass2_math.py | PLURAL_SINGULAR_MAP + O(N) rewrite | 8 plural/possessive merges, raw_variants populated |
| Fix 3 | identity_signal_math.py | proximity_cooccurrence + avg_verb_distance | All 7,984 records gain 2 new deterministic fields |

---

## Fix 1: Stop Word & All-Caps Filter (artifact_extractor.py)

### Changes Applied (line references)
- **Lines 62–84**: Replaced `_STOP_WORDS` (60 words) with `STOP_WORD_SET` (~95 words). Added: `across, almost, alone, along, already, always, away, back, below, either, else, herself, himself, however, itself, let, like, made, many, myself, near, never, new, next, never, off, once, own, re, same, themselves, whether, within, without, yourself`, plus pronoun/possessive variants.
- **Lines 85–90**: Added `CANON_ACRONYM_WHITELIST = {'RCS', 'BH', 'AH', 'TTS', 'NLP', 'AI', 'GPS'}` and `_ALL_CAPS_ONLY_RE`.
- **Lines 92–127**: `extract_tokens` gains `drop_log` parameter; all-caps filter applied to single-word tokens before append.
- **Lines 217–281**: `extract_chapter` returns 3-tuple `(artifacts, chron, drop_count)`; per-chapter drop log printed (first 5 examples + total count).
- **Lines 389–426**: `main()` unpacks 3-tuple, accumulates `total_dropped`, prints in summary.

### Full Re-extraction Results
```
total_artifacts (pre-fix):  50,283
total_artifacts (post-fix): 48,214
reduction:                  −2,069 artifacts (−4.1%)
total_dropped tokens:       50,437 across 139 chapters
```

### 7-Target Delta (Fix 1)

| Target | Pre-fix (mentions) | Post-fix | Change |
|---|---|---|---|
| `Always` | 46 | absent | FILTERED — now in STOP_WORD_SET |
| `ACT` | 116 | absent | FILTERED — all-caps, not in whitelist |
| `Never` | 20 | absent | FILTERED — now in STOP_WORD_SET |
| `Within` | 42 | absent | FILTERED — now in STOP_WORD_SET |
| `CHAPTER` | 31 | absent | FILTERED — all-caps, not in whitelist |
| `BOOK` | 16 | absent | FILTERED — all-caps, not in whitelist |
| `GPT` | 269 | absent | FILTERED — all-caps, not in whitelist¹ |

> ¹ Note: `GPT` was not added to `CANON_ACRONYM_WHITELIST` per spec. The whitelist contains only: `RCS, BH, AH, TTS, NLP, AI, GPS`. Add `GPT` to `CANON_ACRONYM_WHITELIST` in artifact_extractor.py if it represents a meaningful canon term in the corpus.

---

## Fix 2: Lightweight Normalization (pass2_math.py)

### Changes Applied (line references)
- **Lines 70–93**: Added `_POSSESSIVE_RE`, `PLURAL_SINGULAR_MAP`, `normalize_surface_form()`.
- **Lines 254–338**: Rewrote `compute_stats`:
  - Grouping key changed from `art["surface_form"]` to `normalize_surface_form(art["surface_form"])`.
  - `chron_to_chapter` built inline during grouping pass — eliminates prior O(S×N) inner loop.
  - `raw_variants` set tracks original pre-normalization forms per group.
  - Output records gain `raw_variants: list[str]` field.

### Possessive Strip Behavior
The spec regex `(?i)([a-zA-Z]+)'s(?=\s+[a-z])` has `(?i)` which makes the lookahead `[a-z]` case-insensitive. This causes stripping before both lowercase AND uppercase words (e.g., `"Baghdad's House"` → `"Baghdad House"`). This is the literal behavior of the spec as written. 8 possessive merges were observed.

### Observed Merges (all via raw_variants)

| Normalized key | Merged raw variants | Pre-fix mentions | Post-fix mentions | Delta |
|---|---|---|---|---|
| `Giant` | `['Giant', 'Giants']` | Giant=128, Giants=217 | 345 | +217 from Giants |
| `Keeper` | `['Keeper', 'Keepers']` | Keeper=109, Keepers=22 | 131 | +22 from Keepers |
| `Shadow` | `['Shadow', 'Shadows']` | Shadow=22, Shadows=12 | 34 | +12 from Shadows |
| `Earth Spire` | `['Earth Spire', "Earth's Spire"]` | separate | 3 | merged |
| `Earth Void Spire` | `['Earth Void Spire', "Earth's Void Spire"]` | separate | 2 | merged |
| `Mars Void Spire` | `['Mars Void Spire', "Mars's Void Spire"]` | separate | 4 | merged |
| `Senareth Prime` | `['Senareth Prime', "Senareth's Prime"]` | separate | 2 | merged |
| `Tidecaller Mountain` | `['Tidecaller Mountain', "Tidecaller's Mountain"]` | separate | 7 | merged |

> `Students` from the PLURAL_SINGULAR_MAP had no `Student` counterpart; no merge occurred (single form in corpus).
> `Factions` had 1 mention; `Faction` was absent. No meaningful merge.

### 7-Target Delta (Fix 2)

| Target | Pre-fix mentions/chapters | Post-fix mentions/chapters | raw_variants |
|---|---|---|---|
| `Giant` | 128 / 28 | **345 / 48** | `['Giant', 'Giants']` |
| `Giants` | 217 / 45 | **absent** (merged into Giant) | — |
| `Keeper` | 109 / 29 | **131 / 33** | `['Keeper', 'Keepers']` |
| `Keepers` | 22 / 10 | **absent** (merged into Keeper) | — |
| `Geralt` | 1557 / 37 | 1557 / 37 | `['Geralt']` (no normalization applied) |

### Algorithm Improvement
The original `compute_stats` had an O(S×N) inner loop (for each of S unique surface_forms, a full scan of all N artifacts). The Fix 2 rewrite makes this O(N) total by building `chron_to_chapter` during the initial grouping pass. For 8,275 forms × 50,283 artifacts = ~416M operations eliminated.

---

## Fix 3: Proximity Metrics (identity_signal_math.py)

### Changes Applied (line references)
- **Lines 51–173**: Added `STATIC_VERB_SET` (25 verbs), `_PROXIMITY_STOP_WORDS` (mirrors STOP_WORD_SET), `_PASS2_PLURAL_MAP` mirror, `_normalize_for_index()`, `_tokenize()`, `_find_form_positions()`, `compute_proximity_cooccurrence()`, `compute_avg_verb_distance()`.
- **Lines ~340–350**: `compute_signals` indexes artifacts under both original and normalized forms for cross-Fix-2 alignment.
- **Lines ~425–430**: Two new fields added to every output record: `proximity_cooccurrence` and `avg_verb_distance`.
- **Lines ~530**: Coherence check updated to compare normalized artifact forms against normalized pass2 keys.

### Proximity Metric Definitions
- **`proximity_cooccurrence`**: Top-3 capitalized tokens (by frequency) within ±10-word window of the surface_form across all mention quotes. Stop words and self-references excluded. Sorted deterministically (frequency desc, then lexicographic). Padded with `""` if fewer than 3 found.
- **`avg_verb_distance`**: Mean token-index distance from first occurrence of surface_form to nearest verb in `STATIC_VERB_SET` per quote. `0.0` when no verb found in the quote.

### 7-Target Proximity Results

| Target | `proximity_cooccurrence` | `avg_verb_distance` |
|---|---|---|
| `Geralt` | `['Oreck', 'Mika', 'Luminaire']` | 1.319846 |
| `Giant` | `['Torhh', 'Senareth', 'Elyraen']` | 1.4 |
| `Keeper` | `['Spire', 'Graviton', 'Vale']` | 3.839695 |
| `Shadow` | `['Phoenix', 'Chapter', 'Fire']` | 3.117647 |

**Interpretation (documentation only — no classification applied):**
- `Geralt` avg_verb_distance = 1.32: subject-adjacent verb placement — consistent with active character.
- `Keeper` avg_verb_distance = 3.84: verbs are further away — consistent with referenced/mentioned entity rather than active subject.
- `Giant` cooccurrence `['Torhh', 'Senareth', 'Elyraen']`: appears in close proximity to named characters.

---

## Pipeline Output Stats (post-fix)

| File | Pre-fix | Post-fix |
|---|---|---|
| `raw/artifacts/batch_*.jsonl` | 50,283 artifacts (2 batches) | 48,214 artifacts (1 batch) |
| `raw/math/surface_form_stats.jsonl` | 8,275 forms, 5.5 MB | 7,984 forms, 5.6 MB |
| `raw/math/identity_signal_stats.jsonl` | 8,275 records, 6.9 MB | 7,984 records, 6.7 MB |

---

## Verification Checklist

- [x] artifact_extractor.py drops stop-word tokens (Always, Within → absent)
- [x] artifact_extractor.py drops unwhitelisted all-caps tokens (ACT, CHAPTER → absent)
- [x] artifact_extractor.py logs drop count + first 5 examples per chapter
- [x] pass2_math.py merges Giants → Giant (raw_variants=['Giant', 'Giants'], mentions=345)
- [x] pass2_math.py merges Keepers → Keeper (raw_variants=['Keeper', 'Keepers'], mentions=131)
- [x] pass2_math.py `raw_variants` array populated for all merged forms
- [x] identity_signal_math.py outputs `proximity_cooccurrence` for every record
- [x] identity_signal_math.py outputs `avg_verb_distance` for every record
- [x] All 7,984 records have both new fields
- [x] No semantic classification or canon promotion introduced
- [x] Byte-identical output on re-run with same inputs (deterministic sort + fixed timestamp)
- [x] `provisional: true`, `audit_only: true` preserved on all outputs
- [x] Atomic writes via temp + rename maintained

---

## Notes & Observations

1. **GPT filtering**: With 269 pre-fix mentions, `GPT` was a high-volume term. If it represents a canon entity in the corpus, add it to `CANON_ACRONYM_WHITELIST` in artifact_extractor.py.

2. **Possessive strip breadth**: The `(?i)` flag in `_POSSESSIVE_RE` makes the lookahead `[a-z]` case-insensitive, stripping before uppercase words too. This is the spec-literal behavior. If intended behavior is "lowercase-only lookahead," change to `re.compile(r"([a-zA-Z]+)'s(?=\s+[a-z])")` (drop `(?i)`).

3. **Student/Faction map entries**: `Students` → `Student` and `Factions` → `Faction` are in `PLURAL_SINGULAR_MAP` but no merges occurred because singular counterparts had zero mentions in this corpus. Map entries are live but idle.

4. **O(N) fix**: The original `compute_stats` O(S×N) inner loop was eliminated as a side-effect of Fix 2. Grouping is now fully O(N).

---

*Awaiting approval before TASK 6.3A provisional_identity_router.py.*
