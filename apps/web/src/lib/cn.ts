import { twMerge } from "tailwind-merge";

/**
 * Class-name joiner with Tailwind conflict resolution.
 *
 * The conflict resolution is not cosmetic. A component whose base styles set `inline-flex`
 * and whose caller passes `hidden sm:inline-flex` gets BOTH utilities, and the winner is
 * decided by Tailwind's stylesheet order rather than the order in the attribute — so the
 * element stays visible and the responsive intent is silently lost. That exact bug shipped
 * the navbar CTA at 375px in S2 and was caught by the overflow test, not by review.
 *
 * twMerge makes the last class in the string win, which is what every caller already assumes.
 */
export function cn(...values: Array<string | false | null | undefined>): string {
  return twMerge(values.filter(Boolean).join(" "));
}
