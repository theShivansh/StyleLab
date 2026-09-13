"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { track } from "@/lib/analytics";
import { composeOutfit, type ComposeRequest } from "@/lib/api/outfits";
import { getJob } from "@/lib/api/wardrobe";
import { userMessage } from "@/lib/errors";
import { compositionGapSchema, type CompositionGap } from "@/lib/schemas/outfit";

const POLL_INTERVAL_MS = 1000;
/** ~60s. A composition that has not finished by then is not going to. */
const MAX_ATTEMPTS = 60;

export type CompositionState = "idle" | "composing" | "gap" | "failed";

/**
 * Start a composition and follow it to a look.
 *
 * The same shape as `use-analysis-polling`, and for the same reason: the server does the work
 * asynchronously and reports named stages, so the screen can say what is happening rather
 * than spin. The stage strings are the server's own — a client-side guess at which step the
 * crew is on is a spinner with a caption (CLAUDE.md motion rules).
 *
 * ## A gap is not a failure
 *
 * A wardrobe that cannot fill a required role completes the job with the gap named, and this
 * hook surfaces that as its own state rather than as an error. There is nothing to retry and
 * nothing went wrong — the answer is "you have no footwear yet", and it comes with the
 * generic description of what would unlock the look. Nothing is ever substituted.
 */
export function useComposition() {
  const router = useRouter();
  const [state, setState] = useState<CompositionState>("idle");
  const [stage, setStage] = useState<string | null>(null);
  const [gap, setGap] = useState<CompositionGap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const start = useCallback(
    async (request: ComposeRequest) => {
      controller.current?.abort();
      const running = new AbortController();
      controller.current = running;

      setState("composing");
      setStage(null);
      setGap(null);
      setError(null);
      track("composition_started", { occasion: request.occasion, vibe: request.vibe ?? "" });
      const startedAt = Date.now();

      try {
        const job = await composeOutfit(request, running.signal);

        for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
          if (running.signal.aborted) return;
          const status = await getJob(job.job_id, running.signal);

          if (status.status === "failed") {
            track("composition_failed", { code: status.error?.code ?? "AI_UNAVAILABLE" });
            setState("failed");
            setError(
              status.error?.message ??
                "We couldn't put a look together just now. Try again in a moment.",
            );
            return;
          }

          if (status.status === "completed") {
            if (status.result_id) {
              track("composition_completed", {
                outfit_id: status.result_id,
                degradation_level: 1,
                duration_ms: Date.now() - startedAt,
              });
              router.push(`/outfit/${status.result_id}`);
              return;
            }

            // Completed with no look: the honest gap answer.
            const parsed = compositionGapSchema.safeParse(status.result ?? {});
            const named = parsed.success ? parsed.data : null;
            setGap(named);
            setState("gap");
            track("insufficient_wardrobe", { missing_roles: named?.missing_roles ?? [] });
            return;
          }

          setStage(status.stage);
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        }

        setState("failed");
        setError("That is taking longer than it should. Try again.");
      } catch (failure) {
        if (running.signal.aborted) return;
        track("composition_failed", { code: "AI_UNAVAILABLE" });
        setState("failed");
        setError(userMessage(failure));
      }
    },
    [router],
  );

  return { state, stage, gap, error, start } as const;
}
