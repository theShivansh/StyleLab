import { ButtonLink } from "@/components/ui/Button";
import { Reveal } from "@/components/motion/Reveal";
import { StaggerText } from "@/components/vendor/StaggerText";
import { HeroRead } from "@/components/landing/HeroRead";

/**
 * Hero. Copy from UX-UI-SPEC section 1: "YOUR WARDROBE. RECOMPOSED."
 *
 * The spec's secondary CTA was "Explore demo". Demo mode was removed
 * (docs/DECISIONS.md, 2026-09-12), so there is nothing to explore without uploading — the
 * secondary action scrolls to the explanation instead of promising a demo that cannot exist.
 *
 * Two columns since the landing refresh: the promise on the left, and on the right the thing
 * that makes it believable — a photograph being read, stage by stage (`HeroRead`). The motion
 * budget is spent on exactly two moments, the headline and the read; everything else here
 * reveals the way the rest of the page does.
 */

const PROMISES = [
  "Outfits only from garments you own",
  "Every guess marked as a guess",
  "Nothing for sale, no retailer involved",
];

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden">
      {/* Decorative: a warm wash and a faint lab grid, both fading out before the edges. */}
      <div aria-hidden="true" className="hero-backdrop pointer-events-none absolute inset-0" />
      <div aria-hidden="true" className="hero-grid pointer-events-none absolute inset-0" />

      <div className="relative mx-auto grid max-w-6xl items-center gap-14 px-5 pt-12 pb-20 md:px-8 md:pt-20 md:pb-28 lg:grid-cols-[1.1fr_0.9fr] lg:gap-10">
        <div>
          <Reveal>
            <p className="border-border bg-surface/80 text-eyebrow text-ink-muted inline-flex items-center gap-2.5 rounded-[var(--radius-pill)] border px-3.5 py-2 uppercase backdrop-blur-sm">
              <span aria-hidden="true" className="hero-dot" />
              Your wardrobe, recomposed by AI
            </p>
          </Reveal>

          {/* Sized to its column from lg up: the display scale assumes the full container, and in
              two columns "Your wardrobe." broke across lines at 1440px. */}
          <h1 className="text-display mt-6 max-w-[16ch] lg:max-w-none lg:text-[4rem] xl:text-[4.5rem]">
            <StaggerText text="Your wardrobe." delayMs={80} />
            <br />
            <StaggerText text="Recomposed." delayMs={260} className="text-accent-deep" />
          </h1>

          <Reveal delayMs={180}>
            <p className="text-lede text-ink-muted mt-7 max-w-[46ch]">
              Photograph the clothes you already own. STYLELAB reads each one into a wardrobe that
              understands itself, then styles outfits from what is actually in your closet.
            </p>
          </Reveal>

          <Reveal delayMs={260}>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
              <ButtonLink href="/wardrobe" size="lg" className="group">
                Start my wardrobe
                <span
                  aria-hidden="true"
                  className="transition-transform duration-[var(--duration-functional)] ease-[var(--ease-standard)] group-hover:translate-x-1 motion-reduce:transition-none"
                >
                  →
                </span>
              </ButtonLink>
              <ButtonLink href="#how" size="lg" variant="secondary">
                See how it works
              </ButtonLink>
            </div>
          </Reveal>

          <Reveal delayMs={340}>
            <ul className="text-ink-muted mt-8 grid gap-2.5 text-sm sm:grid-cols-1">
              {PROMISES.map((promise) => (
                <li key={promise} className="flex items-center gap-2.5">
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 16 16"
                    className="text-accent-deep h-4 w-4 shrink-0"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                  >
                    <path d="M3.5 8.5l3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {promise}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>

        <Reveal delayMs={200}>
          <HeroRead />
        </Reveal>
      </div>
    </section>
  );
}
