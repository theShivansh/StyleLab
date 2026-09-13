"use client";

import { Chip } from "@/components/ui/Chip";
import { cn } from "@/lib/cn";
import { config } from "@/lib/config";
import type { OutfitSlot } from "@/lib/schemas/outfit";
import { describeGarment, isHedged, type WardrobeItem } from "@/lib/schemas/wardrobe";

/**
 * One role in the look, and whatever is filling it.
 *
 * Two states, both first-class:
 *
 * * **Filled** — the user's own photograph, large, with a swap affordance.
 * * **Empty** — the garment was deleted after this look was composed. The slot keeps its
 *   place and says which piece went missing, because a look that quietly got shorter is the
 *   silent gap docs/AI-EVAL-CASES.md Case 14 forbids. The swap affordance becomes the repair.
 *
 * `settling` drives a short animation on **this card only**. That is the product promise made
 * visible: one slot changed, so one slot moves. Reduced motion removes it globally
 * (globals.css) and the swap still reads, because the image and the label have changed.
 */
export function LookSlot({
  slot,
  onSwap,
  settling = false,
  busy = false,
}: {
  slot: OutfitSlot;
  onSwap: () => void;
  settling?: boolean;
  busy?: boolean;
}) {
  const item = slot.item;

  return (
    <figure
      className="group relative"
      data-slot-role={slot.role}
      data-slot-settle={settling || undefined}
      data-testid={`slot-${slot.role}`}
    >
      <div
        className={cn(
          "bg-surface-muted relative aspect-[4/5] w-full overflow-hidden",
          "rounded-[var(--radius-card-lg)]",
          !item && "border-border border border-dashed",
        )}
      >
        {item ? (
          <SlotImage item={item} />
        ) : (
          <div className="text-ink-muted grid h-full w-full place-items-center px-6 text-center">
            <p className="text-sm">The {slot.role} you had here was removed from your wardrobe.</p>
          </div>
        )}
      </div>

      <figcaption className="mt-3 space-y-1">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-eyebrow text-ink-muted uppercase">{slot.role}</span>
          <button
            type="button"
            onClick={onSwap}
            disabled={busy}
            aria-label={`Swap the ${slot.role}`}
            className={cn(
              "text-accent-deep hover:bg-accent-soft inline-flex min-h-[var(--size-touch)]",
              "items-center rounded-[var(--radius-pill)] px-3 text-sm font-medium",
              "transition-colors duration-[var(--duration-functional)]",
              "disabled:pointer-events-none disabled:opacity-45",
            )}
          >
            {item ? "Swap" : `Choose a ${slot.role}`}
          </button>
        </div>

        {item && (
          <>
            <p className="text-sm">{describe(item)}</p>
            {isHedged(item, "material_guess", config.confidenceFloor) && item.material_guess && (
              // A guess must look like a guess, on this screen as much as on the card.
              <Chip tone="hedged" className="px-2 py-0.5 text-[10px]">
                {item.material_guess} — best guess
              </Chip>
            )}
          </>
        )}
      </figcaption>
    </figure>
  );
}

/**
 * Colour, pattern and cut. Never a claim about material, fit on a body, or the wearer.
 *
 * Delegates to `describeGarment`, which is where the same expression used to live three
 * times over — with the same defect in each (S11 found `white solid_color sneaker` on the
 * result screen).
 */
export function describe(item: WardrobeItem): string {
  return describeGarment(item) || "A garment from your wardrobe";
}

/**
 * A plain `<img>`, for the reason set out in `wardrobe/GarmentCard.tsx`: `next/image` caches
 * every photograph on the Next server's disk, outside the private store and outside the
 * deletion flow. One unsigned copy of a user's wardrobe is one too many.
 */
function SlotImage({ item }: { item: WardrobeItem }) {
  if (!item.image_url) {
    return (
      <div className="text-ink-muted/25 grid h-full w-full place-items-center" aria-hidden="true">
        <svg
          viewBox="0 0 64 64"
          className="w-1/3"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M24 8l8 6 8-6 12 8-4 10-4-2v30H20V24l-4 2-4-10z" strokeLinejoin="round" />
        </svg>
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- the optimiser's disk cache would hold an unsigned copy of a private photograph
    <img
      src={item.image_url}
      alt={`${describe(item)}, from your wardrobe`}
      decoding="async"
      className="h-full w-full object-cover"
    />
  );
}
