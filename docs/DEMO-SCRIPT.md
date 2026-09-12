# STYLELAB Demo Script

There is no demo wardrobe. The demo is **your own closet** — photograph 6-8 of your
garments once, keep them in a folder on the demo machine, and upload them live. That is
authentic, it needs no fabricated catalogue, and the interviewer watches real extraction
run on real clothes.

## Preparation (once, ~15 minutes)

- 6-8 garment photos: 2-3 tops, 2 bottoms, 1-2 footwear, 1 outerwear. Plain background,
  even light, one garment per frame.
- Keep one deliberately imperfect photo — dim or cropped. You will use it.
- Folder on the desktop, named, open before you start.
- **Verify the live path that morning.** There is no demo mode: a real `GROQ_API_KEY`
  must be set, both vision models must pass the boot availability check, and Groq must be
  up. Do one full rehearsal run end to end — not a mock.
- Check the trend corpus is within `TREND_MAX_AGE_DAYS`, or the Trend Scout is skipped.

## 30-second pitch

"STYLELAB reads a photo of your clothes and turns your actual closet into structured
data, then styles outfits only from what you own. The interesting engineering problem
isn't the styling — it's that a vision model produces guesses, and everything downstream
has to stay honest about which parts are measured, which are guessed, and which the user
corrected."

## 90-second walkthrough — the timing budget

| Window | Beat | Watch for |
|--------|------|-----------|
| 0-10s | Landing → Start my wardrobe | one tap, no signup |
| 10-25s | Select all 8 photos at once | single gesture, not 8 dialogs |
| 25-55s | Analysis runs in parallel; cards appear as each finishes | never one blocking spinner |
| 55-65s | Skim the cards. Land on the dim photo — it is flagged low-confidence | the hedge, not a confident wrong answer |
| 65-72s | Correct one field on purpose. "It called this black; it's navy." | correction is a feature, not an apology |
| 72-80s | Occasion + vibe, tap through the defaults | skippable |
| 80-90s | Compose → outfit with rationale | grounded in the items just uploaded |

Encore, after the 90 seconds: **What If? → swap the bottom.** One slot changes, the rest
stay still, no page navigation.

If analysis is slower than budget, cut to 5 photos. Do not cut the correction beat — it
is the most differentiated moment in the run.

## 120-second technical walkthrough

- ownership enforced in SQL before the prompt, re-validated after — not asked for in
  prompt text
- vision extraction → JSON Schema → Pydantic → business validation → ownership validation
- per-field confidence, and what the UI does below the confidence floor
- `corrected_fields` survives re-analysis
- the agent crew: seven roles, four sequential hops, per-agent stages in the progress UI
- every agent's output is untrusted — ownership validation runs on the merged response
  regardless of what the Critic approved
- trend notes carry source and date, or they are dropped rather than shown
- adapter boundary: `git grep -i groq` outside `adapters/` returns nothing
- async per-image jobs, partial-batch success
- the eval fixtures — especially cross-user isolation and injection-via-image

## The two moments to actually show

**Grounding.** Open the extraction audit for one item: what the model returned, what was
rejected, why. Then force the model to name an item the user doesn't own and show the
app refusing it. This is worth more than any feature in the build.

**Insufficient wardrobe.** Delete the only footwear and compose again. The app says what
is missing instead of inventing a shoe. Interviewers remember the system that declines.

## Claims discipline

Say:
- "portfolio concept"
- "measured in our demo environment"
- "hypothesis to validate"
- "the model guessed this; the user corrected it"

Do not say:
- retailer integration or affiliation of any kind
- real user or customer numbers
- that material or fibre content is known rather than estimated
- that this measures body shape or fit

The product sells nothing and links to no merchant. If a question heads toward commerce,
say it was deliberately scoped out and why.
