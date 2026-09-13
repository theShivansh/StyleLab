import { describe, expect, it } from "vitest";
import { alternativesSchema, compositionGapSchema, outfitSchema, trendNoteSchema } from "./outfit";

/**
 * The outfit wire contract.
 *
 * These moved here from `wardrobe.test.ts` in S7, along with the schemas they cover. They
 * used to test a payload no endpoint produced; now they test the one the API actually sends,
 * which is the difference between a contract and a wish.
 */

const item = {
  item_id: "item_1",
  status: "ready",
  category: "footwear",
  subcategory: "sneaker",
  color_primary: "white",
  color_secondary: null,
  pattern: "solid",
  material_guess: "leather",
  fit: "regular",
  formality: "casual",
  image_url: "http://api.test/api/v1/assets/asset_1/tok",
};

const look = {
  outfit_id: "outfit_1",
  name: "Quiet Navy",
  occasion: "everyday",
  match_score: 84,
  status: "ready",
  degradation_level: 1,
  slots: [{ role: "footwear", item_id: "item_1", item }],
};

describe("trend notes", () => {
  it("accepts a note carrying source, date and link", () => {
    expect(
      trendNoteSchema.safeParse({
        trend: "Relaxed tailoring holding through AW26",
        source: "example-publication",
        published_at: "2026-07-14",
        url: "https://example-publication.test/aw26-tailoring",
      }).success,
    ).toBe(true);
  });

  it("rejects an unattributed note", () => {
    // AI-EVAL-CASES Case 15: unattributed trend claims are dropped, never rendered.
    expect(trendNoteSchema.safeParse({ trend: "Wide legs are back" }).success).toBe(false);
    expect(
      trendNoteSchema.safeParse({
        trend: "Wide legs are back",
        source: "",
        published_at: "2026-07-14",
        url: "https://example.test/a",
      }).success,
    ).toBe(false);
  });

  it("rejects a note the reader could not check", () => {
    // S8b: a source and a date with no link is a citation nobody can follow, which is what a
    // model inventing one produces. The url is also the note's identity server-side.
    expect(
      trendNoteSchema.safeParse({
        trend: "Wide legs are back",
        source: "A Real Magazine",
        published_at: "2026-07-14",
      }).success,
    ).toBe(false);
  });
});

describe("the outfit contract", () => {
  it("parses a complete look", () => {
    const parsed = outfitSchema.parse(look);
    expect(parsed.slots[0]?.item?.item_id).toBe("item_1");
    expect(parsed.saved).toBe(false);
  });

  it("keeps a slot whose garment was deleted", () => {
    // Case 14: the slot survives so the screen can say which piece went missing. A schema
    // that refused a null item would force the server to send a shorter look instead.
    const parsed = outfitSchema.parse({
      ...look,
      status: "incomplete",
      missing_roles: ["footwear"],
      slots: [{ role: "footwear", item_id: "item_1", item: null }],
    });
    expect(parsed.slots).toHaveLength(1);
    expect(parsed.slots[0]?.item).toBeNull();
    expect(parsed.missing_roles).toEqual(["footwear"]);
  });

  it("has no commerce fields anywhere in the contract", () => {
    // The product sells nothing. If a price or merchant field is ever added to the wire
    // format, this fails and forces the conversation.
    const serialised = JSON.stringify(
      outfitSchema.parse({
        ...look,
        wardrobe_gaps: [
          {
            category: "footwear",
            generic_description: "a white leather sneaker",
            unlocks_outfits: 5,
          },
        ],
      }),
    );
    for (const banned of ["price", "brand", "commerce_url", "merchant", "buy_url", "total"]) {
      expect(serialised).not.toContain(banned);
    }
  });

  it("refuses a match score outside the scale it is drawn on", () => {
    expect(outfitSchema.safeParse({ ...look, match_score: 140 }).success).toBe(false);
  });
});

describe("the alternatives contract", () => {
  it("treats an empty list with a named gap as a valid answer", () => {
    // prompts/06: "empty is a valid answer — name the gap and offer to add an item".
    const parsed = alternativesSchema.parse({
      role: "footwear",
      current_item_id: "item_1",
      alternatives: [],
      gap: { category: "footwear", generic_description: "a clean low-profile shoe" },
    });
    expect(parsed.alternatives).toEqual([]);
    expect(parsed.gap?.generic_description).toContain("shoe");
  });

  it("carries a negative delta rather than hiding it", () => {
    const parsed = alternativesSchema.parse({
      role: "footwear",
      current_item_id: "item_1",
      alternatives: [{ item, match_score: 70, delta: -14 }],
    });
    expect(parsed.alternatives[0]?.delta).toBe(-14);
  });
});

describe("the composition gap contract", () => {
  it("reads the payload a completed-but-empty composition carries", () => {
    const parsed = compositionGapSchema.parse({
      missing_roles: ["bottom", "footwear"],
      wardrobe_gaps: [
        { category: "bottom", generic_description: "a straight-leg trouser", unlocks_outfits: 0 },
      ],
      rationale: ["Your wardrobe needs bottom and footwear before this look can be built."],
      degradation_level: 5,
    });
    expect(parsed.missing_roles).toEqual(["bottom", "footwear"]);
    expect(parsed.degradation_level).toBe(5);
  });

  it("survives an empty payload rather than throwing on the screen", () => {
    expect(compositionGapSchema.parse({}).missing_roles).toEqual([]);
  });
});
