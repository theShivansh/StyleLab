"use client";

/**
 * Typed analytics, per docs/ANALYTICS.md: "Create a typed `AnalyticsClient` abstraction. Do
 * not scatter vendor event APIs across React components."
 *
 * There is no vendor yet — PostHog is wired up with the rest of the funnel in S9. What
 * exists now is the seam and the type, so that the events S7 owes (`item_swapped`,
 * `outfit_regenerated`, `outfit_saved`) are emitted from the right places with the right
 * payloads, and adding a sink later is one function.
 *
 * ## The payload type is the data-hygiene rule
 *
 * docs/ANALYTICS.md forbids sending image URLs, image content, secrets, free-form user text
 * and inferences about a person. A signed image URL is a live capability — putting one in an
 * analytics payload would hand a third party a working link to someone's photograph. So the
 * event map below names every property each event may carry, and none of them is a URL, a
 * garment name typed by a user, or anything derived from a photograph beyond the metadata
 * the wardrobe already shows.
 *
 * Item ids are allowed. They are opaque, scoped to one user's wardrobe, and useless without
 * a session token.
 */

export interface AnalyticsEvents {
  // --- wardrobe capture ---------------------------------------------------------------
  // Added in S11. docs/ANALYTICS.md has named these since S0 and only the composition half
  // was ever emitted — which left the funnel blind at exactly the step the spec calls the
  // one that matters: *"The drop-off that matters most is Landing → Images uploaded. With
  // no demo wardrobe, that step is the entire cold-start risk."*
  images_selected: { count: number; rejected: number };
  image_rejected: { reason: string };
  extraction_completed: { confidence: "high" | "mixed" | "low"; duration_ms: number };
  extraction_failed: { code: string };
  /**
   * A correction happened. **The field name only — never the old or new value.**
   *
   * docs/ANALYTICS.md asked for "field name, from → to", and S11 declined the second half.
   * The values of `subcategory`, `pattern`, `color_primary` and `fit` are free text written
   * by a vision model looking at a photograph taken inside somebody's home, and blocker B18
   * is open precisely because those fields can carry a description of a person in the
   * frame. Sending them to an analytics vendor would take the one channel we know is
   * imperfect and pipe it to a third party.
   *
   * The lost information is smaller than it looks. The KPI the spec actually wants is
   * *extraction acceptance rate* — fields kept versus corrected — and that is a count of
   * corrections per field, which is exactly what this carries.
   */
  extraction_field_corrected: { field: string };
  item_deleted: { role: string };
  wardrobe_cleared: { items: number };

  // --- composition --------------------------------------------------------------------
  compose_clicked: { items: number; occasion: string };
  composition_started: { occasion: string; vibe: string };
  composition_completed: { outfit_id: string; degradation_level: number; duration_ms: number };
  composition_failed: { code: string };
  insufficient_wardrobe: { missing_roles: string[] };
  outfit_viewed: { outfit_id: string; match_score: number; degradation_level: number };
  swap_opened: { outfit_id: string; role: string; alternatives: number };
  item_swapped: { outfit_id: string; role: string; delta: number };
  outfit_regenerated: { outfit_id: string | null };
  outfit_saved: { outfit_id: string };
  outfit_shared: { outfit_id: string; method: "clipboard" | "share_sheet" };
  wardrobe_gap_shown: { role: string; where: "compose" | "swap" | "result" };
}

export type AnalyticsEvent = keyof AnalyticsEvents;

/** Bumped when a payload changes shape, so a dashboard can tell the versions apart. */
export const SCHEMA_VERSION = 1;

export interface AnalyticsEnvelope<E extends AnalyticsEvent = AnalyticsEvent> {
  event: E;
  properties: AnalyticsEvents[E];
  schema_version: number;
  timestamp: string;
}

type Sink = (envelope: AnalyticsEnvelope) => void;

/**
 * Where events go. Replaced wholesale in S9 by a vendor sink; until then the default drops
 * them, and a test or a debugging session can install its own.
 *
 * Deliberately not console.log by default: a product that prints a running commentary of the
 * user's session to their devtools looks like it is leaking, whatever it is actually doing.
 */
let sink: Sink = () => {};

export function setAnalyticsSink(next: Sink): void {
  sink = next;
}

export function track<E extends AnalyticsEvent>(event: E, properties: AnalyticsEvents[E]): void {
  try {
    sink({
      event,
      properties,
      schema_version: SCHEMA_VERSION,
      timestamp: new Date().toISOString(),
    } as AnalyticsEnvelope);
  } catch {
    // Analytics must never be able to break the product. A sink that throws costs an event,
    // not the user's outfit.
  }
}
