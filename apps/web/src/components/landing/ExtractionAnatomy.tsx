import { Reveal } from "@/components/motion/Reveal";
import { GarmentCard } from "@/components/wardrobe/GarmentCard";
import { Card } from "@/components/ui/Card";
import { wardrobeItemSchema } from "@/lib/schemas/wardrobe";

/**
 * Replaces the "sample looks" section in UX-UI-SPEC section 1.
 *
 * Sample looks would need garment photography, and the project ships zero garment assets by
 * decision (docs/DECISIONS.md — B1/B2 closed by the wardrobe pivot). Rather than fabricate a
 * closet, this section shows the thing that actually differentiates the product: how a
 * model's reading is presented when it is unsure, and what happens when the user corrects it.
 *
 * The two cards below are interface illustrations, labelled as such. They are parsed through
 * the real schema so this section cannot drift from the live contract.
 */

const hedgedItem = wardrobeItemSchema.parse({
  item_id: "illustration-1",
  status: "ready",
  category: "top",
  subcategory: "oxford shirt",
  color_primary: "black",
  color_secondary: null,
  pattern: "solid",
  material_guess: "cotton",
  fit: "regular",
  formality: "smart-casual",
  field_confidence: {
    category: 0.97,
    subcategory: 0.88,
    color_primary: 0.52,
    material_guess: 0.41,
  },
  corrected_fields: [],
  quality_warnings: ["low_light"],
  image_url: "",
});

const correctedItem = wardrobeItemSchema.parse({
  ...hedgedItem,
  item_id: "illustration-2",
  color_primary: "navy",
  corrected_fields: ["color_primary"],
  quality_warnings: [],
});

export function ExtractionAnatomy() {
  return (
    <section id="honesty" className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
      <Reveal>
        <p className="text-eyebrow text-ink-muted uppercase">Anatomy of a read</p>
        <h2 className="text-headline mt-4 max-w-[28ch] text-balance">
          A guess is shown as a guess.
        </h2>
        <p className="text-lede text-ink-muted mt-6 max-w-[52ch]">
          Vision models are confidently wrong about colour under bad light. So confidence is part of
          the interface, not hidden behind it — and correcting the model is a normal thing to do
          rather than an apology for it.
        </p>
      </Reveal>

      <div className="mt-12 grid items-start gap-6 lg:grid-cols-[1fr_1fr_1.1fr]">
        <Reveal delayMs={60}>
          <p className="text-ink-muted mb-3 text-sm font-medium">Before — the model is unsure</p>
          <GarmentCard item={hedgedItem} />
        </Reveal>

        <Reveal delayMs={130}>
          <p className="text-ink-muted mb-3 text-sm font-medium">After — you corrected it</p>
          <GarmentCard item={correctedItem} />
        </Reveal>

        <Reveal delayMs={200}>
          <Card className="p-6 lg:mt-9">
            <h3 className="text-title">What that buys you</h3>
            <ul className="text-ink-muted mt-4 space-y-3 text-sm leading-relaxed">
              <li>
                <strong className="text-ink font-medium">Material is a guess, and says so.</strong>{" "}
                Nothing here claims to know fibre content from a photograph.
              </li>
              <li>
                <strong className="text-ink font-medium">Your correction is final.</strong>{" "}
                Re-running the analysis never overwrites a field you have set.
              </li>
              <li>
                <strong className="text-ink font-medium">
                  Every outfit traces to an item you own.
                </strong>{" "}
                The model cannot introduce a garment that is not in your closet.
              </li>
            </ul>
            <p className="text-ink-muted/70 mt-5 text-xs">
              Cards above are interface illustrations, not a real wardrobe.
            </p>
          </Card>
        </Reveal>
      </div>
    </section>
  );
}
