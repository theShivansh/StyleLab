"use client";

import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "@/lib/a11y";

/** Reveal everything after this long regardless of what fired. */
const SAFETY_MS = 2500;

/**
 * Reveals content once as it enters the viewport.
 *
 * The whole motion budget for the landing page runs through this one component, which is how
 * "do not animate everything" is enforced structurally rather than by discipline.
 *
 * ## Why there are three triggers
 *
 * Visibility must never depend on a single API firing. During S2 the page rendered
 * completely blank in a browser whose window was occluded: the browser throttled
 * IntersectionObserver so hard that a freshly-created observer never invoked its callback at
 * all. Content that is invisible until an observer fires is content that is sometimes
 * invisible, full stop.
 *
 * So three independent triggers, any of which reveals:
 *   1. IntersectionObserver — the normal path, gives the nice scroll-linked stagger.
 *   2. A scroll/resize position check — works when IO is throttled or unavailable.
 *   3. A 2.5s timer — covers "never scrolled, IO never fired".
 *
 * Plus two static escapes that need no JS at all: prefers-reduced-motion renders visible
 * immediately, and a <noscript> rule in layout.tsx forces every reveal visible. Under
 * reduced motion no observer or listener is attached in the first place.
 *
 * Every failure mode lands on "visible". That is the whole design rule here.
 */
export function Reveal({
  children,
  delayMs = 0,
  className,
}: {
  children: React.ReactNode;
  delayMs?: number;
  className?: string;
}) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion) return;

    const element = ref.current;
    if (!element) return;

    let settled = false;
    const cleanups: Array<() => void> = [];

    const reveal = () => {
      if (settled) return;
      settled = true;
      setShown(true);
      for (const cleanup of cleanups) cleanup();
      cleanups.length = 0;
    };

    // 1. IntersectionObserver — preferred, but never trusted as the only signal.
    if (typeof IntersectionObserver !== "undefined") {
      const observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            // "Already scrolled past" counts too: an instant jump (scrollTo, an anchor
            // link, a restored scroll position) moves past elements without them ever
            // being in the viewport for a frame.
            if (entry.isIntersecting || entry.boundingClientRect.bottom < 0) reveal();
          }
        },
        { rootMargin: "-8% 0px -8% 0px" },
      );
      observer.observe(element);
      cleanups.push(() => observer.disconnect());
    }

    // 2. Position check on scroll/resize, for when IO is throttled or missing.
    const checkPosition = () => {
      const rect = element.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.92) reveal();
    };
    checkPosition();
    if (!settled) {
      window.addEventListener("scroll", checkPosition, { passive: true });
      window.addEventListener("resize", checkPosition, { passive: true });
      cleanups.push(() => {
        window.removeEventListener("scroll", checkPosition);
        window.removeEventListener("resize", checkPosition);
      });
    }

    // 3. Last resort. Below-fold content revealing early is imperceptible; a permanently
    //    blank page is not.
    if (!settled) {
      const timer = window.setTimeout(reveal, SAFETY_MS);
      cleanups.push(() => window.clearTimeout(timer));
    }

    return () => {
      for (const cleanup of cleanups) cleanup();
    };
  }, [prefersReducedMotion]);

  const revealed = prefersReducedMotion || shown;

  return (
    <div
      ref={ref}
      className={className}
      // Visibility is driven by this attribute plus CSS, never an inline opacity, so a
      // transition that cannot run leaves the content visible rather than hidden.
      data-revealed={revealed ? "true" : "false"}
      style={revealed && !prefersReducedMotion ? { transitionDelay: `${delayMs}ms` } : undefined}
    >
      {children}
    </div>
  );
}
