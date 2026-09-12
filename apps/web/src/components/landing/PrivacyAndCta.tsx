import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Reveal } from "@/components/motion/Reveal";

/**
 * Trust/privacy and the final CTA.
 *
 * Claims here are load-bearing and every one is enforced somewhere in the codebase — see
 * docs/SECURITY-PRIVACY.md. Do not add a promise to this section that nothing implements.
 */

const PROMISES = [
  {
    title: "Your photos stay private",
    body: "Private storage, short-lived signed links. Nobody else sees your closet, and no image URL reaches analytics.",
  },
  {
    title: "Location is stripped on upload",
    body: "Photos taken indoors carry GPS. It is removed on ingest, along with the rest of the EXIF.",
  },
  {
    title: "Delete means delete",
    body: "Remove one garment or the whole wardrobe. We tell you which looks that breaks before you confirm.",
  },
  {
    title: "Nothing is inferred about you",
    body: "The model's job is the garment, not the wearer. No body, age or appearance inference — ever.",
  },
];

export function PrivacyAndCta() {
  return (
    <>
      <section id="privacy" className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <Reveal>
          <p className="text-eyebrow text-ink-muted uppercase">Privacy</p>
          <h2 className="text-headline mt-4 max-w-[26ch] text-balance">
            Photographs of your home, treated like it.
          </h2>
          <p className="text-lede text-ink-muted mt-6 max-w-[52ch]">
            Cataloguing a closet means uploading a lot of pictures taken inside your house.
            That is personal data with things in the background you did not mean to share.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-4 sm:grid-cols-2">
          {PROMISES.map((promise, index) => (
            <Reveal key={promise.title} delayMs={index * 60}>
              <Card className="h-full p-6">
                <h3 className="text-title">{promise.title}</h3>
                <p className="text-ink-muted mt-2.5 text-sm leading-relaxed">{promise.body}</p>
              </Card>
            </Reveal>
          ))}
        </div>

        <Reveal delayMs={260}>
          <p className="text-ink-muted mt-8 max-w-[62ch] text-sm leading-relaxed">
            One thing stated plainly: styling runs on a hosted model provider, so each garment
            photo you upload is sent there to be read. There is no offline mode. If that is not
            a trade you want to make, this is not the product for you.
          </p>
        </Reveal>
      </section>

      <section id="start" className="border-border bg-surface border-t">
        <div className="mx-auto max-w-3xl px-5 py-24 text-center md:px-8 md:py-32">
          <Reveal>
            <h2 className="text-display text-balance">Start with six photos.</h2>
            <p className="text-lede text-ink-muted mx-auto mt-6 max-w-[42ch]">
              No account. No catalogue. Just the clothes you already own, finally legible to
              something that can style them.
            </p>
            <div className="mt-9 flex justify-center">
              <ButtonLink href="#start" size="lg">
                Start my wardrobe
              </ButtonLink>
            </div>
            <p className="text-ink-muted/70 mt-5 text-xs">
              Upload arrives in the next build phase.
            </p>
          </Reveal>
        </div>
      </section>
    </>
  );
}
