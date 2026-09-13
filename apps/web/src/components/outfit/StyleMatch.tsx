"use client";

import { Card } from "@/components/ui/Card";
import { Chip } from "@/components/ui/Chip";

/**
 * Style Match, labelled as what it is.
 *
 * docs/PRD.md: "a UX heuristic, not a scientific body/fit measurement". So the label is on
 * the card rather than in a tooltip nobody opens — a number between 0 and 100 next to a
 * photograph of someone's clothes reads as a verdict on them unless it is told not to.
 *
 * The rationale lines come from the server. They describe the *scoring* — palette, volumes,
 * register — which is something the system knows first-hand, rather than an opinion about
 * how the user will look.
 */
export function StyleMatch({
  score,
  rationale,
  degradationLevel,
}: {
  score: number;
  rationale: readonly string[];
  degradationLevel: number;
}) {
  return (
    <Card raised className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-eyebrow text-ink-muted uppercase">Style Match</p>
          <p className="text-display mt-1 tabular-nums" data-testid="style-match-score">
            {score}
          </p>
        </div>
        <Chip tone="neutral" className="mt-1">
          a styling heuristic
        </Chip>
      </div>

      <p className="text-ink-muted mt-2 text-xs">
        How well these pieces work together for the occasion you picked. Not a measurement of
        fit, and not a judgement of you.
      </p>

      {rationale.length > 0 && (
        <ul className="mt-4 space-y-2">
          {rationale.map((line) => (
            <li key={line} className="text-sm">
              {line}
            </li>
          ))}
        </ul>
      )}

      {degradationLevel > 1 && (
        // Disclosed, not hidden. A degraded answer that looks identical to a full one is the
        // gimmick this project exists to avoid (docs/AGENT-SYSTEM.md, AI-EVAL-CASES Case 23).
        <p className="text-ink-muted border-border mt-4 border-t pt-3 text-xs">
          {degradationText(degradationLevel)}
        </p>
      )}
    </Card>
  );
}

function degradationText(level: number): string {
  switch (level) {
    case 2:
      return "Styled without trend input — the trend source was unreachable, so nothing here claims to be current.";
    case 3:
      return "Styled with a shorter round of reasoning than usual.";
    case 4:
      return "Styled by the ranker rather than the advisory crew. The pieces are all yours; the reasoning is reduced, not the wardrobe.";
    default:
      return "This look is missing part of its usual reasoning.";
  }
}
