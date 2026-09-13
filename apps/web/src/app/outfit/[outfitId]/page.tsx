"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { LookSlot } from "@/components/outfit/LookSlot";
import { StyleMatch } from "@/components/outfit/StyleMatch";
import { SwapSheet } from "@/components/outfit/SwapSheet";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { useAnnouncer } from "@/lib/a11y";
import { track } from "@/lib/analytics";
import { useComposition } from "@/lib/use-composition";
import { useWardrobe } from "@/lib/wardrobe-store";
import { getOutfit, saveOutfit, swapSlot } from "@/lib/api/outfits";
import { userMessage } from "@/lib/errors";
import type { Alternative, Outfit } from "@/lib/schemas/outfit";
import type { GarmentCategory } from "@/lib/schemas/wardrobe";

/**
 * The result screen — the strongest product moment.
 *
 * Everything on it traces to a garment the user owns. There is no price, no total and no way
 * to buy anything, because the product sells nothing (docs/DECISIONS.md).
 *
 * ## Why the whole outfit is replaced on a swap
 *
 * `swapSlot` returns the entire look and this component renders that payload wholesale.
 * Merging a partial response into local state is how a screen ends up showing a combination
 * the wardrobe does not agree with — the acceptance criterion for this phase is exactly
 * "visual state never disagrees with wardrobe state", and one payload from one authority is
 * the cheapest way to hold it.
 *
 * The interaction still *reads* as one slot changing: the other slots re-render with
 * identical props, so nothing about them moves, and only the changed card animates.
 */
export default function OutfitPage() {
  const params = useParams<{ outfitId: string }>();
  const outfitId = params.outfitId;
  const announce = useAnnouncer();
  const preferences = useWardrobe((s) => s.preferences);
  const composition = useComposition();

  const [outfit, setOutfit] = useState<Outfit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [swapping, setSwapping] = useState<GarmentCategory | null>(null);
  const [settled, setSettled] = useState<GarmentCategory | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const viewed = useRef(false);
  const composing = composition.state === "composing";

  useEffect(() => {
    const controller = new AbortController();
    void getOutfit(outfitId, controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) return;
        setOutfit(loaded);
        if (!viewed.current) {
          viewed.current = true;
          track("outfit_viewed", {
            outfit_id: loaded.outfit_id,
            match_score: loaded.match_score,
            degradation_level: loaded.degradation_level,
          });
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(userMessage(failure));
      });
    return () => controller.abort();
  }, [outfitId]);

  const handleSwap = useCallback(
    async (alternative: Alternative) => {
      const role = swapping;
      if (!role) return;

      setBusy(true);
      try {
        const updated = await swapSlot(outfitId, role, alternative.item.item_id);
        setOutfit(updated);
        setSwapping(null);
        setSettled(role);
        track("item_swapped", {
          outfit_id: outfitId,
          role,
          delta: alternative.delta,
        });
        announce(`${role} swapped. Style Match is now ${updated.match_score}.`);
      } catch (failure) {
        setError(userMessage(failure));
      } finally {
        setBusy(false);
      }
    },
    [announce, outfitId, swapping],
  );

  const handleSave = useCallback(async () => {
    if (!outfit) return;
    setBusy(true);
    try {
      await saveOutfit(outfit.outfit_id);
      setOutfit({ ...outfit, saved: true });
      track("outfit_saved", { outfit_id: outfit.outfit_id });
      announce("Look saved.");
    } catch (failure) {
      setError(userMessage(failure));
    } finally {
      setBusy(false);
    }
  }, [announce, outfit]);

  /**
   * Share copies the look as text, and deliberately not as a link.
   *
   * A link to this page would only work for the person who composed it: the images are
   * served against a signed, expiring capability tied to one owner. A URL that silently
   * fails for everyone the user sends it to is a worse feature than no URL, and making it
   * work would mean publishing someone's private photographs. A rendered share card with no
   * live image capability is the real answer, and it lands with `flags.shareCards`.
   */
  const handleShare = useCallback(async () => {
    if (!outfit) return;
    const lines = [
      `${outfit.name} — ${outfit.occasion}`,
      ...outfit.slots.map((slot) => `${slot.role}: ${slotText(slot.item)}`),
      "Styled from my own wardrobe with STYLELAB.",
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      track("outfit_shared", { outfit_id: outfit.outfit_id, method: "clipboard" });
      announce("Look copied to your clipboard.");
    } catch {
      setError("Your browser wouldn't let us reach the clipboard.");
    }
  }, [announce, outfit]);

  /**
   * Compose again, from here.
   *
   * The same endpoint as the first composition — there is no `regenerate` route, because a
   * second endpoint would have been a synonym for the first with a different name in the log.
   * The distinction docs/ANALYTICS.md wants lives in the event, which is where it belongs.
   *
   * The occasion comes off the look being regenerated rather than from the store: the user
   * asked for another take on *this*, and it is their preferences that vary, not the brief.
   * `useComposition` routes to the new look when it lands.
   */
  const handleRegenerate = useCallback(() => {
    if (!outfit) return;
    track("outfit_regenerated", { outfit_id: outfit.outfit_id });
    void composition.start({
      occasion: outfit.occasion,
      vibe: preferences.vibe,
      fitPreference: preferences.fitPreference,
      colorPreferences: preferences.colorPreferences,
    });
  }, [composition, outfit, preferences]);

  if (error && !outfit) {
    return (
      <Shell>
        <Card className="p-6">
          <h1 className="text-title">That look isn&apos;t here</h1>
          <p className="text-ink-muted mt-2 text-sm">{error}</p>
          <ButtonLink href="/compose" size="lg" className="mt-5">
            Compose another
          </ButtonLink>
        </Card>
      </Shell>
    );
  }

  if (!outfit) {
    return (
      <Shell>
        <p className="text-ink-muted text-sm" role="status">
          Reading your look…
        </p>
      </Shell>
    );
  }

  const complete = outfit.status === "ready";

  return (
    <Shell>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-eyebrow text-ink-muted uppercase">{outfit.occasion}</p>
          <h1 className="text-headline mt-1">{outfit.name}</h1>
        </div>
        {outfit.saved && <Chip tone="accent">Saved</Chip>}
      </header>

      {outfit.status === "incomplete" && (
        // Case 14. Say which piece went missing and offer the repair — never a broken image
        // and never a silently shorter look.
        <Card className="border-hedged/40 mt-6 border p-5">
          <h2 className="text-title">
            This look is missing its {outfit.missing_roles.join(" and ")}
          </h2>
          <p className="text-ink-muted mt-2 text-sm">
            You removed that garment from your wardrobe. Pick another and the look is whole
            again — nothing gets substituted on your behalf.
          </p>
        </Card>
      )}

      {error && (
        <p className="text-danger mt-6 text-sm" role="alert">
          {error}
        </p>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[2fr_1fr] lg:items-start">
        {/* The garments are the point of this screen, so they get the width. UX-UI-SPEC:
            large imagery, editorial layout — a result page whose photographs are thumbnails
            is a spreadsheet with pictures. */}
        <section aria-label="The look" className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {outfit.slots.map((slot) => (
            <LookSlot
              key={slot.role}
              slot={slot}
              busy={busy}
              settling={settled === slot.role}
              onSwap={() => setSwapping(slot.role)}
            />
          ))}
        </section>

        <aside className="space-y-6">
          {/* An incomplete look gets no score and no styling notes.
              Both describe the combination that was composed, and one of its pieces is gone:
              a Style Match of 84 for a look missing its trousers, next to a tip about
              cuffing them, is the visual state disagreeing with the wardrobe state. The
              swap path rewrites the narration server-side; a deletion cannot rescore a look
              with a hole in it, so the honest thing is to stop showing a number until the
              look is whole again. */}
          {complete ? (
            <StyleMatch
              score={outfit.match_score}
              rationale={outfit.rationale}
              degradationLevel={outfit.degradation_level}
            />
          ) : (
            <Card className="p-6">
              <p className="text-eyebrow text-ink-muted uppercase">Style Match</p>
              <p className="text-ink-muted mt-2 text-sm">
                Held back until the look is whole. Scoring a look with a piece missing would
                be scoring something you cannot wear.
              </p>
            </Card>
          )}

          <div className="flex flex-wrap gap-2">
            <Button size="lg" onClick={handleSave} disabled={busy || outfit.saved}>
              {outfit.saved ? "Saved" : "Save this look"}
            </Button>
            <Button variant="secondary" onClick={handleShare} disabled={busy}>
              {copied ? "Copied" : "Copy the look"}
            </Button>
            <Button
              variant="ghost"
              onClick={handleRegenerate}
              disabled={busy || composing}
            >
              {composing ? "Composing…" : "Regenerate"}
            </Button>
          </div>

          {composing && (
            // The server's own stage name. Named work, never a bare spinner.
            <p className="text-ink-muted text-sm" role="status" aria-live="polite">
              {composition.stage ?? "reading your wardrobe"}…
            </p>
          )}

          {composition.state === "gap" && (
            <p className="text-ink-muted text-sm">
              Your wardrobe can&apos;t fill{" "}
              {composition.gap?.missing_roles.join(" or ") ?? "every slot"} right now, so this
              look stands. Nothing gets substituted.
            </p>
          )}

          {complete && outfit.pro_tips.length > 0 && (
            <Card className="p-5">
              <h2 className="text-eyebrow text-ink-muted uppercase">Pro tips</h2>
              <ul className="mt-3 space-y-2">
                {outfit.pro_tips.map((tip) => (
                  <li key={tip.tip} className="text-sm">
                    {tip.tip}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {complete && outfit.budget_tricks.length > 0 && (
            <Card className="p-5">
              <h2 className="text-eyebrow text-ink-muted uppercase">More from what you own</h2>
              <ul className="mt-3 space-y-2">
                {outfit.budget_tricks.map((trick) => (
                  <li key={trick} className="text-sm">
                    {trick}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {complete && outfit.trend_notes.length > 0 && (
            <Card className="p-5">
              <h2 className="text-eyebrow text-ink-muted uppercase">What&apos;s current</h2>
              {/*
                Every claim carries its publication, its date and a link, because a trend the
                reader cannot check is a trend we are asking them to take on faith — and the
                whole reason this comes from a search adapter rather than the model is that we
                are not asking them to. A note that lost any of the three was dropped before
                it reached this page.
              */}
              <ul className="mt-3 space-y-3">
                {outfit.trend_notes.map((note) => (
                  <li key={note.url} className="text-sm">
                    {note.trend}
                    <span className="text-ink-muted block text-xs">
                      <a
                        href={note.url}
                        target="_blank"
                        rel="noopener noreferrer nofollow"
                        className="hover:text-ink underline underline-offset-2"
                      >
                        {note.source}
                      </a>
                      {" · "}
                      {formatDate(note.published_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {outfit.wardrobe_gaps.length > 0 && (
            <Card className="p-5">
              <h2 className="text-eyebrow text-ink-muted uppercase">What would unlock more</h2>
              <ul className="mt-3 space-y-2">
                {outfit.wardrobe_gaps.map((gap) => (
                  <li key={gap.category} className="text-sm">
                    {gap.generic_description}
                    {typeof gap.unlocks_outfits === "number" && gap.unlocks_outfits > 0 && (
                      <span className="text-ink-muted">
                        {" "}
                        — {gap.unlocks_outfits} more look
                        {gap.unlocks_outfits === 1 ? "" : "s"}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              {/* Generic only. No brand, price, merchant or link — the product sells nothing. */}
              <p className="text-ink-muted mt-3 text-xs">
                Described generically on purpose. We don&apos;t sell anything and we
                won&apos;t send you anywhere to buy it.
              </p>
            </Card>
          )}

          <p className="text-ink-muted text-xs">
            Every piece here is one you photographed.{" "}
            <Link href="/wardrobe" className="underline">
              Your wardrobe
            </Link>
          </p>
        </aside>
      </div>

      <SwapSheet
        outfitId={outfit.outfit_id}
        role={swapping}
        open={swapping !== null}
        onClose={() => setSwapping(null)}
        onChoose={handleSwap}
        busy={busy}
      />
    </Shell>
  );
}

/**
 * A publication date, readably.
 *
 * Falls back to the raw string rather than throwing or hiding: a date we cannot parse is
 * still a date the publisher gave, and showing it is more honest than showing nothing beside
 * a claim about what is current.
 */
function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 md:px-8 md:py-16">
      <Link href="/compose" className="text-ink-muted hover:text-ink text-sm">
        ← Compose
      </Link>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function slotText(item: Outfit["slots"][number]["item"]): string {
  if (!item) return "(removed)";
  return [item.color_primary, item.pattern, item.subcategory ?? item.category]
    .filter(Boolean)
    .join(" ");
}
