/**
 * Foundation placeholder.
 *
 * Phase 1 explicitly does not build product screens. The landing page is S2 (prompt 02);
 * the upload and composer flows are S3. This page exists so the app boots and the build,
 * typecheck and smoke test have something real to run against.
 */
export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6 py-24">
      <p className="text-[var(--color-ink-faint)] font-mono text-xs tracking-widest uppercase">
        Foundation — phase 1
      </p>

      <h1 className="text-5xl leading-[1.05] font-semibold tracking-tight text-balance">
        STYLELAB
      </h1>

      <p className="max-w-prose text-lg text-[var(--color-ink-muted)]">
        Reads photos of the clothes you own, turns them into a wardrobe that understands
        itself, and styles outfits from what is already in it.
      </p>

      <div className="rounded-[var(--radius-card)] border border-[var(--color-line)] bg-[var(--color-ivory-raised)] p-6">
        <h2 className="text-sm font-medium">Scaffolded, not yet built</h2>
        <ul className="mt-3 space-y-1.5 text-sm text-[var(--color-ink-muted)]">
          <li>Design tokens, config, API client, error contract and a11y utilities are in place.</li>
          <li>The landing page arrives in phase 2, upload and composer in phase 3.</li>
        </ul>
      </div>
    </div>
  );
}
