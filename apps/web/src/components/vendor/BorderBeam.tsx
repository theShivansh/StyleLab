import { cn } from "@/lib/cn";

/**
 * A short light travelling around the edge of its parent.
 *
 * Vendored from Vengeance UI `border-beam` — MIT, github.com/Ashutoshx7/VengeanceUI, commit
 * 813d9c192b1f82cb36db3d5af93c2ac7d3285ae4. Kept: the offset-path technique and the masked
 * border. Changed on the way in:
 *
 * - The keyframes and styles live in `globals.css` as `.border-beam`, rather than a `<style>`
 *   element injected by every instance and a dozen arbitrary Tailwind classes.
 * - Colours default to the accent tokens. Upstream's orange-to-violet is exactly the "neon
 *   everywhere" CLAUDE.md rules out; one controlled pink is the brand.
 * - Decorative, so hidden from assistive technology, and not rendered at all under reduced
 *   motion (the CSS removes it) — a beam frozen mid-edge is a smudge, not a state.
 *
 * The parent needs `position: relative` and a border radius to inherit.
 */
export function BorderBeam({
  className,
  size = 140,
  durationS = 9,
  anchor = 90,
  borderWidth = 1.5,
  delayS = 0,
}: {
  className?: string;
  size?: number;
  durationS?: number;
  anchor?: number;
  borderWidth?: number;
  delayS?: number;
}) {
  return (
    <div
      aria-hidden="true"
      className={cn("border-beam", className)}
      style={
        {
          "--beam-size": size,
          "--beam-duration": durationS,
          "--beam-anchor": anchor,
          "--beam-width": borderWidth,
          "--beam-delay": delayS,
        } as React.CSSProperties
      }
    />
  );
}
