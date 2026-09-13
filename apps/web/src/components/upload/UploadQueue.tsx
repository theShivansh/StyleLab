"use client";

import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { cn } from "@/lib/cn";
import { garmentCategory } from "@/lib/schemas/wardrobe";
import type { GarmentCategory } from "@/lib/schemas/wardrobe";
import type { UploadEntry } from "@/lib/wardrobe-store";

/**
 * Per-photo progress during a batch.
 *
 * Each entry resolves independently — that is the whole point. One refused or failed photo
 * shows its own reason in its own card and leaves the other seven alone
 * (docs/USER-FLOWS.md Flow 1, constraint 4).
 *
 * Stages are named, never a bare spinner (CLAUDE.md motion rules). The names come from the
 * job endpoint, verbatim — `STAGE_COPY` below is only the fallback for the moments before
 * the server has anything to report, and for states the server has no opinion about
 * (validating locally, refused locally). A stage the client invented would be a caption on
 * a spinner.
 */

const STAGE_COPY: Record<UploadEntry["state"], string> = {
  validating: "Checking the photo",
  rejected: "Not usable",
  uploading: "Sending",
  analyzing: "Reading the garment",
  ready: "Read",
  failed: "Couldn't read it",
};

export function UploadQueue({
  entries,
  onSetHint,
  onDismiss,
  onRetry,
}: {
  entries: readonly UploadEntry[];
  onSetHint: (localId: string, hint: GarmentCategory | null) => void;
  onDismiss: (localId: string) => void;
  /** Re-runs extraction for one photo. Absent means the affordance is not offered. */
  onRetry?: (localId: string) => void;
}) {
  if (entries.length === 0) return null;

  const pending = entries.filter((e) => e.state === "uploading" || e.state === "analyzing").length;

  return (
    <section aria-label="Photos being processed" className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-title">
          {pending > 0 ? `Reading ${pending} of ${entries.length}` : `${entries.length} photos`}
        </h2>
        {/* Progress is per-card; this is a summary for screen readers and glanceability. */}
        <p aria-live="polite" className="text-ink-muted text-sm">
          {pending > 0 ? "Cards appear as each one finishes." : "All done."}
        </p>
      </div>

      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {entries.map((entry) => {
          const failed = entry.state === "rejected" || entry.state === "failed";
          const busy = entry.state === "uploading" || entry.state === "analyzing";
          // A locally refused file has no item on the server, so there is nothing to
          // re-analyse — the user has to pick a different photo. Only a failed *extraction*
          // can be retried, and only when the API said it was worth trying.
          const canRetry =
            onRetry !== undefined &&
            entry.state === "failed" &&
            entry.retryable &&
            entry.itemId !== null;

          return (
            <li key={entry.localId}>
              <Card
                size="sm"
                className={cn("p-4", failed && "border-danger/35")}
                aria-busy={busy || undefined}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="truncate text-sm font-medium" title={entry.fileName}>
                    {entry.fileName}
                  </p>
                  <button
                    type="button"
                    onClick={() => onDismiss(entry.localId)}
                    aria-label={`Dismiss ${entry.fileName}`}
                    className="text-ink-muted hover:text-ink shrink-0 text-xs"
                  >
                    Dismiss
                  </button>
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <Chip
                    tone={failed ? "hedged" : entry.state === "ready" ? "confident" : "neutral"}
                  >
                    {(busy && entry.stage) || STAGE_COPY[entry.state]}
                  </Chip>
                  {busy && (
                    <span
                      aria-hidden="true"
                      className="bg-surface-muted relative h-1 flex-1 overflow-hidden rounded-full"
                    >
                      <span className="bg-accent absolute inset-y-0 left-0 w-1/3 animate-pulse rounded-full" />
                    </span>
                  )}
                </div>

                {entry.error && <p className="text-danger mt-3 text-sm">{entry.error}</p>}

                {canRetry && (
                  <button
                    type="button"
                    onClick={() => onRetry(entry.localId)}
                    className="border-border hover:border-ink mt-3 min-h-[var(--size-touch)] w-full rounded-[var(--radius-control)] border text-sm font-medium"
                  >
                    Read it again
                  </button>
                )}

                {/* The hint is optional and editable while the photo is still in flight —
                    it is a prior for the model, not a decision the user is locked into. */}
                {!failed && (
                  <label className="mt-3 block">
                    <span className="text-ink-muted text-xs">What is it? (optional)</span>
                    <select
                      value={entry.categoryHint ?? ""}
                      onChange={(event) =>
                        onSetHint(
                          entry.localId,
                          event.target.value === ""
                            ? null
                            : (event.target.value as GarmentCategory),
                        )
                      }
                      className="border-border bg-surface mt-1 min-h-[var(--size-touch)] w-full rounded-[var(--radius-control)] border px-2 text-sm"
                    >
                      <option value="">Let it decide</option>
                      {garmentCategory.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </Card>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
