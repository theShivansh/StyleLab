import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/**
 * Surface primitive. 20-28px radii per UX-UI-SPEC; shadows are soft neutral, never a
 * coloured glow ("restrained glass effects", "avoid excessive glassmorphism").
 */
export function Card({
  className,
  size = "md",
  raised = false,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { size?: "sm" | "md" | "lg"; raised?: boolean }) {
  const radius = {
    sm: "rounded-[var(--radius-card-sm)]",
    md: "rounded-[var(--radius-card)]",
    lg: "rounded-[var(--radius-card-lg)]",
  }[size];

  return (
    <div
      className={cn(
        "border-border bg-surface border",
        radius,
        raised && "shadow-[var(--shadow-raised)]",
        className,
      )}
      {...rest}
    />
  );
}
