import { Card } from "@/components/ui/Card";
import { Reveal } from "@/components/motion/Reveal";

const STEPS = [
  {
    n: "01",
    title: "Photograph what you own",
    body: "Pick six or eight garments in one go. Plain background, even light, one garment per frame.",
  },
  {
    n: "02",
    title: "Each photo becomes data",
    body: "A vision model reads category, colour, cut and formality — and tells you how sure it is about each one.",
  },
  {
    n: "03",
    title: "Correct what it got wrong",
    body: "It called something black that is navy. Fix it once; the correction sticks and is never overwritten.",
  },
  {
    n: "04",
    title: "Get looks from your own closet",
    body: "Outfits assembled only from items you own, with the reasoning shown. Swap one piece without rebuilding the rest.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="border-border bg-surface border-y">
      <div className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <Reveal>
          <p className="text-eyebrow text-ink-muted uppercase">How it works</p>
          <h2 className="text-headline mt-4 max-w-[24ch] text-balance">
            Four steps, and the third one is the point.
          </h2>
        </Reveal>

        <ol className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, index) => (
            <li key={step.n} className="h-full">
              <Reveal delayMs={index * 70} className="h-full">
                <Card className="h-full p-6">
                  <span className="text-ink-muted/50 font-mono text-sm">{step.n}</span>
                  <h3 className="text-title mt-4">{step.title}</h3>
                  <p className="text-ink-muted mt-2.5 text-sm leading-relaxed">{step.body}</p>
                </Card>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
