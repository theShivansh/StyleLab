/**
 * Colophon.
 *
 * No Skiper UI attribution line here yet: no Skiper UI component is vendored (see
 * docs/DECISIONS.md, S2 entry). If one is ever added, its free licence requires
 * attribution and it belongs in this block.
 */
export function Footer() {
  return (
    <footer className="border-border border-t">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-10 md:flex-row md:items-center md:justify-between md:px-8">
        <p className="text-ink-muted text-sm">
          STYLELAB <span aria-hidden="true">✦</span> — an independent portfolio project.
        </p>
        <p className="text-ink-muted/70 max-w-[52ch] text-xs">
          Not affiliated with any retailer or brand. Nothing here is for sale, and no garment shown
          is offered for purchase.
        </p>
      </div>
    </footer>
  );
}
