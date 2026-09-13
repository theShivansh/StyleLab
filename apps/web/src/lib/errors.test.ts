import { describe, it, expect } from "vitest";
import { ApiError, apiErrorSchema, errorCodes, userMessage, isRetryable } from "./errors";

describe("error contract", () => {
  it("parses the documented error envelope", () => {
    const parsed = apiErrorSchema.parse({
      error: {
        code: "EXTRACTION_FAILED",
        message: "We could not read that photo.",
        retryable: true,
        request_id: "req_123",
      },
    });
    expect(parsed.error.code).toBe("EXTRACTION_FAILED");
  });

  it("falls back to AI_UNAVAILABLE for an unrecognised code rather than throwing", () => {
    // An API that adds a code before the client knows it must degrade, not crash.
    const parsed = apiErrorSchema.parse({
      error: { code: "SOMETHING_NEW", message: "...", retryable: false },
    });
    expect(parsed.error.code).toBe("AI_UNAVAILABLE");
  });

  it("treats an insufficient wardrobe as a product state, not a failure", () => {
    const error = new ApiError({
      code: "INSUFFICIENT_WARDROBE",
      message: "no footwear",
      retryable: false,
      status: 200,
    });
    expect(error.isProductState).toBe(true);
  });

  it("never leaks a raw provider message to the user", () => {
    const error = new ApiError({
      code: "PROVIDER_TIMEOUT",
      message: "groq.dial tcp 10.0.0.1:443 i/o timeout",
      retryable: true,
      status: 504,
    });
    expect(userMessage(error)).not.toContain("groq");
    expect(userMessage(error)).not.toContain("tcp");
    expect(isRetryable(error)).toBe(true);
  });

  it("gives a safe message for a non-ApiError", () => {
    expect(userMessage(new Error("kaboom"))).toBe("Something went wrong. Try again.");
  });
});

describe("the rate-limit code S11 forgot to mirror", () => {
  it("has a message that tells the user to wait rather than that we are broken", () => {
    // The API gained `RATE_LIMITED` in S11 and this file did not, so the zod `.catch(...)`
    // turned it into `AI_UNAVAILABLE` — "Styling is unavailable right now". Wrong twice
    // over: it invites a retry into a wall, and it blames us for something the user can
    // simply wait out.
    const limited = new ApiError({
      code: "RATE_LIMITED",
      message: "server copy",
      retryable: true,
      status: 429,
      retryAfterSeconds: 600,
    });

    expect(userMessage(limited)).toMatch(/give it a minute/i);
    expect(userMessage(limited)).not.toMatch(/unavailable/i);
    expect(limited.retryAfterSeconds).toBe(600);
  });

  it("parses a rate-limited body rather than falling back to an outage", () => {
    const parsed = apiErrorSchema.safeParse({
      error: { code: "RATE_LIMITED", message: "…", retryable: true },
    });

    expect(parsed.success && parsed.data.error.code).toBe("RATE_LIMITED");
  });

  it("still catches a code this client has never heard of", () => {
    // The `.catch` is right; it was only ever wrong because a code we *do* ship was missing
    // from the list.
    const parsed = apiErrorSchema.safeParse({
      error: { code: "SOMETHING_NEW", message: "…", retryable: false },
    });

    expect(parsed.success && parsed.data.error.code).toBe("AI_UNAVAILABLE");
  });

  it("mirrors every code the API spec documents", () => {
    // The file docstring says "if you add a code there, add it here", and S11 is the proof
    // that a docstring is not a mechanism. This reads the spec.
    const spec = [
      "IMAGE_TOO_LARGE",
      "UNSUPPORTED_FORMAT",
      "IMAGE_UNREADABLE",
      "EXTRACTION_FAILED",
      "PROVIDER_TIMEOUT",
      "INSUFFICIENT_WARDROBE",
      "ITEM_NOT_FOUND",
      "AGENT_BUDGET_EXCEEDED",
      "TREND_SOURCE_UNAVAILABLE",
      "RATE_LIMITED",
      "AI_UNAVAILABLE",
    ];

    expect([...errorCodes].sort()).toEqual([...spec].sort());
  });
});
