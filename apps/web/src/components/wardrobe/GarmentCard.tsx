import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";
import { cn } from "@/lib/cn";
import { config } from "@/lib/config";
import { isHedged, type WardrobeItem } from "@/lib/schemas/wardrobe";

/**
 * The product's core primitive: one garment the user owns, with the model's reading of it
 * shown honestly.
 *
 * The design rule this encodes is the one the whole product rests on — a guess must look
 * like a guess. A field below the confidence floor renders as a hedge with a correction
 * affordance; a field the user has corrected renders as settled and is never re-hedged.
 *
 * Interaction (correcting a field, choosing it for an outfit) arrives in S3. This is the
 * presentational primitive the landing page and the wardrobe grid both use.
 */

const FIELD_LABELS: Array<{ key: keyof WardrobeItem & string; label: string }> = [
  { key: "subcategory", label: "Type" },
  { key: "color_primary", label: "Colour" },
  { key: "material_guess", label: "Material" },
  { key: "fit", label: "Fit" },
];

export function GarmentCard({
  item,
  className,
  imageSlot,
}: {
  item: WardrobeItem;
  className?: string;
  /** S3 swaps in a real <Image>. Kept injectable so this primitive needs no asset to render. */
  imageSlot?: React.ReactNode;
}) {
  const analyzing = item.status === "analyzing";

  return (
    <Card
      raised
      className={cn("overflow-hidden", className)}
      aria-busy={analyzing || undefined}
    >
      <div className="bg-surface-muted relative aspect-[4/5] w-full">
        {imageSlot ?? <GarmentPlaceholder label={item.category ?? "garment"} />}

        {item.quality_warnings.length > 0 && (
          <div className="absolute inset-x-3 bottom-3">
            <Chip tone="hedged" className="bg-surface/95 backdrop-blur-sm">
              {/* Named, not just coloured — colour alone is never the signal. */}
              {warningLabel(item.quality_warnings[0])}
            </Chip>
          </div>
        )}
      </div>

      <div className="space-y-3 p-4">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-eyebrow text-ink-muted uppercase">{item.category ?? "Unsorted"}</p>
          {analyzing && <span className="text-ink-muted text-xs">Reading…</span>}
        </div>

        <dl className="space-y-1.5">
          {FIELD_LABELS.map(({ key, label }) => {
            const value = item[key];
            if (typeof value !== "string" || value.length === 0) return null;

            const corrected = item.corrected_fields.includes(key);
            const hedged = isHedged(item, key, config.confidenceFloor);

            return (
              <div key={key} className="flex items-center justify-between gap-3 text-sm">
                <dt className="text-ink-muted">{label}</dt>
                <dd className="flex items-center gap-2">
                  <span className={cn(hedged && "text-ink-muted")}>{value}</span>
                  {corrected ? (
                    <Chip tone="accent" className="px-2 py-0.5 text-[10px]">
                      you set this
                    </Chip>
                  ) : hedged ? (
                    <Chip tone="hedged" className="px-2 py-0.5 text-[10px]">
                      best guess
                    </Chip>
                  ) : null}
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
    </Card>
  );
}

function warningLabel(warning: string | undefined): string {
  switch (warning) {
    case "low_light":
      return "Dim photo — check the colour";
    case "cropped":
      return "Partly cropped";
    case "multiple_garments":
      return "More than one garment in frame";
    default:
      return "Worth a second look";
  }
}

/** Geometric stand-in. Not a photograph of a garment, and not pretending to be one. */
function GarmentPlaceholder({ label }: { label: string }) {
  return (
    <div className="text-ink-muted/25 grid h-full w-full place-items-center" aria-hidden="true">
      <svg viewBox="0 0 64 64" className="w-1/3" fill="none" stroke="currentColor" strokeWidth="2">
        <title>{label}</title>
        <path d="M24 8l8 6 8-6 12 8-4 10-4-2v30H20V24l-4 2-4-10z" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
