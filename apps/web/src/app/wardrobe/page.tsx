"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ImagePicker } from "@/components/upload/ImagePicker";
import { UploadQueue } from "@/components/upload/UploadQueue";
import { FieldCorrection } from "@/components/wardrobe/FieldCorrection";
import { GarmentCard } from "@/components/wardrobe/GarmentCard";
import { useAnnouncer } from "@/lib/a11y";
import { track } from "@/lib/analytics";
import { config } from "@/lib/config";
import { userMessage } from "@/lib/errors";
import {
  correctWardrobeItem,
  deleteWardrobe,
  deleteWardrobeItem,
  listWardrobeItems,
  reanalyzeWardrobeItem,
  uploadWardrobeImages,
} from "@/lib/api/wardrobe";
import { useAnalysisPolling } from "@/lib/use-analysis-polling";
import { useWardrobe, type UploadEntry } from "@/lib/wardrobe-store";
import type { GarmentCategory } from "@/lib/schemas/wardrobe";

/**
 * The wardrobe screen. Upload, watch each photo resolve, correct what the model got wrong.
 *
 * This is the cold-start path: there is no demo wardrobe, so a first-time visitor meets the
 * product here and it carries the whole first impression.
 *
 * Live against the API as of S6. Every mutation goes to the server and the server's answer
 * is what the screen shows — the store is a cache, not a source of truth. A correction that
 * only ever updated local state would look identical until the page reloaded, which is the
 * worst possible time to find out it never saved.
 */
export default function WardrobePage() {
  const announce = useAnnouncer();
  const [correcting, setCorrecting] = useState<string | null>(null);
  // Two-tap confirmation for the one irreversible-looking action in the product.
  const [confirmingClear, setConfirmingClear] = useState(false);

  // Each analysing upload resolves on its own schedule, so cards appear one at a time.
  useAnalysisPolling();

  const uploads = useWardrobe((s) => s.uploads);
  const items = useWardrobe((s) => s.items);
  const enqueue = useWardrobe((s) => s.enqueue);
  const updateUpload = useWardrobe((s) => s.updateUpload);
  const setCategoryHint = useWardrobe((s) => s.setCategoryHint);
  const correctField = useWardrobe((s) => s.correctField);
  const removeItem = useWardrobe((s) => s.removeItem);
  const setItems = useWardrobe((s) => s.setItems);

  const upsertItem = useWardrobe((s) => s.upsertItem);

  const readyCount = items.filter((i) => i.status === "ready").length;
  const correctingItem = items.find((i) => i.item_id === correcting) ?? null;

  // The wardrobe lives on the server. The persisted store is a cache for the moment before
  // this lands, so the grid is not empty on a reload — it is then overwritten by the truth.
  useEffect(() => {
    const controller = new AbortController();
    void listWardrobeItems(controller.signal)
      .then(({ items: fetched }) => fetched.forEach(upsertItem))
      .catch(() => {
        // A cold API is not worth a banner over an empty wardrobe: the picker is the
        // primary action on this screen either way, and an upload will surface the failure
        // with something the user can act on.
      });
    return () => controller.abort();
  }, [upsertItem]);

  const handlePicked = useCallback(
    async (files: File[], rejected: Array<{ name: string; message: string }>) => {
      const rejectedEntries: UploadEntry[] = rejected.map((r) => ({
        localId: crypto.randomUUID(),
        fileName: r.name,
        state: "rejected",
        categoryHint: null,
        itemId: null,
        jobId: null,
        error: r.message,
        retryable: false,
        stage: null,
        previewUrl: null,
      }));

      const acceptedEntries: UploadEntry[] = files.map((file) => ({
        localId: crypto.randomUUID(),
        fileName: file.name,
        state: "uploading",
        categoryHint: null,
        itemId: null,
        jobId: null,
        error: null,
        retryable: false,
        stage: null,
        previewUrl: URL.createObjectURL(file),
      }));

      enqueue([...acceptedEntries, ...rejectedEntries]);

      // The funnel step docs/ANALYTICS.md calls the whole cold-start risk. Counts and
      // reason codes only — never a filename, which is user-authored text.
      track("images_selected", { count: files.length, rejected: rejected.length });
      for (const item of rejected) {
        track("image_rejected", { reason: item.message.slice(0, 60) });
      }

      if (rejected.length > 0) {
        announce(`${rejected.length} photo${rejected.length === 1 ? "" : "s"} could not be used.`);
      }
      if (files.length === 0) return;

      announce(`Uploading ${files.length} photo${files.length === 1 ? "" : "s"}.`);

      try {
        const result = await uploadWardrobeImages(
          files.map((file, index) => ({
            file,
            categoryHint: acceptedEntries[index]?.categoryHint ?? null,
          })),
        );

        // Per-file results, so one refusal marks one card.
        result.items.forEach((serverItem, index) => {
          const entry = acceptedEntries[index];
          if (!entry) return;
          updateUpload(
            entry.localId,
            serverItem.status === "rejected"
              ? { state: "rejected", error: serverItem.error?.message ?? "That photo was refused." }
              : { state: "analyzing", itemId: serverItem.item_id, jobId: serverItem.job_id },
          );
        });
      } catch (error) {
        // A transport-level failure hits the whole batch; each card says so individually
        // rather than one banner replacing the queue.
        for (const entry of acceptedEntries) {
          updateUpload(entry.localId, { state: "failed", error: userMessage(error) });
        }
        announce("Upload failed.");
      }
    },
    [announce, enqueue, updateUpload],
  );

  /** Re-run extraction on one photo. The job replaces the card's failure with a stage. */
  const handleRetry = useCallback(
    async (localId: string) => {
      const entry = uploads.find((u) => u.localId === localId);
      if (!entry?.itemId) return;

      updateUpload(localId, { state: "analyzing", error: null, stage: null });
      try {
        const job = await reanalyzeWardrobeItem(entry.itemId);
        updateUpload(localId, { jobId: job.job_id });
        announce("Reading that photo again.");
      } catch (error) {
        updateUpload(localId, { state: "failed", error: userMessage(error), retryable: true });
      }
    },
    [announce, updateUpload, uploads],
  );

  /**
   * Send a correction, then take the server's version of the item.
   *
   * Optimistic locally so the sheet closes instantly, reconciled from the response because
   * the server decides what `corrected_fields` becomes — that list is what protects the
   * field from the next re-analysis, and guessing at it here would be guessing at the
   * guarantee.
   */
  const handleCorrect = useCallback(
    async (itemId: string, field: string, value: string) => {
      correctField(itemId, field, value);
      // Field name only. The *value* is free text a vision model wrote about a photograph
      // of somebody's home (blocker B18), and the KPI the spec wants — extraction
      // acceptance rate — is a count per field either way.
      track("extraction_field_corrected", { field });
      announce(`${field} set to ${value}.`);
      try {
        upsertItem(await correctWardrobeItem(itemId, { [field]: value }));
      } catch (error) {
        announce(`That correction did not save. ${userMessage(error)}`);
      }
    },
    [announce, correctField, upsertItem],
  );

  /** Delete a garment, and say which saved looks it broke (AI-EVAL-CASES Case 14). */
  const handleRemove = useCallback(
    async (itemId: string) => {
      const role = items.find((i) => i.item_id === itemId)?.category ?? "unknown";
      removeItem(itemId);
      track("item_deleted", { role });
      try {
        const { affected_outfits } = await deleteWardrobeItem(itemId);
        announce(
          affected_outfits.length === 0
            ? "Garment removed."
            : `Garment removed. ${affected_outfits.length} saved ${
                affected_outfits.length === 1 ? "outfit is" : "outfits are"
              } now incomplete.`,
        );
      } catch (error) {
        announce(`That garment could not be removed. ${userMessage(error)}`);
      }
    },
    [announce, items, removeItem],
  );

  /**
   * Clear the whole wardrobe. docs/SECURITY-PRIVACY.md: *"A user must be able to remove
   * their entire wardrobe in one action."*
   *
   * Two-tap rather than a `window.confirm`. The native dialog is unstyleable, reads as a
   * browser error, and — the part that matters here — cannot say the one thing this
   * confirmation needs to say, which is what "delete" actually means: gone from the closet
   * now, erased from disk within the retention window.
   */
  const handleRemoveAll = useCallback(async () => {
    setConfirmingClear(false);
    const previous = items;
    setItems([]);
    try {
      const result = await deleteWardrobe();
      track("wardrobe_cleared", { items: result.items });
      announce(
        `Wardrobe cleared. ${result.items} garment${result.items === 1 ? "" : "s"} removed; ` +
          `photos are erased within ${result.images_erased_after_days} days.`,
      );
    } catch (error) {
      // Put it back. Optimistic removal is right for one card and wrong to leave in place
      // for a whole wardrobe: a user looking at an empty screen after a failed request has
      // been told their clothes are gone when they are not.
      setItems(previous);
      announce(`Your wardrobe could not be cleared. ${userMessage(error)}`);
    }
  }, [announce, items, setItems]);

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 md:px-8 md:py-16">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link
            href="/"
            className="text-ink-muted hover:text-ink -ml-2 inline-flex min-h-11 items-center rounded-[var(--radius-control)] px-2 text-sm"
          >
            ← STYLELAB
          </Link>
          <h1 className="text-headline mt-3">Your wardrobe</h1>
          <p className="text-ink-muted mt-2 text-sm">
            {readyCount === 0
              ? "Add a few garments to begin. Three is enough."
              : `${readyCount} garment${readyCount === 1 ? "" : "s"} read.`}
          </p>
        </div>

        {/* Reachable early — never gated behind finishing the whole wardrobe. */}
        <ButtonLink
          href="/compose"
          size="lg"
          variant={readyCount >= config.minItemsToCompose ? "primary" : "secondary"}
        >
          Compose outfit
        </ButtonLink>
      </div>

      <div className="mt-10 space-y-10">
        <ImagePicker onPicked={handlePicked} />

        <UploadQueue
          entries={uploads}
          onSetHint={(localId, hint: GarmentCategory | null) => setCategoryHint(localId, hint)}
          onDismiss={(localId) => updateUpload(localId, { state: "ready" })}
          onRetry={handleRetry}
        />

        <section aria-label="Wardrobe" className="space-y-4">
          <h2 className="text-title">Garments</h2>

          {items.length === 0 ? (
            <Card className="p-8 text-center">
              <p className="text-ink-muted text-sm">
                Nothing here yet. Photos you add appear as cards once each one has been read.
              </p>
            </Card>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {items.map((item) => (
                <li key={item.item_id}>
                  <GarmentCard
                    item={item}
                    onCorrect={() => setCorrecting(item.item_id)}
                    onRemove={() => void handleRemove(item.item_id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>

        {items.length > 0 && (
          <section
            aria-label="Delete everything"
            className="border-line flex flex-wrap items-center justify-between gap-4 border-t pt-8"
          >
            <p className="text-ink-muted max-w-md text-sm">
              {confirmingClear
                ? "This removes every garment and every photo. Saved looks that used them will be marked incomplete. Photos are erased from storage within 30 days."
                : "Changed your mind about all of it?"}
            </p>
            {confirmingClear ? (
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setConfirmingClear(false)}>
                  Keep my wardrobe
                </Button>
                <Button variant="danger" onClick={() => void handleRemoveAll()}>
                  Yes, delete everything
                </Button>
              </div>
            ) : (
              <Button variant="secondary" onClick={() => setConfirmingClear(true)}>
                Delete my whole wardrobe
              </Button>
            )}
          </section>
        )}
      </div>

      {correctingItem && (
        <FieldCorrection
          item={correctingItem}
          open
          onClose={() => setCorrecting(null)}
          onSubmit={(field, value) => void handleCorrect(correctingItem.item_id, field, value)}
        />
      )}
    </div>
  );
}
