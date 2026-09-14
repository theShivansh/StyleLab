"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { garmentCategory, humanise, type WardrobeItem } from "@/lib/schemas/wardrobe";

/**
 * Correcting a field the model got wrong.
 *
 * One tap from the card, never buried in settings — the prompt is explicit about that, and
 * it is the product's most differentiated interaction. Rendered in a Sheet so it is a bottom
 * sheet on mobile and a dialog on desktop with no separate implementation.
 *
 * The copy deliberately avoids apologising. Correction is a normal part of using the product,
 * not an error report.
 */

export const CORRECTABLE_FIELDS = [
  { key: "category", label: "Category", options: garmentCategory.options },
  { key: "subcategory", label: "Type", options: null },
  { key: "color_primary", label: "Colour", options: null },
  { key: "material_guess", label: "Material", options: null },
  { key: "fit", label: "Fit", options: ["slim", "regular", "relaxed", "oversized"] },
  { key: "formality", label: "Formality", options: ["casual", "smart-casual", "formal"] },
] as const;

type FieldKey = (typeof CORRECTABLE_FIELDS)[number]["key"];

export function FieldCorrection({
  item,
  open,
  onClose,
  onSubmit,
}: {
  item: WardrobeItem;
  open: boolean;
  onClose: () => void;
  onSubmit: (field: FieldKey, value: string) => void;
}) {
  const [field, setField] = useState<FieldKey>("color_primary");
  const [value, setValue] = useState("");

  const definition = CORRECTABLE_FIELDS.find((f) => f.key === field);
  const currentValue = item[field];
  const wasCorrected = item.corrected_fields.includes(field);

  const submit = () => {
    const trimmed = value.trim();
    if (trimmed.length === 0) return;
    onSubmit(field, trimmed);
    setValue("");
    onClose();
  };

  return (
    <Sheet open={open} onClose={onClose} title="Set it straight">
      <div className="space-y-5">
        <p className="text-ink-muted text-sm">
          Pick the field and tell us what it actually is. Your answer sticks — re-analysing this
          photo later will not overwrite it.
        </p>

        <div className="space-y-2">
          <label htmlFor="correction-field" className="text-sm font-medium">
            Field
          </label>
          <select
            id="correction-field"
            value={field}
            onChange={(event) => {
              setField(event.target.value as FieldKey);
              setValue("");
            }}
            className="border-border bg-surface min-h-[var(--size-touch)] w-full rounded-[var(--radius-control)] border px-3 text-sm"
          >
            {CORRECTABLE_FIELDS.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
          <p className="text-ink-muted text-xs">
            {typeof currentValue === "string" && currentValue.length > 0
              ? wasCorrected
                ? `Currently "${humanise(currentValue)}" — you set this.`
                : `Currently read as "${humanise(currentValue)}".`
              : "Not read yet."}
          </p>
        </div>

        <div className="space-y-2">
          <label htmlFor="correction-value" className="text-sm font-medium">
            Correct value
          </label>
          {definition?.options ? (
            <select
              id="correction-value"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className="border-border bg-surface min-h-[var(--size-touch)] w-full rounded-[var(--radius-control)] border px-3 text-sm"
            >
              <option value="">Choose…</option>
              {definition.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : (
            <input
              id="correction-value"
              type="text"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submit();
              }}
              placeholder="e.g. navy"
              autoComplete="off"
              className="border-border bg-surface min-h-[var(--size-touch)] w-full rounded-[var(--radius-control)] border px-3 text-sm"
            />
          )}
        </div>

        <div className="flex gap-2">
          <Button
            size="lg"
            onClick={submit}
            disabled={value.trim().length === 0}
            className="flex-1"
          >
            Save correction
          </Button>
          <Button size="lg" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
