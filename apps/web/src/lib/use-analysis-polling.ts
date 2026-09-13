"use client";

import { useEffect, useRef } from "react";
import { pollAnalysis } from "./analysis-poll";
import { track } from "./analytics";
import { getJob, getWardrobeItem } from "./api/wardrobe";
import { config } from "./config";
import type { WardrobeItem } from "./schemas/wardrobe";
import { useWardrobe } from "./wardrobe-store";

/**
 * Turns analysing uploads into garment cards.
 *
 * Each upload is polled on its own schedule and resolves on its own, which is what makes the
 * cards appear progressively rather than all at once behind a single batch spinner. One
 * photo's failure marks one card.
 *
 * What to do with each answer lives in `analysis-poll.ts`, as a pure function with its own
 * tests. It moved there after the first live deployment, where this hook's rule — any error
 * ends the card — turned a poll that reached a different API instance into "That item isn't in
 * your wardrobe" for a garment that was being read correctly.
 *
 * ## Why the controllers are per job
 *
 * The first version shared one AbortController across every poller started in an effect run,
 * and aborted it in the effect's cleanup. Because `uploads` is a dependency and every
 * `updateUpload` mutates it, the effect re-ran each time a photo resolved — and the cleanup
 * aborted all the *other* in-flight pollers. With the started-jobs guard preventing a
 * restart, a batch of eight photos produced exactly one card. Caught by the e2e, not review.
 *
 * So: one controller per job, aborted only on unmount.
 *
 * Polling rather than SSE is deliberate for the MVP (docs/ARCHITECTURE.md §7). The seam is
 * this hook, so switching transports later touches one file.
 */
export function useAnalysisPolling() {
  const uploads = useWardrobe((s) => s.uploads);
  const updateUpload = useWardrobe((s) => s.updateUpload);
  const upsertItem = useWardrobe((s) => s.upsertItem);

  const controllers = useRef(new Map<string, AbortController>());

  // Abort every in-flight poller on unmount, and only on unmount.
  useEffect(
    () => () => {
      for (const controller of controllers.current.values()) controller.abort();
      controllers.current.clear();
    },
    [],
  );

  useEffect(() => {
    const pending = uploads.filter(
      (u) => u.state === "analyzing" && u.jobId !== null && !controllers.current.has(u.jobId),
    );

    for (const upload of pending) {
      const jobId = upload.jobId;
      if (!jobId) continue;

      const controller = new AbortController();
      controllers.current.set(jobId, controller);
      const startedAt = Date.now();

      void (async () => {
        try {
          const outcome = await pollAnalysis(
            { jobId, itemId: upload.itemId },
            {
              getJob,
              getItem: getWardrobeItem,
              sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
              // Named work, straight from the job. This is what makes the card say "reading
              // colour and cut" rather than spinning.
              onStage: (stage) => updateUpload(upload.localId, { stage }),
            },
            controller.signal,
          );

          if (outcome === null) return;

          if (outcome.kind === "ready") {
            upsertItem(outcome.item);
            // docs/ANALYTICS.md wants a confidence *bucket*, not the scores: the KPI is "how
            // often does the model come back unsure", and a histogram of raw floats per field
            // would be a description of one person's wardrobe.
            track("extraction_completed", {
              confidence: confidenceBucket(outcome.item),
              duration_ms: Date.now() - startedAt,
            });
            updateUpload(upload.localId, { state: "ready", stage: outcome.stage });
            return;
          }

          if (outcome.kind === "failed") {
            updateUpload(upload.localId, {
              state: "failed",
              stage: outcome.stage,
              error: outcome.message,
              retryable: outcome.retryable,
            });
            track("extraction_failed", { code: outcome.code });
            return;
          }

          updateUpload(upload.localId, {
            state: "failed",
            error: "That one is taking too long. Try it again.",
          });
        } finally {
          controllers.current.delete(jobId);
        }
      })();
    }
  }, [uploads, updateUpload, upsertItem]);
}

/**
 * A confidence bucket, not the scores.
 *
 * docs/ANALYTICS.md asks for "confidence bucket" and the distinction is the data-hygiene
 * rule: the per-field floats describe one person's specific garments, and a histogram of
 * them at a vendor is a description of somebody's wardrobe. How often the model comes back
 * unsure is the question worth answering, and it needs three words rather than eleven
 * numbers.
 */
function confidenceBucket(item: WardrobeItem): "high" | "mixed" | "low" {
  const scores = Object.values(item.field_confidence);
  if (scores.length === 0) return "low";
  const below = scores.filter((score) => score < config.confidenceFloor).length;
  if (below === 0) return "high";
  return below >= scores.length / 2 ? "low" : "mixed";
}
