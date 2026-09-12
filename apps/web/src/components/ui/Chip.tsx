import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Tone = "neutral" | "accent" | "confident" | "hedged" | "unknown";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-muted text-ink-muted border-transparent",
  accent: "bg-accent-soft text-accent-deep border-transparent",
  // Confidence tones carry meaning, so they never rely on colour alone —
  // callers pair them with a word ("likely", "unread"). UX-UI-SPEC accessibility.
  confident: "bg-transparent text-confident border-current/25",
  hedged: "bg-transparent text-hedged border-current/25",
  unknown: "bg-transparent text-unknown border-current/25",
};

export function Chip({
  className,
  tone = "neutral",
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] border",
        "px-3 py-1 text-xs font-medium",
        tones[tone],
        className,
      )}
      {...rest}
    />
  );
}
