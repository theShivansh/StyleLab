import { describe, it, expect } from "vitest";
import { ApiError, apiErrorSchema, userMessage, isRetryable } from "./errors";

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
