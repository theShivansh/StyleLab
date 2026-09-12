"use client";

import Link from "next/link";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { config } from "@/lib/config";
import { garmentCategory } from "@/lib/schemas/wardrobe";
import { useWardrobe } from "@/lib/wardrobe-store";

/**
 * Preferences, then compose.
 *
 * Every control here has a working default and the whole step is skippable — a user who taps
 * straight through still reaches an outfit. The defaults live in the store rather than in
 * this component so "skipped" and "accepted the default" are the same state downstream.
 *
 * The result screen is S7. What this phase owns is the honest gap state: when the wardrobe
 * cannot fill the requested roles, name what is missing instead of inventing it
 * (docs/USER-FLOWS.md Flow 5).
 */

const OCCASIONS = ["everyday", "work", "evening", "campus", "weekend"] as const;
const VIBES = ["minimal", "street", "classic", "playful"] as const;
const FITS = ["slim", "regular", "relaxed", "oversized"] as const;
const REQUIRED_ROLES = ["top", "bottom", "footwear"] as const;

export default function ComposePage() {
  const preferences = useWardrobe((s) => s.preferences);
  const touched = useWardrobe((s) => s.preferencesTouched);
  const setPreferences = useWardrobe((s) => s.setPreferences);
  const resetPreferences = useWardrobe((s) => s.resetPreferences);
  const items = useWardrobe((s) => s.items);

  const ready = items.filter((i) => i.status === "ready");
  const present = new Set(ready.map((i) => i.category));
  const missing = REQUIRED_ROLES.filter((role) => !present.has(role));
  const enoughItems = ready.length >= config.minItemsToCompose;

  return (
    <div className="mx-auto max-w-3xl px-5 py-12 md:px-8 md:py-16">
      <Link href="/wardrobe" className="text-ink-muted hover:text-ink text-sm">
        ← Wardrobe
      </Link>
      <h1 className="text-headline mt-3">Compose an outfit</h1>
      <p className="text-ink-muted mt-2 text-sm">
        {touched ? "Tuned to your answers." : "Sensible defaults are already set — skip straight to it."}
      </p>

      <div className="mt-10 space-y-4">
        <ChoiceRow
          label="Occasion"
          options={OCCASIONS}
          value={preferences.occasion}
          onChange={(occasion) => setPreferences({ occasion })}
        />
        <ChoiceRow
          label="Vibe"
          options={VIBES}
          value={preferences.vibe}
          onChange={(vibe) => setPreferences({ vibe })}
        />
        <ChoiceRow
          label="Fit"
          options={FITS}
          value={preferences.fitPreference}
          onChange={(fitPreference) => setPreferences({ fitPreference })}
        />

        {touched && (
          <button
            type="button"
            onClick={resetPreferences}
            className="text-ink-muted hover:text-ink min-h-[var(--size-touch)] text-sm"
          >
            Reset to defaults
          </button>
        )}
      </div>

      <div className="mt-10">
        {!enoughItems ? (
          <Card className="p-6">
            <h2 className="text-title">Your wardrobe needs a little more</h2>
            <p className="text-ink-muted mt-2 text-sm">
              {ready.length === 0
                ? "There is nothing to style yet."
                : `${ready.length} garment${ready.length === 1 ? "" : "s"} so far — ${
                    config.minItemsToCompose
                  } is enough to start.`}
            </p>
            <ButtonLink href="/wardrobe" size="lg" className="mt-5">
              Add garments
            </ButtonLink>
          </Card>
        ) : missing.length > 0 ? (
          // The honest gap state. No invented garment, no partial outfit dressed up as
          // complete — name what is missing and offer the way to fix it.
          <Card className="p-6">
            <h2 className="text-title">
              You have no {formatRoles(missing)} yet
            </h2>
            <p className="text-ink-muted mt-2 text-sm">
              Add {missing.length === 1 ? "one" : "them"} and this look finishes itself. Nothing
              gets invented on your behalf.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {garmentCategory.options.map((role) => (
                <Chip key={role} tone={present.has(role) ? "confident" : "unknown"}>
                  {role}
                  {present.has(role) ? " ✓" : " — none"}
                </Chip>
              ))}
            </div>
            <ButtonLink href="/wardrobe" size="lg" className="mt-5">
              Add {formatRoles(missing)}
            </ButtonLink>
          </Card>
        ) : (
          <Card className="p-6">
            <h2 className="text-title">Ready to compose</h2>
            <p className="text-ink-muted mt-2 text-sm">
              {ready.length} garments, every role covered. Styling arrives in the next build
              phase — the crew that reasons about these looks is not wired up yet.
            </p>
            <Button size="lg" className="mt-5" disabled>
              Compose outfit
            </Button>
          </Card>
        )}
      </div>
    </div>
  );
}

function formatRoles(roles: readonly string[]): string {
  if (roles.length === 1) return roles[0] ?? "";
  return `${roles.slice(0, -1).join(", ")} or ${roles[roles.length - 1]}`;
}

function ChoiceRow<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly T[];
  value: string;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset>
      <legend className="text-eyebrow text-ink-muted uppercase">{label}</legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((option) => {
          const selected = option === value;
          return (
            <button
              key={option}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(option)}
              className={
                selected
                  ? "bg-ink min-h-[var(--size-touch)] rounded-[var(--radius-pill)] px-4 text-sm text-white"
                  : "border-border bg-surface hover:border-border-strong min-h-[var(--size-touch)] rounded-[var(--radius-pill)] border px-4 text-sm"
              }
            >
              {option}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
