import { z } from "zod";
import { garmentCategory, wardrobeItemSchema } from "./wardrobe";

/**
 * Outfit wire schemas, mirroring `docs/API-SPEC.md` and `app/routers/serialization.py`.
 *
 * These replaced a speculative `outfitAdviceSchema` that had been written in S2 against the
 * crew-shaped payload in the spec — `critique`, `combinations`, model-authored
 * `alternatives`. None of it existed on the wire, so the schema validated nothing and would
 * have failed the moment the real endpoint answered. What is here matches what the API
 * actually sends today; the crew's extra fields arrive with the crew in S8b, and adding them
 * before then would only recreate a contract nobody honours.
 *
 * Note what is absent and must stay absent: price, brand, merchant, any total. The product
 * sells nothing (docs/DECISIONS.md, 2026-09-12), and there is no price sum on a result
 * screen for the same reason there is no shop button.
 */

/** Trend claims without a source and a date are dropped server-side; enforced here too. */
export const trendNoteSchema = z.object({
  trend: z.string(),
  source: z.string().min(1),
  published_at: z.string(),
  applies_to_items: z.array(z.string()).default([]),
});

export const wardrobeGapSchema = z.object({
  category: garmentCategory,
  generic_description: z.string(),
  unlocks_outfits: z.number().int().nonnegative().optional(),
});

/**
 * One role in the look. `item` is null when the garment was deleted after composing — the
 * slot keeps its place so the screen can say which piece went missing and offer a swap for
 * that role (docs/AI-EVAL-CASES.md Case 14).
 */
export const outfitSlotSchema = z.object({
  role: garmentCategory,
  item_id: z.string(),
  item: wardrobeItemSchema.nullable(),
});

export const outfitSchema = z.object({
  outfit_id: z.string(),
  name: z.string(),
  occasion: z.string(),
  /** Style Match. A UX heuristic, labelled as one wherever it is rendered. */
  match_score: z.number().int().min(0).max(100),
  status: z.enum(["ready", "incomplete"]),
  /** 1 = full crew, 5 = honest gap statement. Disclosed, never hidden. */
  degradation_level: z.number().int().min(1).max(5),
  rationale: z.array(z.string()).default([]),
  saved: z.boolean().default(false),
  missing_roles: z.array(garmentCategory).default([]),
  slots: z.array(outfitSlotSchema).default([]),
  confidence: z.number().min(0).max(1).nullable().default(null),
  pro_tips: z.array(z.object({ tip: z.string(), type: z.string() })).default([]),
  budget_tricks: z.array(z.string()).default([]),
  wardrobe_gaps: z.array(wardrobeGapSchema).default([]),
  trend_notes: z.array(trendNoteSchema).default([]),
});
export type Outfit = z.infer<typeof outfitSchema>;
export type OutfitSlot = z.infer<typeof outfitSlotSchema>;

export const alternativesSchema = z.object({
  role: garmentCategory,
  current_item_id: z.string().nullable(),
  alternatives: z
    .array(
      z.object({
        item: wardrobeItemSchema,
        /** What the *look* would score with this garment in, not what it scores alone. */
        match_score: z.number().int().min(0).max(100),
        delta: z.number().int(),
      }),
    )
    .default([]),
  /** Present only when there are no alternatives. An empty wardrobe slot is not an error. */
  gap: wardrobeGapSchema.nullable().default(null),
});
export type Alternatives = z.infer<typeof alternativesSchema>;
export type Alternative = Alternatives["alternatives"][number];

/**
 * What a finished `compose_outfit` job carries when the wardrobe could not fill a role.
 * There is no outfit to fetch, so the gap arrives inline on the job.
 */
export const compositionGapSchema = z.object({
  missing_roles: z.array(garmentCategory).default([]),
  wardrobe_gaps: z.array(wardrobeGapSchema).default([]),
  rationale: z.array(z.string()).default([]),
  degradation_level: z.number().int().min(1).max(5).default(5),
});
export type CompositionGap = z.infer<typeof compositionGapSchema>;
