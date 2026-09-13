import { afterEach, describe, expect, it, vi } from "vitest";
import {
  SCHEMA_VERSION,
  setAnalyticsSink,
  track,
  type AnalyticsEnvelope,
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
