import { z } from "zod";

/**
 * Wire schemas. These mirror docs/DATA-MODEL.md and docs/API-SPEC.md.
 *
 * Note what is absent and must stay absent: brand, price, commerce_url, active. The product
 * sells nothing (docs/DECISIONS.md, 2026-09-12). If one of those reappears here, commerce
 * has crept back in through the type layer.
 *
 * Outfits, slots, alternatives and trend notes live in `schemas/outfit.ts` as of S7, when
 * they stopped being a guess about a future payload and became a contract with a live one.
 */

export const garmentCategory = z.enum(["top", "bottom", "footwear", "outerwear", "accessory"]);
export type GarmentCategory = z.infer<typeof garmentCategory>;

export const formality = z.enum(["casual", "smart-casual", "formal"]);

export const itemStatus = z.enum(["analyzing", "ready", "failed", "archived"]);

export const wardrobeItemSchema = z.object({
  item_id: z.string(),
  status: itemStatus,
  category: garmentCategory.nullable(),
  subcategory: z.string().nullable(),
  color_primary: z.string().nullable(),
  color_secondary: z.string().nullable(),
  pattern: z.string().nullable(),
  /** Named a guess in the wire format because it must read as one on screen. */
  material_guess: z.string().nullable(),
  fit: z.string().nullable(),
  formality: formality.nullable(),
  season_tags: z.array(z.string()).default([]),
  occasion_tags: z.array(z.string()).default([]),
  style_tags: z.array(z.string()).default([]),
  field_confidence: z.record(z.string(), z.number().min(0).max(1)).default({}),
  corrected_fields: z.array(z.string()).default([]),
  quality_warnings: z.array(z.string()).default([]),
  image_url: z.string(),
});
export type WardrobeItem = z.infer<typeof wardrobeItemSchema>;

export const uploadResultSchema = z.object({
  items: z.array(
    z.object({
      item_id: z.string().nullable(),
      asset_id: z.string().nullable(),
      job_id: z.string().nullable(),
      status: z.enum(["analyzing", "rejected"]),
      error: z.object({ code: z.string(), message: z.string() }).optional(),
    }),
  ),
});

export const jobStatusSchema = z.object({
  job_id: z.string(),
  type: z.enum(["analyze_item", "compose_outfit"]),
  status: z.enum(["queued", "processing", "completed", "failed"]),
  /**
   * Named work, straight from the API. Rendered verbatim rather than mapped to local copy:
   * the server knows which step it is actually on, and a client-side guess at the stage is
   * a spinner with a caption.
   */
  stage: z.string().nullable(),
  progress: z.number().min(0).max(1).nullable(),
  /**
   * What the job produced: an item id for an extraction, an outfit id for a composition.
   * Null until it finishes, and null on a composition that named a gap instead — there is
   * no row to point at, and `result` carries the answer in that case.
   */
  result_id: z.string().nullable().default(null),
  /** A terminal payload for a job whose answer is not a row. See `schemas/outfit.ts`. */
  result: z.unknown().optional(),
  /**
   * Present on failure. Carried so a card can say what went wrong and whether retrying is
   * worth the user's time — the message was already written honestly server-side, and
   * inventing a second one here would be worse copy about a failure we know less about.
   */
  error: z
    .object({
      code: z.string(),
      message: z.string().nullable(),
      retryable: z.boolean().default(false),
    })
    .optional(),
});

/**
 * Fields that read as a guess whatever the confidence score says.
 *
 * The floor decides the hedge for everything else: a model confident about a colour has
 * usually seen the colour. Fibre content is different in kind — a photograph does not show
 * what a garment is made of, so a high score there is confidence about an inference rather
 * than about an observation.
 *
 * S8's eval harness found the product presenting one as fact: an extraction asserting
 * "100% merino wool" at 0.99 cleared the floor and rendered with no hedge, which is exactly
 * the Fail clause of AI-EVAL-CASES Case 08 and the rule CLAUDE.md states outright.
 *
 * Mirrors `ALWAYS_A_GUESS` in `apps/api/app/domain/corrections.py`, the same way the upload
 * limits mirror the API's.
 */
export const ALWAYS_A_GUESS: readonly string[] = ["material_guess"];

/** True when a field should be presented as a hedge rather than a fact. */
export function isHedged(item: WardrobeItem, field: string, floor: number): boolean {
  if (item.corrected_fields.includes(field)) return false; // the user settled it
  if (ALWAYS_A_GUESS.includes(field)) return true; // no score settles this one
  const score = item.field_confidence[field];
  return score === undefined || score < floor;
}

/**
 * One garment, in words: colour, pattern, cut. Never material, never fit on a body, never
 * the wearer — there is no field here that could describe any of them.
 *
 * ## Why the humanising step
 *
 * S11 found `white solid_color sneaker` rendered on the result screen. `pattern`,
 * `subcategory`, `color_primary` and `fit` are genuinely open sets in the world, so they
 * cannot be a closed vocabulary the way `style_tags` became in S8 (blocker B18) — which
 * means whatever the model writes reaches the screen. It usually writes English. Sometimes
 * it writes an identifier, because it has read a great many JSON schemas.
 *
 * Normalising here rather than at extraction is deliberate. The stored value is what the
 * model actually said, which is what the audit trail is for; this is presentation, and
 * presentation is where a machine-shaped word should stop being one.
 *
 * ## Why one function
 *
 * There were three copies of this expression — the look slot, the wardrobe card's alt text
 * and the outfit page — built from the same fields in the same order, and all three had the
 * same underscore. Three copies of a rule is three chances to fix it once.
 */
export function describeGarment(item: {
  color_primary?: string | null;
  pattern?: string | null;
  subcategory?: string | null;
  category?: string | null;
}): string {
  const parts = [item.color_primary, item.pattern, item.subcategory ?? item.category];
  return parts.filter(Boolean).map(humanise).join(" ");
}

/** `solid_color` → `solid color`. Identifiers are for programs; this string is for a person. */
function humanise(value: string | null | undefined): string {
  return String(value).replace(/[_-]+/g, " ").trim();
}
