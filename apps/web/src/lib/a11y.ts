"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

/**
 * Accessibility primitives.
 *
 * QA-RELEASE gates on keyboard navigation, visible focus, and reduced motion. These are the
 * shared pieces so each screen does not reimplement them slightly differently.
 */

const reducedMotionQuery = "(prefers-reduced-motion: reduce)";

function subscribeToReducedMotion(onChange: () => void): () => void {
  const query = window.matchMedia(reducedMotionQuery);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/**
 * Tracks prefers-reduced-motion.
 *
 * useSyncExternalStore rather than useState+useEffect: matchMedia is an external store, and
 * subscribing to it this way avoids the cascading-render pattern the React Compiler rejects,
 * while still giving a correct SSR snapshot.
 *
 * Components must use this to skip animation entirely rather than shortening it — and a
 * state change the user needs to perceive still has to be perceivable without the motion.
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeToReducedMotion,
    () => window.matchMedia(reducedMotionQuery).matches,
    () => false, // server snapshot: assume motion is fine, correct on hydration
  );
}

/**
 * Announces a message to screen readers via a polite live region.
 *
 * The upload flow needs this: cards resolve independently and asynchronously, so a sighted
 * user sees progress that a screen-reader user would otherwise miss entirely.
 */
export function useAnnouncer(): (message: string) => void {
  const regionRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const element = document.createElement("div");
    element.setAttribute("aria-live", "polite");
    element.setAttribute("aria-atomic", "true");
    element.className = "sr-only";
    document.body.appendChild(element);
    regionRef.current = element;

    return () => {
      element.remove();
      regionRef.current = null;
    };
  }, []);

  return useCallback((message: string) => {
    const region = regionRef.current;
    if (!region) return;

    // Clearing first forces re-announcement of an identical consecutive message.
    region.textContent = "";
    window.setTimeout(() => {
      // The region may have unmounted during the timeout.
      if (regionRef.current) regionRef.current.textContent = message;
    }, 50);
  }, []);
}

/** Stable id helper for label/description wiring. */
export function describedBy(...ids: Array<string | false | null | undefined>): string | undefined {
  const present = ids.filter((id): id is string => Boolean(id));
  return present.length > 0 ? present.join(" ") : undefined;
}
