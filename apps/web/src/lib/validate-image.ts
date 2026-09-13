import { config } from "./config";

/**
 * Client-side image validation.
 *
 * A courtesy, never the gate. The API validates independently (docs/API-SPEC.md) because
 * anything enforced only in the browser is not enforced. The point here is *immediate,
 * actionable* feedback — a user who picked eight photos should learn which one is too big
 * before waiting on a round trip.
 *
 * Pure and synchronous so it is trivially testable; dimension checks that need decoding live
 * in `readImageDimensions`.
 */

export type RejectionCode = "IMAGE_TOO_LARGE" | "UNSUPPORTED_FORMAT" | "EMPTY_FILE";

export interface Rejection {
  code: RejectionCode;
  /** Actionable, not a status code restated at the user. */
  message: string;
}

const ACCEPTED = new Set<string>(config.upload.acceptedMimeTypes);

export function validateImageFile(file: {
  name: string;
  size: number;
  type: string;
}): Rejection | null {
  if (file.size === 0) {
    return { code: "EMPTY_FILE", message: "That file is empty. Try picking it again." };
  }

  if (!ACCEPTED.has(file.type)) {
    return {
      code: "UNSUPPORTED_FORMAT",
      message: "Use a JPEG, PNG, WebP or AVIF photo.",
    };
  }

  if (file.size > config.upload.maxBytes) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    const limit = Math.round(config.upload.maxBytes / (1024 * 1024));
    return {
      code: "IMAGE_TOO_LARGE",
      message: `That photo is ${mb} MB. Keep it under ${limit} MB.`,
    };
  }

  return null;
}

/**
 * Splits a picked batch into what will be sent and what was refused.
 *
 * Partial success is success: one bad photo must never block the other seven
 * (docs/USER-FLOWS.md Flow 1). Over-count is reported rather than silently truncating,
 * because silently dropping a user's file is worse than telling them.
 */
export function partitionBatch<T extends { name: string; size: number; type: string }>(
  files: readonly T[],
): {
  accepted: T[];
  rejected: Array<{ file: T; rejection: Rejection }>;
  overflow: T[];
} {
  const accepted: T[] = [];
  const rejected: Array<{ file: T; rejection: Rejection }> = [];

  for (const file of files) {
    const rejection = validateImageFile(file);
    if (rejection) rejected.push({ file, rejection });
    else accepted.push(file);
  }

  const overflow = accepted.splice(config.upload.maxImagesPerBatch);
  return { accepted, rejected, overflow };
}
