import { z } from "zod";

/**
 * Error contract. Mirrors docs/API-SPEC.md exactly — if you add a code there, add it here.
 *
 * Two conventions the product depends on:
 *  - `AI_UNAVAILABLE` is a real outage, not a downgrade path. There is no demo mode to fall
 *    back to, so the UI says so plainly rather than showing a fabricated result.
 *  - `INSUFFICIENT_WARDROBE` is not rendered as an error at all. It is a product state:
 *    name the gap, offer to add an item. See docs/USER-FLOWS.md Flow 5.
 */

export const errorCodes = [
  "IMAGE_TOO_LARGE",
  "UNSUPPORTED_FORMAT",
  "IMAGE_UNREADABLE",
  "EXTRACTION_FAILED",
  "PROVIDER_TIMEOUT",
  "INSUFFICIENT_WARDROBE",
  "ITEM_NOT_FOUND",
  "AGENT_BUDGET_EXCEEDED",
  "TREND_SOURCE_UNAVAILABLE",
  "AI_UNAVAILABLE",
] as const;

export type ErrorCode = (typeof errorCodes)[number];

export const apiErrorSchema = z.object({
  error: z.object({
    code: z.enum(errorCodes).catch("AI_UNAVAILABLE"),
    message: z.string(),
    retryable: z.boolean().default(false),
    request_id: z.string().optional(),
  }),
});

export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly retryable: boolean;
  readonly requestId: string | undefined;
  readonly status: number;

  constructor(args: {
    code: ErrorCode;
    message: string;
    retryable: boolean;
    requestId?: string | undefined;
    status: number;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.code = args.code;
    this.retryable = args.retryable;
    this.requestId = args.requestId;
    this.status = args.status;
  }

  /** A gap in the user's wardrobe is a product state, not a failure to render as one. */
  get isProductState(): boolean {
    return this.code === "INSUFFICIENT_WARDROBE";
  }
}

/** Never surface a raw provider or stack message. docs/SECURITY-PRIVACY.md. */
const userFacingMessages: Record<ErrorCode, string> = {
  IMAGE_TOO_LARGE: "That photo is too large. Try one under 10 MB.",
  UNSUPPORTED_FORMAT: "That file type isn't supported. Use JPEG, PNG, WebP or AVIF.",
  IMAGE_UNREADABLE: "We couldn't read that photo. Try a clearer one.",
  EXTRACTION_FAILED: "We couldn't read that garment clearly. You can retry or add it by hand.",
  PROVIDER_TIMEOUT: "That took too long. Retry when you're ready.",
  INSUFFICIENT_WARDROBE: "Your wardrobe is missing a piece for this look.",
  ITEM_NOT_FOUND: "That item isn't in your wardrobe.",
  AGENT_BUDGET_EXCEEDED: "Styling took longer than expected, so this look is a simpler one.",
  TREND_SOURCE_UNAVAILABLE: "Trend context is unavailable right now.",
  AI_UNAVAILABLE: "Styling is unavailable right now. Nothing was lost — try again shortly.",
};

export function userMessage(error: unknown): string {
  if (error instanceof ApiError) return userFacingMessages[error.code];
  return "Something went wrong. Try again.";
}

export function isRetryable(error: unknown): boolean {
  return error instanceof ApiError && error.retryable;
}
