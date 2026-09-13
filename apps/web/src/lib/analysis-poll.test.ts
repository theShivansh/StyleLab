import { describe, expect, it, vi } from "vitest";
import { pollAnalysis, type AnalysisPollDeps, type PollLimits } from "./analysis-poll";
import { ApiError } from "./errors";
import type { WardrobeItem } from "./schemas/wardrobe";

/**
 * The decision logic behind an upload card.
 *
 * The case that matters most is the second one below, because it is what a user actually saw
 * on the deployed site: a job that answers 404 because the poll reached a different instance
 * than the upload, for a garment that was ready in the database the whole time.
 */

const LIMITS: PollLimits = { intervalMs: 0, maxAttempts: 10, maxTransient: 3 };
const TARGET = { jobId: "job_1", itemId: "item_1" };

function job(status: string, extra: Record<string, unknown> = {}) {
  return {
    job_id: "job_1",
    type: "analyze_item",
    status,
    stage: null,
    progress: null,
    ...extra,
  } as never;
}

function item(status: WardrobeItem["status"]): WardrobeItem {
  return { item_id: "item_1", status } as WardrobeItem;
}

function apiError(status: number, code = "AI_UNAVAILABLE") {
  return new ApiError({ code: code as never, message: "x", retryable: status >= 500, status });
}

function deps(over: Partial<AnalysisPollDeps>): AnalysisPollDeps {
  return {
    getJob: vi.fn(async () => job("completed")),
    getItem: vi.fn(async () => item("ready")),
    sleep: vi.fn(async () => undefined),
    ...over,
  };
}

const signal = () => new AbortController().signal;

describe("pollAnalysis", () => {
  it("reads the garment once the job completes", async () => {
    const d = deps({});

    const outcome = await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(outcome).toMatchObject({ kind: "ready", item: { item_id: "item_1" } });
  });

  it("re-reads the item when the job is missing, instead of calling the garment missing", async () => {
    // The deployed bug, exactly: 404 on the job, garment ready in the shared database.
    const d = deps({ getJob: vi.fn(async () => Promise.reject(apiError(404, "ITEM_NOT_FOUND"))) });

    const outcome = await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(outcome).toMatchObject({ kind: "ready" });
    expect(d.getItem).toHaveBeenCalledWith("item_1", expect.anything());
  });

  it("keeps watching the item while another instance is still reading it", async () => {
    const statuses: WardrobeItem["status"][] = ["analyzing", "analyzing", "ready"];
    const d = deps({
      getJob: vi.fn(async () => Promise.reject(apiError(404, "ITEM_NOT_FOUND"))),
      getItem: vi.fn(async () => item(statuses.shift() ?? "ready")),
    });

    const outcome = await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(outcome).toMatchObject({ kind: "ready" });
    // Asked about the job once. After that the item is the answer, not whichever replied last.
    expect(d.getJob).toHaveBeenCalledTimes(1);
    expect(d.getItem).toHaveBeenCalledTimes(3);
  });

  it("reports a genuinely missing garment when the item is gone too", async () => {
    const d = deps({
      getJob: vi.fn(async () => Promise.reject(apiError(404, "ITEM_NOT_FOUND"))),
      getItem: vi.fn(async () => Promise.reject(apiError(404, "ITEM_NOT_FOUND"))),
    });

    const outcome = await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(outcome).toMatchObject({ kind: "failed", code: "ITEM_NOT_FOUND", retryable: false });
  });

  it("treats an item that failed analysis as a failed card with a retry", async () => {
    const d = deps({
      getJob: vi.fn(async () => Promise.reject(apiError(404, "ITEM_NOT_FOUND"))),
      getItem: vi.fn(async () => item("failed")),
    });

    const outcome = await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(outcome).toMatchObject({ kind: "failed", retryable: true });
  });

  it("rides out a passing 5xx during a rollout", async () => {
    const answers = [apiError(503), apiError(502), null];
    const d = deps({
      getJob: vi.fn(async () => {
        const next = answers.shift();
        if (next) throw next;
        return job("completed");
      }),
    });

    const outcome = await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(outcome).toMatchObject({ kind: "ready" });
  });

  it("rides out a dropped connection, which is what a replaced instance looks like", async () => {
    const answers: Array<Error | null> = [new TypeError("Failed to fetch"), null];
    const d = deps({
      getJob: vi.fn(async () => {
        const next = answers.shift();
        if (next) throw next;
        return job("completed");
      }),
    });

    expect(await pollAnalysis(TARGET, d, signal(), LIMITS)).toMatchObject({ kind: "ready" });
  });

  it("gives up on a real outage rather than spinning forever", async () => {
    const d = deps({ getJob: vi.fn(async () => Promise.reject(apiError(503))) });

    const outcome = await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(outcome).toMatchObject({ kind: "failed", retryable: true });
    expect(d.getJob).toHaveBeenCalledTimes(LIMITS.maxTransient + 1);
  });

  it("passes the server's own failure message through", async () => {
    const d = deps({
      getJob: vi.fn(async () =>
        job("failed", {
          error: { code: "EXTRACTION_FAILED", message: "From the classifier.", retryable: false },
        }),
      ),
    });

    const outcome = await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(outcome).toEqual({
      kind: "failed",
      message: "From the classifier.",
      retryable: false,
      stage: null,
      code: "EXTRACTION_FAILED",
    });
  });

  it("names each new stage once, not on every poll", async () => {
    const stages = ["reading photo", "reading photo", "finding garment"];
    const onStage = vi.fn();
    const d = deps({
      onStage,
      getJob: vi.fn(async () =>
        stages.length ? job("processing", { stage: stages.shift() }) : job("completed"),
      ),
    });

    await pollAnalysis(TARGET, d, signal(), LIMITS);

    expect(onStage.mock.calls.map(([stage]) => stage)).toEqual([
      "reading photo",
      "finding garment",
      null,
    ]);
  });

  it("times out when nothing ever finishes", async () => {
    const d = deps({ getJob: vi.fn(async () => job("processing")) });

    expect(await pollAnalysis(TARGET, d, signal(), LIMITS)).toEqual({ kind: "timeout" });
  });

  it("resolves null when the user has left", async () => {
    const controller = new AbortController();
    controller.abort();

    expect(await pollAnalysis(TARGET, deps({}), controller.signal, LIMITS)).toBeNull();
  });
});
