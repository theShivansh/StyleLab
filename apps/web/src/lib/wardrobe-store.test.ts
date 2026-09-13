import { describe, it, expect, beforeEach } from "vitest";
import { useWardrobe, DEFAULT_PREFERENCES, type UploadEntry } from "./wardrobe-store";
import { wardrobeItemSchema, type WardrobeItem } from "./schemas/wardrobe";

function item(over: Partial<WardrobeItem> = {}): WardrobeItem {
  return wardrobeItemSchema.parse({
    item_id: "item_1",
    status: "ready",
    category: "top",
    subcategory: "oxford shirt",
    color_primary: "black",
    color_secondary: null,
    pattern: "solid",
    material_guess: "cotton",
    fit: "regular",
    formality: "smart-casual",
    field_confidence: { category: 0.97, color_primary: 0.52 },
    corrected_fields: [],
    image_url: "",
    ...over,
  });
}

function upload(over: Partial<UploadEntry> = {}): UploadEntry {
  return {
    localId: "u1",
    fileName: "a.jpg",
    state: "uploading",
    categoryHint: null,
    itemId: null,
    jobId: null,
    error: null,
    retryable: false,
    stage: null,
    previewUrl: null,
    ...over,
  };
}

beforeEach(() => {
  useWardrobe.setState({
    uploads: [],
    items: [],
    preferences: DEFAULT_PREFERENCES,
    preferencesTouched: false,
  });
});

describe("upload queue", () => {
  it("resolves each entry independently", () => {
    const store = useWardrobe.getState();
    store.enqueue([upload({ localId: "a" }), upload({ localId: "b" }), upload({ localId: "c" })]);

    useWardrobe.getState().updateUpload("b", { state: "failed", error: "Couldn't read it" });

    const states = useWardrobe.getState().uploads.map((u) => u.state);
    // One failure must not disturb its neighbours.
    expect(states).toEqual(["uploading", "failed", "uploading"]);
  });

  it("keeps a rejected entry visible so the user sees the reason", () => {
    useWardrobe
      .getState()
      .enqueue([
        upload({ localId: "ok", state: "ready" }),
        upload({ localId: "bad", state: "rejected", error: "Too large" }),
      ]);

    useWardrobe.getState().clearResolvedUploads();

    const remaining = useWardrobe.getState().uploads;
    expect(remaining.map((u) => u.localId)).toEqual(["bad"]);
  });
});

describe("corrections", () => {
  it("applies the value, flags the field, and drops its confidence score", () => {
    useWardrobe.getState().upsertItem(item());
    useWardrobe.getState().correctField("item_1", "color_primary", "navy");

    const corrected = useWardrobe.getState().items[0];
    expect(corrected?.color_primary).toBe("navy");
    expect(corrected?.corrected_fields).toContain("color_primary");
    // Confidence describes a model guess. This is no longer one.
    expect(corrected?.field_confidence["color_primary"]).toBeUndefined();
    expect(corrected?.field_confidence["category"]).toBe(0.97);
  });

  it("does not duplicate a field corrected twice", () => {
    useWardrobe.getState().upsertItem(item());
    useWardrobe.getState().correctField("item_1", "color_primary", "navy");
    useWardrobe.getState().correctField("item_1", "color_primary", "indigo");

    const corrected = useWardrobe.getState().items[0];
    expect(corrected?.color_primary).toBe("indigo");
    expect(corrected?.corrected_fields).toEqual(["color_primary"]);
  });

  it("survives a later server payload that predates the correction", () => {
    // AI-EVAL-CASES Case 13: re-analysis must never overwrite a user correction.
    useWardrobe.getState().upsertItem(item());
    useWardrobe.getState().correctField("item_1", "color_primary", "navy");

    useWardrobe.getState().upsertItem(item({ color_primary: "black", corrected_fields: [] }));

    const merged = useWardrobe.getState().items[0];
    expect(merged?.corrected_fields).toContain("color_primary");
  });

  it("leaves other items untouched", () => {
    useWardrobe.getState().upsertItem(item({ item_id: "a" }));
    useWardrobe.getState().upsertItem(item({ item_id: "b" }));
    useWardrobe.getState().correctField("a", "color_primary", "navy");

    const b = useWardrobe.getState().items.find((i) => i.item_id === "b");
    expect(b?.color_primary).toBe("black");
  });
});

describe("composability", () => {
  it("is usable at three items — the first-run threshold", () => {
    for (const id of ["a", "b", "c"]) {
      useWardrobe.getState().upsertItem(item({ item_id: id }));
    }
    expect(useWardrobe.getState().canCompose(3)).toBe(true);
  });

  it("ignores items still being analysed", () => {
    useWardrobe.getState().upsertItem(item({ item_id: "a" }));
    useWardrobe.getState().upsertItem(item({ item_id: "b", status: "analyzing" }));
    expect(useWardrobe.getState().readyItems()).toHaveLength(1);
  });

  it("names missing roles rather than implying they can be filled", () => {
    useWardrobe.getState().upsertItem(item({ item_id: "a", category: "top" }));
    useWardrobe.getState().upsertItem(item({ item_id: "b", category: "bottom" }));

    const missing = useWardrobe.getState().missingRoles(["top", "bottom", "footwear"]);
    expect(missing).toEqual(["footwear"]);
  });

  it("reports no gap when every requested role is covered", () => {
    useWardrobe.getState().upsertItem(item({ item_id: "a", category: "top" }));
    useWardrobe.getState().upsertItem(item({ item_id: "b", category: "bottom" }));
    useWardrobe.getState().upsertItem(item({ item_id: "c", category: "footwear" }));

    expect(useWardrobe.getState().missingRoles(["top", "bottom", "footwear"])).toEqual([]);
  });
});

describe("preferences", () => {
  it("starts with working defaults so the step is genuinely skippable", () => {
    const { preferences, preferencesTouched } = useWardrobe.getState();
    expect(preferencesTouched).toBe(false);
    expect(preferences.occasion.length).toBeGreaterThan(0);
    expect(preferences.vibe.length).toBeGreaterThan(0);
    expect(preferences.fitPreference.length).toBeGreaterThan(0);
  });

  it("records that the user touched them, and can reset", () => {
    useWardrobe.getState().setPreferences({ occasion: "evening" });
    expect(useWardrobe.getState().preferencesTouched).toBe(true);

    useWardrobe.getState().resetPreferences();
    expect(useWardrobe.getState().preferences).toEqual(DEFAULT_PREFERENCES);
    expect(useWardrobe.getState().preferencesTouched).toBe(false);
  });
});

describe("removal", () => {
  it("removes only the named item", () => {
    useWardrobe.getState().upsertItem(item({ item_id: "a" }));
    useWardrobe.getState().upsertItem(item({ item_id: "b" }));
    useWardrobe.getState().removeItem("a");
    expect(useWardrobe.getState().items.map((i) => i.item_id)).toEqual(["b"]);
  });
});
