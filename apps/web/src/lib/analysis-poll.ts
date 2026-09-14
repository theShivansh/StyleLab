import type { z } from "zod";
import { ApiError, userMessage } from "./errors";
import type { jobStatusSchema, WardrobeItem } from "./schemas/wardrobe";

type JobStatus = z.infer<typeof jobStatusSchema>;

/**
 * Following one uploaded photograph to a garment card — the decision logic, without React.
 *
 * Pulled out of `use-analysis-polling.ts` after the first live deployment, because the hook's
 * version had one rule for every error: any exception ended the card. That rule was wrong in a
 * way only a real platform shows.
 *
 * ## What happened
 *
 * An upload reached one instance of the API and a poll reached another — a gradual rollout
 * after a configuration change does exactly that. The job record lived in the first instance's
 * memory, so the second answered 404, and the card said "That item isn't in your wardrobe" for
 * a photograph that was being read correctly at that moment. The server now keeps job records
 * in the database (`JOB_BACKEND`), which closes the cause. This closes the class: a poll is an
 * observation of work happening elsewhere, and one failed observation is not a failed job.
 *
 * ## The three rules
 *
 * 1. **A missing job is not a missing garment.** The jobs route says so in its own docstring:
 *    a poller that meets a restart should re-read the item. The item row is in the database
 *    every instance shares, and its `status` is the authoritative answer.
 * 2. **A passing failure is retried, briefly.** A 5xx, a 429 or a network error during a
 *    rollout says nothing about the photograph. A few in a row are tolerated; more than that is
 *    a real outage, and the card says so rather than spinning forever.
 * 3. **Everything else is final**, with the copy it always had.
 */

export interface AnalysisTarget {
  jobId: string;
  itemId: string | null;
}

export interface AnalysisPollDeps {
  getJob: (jobId: string, signal: AbortSignal) => Promise<JobStatus>;
  getItem: (itemId: string, signal: AbortSignal) => Promise<WardrobeItem>;
  sleep: (ms: number) => Promise<void>;
  /** Called when the server names a new stage, and only then. */
  onStage?: (stage: string | null) => void;
}

export interface PollLimits {
  intervalMs: number;
  /** ~90s at the default interval. An extraction that has not finished by then has failed. */
  maxAttempts: number;
  /** Consecutive passing failures tolerated before the card gives up. */
  maxTransient: number;
}

export const DEFAULT_LIMITS: PollLimits = { intervalMs: 1200, maxAttempts: 75, maxTransient: 4 };

export type AnalysisOutcome =
  | { kind: "ready"; item: WardrobeItem; stage: string | null }
  | {
      kind: "failed";
      message: string;
      retryable: boolean;
      stage: string | null;
      code: string;
    }
  | { kind: "timeout" };

/** The server's word for "that garment is not there any more", reused rather than reworded. */
const NO_LONGER_THERE = "That photo is no longer in your wardrobe.";
const UNREADABLE = "We couldn't read that photo. Retake it, or add the details by hand.";

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/**
 * An error that describes the moment rather than the request.
 *
 * Anything that is not an `ApiError` counts — `fetch` rejects with a `TypeError` when the
 * connection drops, which is precisely what an instance being replaced looks like from here.
 */
export function isTransient(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status >= 500 || error.status === 429;
}

/**
 * Poll until the photograph is a garment, a named failure, or out of time.
 *
 * Resolves `null` when aborted, so the caller can tell "the user left" from every outcome
 * that should change a card.
 */
export async function pollAnalysis(
  target: AnalysisTarget,
  deps: AnalysisPollDeps,
  signal: AbortSignal,
  limits: PollLimits = DEFAULT_LIMITS,
): Promise<AnalysisOutcome | null> {
  let transient = 0;
  // Once the job has gone missing it is not asked about again: the item is the answer from
  // here on, and alternating between the two would report whichever one answered last.
  let jobGone = false;
  let lastStage: string | null = null;

  for (let attempt = 0; attempt < limits.maxAttempts; attempt += 1) {
    if (signal.aborted) return null;

    try {
      if (!jobGone) {
        const job = await deps.getJob(target.jobId, signal);
        transient = 0;

        if (job.stage !== lastStage) {
          lastStage = job.stage;
          deps.onStage?.(job.stage);
        }

        if (job.status === "failed") {
          // The server's message, not ours. It was written against the actual failure and
          // it says whether retrying is worth the user's time.
          return {
            kind: "failed",
            message: job.error?.message ?? UNREADABLE,
            retryable: job.error?.retryable ?? true,
            stage: job.stage,
            code: job.error?.code ?? "unknown",
          };
        }

        if (job.status === "completed") {
          if (!target.itemId) return missing(lastStage);
          const item = await deps.getItem(target.itemId, signal);
          // A finished job is not a finished garment; the item's own status is the answer. On
          // the deployed site a re-upload came back with a job marked completed for a photo
          // whose read had failed, and this branch drew it as "Read" with no garment behind it.
          const settled = settle(item, job.stage);
          if (settled) return settled;
          // Completed, yet still being read: watch the item from here, as for a missing job.
          jobGone = true;
        }
      } else {
        if (!target.itemId) return missing(lastStage);
        const item = await deps.getItem(target.itemId, signal);
        transient = 0;

        const settled = settle(item, lastStage);
        if (settled) return settled;
        // Still analysing, on whichever instance took the upload. Keep watching the item.
      }
    } catch (error) {
      if (signal.aborted) return null;

      if (!jobGone && isNotFound(error)) {
        // Rule 1. Straight to the item, with no pause — the garment may well be ready.
        jobGone = true;
        continue;
      }

      if (isTransient(error) && transient < limits.maxTransient) {
        transient += 1;
        await deps.sleep(limits.intervalMs);
        continue;
      }

      return {
        kind: "failed",
        message: userMessage(error),
        retryable: error instanceof ApiError ? error.retryable : true,
        stage: lastStage,
        code: error instanceof ApiError ? error.code : "unknown",
      };
    }

    await deps.sleep(limits.intervalMs);
  }

  return { kind: "timeout" };
}

/** What an item's own status says about its card, or `null` while it is still being read. */
function settle(item: WardrobeItem, stage: string | null): AnalysisOutcome | null {
  if (item.status === "ready") return { kind: "ready", item, stage };
  if (item.status === "failed") {
    return {
      kind: "failed",
      message: UNREADABLE,
      retryable: true,
      stage,
      code: "EXTRACTION_FAILED",
    };
  }
  if (item.status === "archived") {
    return {
      kind: "failed",
      message: NO_LONGER_THERE,
      retryable: false,
      stage,
      code: "ITEM_NOT_FOUND",
    };
  }
  return null;
}

function missing(stage: string | null): AnalysisOutcome {
  return {
    kind: "failed",
    message: "That photo went missing.",
    retryable: false,
    stage,
    code: "ITEM_NOT_FOUND",
  };
}
