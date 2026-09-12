import { ButtonLink } from "@/components/ui/Button";
import { Reveal } from "@/components/motion/Reveal";

/**
 * Hero. Copy from UX-UI-SPEC section 1: "YOUR WARDROBE. RECOMPOSED."
 *
 * The spec's secondary CTA was "Explore demo". Demo mode was removed
 * (docs/DECISIONS.md, 2026-09-12), so there is nothing to explore without uploading — the
 * secondary action scrolls to the explanation instead of promising a demo that cannot exist.
 */
export function Hero() {
  return (
    <section id="top" className="mx-auto max-w-6xl px-5 pt-16 pb-20 md:px-8 md:pt-24 md:pb-28">
      <Reveal>
        <p className="text-eyebrow text-ink-muted uppercase">Your wardrobe, recomposed by AI</p>
      </Reveal>

      <Reveal delayMs={60}>
        <h1 className="text-display mt-5 max-w-[16ch] text-balance">
          Your wardrobe.
          <br />
          <span className="text-accent-deep">Recomposed.</span>
        </h1>
      </Reveal>

      <Reveal delayMs={120}>
        <p className="text-lede text-ink-muted mt-7 max-w-[46ch]">
          Photograph the clothes you already own. STYLELAB reads each one into a wardrobe that
          understands itself, then styles outfits from what is actually in your closet.
        </p>
      </Reveal>

      <Reveal delayMs={180}>
        <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
          <ButtonLink href="/wardrobe" size="lg">
            Start my wardrobe
          </ButtonLink>
          <ButtonLink href="#how" size="lg" variant="secondary">
            See how it works
          </ButtonLink>
        </div>
      </Reveal>

      <Reveal delayMs={240}>
        <p className="text-ink-muted mt-6 text-sm">
          Six photos is enough to begin. Nothing is for sale here, and no retailer is involved.
        </p>
      </Reveal>
    </section>
  );
}
