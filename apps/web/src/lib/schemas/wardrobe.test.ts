import { describe, it, expect } from "vitest";
import { isHedged, wardrobeItemSchema } from "./wardrobe";

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

  it("hedges the material even when the model is certain", () => {
    // AI-EVAL-CASES Case 08, Fail clause: an unhedged claim about fibre content. S8's eval
    // harness fed in `"100% merino wool"` at 0.99 and watched the card render it as a plain
    // fact — a photograph cannot show what a garment is made of at any confidence.
    const certain = {
      ...item,
      material_guess: "100% merino wool",
      field_confidence: { ...item.field_confidence, material_guess: 0.99 },
    };
    expect(isHedged(certain, "material_guess", 0.7)).toBe(true);
    // And the rest of the card is unaffected: this is one field, not a blanket hedge.
    expect(isHedged(certain, "category", 0.7)).toBe(false);
  });

  it("still lets the user settle the material by hand", () => {
    // They can read their own care label, which is the only source that actually knows.
    const settled = { ...item, corrected_fields: ["material_guess"] };
    expect(isHedged(settled, "material_guess", 0.7)).toBe(false);
  });
});
