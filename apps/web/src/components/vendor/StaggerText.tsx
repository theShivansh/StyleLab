"use client";

import { useEffect, useState } from "react";
import { usePrefersReducedMotion } from "@/lib/a11y";
import { cn } from "@/lib/cn";

/**
 * A display line that rises into place one word at a time.
 *
 * Vendored from Vengeance UI `stagger-text` — MIT, github.com/Ashutoshx7/VengeanceUI, commit
 * 813d9c192b1f82cb36db3d5af93c2ac7d3285ae4 (docs/UX-UI-SPEC.md, library strategy). Kept: the
 * masked word rise and its ease. Rewritten on the way in, and ours from here:
 *
 * - **No framer-motion.** Upstream pulls in an animation runtime to translate a handful of
 *   spans; a CSS transition with a per-word delay is the same motion for no dependency.
 * - **Never waits on `whileInView` alone.** Upstream hides every word until an
 *   IntersectionObserver fires, which is the failure `components/motion/Reveal.tsx` exists to
 *   avoid: a throttled observer is a blank headline. Here the words rise on mount, a timer
 *   reveals them regardless, `layout.tsx`'s noscript rule covers JavaScript being off, and
 *   reduced motion renders them in place.
 * - **Real spaces between words**, not trailing non-breaking ones, so the heading's text is
 *   the sentence and not a string a screen reader or a test has to normalise.
 */

/** Delay between consecutive words. Upstream's 0.05s felt hurried at display size. */
const STAGGER_MS = 70;
/** Reveal regardless after this long — the same safety net `Reveal` uses. */
const SAFETY_MS = 2500;

export function StaggerText({
  text,
  delayMs = 0,
  className,
}: {
  text: string;
  delayMs?: number;
  className?: string;
}) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion) return;
    // Two frames: the armed state has to be painted once, or there is nothing to transition from.
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => setShown(true));
    });
    const timer = window.setTimeout(() => setShown(true), SAFETY_MS);
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
      window.clearTimeout(timer);
    };
  }, [prefersReducedMotion]);

  const words = text.split(" ");

  return (
    <span
      className={cn(className)}
      data-stagger={prefersReducedMotion || shown ? "shown" : "armed"}
    >
      {words.map((word, index) => (
        <span key={`${word}-${index}`}>
          <span className="stagger-mask">
            <span
              className="stagger-word"
              style={{ transitionDelay: `${delayMs + index * STAGGER_MS}ms` }}
            >
              {word}
            </span>
          </span>
          {index < words.length - 1 ? " " : null}
        </span>
      ))}
    </span>
  );
}
