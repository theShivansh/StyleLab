# Sample garment photographs

Test fixtures. **Not** a seed catalogue and not a demo wardrobe — `CLAUDE.md` and
`docs/DECISIONS.md` (wardrobe pivot, 2026-09-12) are explicit that no garment assets ship
with the product and the wardrobe is always user-uploaded.

These exist for one test: `tests/live/test_real_inference.py` needs a real photograph to ask
a real vision model about. A synthetic 1x1 pixel would only prove the model can describe a
grey square, so when this directory is empty that test **skips** rather than inventing an
image.

## What to put here

Two or three ordinary photographs of single garments — a shirt, a trouser, a shoe — taken the
way a user would take them. Plain background not required; the point is realism.

Anything here is committed and public, so photograph your own clothes rather than lifting a
product shot.

## Not used by

`apps/api/tests/` and `tests/ai/`, which use recorded provider responses
(`tests/ai/fixtures/groq/`) and never send an image anywhere. That is why the whole suite
runs with no key, no network and no cost.
