import { describe, it, expect } from "vitest";
import { describeGarment, displayValue, humanise, isHedged, wardrobeItemSchema } from "./wardrobe";

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

describe("describing a garment in words", () => {
  it("reads as English rather than as an identifier", () => {
    // S11 found `white solid_color sneaker` on the result screen. `pattern`, `subcategory`,
    // `color_primary` and `fit` are open sets in the world and cannot be closed the way
    // `style_tags` was in S8 (blocker B18), so whatever the model writes reaches the screen.
    // It usually writes English. Sometimes it writes an identifier, having read a great many
    // JSON schemas.
    expect(
      describeGarment({
        color_primary: "white",
        pattern: "solid_color",
        subcategory: "sneaker",
      }),
    ).toBe("white solid color sneaker");
  });

  it("turns a single field the model wrote as an identifier into words", () => {
    // Seen on the deployed site: a sneaker's fit rendered as `one_size` on the card, because
    // only the garment's name went through this, not the field list.
    expect(humanise("one_size")).toBe("one size");
    expect(humanise("solid_color")).toBe("solid color");
    expect(humanise("slim")).toBe("slim");
  });

  it("shows a value the user set exactly as they wrote it", () => {
    // Also seen live: humanising a correction turned "off-white" into "off white".
    expect(
      displayValue({ corrected_fields: ["color_primary"] }, "color_primary", "off-white"),
    ).toBe("off-white");
    expect(displayValue({ corrected_fields: [] }, "fit", "one_size")).toBe("one size");
  });

  it("falls back to the category when there is no subcategory", () => {
    expect(
      describeGarment({ color_primary: "navy", pattern: null, subcategory: null, category: "top" }),
    ).toBe("navy top");
  });

  it("skips absent fields rather than leaving gaps", () => {
    expect(describeGarment({ color_primary: null, pattern: "striped", subcategory: "shirt" })).toBe(
      "striped shirt",
    );
    expect(describeGarment({})).toBe("");
  });

  it("never reaches for a field that could describe a person", () => {
    // The guarantee is structural: the argument type has four properties and none of them
    // is about a body. Asserted so that widening it is a decision somebody has to make on
    // purpose rather than a parameter they add in passing.
    const described = describeGarment({
      color_primary: "black",
      pattern: "solid",
      subcategory: "jacket",
      // @ts-expect-error — there is no field for this, and there must not be.
      fit_on_wearer: "slim build, mid-thirties",
    });
    expect(described).toBe("black solid jacket");
  });
});
