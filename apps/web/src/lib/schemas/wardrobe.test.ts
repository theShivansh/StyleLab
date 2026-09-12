import { describe, it, expect } from "vitest";
import { isHedged, outfitAdviceSchema, trendNoteSchema, wardrobeItemSchema } from "./wardrobe";

/**
 * Baseline tests for the invariants the whole product rests on. These are deliberately
 * about product rules, not framework plumbing — a foundation that only proves "React
 * renders" proves nothing worth gating on.
 */

const item = wardrobeItemSchema.parse({
  item_id: "item_1",
  status: "ready",
  category: "top",
  subcategory: "oxford shirt",
  color_primary: "navy",
  color_secondary: null,
  pattern: "solid",
  material_guess: "cotton",
  fit: "regular",
  formality: "smart-casual",
  field_confidence: { category: 0.97, color_primary: 0.62, material_guess: 0.41 },
  corrected_fields: [],
  image_url: "https://example.test/signed",
});

describe("confidence hedging", () => {
  it("hedges a field below the floor", () => {
    expect(isHedged(item, "color_primary", 0.7)).toBe(true);
    expect(isHedged(item, "material_guess", 0.7)).toBe(true);
  });

  it("does not hedge a field above the floor", () => {
    expect(isHedged(item, "category", 0.7)).toBe(false);
  });

  it("hedges a field with no confidence score at all", () => {
    expect(isHedged(item, "fit", 0.7)).toBe(true);
  });

  it("stops hedging once the user has corrected the field", () => {
    // AI-EVAL-CASES Case 13: a correction settles the question. It must not be re-hedged,
    // and re-analysis must not overwrite it.
    const corrected = { ...item, corrected_fields: ["color_primary"] };
    expect(isHedged(corrected, "color_primary", 0.7)).toBe(false);
  });
});

describe("trend notes", () => {
  it("accepts a note carrying source and date", () => {
    expect(
      trendNoteSchema.safeParse({
        trend: "Relaxed tailoring holding through AW26",
        source: "example-publication",
        published_at: "2026-07-14",
      }).success,
    ).toBe(true);
  });

  it("rejects an unattributed note", () => {
    // AI-EVAL-CASES Case 15: unattributed trend claims are dropped, never rendered.
    expect(trendNoteSchema.safeParse({ trend: "Wide legs are back" }).success).toBe(false);
    expect(
      trendNoteSchema.safeParse({ trend: "Wide legs are back", source: "", published_at: "2026-07-14" })
        .success,
    ).toBe(false);
  });
});

describe("outfit advice contract", () => {
  it("treats an empty wardrobe gap as a valid, complete answer", () => {
    // USER-FLOWS Flow 5: naming the gap is a product state, not an error.
    const parsed = outfitAdviceSchema.parse({
      outfit: null,
      missing_roles: ["footwear"],
      degradation_level: 1,
    });
    expect(parsed.outfit).toBeNull();
    expect(parsed.missing_roles).toEqual(["footwear"]);
  });

  it("defaults degradation level to a full crew run", () => {
    expect(outfitAdviceSchema.parse({ outfit: null }).degradation_level).toBe(1);
  });

  it("has no commerce fields anywhere in the contract", () => {
    // The product sells nothing. If a price or merchant field is ever added to the wire
    // format, this fails and forces the conversation.
    const serialised = JSON.stringify(
      outfitAdviceSchema.parse({
        outfit: null,
        wardrobe_gaps: [
          { category: "footwear", generic_description: "a white leather sneaker", unlocks_outfits: 5 },
        ],
      }),
    );
    for (const banned of ["price", "brand", "commerce_url", "merchant", "buy_url"]) {
      expect(serialised).not.toContain(banned);
    }
  });
});
