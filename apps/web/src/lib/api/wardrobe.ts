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
 * These are the only calls the wardrobe screens make. The endpoints themselves land in S6
 * (prompts/05-VTO.md) — until then these 404 and the UI shows its error states, which is
 * why those states are built in this phase rather than bolted on later.
 *
 * Note what is NOT here: no endpoint accepts client-supplied item ids for composition.
 * Candidates are retrieved server-side from the caller's wardrobe, because accepting ids
 * from the request body would move the ownership boundary into the client's hands.
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
  return apiClient.get(
    `/wardrobe/items/${encodeURIComponent(itemId)}`,
    wardrobeItemSchema,
    { signal },
  );
}

export function listWardrobeItems(signal?: AbortSignal) {
  return apiClient.get(
    "/wardrobe/items",
    z.object({ items: z.array(wardrobeItemSchema) }),
    { signal },
  );
}

/** A correction. Every field named here becomes protected from later re-analysis. */
export function correctWardrobeItem(itemId: string, patch: Record<string, string>) {
  return apiClient.patch(
    `/wardrobe/items/${encodeURIComponent(itemId)}`,
    wardrobeItemSchema,
    patch,
  );
}

export function deleteWardrobeItem(itemId: string) {
  return apiClient.delete(
    `/wardrobe/items/${encodeURIComponent(itemId)}`,
    z.object({ deleted: z.boolean(), affected_outfits: z.array(z.string()).default([]) }),
  );
}
