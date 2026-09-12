import { z } from "zod";

/**
 * Runtime configuration and feature flags.
 *
 * Two rules from CLAUDE.md hold here:
 *  - No model ID appears in this file. Model selection is the API's business; the web app
 *    never names a model. If you find yourself adding GROQ_* here, stop.
 *  - GROQ_API_KEY must never reach the browser. Nothing server-only is read in this module,
 *    which is why everything below is NEXT_PUBLIC_ or a literal.
 */

const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_URL: z.url().default("http://localhost:8000"),
  NEXT_PUBLIC_POSTHOG_KEY: z.string().optional(),
  NEXT_PUBLIC_POSTHOG_HOST: z.string().optional(),
});

function readPublicEnv() {
  // Next inlines process.env.NEXT_PUBLIC_* at build time, so these must be referenced
  // statically rather than through a dynamic key.
  const parsed = publicEnvSchema.safeParse({
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_POSTHOG_KEY: process.env.NEXT_PUBLIC_POSTHOG_KEY,
    NEXT_PUBLIC_POSTHOG_HOST: process.env.NEXT_PUBLIC_POSTHOG_HOST,
  });

  if (!parsed.success) {
    // Fail loudly and early. There is no demo mode to fall back into
    // (docs/DECISIONS.md, 2026-09-12).
    throw new Error(`Invalid public environment configuration:\n${z.prettifyError(parsed.error)}`);
  }
  return parsed.data;
}

export const config = {
  env: readPublicEnv(),

  /** Upload limits mirror the API. Client-side validation is a courtesy, never the gate. */
  upload: {
    maxBytes: 10 * 1024 * 1024,
    maxImagesPerBatch: 12,
    acceptedMimeTypes: ["image/jpeg", "image/png", "image/webp", "image/avif"] as const,
  },

  /** Below this, a field is presented as a hedge and offered for correction. */
  confidenceFloor: 0.7,

  /** Wardrobe is usable at three items — do not gate composition above a first-run count. */
  minItemsToCompose: 3,
} as const;

/**
 * Feature flags. P1 scope that docs/EXECUTION-PLAN triage cuts first lives here so it can
 * be switched off without unpicking code.
 */
export const flags = {
  planner: false,
  shareCards: false,
  preferenceLearning: false,
  trendNotes: true,
} as const;

export type FeatureFlag = keyof typeof flags;

export function isEnabled(flag: FeatureFlag): boolean {
  return flags[flag];
}
