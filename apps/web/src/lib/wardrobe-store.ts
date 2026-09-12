"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { GarmentCategory, WardrobeItem } from "./schemas/wardrobe";

/**
 * Wardrobe client state.
 *
 * Persisted so selection and wardrobe survive navigation (an S3 acceptance criterion).
 * Persistence is per-browser convenience only — the server remains the source of truth, and
 * nothing here is trusted for ownership. Ownership is enforced in SQL server-side; a client
 * store is not a security boundary and must never be treated as one.
 */

export type UploadState = "validating" | "rejected" | "uploading" | "analyzing" | "ready" | "failed";

export interface UploadEntry {
  /** Stable client id, assigned before the server knows about the file. */
  localId: string;
  fileName: string;
  state: UploadState;
  /** The user's own category selection at pick time. A prior, not a decision. */
  categoryHint: GarmentCategory | null;
  /** Populated once the server accepts the upload. */
  itemId: string | null;
  jobId: string | null;
  /** Present when state is "rejected" or "failed" — actionable copy, never a raw error. */
  error: string | null;
  /** True when the API said retrying is worth the user's time. */
  retryable: boolean;
  /**
   * The named stage the API reported, verbatim. Null until the first poll answers.
   *
   * Taken from the server rather than inferred from `state`: the server knows whether it is
   * reading the photo or checking confidence, and a stage the client guesses at is a
   * spinner with a caption on it (CLAUDE.md motion rules).
   */
  stage: string | null;
  /** Object URL for local preview while the server has nothing to show yet. */
  previewUrl: string | null;
}

export interface Preferences {
  occasion: string;
  vibe: string;
  fitPreference: string;
  colorPreferences: string[];
}

/**
 * Working defaults. The whole preferences step is skippable and a user who taps straight
 * through still reaches an outfit, so these have to be genuinely reasonable rather than
 * placeholders.
 */
export const DEFAULT_PREFERENCES: Preferences = {
  occasion: "everyday",
  vibe: "minimal",
  fitPreference: "regular",
  colorPreferences: [],
};

interface WardrobeState {
  uploads: UploadEntry[];
  items: WardrobeItem[];
  preferences: Preferences;
  preferencesTouched: boolean;

  enqueue: (entries: UploadEntry[]) => void;
  updateUpload: (localId: string, patch: Partial<UploadEntry>) => void;
  setCategoryHint: (localId: string, hint: GarmentCategory | null) => void;
  clearResolvedUploads: () => void;

  upsertItem: (item: WardrobeItem) => void;
  correctField: (itemId: string, field: string, value: string) => void;
  removeItem: (itemId: string) => void;

  setPreferences: (patch: Partial<Preferences>) => void;
  resetPreferences: () => void;

  readyItems: () => WardrobeItem[];
  missingRoles: (required: readonly GarmentCategory[]) => GarmentCategory[];
  canCompose: (minItems: number) => boolean;
}

export const useWardrobe = create<WardrobeState>()(
  persist(
    (set, get) => ({
      uploads: [],
      items: [],
      preferences: DEFAULT_PREFERENCES,
      preferencesTouched: false,

      enqueue: (entries) => set((s) => ({ uploads: [...s.uploads, ...entries] })),

      updateUpload: (localId, patch) =>
        set((s) => ({
          uploads: s.uploads.map((u) => (u.localId === localId ? { ...u, ...patch } : u)),
        })),

      setCategoryHint: (localId, hint) =>
        set((s) => ({
          uploads: s.uploads.map((u) => (u.localId === localId ? { ...u, categoryHint: hint } : u)),
        })),

      // Rejected entries stay until dismissed: a refused photo needs to remain visible with
      // its reason, or the user just sees a file silently vanish.
      clearResolvedUploads: () =>
        set((s) => ({ uploads: s.uploads.filter((u) => u.state !== "ready") })),

      upsertItem: (item) =>
        set((s) => {
          const index = s.items.findIndex((i) => i.item_id === item.item_id);
          if (index === -1) return { items: [...s.items, item] };
          const next = [...s.items];
          // Never clobber local corrections with a later server payload that predates them.
          const existing = next[index];
          next[index] = existing
            ? { ...item, corrected_fields: mergeCorrections(existing, item) }
            : item;
          return { items: next };
        }),

      /**
       * Applies a user correction.
       *
       * Adds the field to `corrected_fields`, which is what protects it from being recomputed
       * by a later re-analysis (docs/AI-EVAL-CASES.md Case 13). Confidence for the field is
       * dropped, because confidence describes the model's guess and this is no longer one.
       */
      correctField: (itemId, field, value) =>
        set((s) => ({
          items: s.items.map((item) => {
            if (item.item_id !== itemId) return item;
            const remainingConfidence = omit(item.field_confidence, field);
            return {
              ...item,
              [field]: value,
              field_confidence: remainingConfidence,
              corrected_fields: item.corrected_fields.includes(field)
                ? item.corrected_fields
                : [...item.corrected_fields, field],
            } as WardrobeItem;
          }),
        })),

      removeItem: (itemId) =>
        set((s) => ({ items: s.items.filter((i) => i.item_id !== itemId) })),

      setPreferences: (patch) =>
        set((s) => ({ preferences: { ...s.preferences, ...patch }, preferencesTouched: true })),

      resetPreferences: () => set({ preferences: DEFAULT_PREFERENCES, preferencesTouched: false }),

      readyItems: () => get().items.filter((i) => i.status === "ready"),

      missingRoles: (required) => {
        const present = new Set(get().readyItems().map((i) => i.category));
        return required.filter((role) => !present.has(role));
      },

      canCompose: (minItems) => get().readyItems().length >= minItems,
    }),
    {
      name: "stylelab-wardrobe",
      storage: createJSONStorage(() => localStorage),
      // Object URLs and in-flight upload state are meaningless after a reload.
      partialize: (state) => ({
        items: state.items,
        preferences: state.preferences,
        preferencesTouched: state.preferencesTouched,
      }),
    },
  ),
);

/** Confidence describes a model guess; a corrected field is no longer one, so its score goes. */
function omit(source: Record<string, number>, key: string): Record<string, number> {
  const next: Record<string, number> = {};
  for (const [k, v] of Object.entries(source)) {
    if (k !== key) next[k] = v;
  }
  return next;
}

function mergeCorrections(existing: WardrobeItem, incoming: WardrobeItem): string[] {
  return Array.from(new Set([...existing.corrected_fields, ...incoming.corrected_fields]));
}
