import type { ButtonHTMLAttributes, AnchorHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/**
 * The only button in the app.
 *
 * Renders a real <button> or <a> — never a clickable <div>. UX-UI-SPEC requires semantic
 * buttons, meaningful labels, 44px touch targets and visible focus, so those are structural
 * here rather than left to each caller.
 */

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "md" | "lg";

const base = cn(
  "inline-flex items-center justify-center gap-2 rounded-[var(--radius-pill)]",
  "font-medium whitespace-nowrap select-none",
  // 44px floor on every variant and size — not a utility class a caller can forget.
  "min-h-[var(--size-touch)]",
  "transition-[transform,background-color,border-color,color,box-shadow]",
  "duration-[var(--duration-functional)] ease-[var(--ease-standard)]",
  "active:scale-[0.985]",
  "disabled:pointer-events-none disabled:opacity-45",
  // Reduced motion: the scale cue goes, the colour cue stays.
  "motion-reduce:transition-none motion-reduce:active:scale-100",
);

const variants: Record<Variant, string> = {
  primary: cn(
    "bg-ink text-white",
    "hover:bg-[#2a2a2a]",
    "shadow-[var(--shadow-raised)] hover:shadow-[var(--shadow-floating)]",
  ),
  secondary: cn(
    "bg-surface text-ink border border-border",
    "hover:border-border-strong hover:bg-surface-muted",
  ),
  ghost: cn("bg-transparent text-ink-muted", "hover:bg-surface-muted hover:text-ink"),
  // Added in S11 for "delete my whole wardrobe", and the only destructive control in the
  // product. Uses the `--color-danger` token the design system has carried since S2 rather
  // than a new red: an irreversible action should look different from the primary action,
  // and it should not look like a different product.
  danger: cn(
    "bg-[var(--color-danger)] text-white",
    "hover:brightness-110",
    "shadow-[var(--shadow-raised)]",
  ),
};

const sizes: Record<Size, string> = {
  md: "px-5 text-sm",
  lg: "px-7 py-4 text-base",
};

interface Shared {
  variant?: Variant;
  size?: Size;
  className?: string;
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...rest
}: Shared & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type={type} className={cn(base, variants[variant], sizes[size], className)} {...rest} />
  );
}

export function ButtonLink({
  variant = "primary",
  size = "md",
  className,
  ...rest
}: Shared & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return <a className={cn(base, variants[variant], sizes[size], className)} {...rest} />;
}
