# MrLore 6.4B — Noise Removal Delta Report

**Generated:** 2026-05-18  
**Status:** EXIT 0 — all fixes applied, syntax clean, full pipeline re-run complete  
**Tool patched:** tools/artifact_extractor.py  
**Validation dataset:** validation/noise_samples.jsonl (10 samples), validation/target_7_query.jsonl (7 targets)

---

## Summary

| Metric | Pre-patch | Post-patch | Delta |
|---|---|---|---|
| Total artifacts | 48,214 | 46,693 | −1,521 (−3.2%) |
| Unique surface_forms (pass2) | 7,984 | 7,825 | −159 (−2.0%) |
| Review queue records | 417 | 403 | −14 (−3.4%) |
| `bounded_actor_candidate` in queue | 68 | 68 | 0 |
| `identity_braid_candidate` in queue | 45 | 42 | −3 |
| `ambiguous_review_candidate` in queue | 304 | 293 | −11 |
| Total drop/normalize events (all filters) | — | 52,231 | — |

---

## Fixes Applied

### Fix 1: Leading Conjunction/Preposition Strip

**Constant added:** `_CONJUNCTION_PREFIX_RE`

```
^(?:and|but|or|yet|so|for|nor|however|nevertheless|meanwhile|therefore|
   among|behind|beside|beyond|close|across|along|almost|alone)\s+
```

**Behavior:** Applied to multi-word capitalized tokens before stop-word evaluation.
If the stripped remainder is a single word, it is re-evaluated against STOP_WORD_SET and the all-caps filter.
If remainder length < 2 chars after strip, the record is dropped.

**Corpus examples normalized (sample from log):**

| Original surface_form | Normalized to | Reason |
|---|---|---|
| `But Lyaris` | `Lyaris` | conjunction_prefix_stripped |
| `But Vale` | `Vale` | conjunction_prefix_stripped |
| `But Sera` | `Sera` | conjunction_prefix_stripped |
| `Behind Senareth` | `Senareth` | conjunction_prefix_stripped |
| `But Torhh` | `Torhh` | conjunction_prefix_stripped |
| `And Neferati` | `Neferati` | conjunction_prefix_stripped |
| `And Vale` | `Vale` | conjunction_prefix_stripped |
| `And Brak` | `Brak` | conjunction_prefix_stripped |
| `But Earth` | `Earth` | conjunction_prefix_stripped |
| `But Zephyr` | `Zephyr` | conjunction_prefix_stripped |

**Impact:** 273 pre-patch artifacts normalized to stripped surface_forms (artifact count unchanged for these — kept with corrected key). ~130 artifacts dropped (stripped remainder < 2 chars, e.g. `And I` → `I`).

---

### Fix 2: Expanded STOP_WORD_SET

**New entries added to `STOP_WORD_SET`:**

| Category | New entries |
|---|---|
| Prepositions (single-word safety) | `among`, `behind`, `beside`, `beyond`, `close` |
| Contractions | `ain't`, `isn't`, `aren't`, `wasn't`, `weren't` |
| Subject contractions | `i'm`, `you're`, `he's`, `she's`, `it's`, `we're`, `they're`, `let's` |
| Negative contractions | `don't`, `doesn't`, `didn't`, `haven't`, `hasn't`, `hadn't` |
| Modal negatives | `wouldn't`, `couldn't`, `shouldn't` |
| Perfect modals | `might've`, `could've`, `should've`, `would've` |

**Corpus examples dropped (most frequent by form):**

| surface_form | Pre-patch occurrences | Disposition |
|---|---|---|
| `They're` | high-volume | dropped (stop_word) |
| `It's` | high-volume | dropped (stop_word) |
| `Couldn't` | recurring | dropped (stop_word) |
| `Behind` | recurring | dropped (stop_word) |
| `Beyond` | recurring | dropped (stop_word) |
| `Among` | recurring | dropped (stop_word) |
| `Close` | recurring | dropped (stop_word) |
| `Beside` | recurring | dropped (stop_word) |

**Apostrophe handling:** `_CURLY_APOS_RE` normalizes `'`, `'`, `` ` `` → `'` before STOP_WORD_SET lookup. Ensures `"Ain't"` (curly apostrophe, common in ebook corpus) is caught by the `"ain't"` entry.

**Impact (simulation against pre-patch batch):** 1,375 artifact records affected by new stop-word entries.

---

### Fix 3: Punctuation & Whitespace Normalization

**Constants added:** `_TRAILING_PUNCT_RE = re.compile(r'[.,;:!?)"\']+$')`, `_MULTI_SPACE_RE = re.compile(r'  +')`

**Behavior:** Applied to all tokens (multi-word and single-word) before Fix 1 and Fix 2.
Strips trailing punctuation characters. Collapses multiple internal spaces to one.
Records with length < 2 after normalization are dropped with reason `insufficient_length_after_trim`.

**Impact:** Minimal on this corpus (existing regexes already exclude most punctuation via `[A-Za-z''\\-]*` character class and `\\b` boundaries). Acts as a correctness safety net.

---

### Fix 4: Audit Logging

**Change:** `drop_log` tuple format extended from `(original_form, reason)` to `(original_form, normalized_form_or_None, reason)`.

- `normalized_form` is the stripped form for `conjunction_prefix_stripped` events.
- `normalized_form` is `None` for pure drops (stop_word, all_caps_unwhitelisted, insufficient_length_after_trim).

**Chapter print output example:**
```
  [filter] dropped/normalized 38 token(s)
    L   5  'They're'                       (stop_word)
    L  12  'But Lyaris'                    (conjunction_prefix_stripped → 'Lyaris')
    L  19  'Couldn't'                      (stop_word)
    L  23  'And I'm'                       (conjunction_prefix_stripped → 'I'm')
    L  23  "I'm"                           (stop_word)
    ... and 33 more
```

---

## Noise Sample Validation Results

**Input:** `validation/noise_samples.jsonl` (10 samples)

| Input | Expected | Result | Status |
|---|---|---|---|
| `And Geralt` | normalize → `Geralt` | extracted as `Geralt` | ✓ PASS |
| `But Vale` | normalize → `Vale` | extracted as `Vale` | ✓ PASS |
| `But Sera` | normalize → `Sera` | extracted as `Sera` | ✓ PASS |
| `Among` | drop (stop_word) | dropped | ✓ PASS |
| `Behind` | drop (stop_word) | dropped | ✓ PASS |
| `Beside` | drop (stop_word) | dropped | ✓ PASS |
| `Beyond` | drop (stop_word) | dropped | ✓ PASS |
| `Close` | drop (stop_word) | dropped | ✓ PASS |
| `Ain't` | drop (stop_word) | dropped | ✓ PASS |
| `And I'm` | drop (conjunction then stop_word) | dropped | ✓ PASS |

**All 10 samples: PASS.**

---

## 7-Target Bounded Actor Verification

**Input:** `validation/target_7_query.jsonl` verified against post-patch routing.

| Surface Form | Route (post-patch) | Mentions | Chapters | speech | action | Status |
|---|---|---|---|---|---|---|
| `Geralt` | `bounded_actor_candidate` | 1,585 | 37 | 0.074 | 0.076 | ✓ No regression |
| `Vale` | `bounded_actor_candidate` | 1,400 | 31 | 0.063 | 0.141 | ✓ No regression |
| `Sera` | `bounded_actor_candidate` | 325 | 20 | 0.080 | 0.138 | ✓ No regression |
| `Blue Mika` | `bounded_actor_candidate` | 47 | 8 | 0.128 | 0.064 | ✓ No regression |
| `Anu` | `bounded_actor_candidate` | 22 | 5 | 0.136 | 0.091 | ✓ No regression |
| `Celly` | `bounded_actor_candidate` | 15 | 3 | 0.133 | 0.067 | ✓ No regression |
| `Lyaris` | `sparse_reference_candidate` | 16 | 2 | 0.125 | 0.000 | ¹ |

> ¹ `Lyaris`: routes to `sparse_reference_candidate` (chapters=2 ≤ 2, mentions=16 ≤ 20, action_ratio=0.0 — cannot satisfy `bounded_actor_candidate` threshold of action_ratio ≥ 0.05). This is data-limited, not a patch regression. `Lyaris` is present in the output and absorbs all former `But Lyaris` mentions. The `sparse_reference_candidate` route correctly reflects the character's sparse, low-action corpus presence. Review queue does not include `sparse_reference_candidate` — flagged for manual triage if desired.

**Noisy forms absent from new batch:** `But Lyaris`, `But Vale`, `But Sera`, `Behind Senareth`, `Among`, `Behind`, `Beside`, `Beyond`, `Close`, `Ain't`, `They're`, `It's`, `Couldn't`, `And Geralt`, `And I'm` — all confirmed ABSENT. ✓

---

## Full Pipeline Re-run Summary

| Stage | Tool | Output | Records |
|---|---|---|---|
| Pass 1 | artifact_extractor.py | batch_20260518_062318.jsonl | 46,693 artifacts |
| Pass 2 | pass2_math.py | surface_form_stats.jsonl | 7,825 surface_forms |
| Pass 3A | identity_signal_math.py | identity_signal_stats.jsonl | 7,825 records |
| Pass 3B | provisional_identity_router.py | provisional_identity_routes.jsonl | 7,825 records |
| Pass 3C | identity_review_queue.py | identity_review_queue.jsonl | 403 records |

**Review queue bucket distribution (post-patch):**

| Bucket | Count | vs. pre-patch |
|---|---|---|
| `ambiguous_review_candidate` | 293 | −11 |
| `bounded_actor_candidate` | 68 | 0 |
| `identity_braid_candidate` | 42 | −3 |
| **Total** | **403** | **−14** |

---

## Determinism

- `_CONJUNCTION_PREFIX_RE`, `_TRAILING_PUNCT_RE`, `_MULTI_SPACE_RE`: compile-time constants.
- `_CURLY_APOS_RE`: compile-time constant; no runtime state.
- Normalization order: Fix 3 (trim) → Fix 1 (conjunction strip) → Fix 2 (stop-word) → existing all-caps filter.
- All operations are pure string functions. Re-run on same inputs produces byte-identical output. ✓

---

## Notes

1. **`total_dropped=52,231` in extractor log** includes all filter events across all passes (pre-existing stop_word, all_caps_unwhitelisted, plus new Fix 4B categories). This is not the net artifact delta — it is the cumulative count of every token rejected per occurrence, across all 139 chapters.

2. **`Lyaris` routing**: `sparse_reference_candidate` is the correct route given 2-chapter, 0-action-signal presence. No stop-word or conjunction fix affected Lyaris directly. Former `But Lyaris` occurrences now consolidate under `Lyaris`, giving 16 total mentions. Does not qualify for `bounded_actor_candidate` without action evidence.

3. **Review queue reduction −14**: Mostly from `ambiguous_review_candidate` (−11) and `identity_braid_candidate` (−3). The conjunction-strip normalizations improve clustering — forms that were ambiguous as `But X` now correctly merge into `X`.

---

*Halted. Awaiting approval before resuming TASK 6.4A human review.*
