# Trend corpus

Curated, dated, human-reviewed trend entries. The default `TrendSource`
(`TREND_SOURCE=corpus`). Blocker B8 — not yet populated.

Every entry **must** carry `source` and `published_at`, or it is dropped rather than shown
(`docs/AI-EVAL-CASES.md` Case 15). Trend input never comes from model recall: asking a model
what is currently fashionable returns confident output from a training cutoff with no source
and no date, which is exactly the gimmick this project exists to avoid.

Entry shape:

```json
{
  "trend": "Relaxed tailoring holding through AW26",
  "source": "publication or report name",
  "published_at": "2026-07-14",
  "region": "global",
  "applies_to": ["top", "outerwear"]
}
```

Two hard rules:

1. A trend may only **re-rank or contextualise items the user already owns.** It may never
   introduce a garment. Ownership validation does not care where a suggestion came from.
2. Trend text is **untrusted input**, subject to the same injection rules as text found
   inside an uploaded image (Case 18).

A corpus whose newest entry is older than `TREND_MAX_AGE_DAYS` disables the Trend Scout
(degradation level 2) rather than implying a currency the data does not have.
