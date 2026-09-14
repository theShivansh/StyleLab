"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { BorderBeam } from "@/components/vendor/BorderBeam";
import { Chip } from "@/components/ui/Chip";
import { usePrefersReducedMotion } from "@/lib/a11y";
import { cn } from "@/lib/cn";

/**
 * The hero's showcase: one sample photograph being read, stage by stage.
 *
 * It shows the product's front door rather than a mood. The stage names are the real ones
 * (CLAUDE.md, motion rules — progress names real work), the fields land in the order the
 * extraction reports them, and the guesses are marked as guesses the way a real card marks
 * them. It is labelled as an illustration, because a landing page that implied this was
 * somebody's wardrobe would be the first ungrounded claim a visitor meets.
 *
 * ## Failure lands on something readable
 *
 * The server renders stage one: the photograph, the "Reading photo" label, and placeholder
 * rows. Nothing is hidden behind an animation that might not run. JavaScript advances the
 * stages; with reduced motion it jumps straight to the finished read and offers no replay,
 * because there is nothing to watch.
 */

const STAGES = [
  "Reading photo",
  "Finding garment",
  "Reading colour and cut",
  "Checking confidence",
  "Ready",
] as const;

const FINAL = STAGES.length - 1;
/** Time on each stage. Inside the hero band of the motion system, per step. */
const STEP_MS = 720;
/** A beat on the photograph before the first stage moves. */
const LEAD_MS = 500;

type Field = {
  label: string;
  value: string;
  /** The stage at which this field has been read. */
  at: number;
  sure: boolean;
};

const FIELDS: Field[] = [
  { label: "Category", value: "top", at: 1, sure: true },
  { label: "Type", value: "oxford shirt", at: 2, sure: true },
  { label: "Colour", value: "navy", at: 2, sure: true },
  { label: "Material", value: "cotton", at: 3, sure: false },
  { label: "Fit", value: "regular", at: 3, sure: false },
];

export function HeroRead() {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [stage, setStage] = useState(0);
  const [run, setRun] = useState(0);

  useEffect(() => {
    if (prefersReducedMotion) return;
    const timers = STAGES.slice(1).map((_, index) =>
      window.setTimeout(() => setStage(index + 1), LEAD_MS + STEP_MS * (index + 1)),
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [prefersReducedMotion, run]);

  const current = prefersReducedMotion ? FINAL : stage;
  const reading = current < FINAL;

  return (
    <figure className="relative mx-auto w-full max-w-[420px]">
      <div
        className={cn(
          "bg-surface border-border relative rounded-[var(--radius-card-lg)] border",
          "shadow-[var(--shadow-floating)]",
        )}
      >
        <BorderBeam />

        <div className="bg-surface-muted relative aspect-[4/5] overflow-hidden rounded-t-[var(--radius-card-lg)]">
          <Image
            src="/landing/oxford-shirt.webp"
            alt="Sample photograph of a dark oxford shirt on a plain background"
            fill
            sizes="(min-width: 1024px) 420px, (min-width: 640px) 420px, 90vw"
            loading="eager"
            fetchPriority="high"
            className="object-cover"
          />
          {reading && <div className="hero-scan" aria-hidden="true" />}

          <div className="absolute inset-x-3 top-3 flex items-center justify-between gap-2">
            <Chip tone={reading ? "neutral" : "accent"} className="bg-surface/90 backdrop-blur-sm">
              <span aria-hidden="true" className={cn("hero-dot", !reading && "hero-dot--still")} />
              {STAGES[current]}
            </Chip>
            <span className="bg-surface/90 text-ink-muted rounded-[var(--radius-pill)] px-2.5 py-1 font-mono text-[11px] backdrop-blur-sm">
              {current + 1}/{STAGES.length}
            </span>
          </div>
        </div>

        <div className="p-5">
          <div className="flex gap-1.5" aria-hidden="true">
            {STAGES.map((name, index) => (
              <span
                key={name}
                className={cn(
                  "h-1 flex-1 rounded-[var(--radius-pill)]",
                  "transition-colors duration-[var(--duration-spatial)]",
                  index <= current ? "bg-accent" : "bg-surface-muted",
                )}
              />
            ))}
          </div>

          <dl className="mt-4 space-y-2">
            {FIELDS.map((field) => {
              const read = current >= field.at;
              return (
                <div
                  key={field.label}
                  className="flex min-h-7 items-center justify-between gap-3 text-sm"
                >
                  <dt className="text-ink-muted">{field.label}</dt>
                  <dd className="flex items-center gap-2">
                    {read ? (
                      <span className="hero-field flex items-center gap-2">
                        <span className={cn(!field.sure && "text-ink-muted")}>{field.value}</span>
                        <Chip
                          tone={field.sure ? "confident" : "hedged"}
                          className="px-2 py-0.5 text-[10px] whitespace-nowrap"
                        >
                          {field.sure ? "likely" : "best guess"}
                        </Chip>
                      </span>
                    ) : (
                      <span className="bg-surface-muted block h-2.5 w-24 rounded-[var(--radius-pill)]">
                        <span className="sr-only">not read yet</span>
                      </span>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      </div>

      <figcaption className="text-ink-muted/80 mt-2 flex items-center justify-between gap-3 text-xs">
        <span>Interface illustration with a sample photo — not a real wardrobe.</span>
        {!prefersReducedMotion && (
          <button
            type="button"
            onClick={() => {
              setStage(0);
              setRun((value) => value + 1);
            }}
            disabled={reading}
            className={cn(
              "text-ink-muted hover:text-ink hover:bg-surface-muted inline-flex shrink-0 items-center",
              "min-h-[var(--size-touch)] rounded-[var(--radius-pill)] px-3 font-medium",
              "transition-colors duration-[var(--duration-functional)] disabled:opacity-40",
            )}
          >
            Replay the read
          </button>
        )}
      </figcaption>
    </figure>
  );
}
