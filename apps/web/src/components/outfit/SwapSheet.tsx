"use client";

import { useEffect, useState } from "react";
import { ButtonLink } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { cn } from "@/lib/cn";
import { track } from "@/lib/analytics";
import { getAlternatives } from "@/lib/api/outfits";
import { userMessage } from "@/lib/errors";
import type { Alternative, Alternatives } from "@/lib/schemas/outfit";
import type { GarmentCategory } from "@/lib/schemas/wardrobe";
import { describe } from "./LookSlot";

/**
 * "What if?" — the alternatives for one slot.
 *
 * Everything offered here is a garment the user owns. The list comes from the server, which
 * retrieves it ownership-scoped in SQL and scores each candidate *in this look* rather than
 * on its own; this component does not filter, rank or invent anything.
 *
 * Three states, and the third is the one that matters:
 *
 * * alternatives — pick one
 * * loading — a short named wait, not a bare spinner
 * * **none** — the honest answer for a small wardrobe. Name the gap, offer to add a garment,
 *   never conjure one (prompts/06, USER-FLOWS Flow 3).
 */
export function SwapSheet({
  outfitId,
  role,
  open,
  onClose,
  onChoose,
  busy,
}: {
  outfitId: string;
  role: GarmentCategory | null;
  open: boolean;
  onClose: () => void;
  onChoose: (alternative: Alternative) => void;
  busy: boolean;
}) {
  return (
    <Sheet open={open} onClose={onClose} title={role ? `Another ${role}?` : "What if?"}>
      {open && role && (
        // Keyed by role, so opening a different slot mounts a fresh list rather than
        // resetting one. It also means the list is refetched every time the sheet opens,
        // which matters after a swap: the garment that just went into the look must stop
        // being offered as an alternative to itself.
        <AlternativesList
          key={role}
          outfitId={outfitId}
          role={role}
          onChoose={onChoose}
          busy={busy}
        />
      )}
    </Sheet>
  );
}

function AlternativesList({
  outfitId,
  role,
  onChoose,
  busy,
}: {
  outfitId: string;
  role: GarmentCategory;
  onChoose: (alternative: Alternative) => void;
  busy: boolean;
}) {
  const [view, setView] = useState<Alternatives | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    void getAlternatives(outfitId, role, controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) return;
        setView(loaded);
        track("swap_opened", {
          outfit_id: outfitId,
          role,
          alternatives: loaded.alternatives.length,
        });
        if (loaded.gap) track("wardrobe_gap_shown", { role, where: "swap" });
      })
      .catch((failure) => {
        if (controller.signal.aborted) return;
        setError(userMessage(failure));
      });

    return () => controller.abort();
  }, [outfitId, role]);

  if (error) return <p className="text-danger text-sm">{error}</p>;

  if (view === null) {
    return (
      <p className="text-ink-muted text-sm" role="status">
        Reading your wardrobe…
      </p>
    );
  }

  if (view.alternatives.length === 0) {
    return <EmptySlot role={view.role} description={view.gap?.generic_description} />;
  }

  return (
    <ul className="space-y-2">
      {view.alternatives.map((alternative) => (
        <li key={alternative.item.item_id}>
          <AlternativeRow
            alternative={alternative}
            busy={busy}
            onChoose={() => onChoose(alternative)}
          />
        </li>
      ))}
    </ul>
  );
}

function AlternativeRow({
  alternative,
  onChoose,
  busy,
}: {
  alternative: Alternative;
  onChoose: () => void;
  busy: boolean;
}) {
  const { item, delta } = alternative;

  return (
    <button
      type="button"
      onClick={onChoose}
      disabled={busy}
      className={cn(
        "border-border hover:border-border-strong hover:bg-surface-muted flex w-full",
        "items-center gap-4 rounded-[var(--radius-card)] border p-3 text-left",
        "transition-colors duration-[var(--duration-functional)]",
        "disabled:pointer-events-none disabled:opacity-45",
      )}
    >
      <span className="bg-surface-muted size-16 shrink-0 overflow-hidden rounded-[var(--radius-card)]">
        {item.image_url && (
          // eslint-disable-next-line @next/next/no-img-element -- the optimiser would cache a private photograph unsigned
          <img
            src={item.image_url}
            alt={describe(item)}
            decoding="async"
            className="h-full w-full object-cover"
          />
        )}
      </span>

      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm">{describe(item)}</span>
        <span className="text-ink-muted block text-xs">{deltaLabel(delta)}</span>
      </span>
    </button>
  );
}

/**
 * What the swap would do to the look's score, in words.
 *
 * A negative delta is shown as readily as a positive one. The score is a heuristic, and a
 * swap the user wants for reasons it cannot see is still theirs to make — hiding the number
 * would be deciding for them.
 */
function deltaLabel(delta: number): string {
  if (delta > 0) return `+${delta} to the look`;
  if (delta < 0) return `${delta} to the look`;
  return "About the same for this look";
}

function EmptySlot({ role, description }: { role: string; description?: string | undefined }) {
  return (
    <div className="space-y-3">
      <p className="text-sm">
        This is the only {role} in your wardrobe, so there is nothing to swap it for.
      </p>
      {description && (
        <p className="text-ink-muted text-sm">
          Add {description} and this slot becomes a choice.
        </p>
      )}
      <ButtonLink href="/wardrobe" size="lg">
        Add a {role}
      </ButtonLink>
    </div>
  );
}
