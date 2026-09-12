# User Flows — STYLELAB

There is no demo wardrobe. Every user, including a recruiter seeing the product for the
first time, starts by uploading their own clothes. Flow 1 is therefore the critical path
and the thing to optimise hardest — see `docs/DEMO-SCRIPT.md` for the timing budget.

## Flow 1 — First run (also the recruiter path)

```text
Landing
  ↓
Start my wardrobe
  ↓
Upload 3-6 garment photos        ← multi-select, one gesture
  ↓
Per-image validation
  ├─ invalid → inline retry guidance, other images keep processing
  └─ valid
  ↓
Analysis (async, parallel, progressive)
  ↓
Review extracted metadata        ← corrections here, not buried in settings
  ↓
Occasion + vibe                  ← two taps, skippable with defaults
  ↓
Compose
  ↓
Outfit result
  ├─ Swap
  ├─ Regenerate
  ├─ Edit
  └─ Save
```

Design constraints on this flow, in priority order:

1. **Cards appear as each image finishes.** Never one blocking spinner over the batch.
2. **The wardrobe is usable at three items.** Do not gate composition behind a minimum
   that a first-time user will not reach.
3. **Occasion and vibe have working defaults.** A user who taps straight through still
   reaches an outfit.
4. **A failed extraction costs one card, not the run.** Partial success is success.

## Flow 2 — Returning user

```text
Landing
  ↓
My wardrobe
  ↓
Add items  ·  Browse  ·  Edit  ·  Archive
  ↓
Compose
  ↓
Result → Swap / Regenerate / Save
```

## Flow 3 — Swap

```text
Result
  ↓
What If?
  ↓
choose slot
  ↓
compatible alternatives from the user's own wardrobe
  ├─ none available → name the gap, offer to add an item
  └─ alternatives shown
  ↓
select item
  ↓
recompose that slot only
  ↓
updated result
  ↓
compare / save
```

One swap changes one slot. The other items stay visually stable — no page navigation,
no full rebuild.

## Flow 4 — Extraction correction

```text
Item card
  ↓
low-confidence field flagged
  ↓
user corrects value
  ↓
persisted to corrected_fields
  ↓
affected outfits recomposed
```

A corrected field is never overwritten by later re-analysis.

## Flow 5 — Insufficient wardrobe

```text
Compose
  ↓
required role unfilled
  ↓
"You have no footwear yet — add a pair and I'll finish this look."
  ↓
Add item  →  back to Compose with state preserved
```

Never invent the missing garment. Never return a partial outfit as if it were complete.

## Flow 6 — Failure

```text
Compose
  ↓
provider failure
  ↓
friendly explanation + what was preserved
  ↓
Retry  or  deterministic ranking of the same wardrobe
```

Never strand the user on a dead end.

## Flow 7 — Delete

```text
Wardrobe / Privacy
  ↓
Delete item or photo
  ↓
confirmation naming what else is affected
  ↓
remove source asset
  ↓
outfits referencing it → marked incomplete, swap offered
  ↓
confirmation state
```

## Flow 8 — 7-day planner *(P1, cuttable)*

```text
Wardrobe
  ↓
Generate week
  ↓
7 cards, no garment repeated on consecutive days
  ↓
open day → view / swap / save
```

Feasible only with a wardrobe large enough to vary. State that honestly when it is not.
