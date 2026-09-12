# PHASE 6 — Result + What-If Swap

Build the strongest product moment.

Result screen:
- the composed look, laid out editorially from the user's own garment photos
- style match card, labelled as a heuristic
- item breakdown, each tracing to a wardrobe item the user owns
- rationale from the ranker
- save
- share
- swap
- regenerate

No price sum. No shop action. The product sells nothing — see `docs/DECISIONS.md`.

Swap:
- select a role slot
- show compatible alternatives **from this user's wardrobe**
- empty is a valid answer — name the gap and offer to add an item, never invent one
- choose replacement
- recompose that slot only
- animate the transition
- leave every unchanged item visually stable

UX target:
Changing one item must feel like changing a single parameter, not rebuilding the
experience.

Also handle:
- an item deleted out from under a saved outfit → outfit reports itself incomplete and
  offers a swap; never a broken image or a silent gap

Acceptance:
- swap path is obvious
- no full-page navigation for a simple swap
- visual state never disagrees with wardrobe state
- alternatives are always owned items, verified by ownership re-validation
- analytics fire for swap, regenerate, and save
