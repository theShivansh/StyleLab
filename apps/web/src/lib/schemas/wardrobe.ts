import { z } from "zod";

/**
 * Wire schemas. These mirror docs/DATA-MODEL.md and docs/API-SPEC.md.
 *
 * Note what is absent and must stay absent: brand, price, commerce_url, active. The product
 * sells nothing (docs/DECISIONS.md, 2026-09-12). If one of those reappears here, commerce
 * has crept back in through the type layer.
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

/** Trend notes without source and date are dropped server-side; the schema enforces it here too. */
export const trendNoteSchema = z.object({
  trend: z.string(),
  source: z.string().min(1),
  published_at: z.string(),
  applies_to_items: z.array(z.string()).default([]),
});

export const outfitAdviceSchema = z.object({
  outfit: z
    .object({
      item_ids: z.array(z.string()),
      name: z.string(),
      occasion: z.string(),
      match_score: z.number().min(0).max(100),
    })
    .nullable(),
  rationale: z.array(z.string()).default([]),
  confidence: z.number().min(0).max(1).nullable().default(null),
  critique: z
    .object({
      considered: z.array(z.string()).default([]),
      tradeoffs: z.array(z.string()).default([]),
    })
    .nullable()
    .default(null),
  pro_tips: z
    .array(z.object({ tip: z.string(), type: z.enum(["styling", "proportion", "care"]) }))
    .default([]),
  alternatives: z
    .array(z.object({ swap_role: garmentCategory, item_id: z.string(), why: z.string() }))
    .default([]),
  combinations: z
    .array(z.object({ item_ids: z.array(z.string()), occasion: z.string(), name: z.string() }))
    .default([]),
  budget_tricks: z
    .array(z.object({ trick: z.string(), unlocks_outfits: z.number().int().nonnegative() }))
    .default([]),
  wardrobe_gaps: z
    .array(
      z.object({
        category: garmentCategory,
        generic_description: z.string(),
        unlocks_outfits: z.number().int().nonnegative(),
      }),
    )
    .default([]),
  trend_notes: z.array(trendNoteSchema).default([]),
  /** 1 = full crew, 5 = honest gap statement. docs/AGENT-SYSTEM.md. */
  degradation_level: z.number().int().min(1).max(5).default(1),
  missing_roles: z.array(garmentCategory).default([]),
});
export type OutfitAdvice = z.infer<typeof outfitAdviceSchema>;

/** True when a field should be presented as a hedge rather than a fact. */
export function isHedged(item: WardrobeItem, field: string, floor: number): boolean {
  if (item.corrected_fields.includes(field)) return false; // the user settled it
  const score = item.field_confidence[field];
  return score === undefined || score < floor;
}
