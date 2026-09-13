import { z } from "zod";
import { apiClient } from "../api-client";
import {
  jobStatusSchema,
  uploadResultSchema,
  wardrobeItemSchema,
  type GarmentCategory,
} from "../schemas/wardrobe";

/**
 * Wardrobe API surface, matching docs/API-SPEC.md.
 *
 * These are the only calls the wardrobe screens make. Live as of S6.
 *
 * Note what is NOT here: no endpoint accepts client-supplied item ids for composition.
 * Candidates are retrieved server-side from the caller's wardrobe, because accepting ids
 * from the request body would move the ownership boundary into the client's hands.
 *
 * Nothing here passes a user id either, for the same reason. Identity is the signed session
 * token `apiClient` attaches — see `lib/session.ts`.
 */

export interface PickedFile {
  file: File;
  categoryHint: GarmentCategory | null;
}

export function uploadWardrobeImages(picked: readonly PickedFile[], signal?: AbortSignal) {
  const body = new FormData();
  for (const { file, categoryHint } of picked) {
    body.append("images[]", file);
    // Sent positionally alongside each file; the API treats it as a prior, not a decision.
    body.append("category_hints[]", categoryHint ?? "");
  }

  return apiClient.post("/wardrobe/items", uploadResultSchema, body, { signal });
}

export function getJob(jobId: string, signal?: AbortSignal) {
  return apiClient.get(`/jobs/${encodeURIComponent(jobId)}`, jobStatusSchema, { signal });
}

export function getWardrobeItem(itemId: string, signal?: AbortSignal) {
  return apiClient.get(`/wardrobe/items/${encodeURIComponent(itemId)}`, wardrobeItemSchema, {
    signal,
  });
}

export function listWardrobeItems(signal?: AbortSignal) {
  return apiClient.get("/wardrobe/items", z.object({ items: z.array(wardrobeItemSchema) }), {
    signal,
  });
}

/** A correction. Every field named here becomes protected from later re-analysis. */
export function correctWardrobeItem(itemId: string, patch: Record<string, string>) {
  return apiClient.patch(
    `/wardrobe/items/${encodeURIComponent(itemId)}`,
    wardrobeItemSchema,
    patch,
  );
}

/**
 * Re-run extraction on one garment.
 *
 * The per-image retry the upload queue offers, and the one behind "read it again" on a card
 * that failed. Returns a job, not a result: a retry that blocked would be a worse version of
 * the thing the async pipeline exists to avoid.
 *
 * Fields the user has corrected are preserved server-side (docs/AI-EVAL-CASES.md Case 13) —
 * the client does not have to protect them and must not try.
 */
export function reanalyzeWardrobeItem(itemId: string) {
  return apiClient.post(
    `/wardrobe/items/${encodeURIComponent(itemId)}/reanalyze`,
    z.object({ item_id: z.string(), job_id: z.string(), status: z.string() }),
  );
}

/**
 * Soft-delete a garment, and learn what else it broke.
 *
 * `affected_outfits` is why this returns a body. A garment can be in a saved look, and
 * deleting it without saying so leaves the user to find the hole themselves.
 */
/**
 * Remove every garment in one request.
 *
 * docs/SECURITY-PRIVACY.md: *"A user must be able to remove their entire wardrobe in one
 * action."* Built in S11 — until then the right existed only as a sentence in a spec and a
 * claim on the landing page.
 *
 * `images_erased_after_days` comes back because the deletion is soft, and a response that
 * said only `deleted: true` would invite the reading that the photographs are already gone.
 */
export function deleteWardrobe() {
  return apiClient.delete(
    "/wardrobe/items",
    z.object({
      deleted: z.boolean(),
      items: z.number(),
      assets: z.number(),
      affected_outfits: z.number(),
      images_erased_after_days: z.number(),
    }),
  );
}

export function deleteWardrobeItem(itemId: string) {
  return apiClient.delete(
    `/wardrobe/items/${encodeURIComponent(itemId)}`,
    z.object({ deleted: z.boolean(), affected_outfits: z.array(z.string()).default([]) }),
  );
}
