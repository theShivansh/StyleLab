import { describe, it, expect } from "vitest";
import { config, flags, isEnabled } from "./config";

describe("config", () => {
  it("exposes no model identifiers to the browser bundle", () => {
    // CLAUDE.md: model IDs live in .env.example and the adapter config, nowhere else.
    // The web app must never name a model.
    const serialised = JSON.stringify(config);
    for (const banned of ["groq", "qwen", "gpt-oss", "GROQ_API_KEY"]) {
      expect(serialised.toLowerCase()).not.toContain(banned.toLowerCase());
    }
  });

  it("keeps the compose threshold low enough for a first-run wardrobe", () => {
    // USER-FLOWS Flow 1: usable at three items. Do not gate above what a new user reaches.
    expect(config.minItemsToCompose).toBeLessThanOrEqual(3);
  });

  it("has P1 scope behind flags so triage can cut it without unpicking code", () => {
    expect(isEnabled("planner")).toBe(false);
    expect(flags.shareCards).toBe(false);
  });
});
