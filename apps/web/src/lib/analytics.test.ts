import { afterEach, describe, expect, it, vi } from "vitest";
import {
  SCHEMA_VERSION,
  setAnalyticsSink,
  track,
  type AnalyticsEnvelope,
  type AnalyticsEvents,
} from "./analytics";

/**
 * The analytics seam.
 *
 * Two things worth holding: the envelope every event carries, and the rule that analytics can
 * never break the product. The payload *types* are the data-hygiene rule and are enforced by
 * the compiler — a test cannot assert that an image URL is unrepresentable, but `tsc` refuses
 * the code that would send one.
 */

function collector() {
  const seen: AnalyticsEnvelope[] = [];
  setAnalyticsSink((envelope) => seen.push(envelope));
  return seen;
}

afterEach(() => {
  setAnalyticsSink(() => {});
});

describe("the analytics seam", () => {
  it("wraps an event with its schema version and a timestamp", () => {
    const seen = collector();

    track("item_swapped", { outfit_id: "outfit_1", role: "footwear", delta: 4 });

    expect(seen).toHaveLength(1);
    expect(seen[0]?.event).toBe("item_swapped");
    expect(seen[0]?.properties).toEqual({
      outfit_id: "outfit_1",
      role: "footwear",
      delta: 4,
    });
    expect(seen[0]?.schema_version).toBe(SCHEMA_VERSION);
    expect(Date.parse(seen[0]?.timestamp ?? "")).not.toBeNaN();
  });

  it("carries the three events this phase owes", () => {
    // prompts/06 acceptance: "analytics fire for swap, regenerate, and save".
    const seen = collector();

    track("item_swapped", { outfit_id: "o1", role: "top", delta: -3 });
    track("outfit_regenerated", { outfit_id: "o1" });
    track("outfit_saved", { outfit_id: "o1" });

    expect(seen.map((e) => e.event)).toEqual([
      "item_swapped",
      "outfit_regenerated",
      "outfit_saved",
    ]);
  });

  it("drops events by default rather than printing them", () => {
    // A product that prints a running commentary of the session to the devtools console
    // looks like it is leaking, whatever it is actually doing.
    const spy = vi.spyOn(console, "log").mockImplementation(() => {});

    track("outfit_saved", { outfit_id: "o1" });

    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("never lets a broken sink break the product", () => {
    setAnalyticsSink(() => {
      throw new Error("the vendor SDK fell over");
    });

    // An analytics failure costs an event, not the user's outfit.
    expect(() => track("outfit_saved", { outfit_id: "o1" })).not.toThrow();
  });
});

describe("the capture half of the funnel", () => {
  it("emits the events docs/ANALYTICS.md names for the step that matters most", () => {
    // *"The drop-off that matters most is Landing → Images uploaded. With no demo wardrobe,
    // that step is the entire cold-start risk."* Every one of these was in the spec from S0
    // and none was emitted until S11 — the funnel was instrumented from `compose_clicked`
    // onwards, which is to say from after the point where people actually leave.
    const events: Array<keyof AnalyticsEvents> = [
      "images_selected",
      "image_rejected",
      "extraction_completed",
      "extraction_failed",
      "extraction_field_corrected",
      "item_deleted",
      "wardrobe_cleared",
    ];
    const seen: string[] = [];
    setAnalyticsSink((envelope) => seen.push(envelope.event));

    track("images_selected", { count: 3, rejected: 0 });
    track("image_rejected", { reason: "unsupported format" });
    track("extraction_completed", { confidence: "mixed", duration_ms: 1841 });
    track("extraction_failed", { code: "EXTRACTION_FAILED" });
    track("extraction_field_corrected", { field: "color_primary" });
    track("item_deleted", { role: "top" });
    track("wardrobe_cleared", { items: 6 });

    expect(seen).toEqual(events);
  });

  it("sends the corrected field's name and never its value", () => {
    // The spec asked for "field name, from → to" and S11 declined the second half. The
    // values of `subcategory`, `pattern`, `color_primary` and `fit` are free text a vision
    // model wrote while looking at a photograph taken inside somebody's home, and blocker
    // B18 is open precisely because they can carry a description of a person in the frame.
    //
    // Asserted on the payload's shape rather than on one string, so adding the value back
    // is a red test rather than a quiet regression.
    let captured: Record<string, unknown> = {};
    setAnalyticsSink((envelope) => {
      captured = envelope.properties as Record<string, unknown>;
    });

    track("extraction_field_corrected", { field: "subcategory" });

    expect(Object.keys(captured)).toEqual(["field"]);
    expect(Object.values(captured).join(" ")).not.toContain("navy");
  });
});
