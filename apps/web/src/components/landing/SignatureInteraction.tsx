import { Reveal } from "@/components/motion/Reveal";
import { Chip } from "@/components/ui/Chip";
import { cn } from "@/lib/cn";

/**
 * The signature interaction: swap one slot, leave the rest still.
 *
 * Presented as a diagram rather than a live widget. The real interaction needs a wardrobe,
 * and a fake interactive version on a landing page would be a promise the product has to
 * keep twice. The live one arrives in S7 (prompts/06-RESULT-REMIX.md).
 */

const SLOTS = [
  { role: "Top", value: "Oxford shirt", changed: false },
  { role: "Bottom", value: "Straight jeans", changed: true },
  { role: "Footwear", value: "Leather sneaker", changed: false },
  { role: "Layer", value: "Unstructured blazer", changed: false },
] as const;

export function SignatureInteraction() {
  return (
    <section className="border-border bg-surface border-y">
      <div className="mx-auto grid max-w-6xl gap-12 px-5 py-20 md:px-8 md:py-28 lg:grid-cols-2 lg:items-center">
        <Reveal>
          <p className="text-eyebrow text-ink-muted uppercase">Signature interaction</p>
          <h2 className="text-headline mt-4 max-w-[22ch] text-balance">
            Change one thing, not everything.
          </h2>
          <p className="text-lede text-ink-muted mt-6 max-w-[46ch]">
            Ask <em>what if?</em> and swap a single slot. The other pieces hold still — no page
            reload, no rebuild, no losing the look you almost liked. Alternatives are drawn only
            from your own closet, so an empty list is an honest answer.
          </p>
        </Reveal>

        <Reveal delayMs={100}>
          <ul className="space-y-2.5" aria-label="Outfit slots, with one swapped">
            {SLOTS.map((slot) => (
              <li
                key={slot.role}
                className={cn(
                  "flex items-center justify-between gap-4 rounded-[var(--radius-control)] border p-4",
                  slot.changed
                    ? "border-accent/35 bg-accent-soft/45"
                    : "border-border bg-bg opacity-70",
                )}
              >
                <div>
                  <p className="text-eyebrow text-ink-muted uppercase">{slot.role}</p>
                  <p className="mt-1.5 text-sm font-medium">{slot.value}</p>
                </div>
                {slot.changed ? (
                  <Chip tone="accent">swapped</Chip>
                ) : (
                  <span className="text-ink-muted text-xs">unchanged</span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-ink-muted/70 mt-4 text-xs">
            Diagram of the interaction. Garment names are placeholders.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
