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
      error: z
        .object({ code: z.string(), message: z.string() })
        .optional(),
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

/** True when a field should be presented as a hedge rather than a fact. */
export function isHedged(item: WardrobeItem, field: string, floor: number): boolean {
  if (item.corrected_fields.includes(field)) return false; // the user settled it
  const score = item.field_confidence[field];
  return score === undefined || score < floor;
}
