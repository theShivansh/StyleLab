"use client";

import { useEffect, useRef } from "react";
import { getJob, getWardrobeItem } from "./api/wardrobe";
import { userMessage } from "./errors";
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
              return;
            }

            if (job.status === "completed") {
              if (!itemId) {
                updateUpload(upload.localId, { state: "failed", error: "That photo went missing." });
                return;
              }
              const item = await getWardrobeItem(itemId, controller.signal);
              upsertItem(item);
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
