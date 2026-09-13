import { z } from "zod";
import { apiClient } from "../api-client";
import { alternativesSchema, outfitSchema } from "../schemas/outfit";
import { jobStatusSchema, type GarmentCategory } from "../schemas/wardrobe";

/**
 * Outfit API surface, matching docs/API-SPEC.md.
 *
 * As with the wardrobe calls: no user id is ever sent, and no endpoint accepts the item ids
 * to style with. Identity is the signed session token `apiClient` attaches, and candidates
 * are retrieved server-side from the caller's own wardrobe.
 */

export interface ComposeRequest {
  occasion: string;
  vibe?: string;
  fitPreference?: string;
  colorPreferences?: readonly string[];
}

/**
 * Start a composition. Returns a job, not a look.
 *
 * Async because the server calls a provider, and because the crew that replaces today's
 * single call in S8b will take longer. A client written against a blocking version of this
 * would have to be rewritten then.
 */
export function composeOutfit(request: ComposeRequest, signal?: AbortSignal) {
  return apiClient.post(
    "/outfits/compose",
    jobStatusSchema,
    {
      occasion: request.occasion,
      vibe: request.vibe,
      fit_preference: request.fitPreference,
      color_preferences: request.colorPreferences ?? [],
    },
    { signal },
  );
}

export function getOutfit(outfitId: string, signal?: AbortSignal) {
  return apiClient.get(`/outfits/${encodeURIComponent(outfitId)}`, outfitSchema, { signal });
}

/**
 * What else the user owns that could fill one slot.
 *
 * An empty list is a valid answer and arrives with a named gap rather than an error — a
 * wardrobe with one pair of shoes is small, not broken (USER-FLOWS Flow 3).
 */
export function getAlternatives(outfitId: string, role: GarmentCategory, signal?: AbortSignal) {
  return apiClient.get(
    `/outfits/${encodeURIComponent(outfitId)}/alternatives?role=${encodeURIComponent(role)}`,
    alternativesSchema,
    { signal },
  );
}

/**
 * Change one slot, keep the rest.
 *
 * Returns the whole updated look rather than a patch, so the screen renders from one payload
 * the server assembled. A client that merged a partial response into its own copy is a
 * client that can show a look the wardrobe does not agree with.
 */
export function swapSlot(outfitId: string, role: GarmentCategory, replacementItemId: string) {
  return apiClient.post(`/outfits/${encodeURIComponent(outfitId)}/swap`, outfitSchema, {
    role,
    replacement_item_id: replacementItemId,
  });
}

/** Keep a look. Idempotent server-side, so a double tap is not a double row. */
export function saveOutfit(outfitId: string) {
  return apiClient.post(
    `/outfits/${encodeURIComponent(outfitId)}/save`,
    z.object({ outfit_id: z.string(), saved: z.boolean() }),
  );
}
