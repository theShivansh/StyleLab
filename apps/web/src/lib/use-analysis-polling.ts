"use client";

import { useEffect, useRef } from "react";
import { track } from "./analytics";
import { getJob, getWardrobeItem } from "./api/wardrobe";
import { config } from "./config";
import { userMessage } from "./errors";
import type { WardrobeItem } from "./schemas/wardrobe";
import { useWardrobe } from "./wardrobe-store";

const POLL_INTERVAL_MS = 1200;
/** ~90s at the interval above. An extraction that has not finished by then has failed. */
const MAX_ATTEMPTS = 75;

/**
 * Turns analysing uploads into garment cards.
 *
 * Each upload is polled on its own schedule and resolves on its own, which is what makes the
 * cards appear progressively rather than all at once behind a single batch spinner. One
 * photo's failure marks one card.
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
      const itemId = upload.itemId;
      if (!jobId) continue;

      const controller = new AbortController();
      controllers.current.set(jobId, controller);
      const startedAt = Date.now();

      void (async () => {
        try {
          for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
            if (controller.signal.aborted) return;

            const job = await getJob(jobId, controller.signal);

            if (job.status === "failed") {
              // The server's message, not ours. It was written against the actual failure
              // and it says whether retrying is worth the user's time; a generic local
              // string would be worse copy about something we know less about.
              updateUpload(upload.localId, {
                state: "failed",
                stage: job.stage,
                error:
                  job.error?.message ??
                  "We couldn't read that photo. Retake it, or add the details by hand.",
                retryable: job.error?.retryable ?? true,
              });
              track("extraction_failed", { code: job.error?.code ?? "unknown" });
              return;
            }

            if (job.status === "completed") {
              if (!itemId) {
                updateUpload(upload.localId, {
                  state: "failed",
                  error: "That photo went missing.",
                });
                return;
              }
              const item = await getWardrobeItem(itemId, controller.signal);
              upsertItem(item);
              // docs/ANALYTICS.md wants a confidence *bucket*, not the scores: the KPI is
              // "how often does the model come back unsure", and a histogram of raw floats
              // per field would be a description of one person's wardrobe.
              track("extraction_completed", {
                confidence: confidenceBucket(item),
                duration_ms: Date.now() - startedAt,
              });
              updateUpload(upload.localId, { state: "ready", stage: job.stage });
              return;
            }

            // Named work, straight from the job. This is what makes the card say "reading
            // colour and cut" rather than spinning.
            if (job.stage !== upload.stage) {
              updateUpload(upload.localId, { stage: job.stage });
            }

            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          }

          updateUpload(upload.localId, {
            state: "failed",
            error: "That one is taking too long. Try it again.",
          });
        } catch (error) {
          if (controller.signal.aborted) return;
          updateUpload(upload.localId, { state: "failed", error: userMessage(error) });
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
