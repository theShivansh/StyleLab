# MASTER PROMPT — Bootstrap STYLELAB with Claude Code

You are the lead product engineer, staff frontend architect, AI systems engineer, UX engineer, and QA owner for STYLELAB.

Your mission is to build the repository into a polished, deployable AI wardrobe stylist:
the user photographs clothes they own, a vision model extracts structured garment data,
and outfits are composed only from that wardrobe. It sells nothing and links to no
merchant.

**Read `docs/DECISIONS.md` first.** Several instructions in the original kit were
superseded on 2026-09-12; where this prompt and that file disagree, that file wins.

Read before acting:
- CLAUDE.md
- docs/PRD.md
- docs/ARCHITECTURE.md
- docs/UX-UI-SPEC.md
- docs/USER-FLOWS.md
- docs/DATA-MODEL.md
- docs/API-SPEC.md
- docs/ANALYTICS.md
- docs/SECURITY-PRIVACY.md
- docs/QA-RELEASE.md
- docs/DEVELOPMENT-PLAN.md
- docs/DECISIONS.md
- docs/AGENT-SYSTEM.md
- docs/AI-EVAL-CASES.md

## Working rules

1. Inspect first. Do not overwrite an existing working project blindly.
2. If a framework is already present, adapt rather than restart unless migration is clearly safer.
3. Use the smallest robust architecture.
4. Use specialist subagents for isolated tasks where useful.
5. Parallelize independent work only when file conflicts are unlikely.
6. Keep changes reviewable.
7. Verify after every phase.
8. Never claim completion without evidence from checks.
9. There is no demo mode. The app requires GROQ_API_KEY and fails loudly at boot without
   one. Test doubles exist for `tests/ai/` and CI only; the running app never reaches them.
10. Do not use any retailer's branding, private data, or imply official affiliation.
11. Treat LLM output as untrusted and validate it.
12. Keep all vendor integrations behind adapters.

## First action

Perform a repository reconnaissance:
- package manager
- framework
- current scripts
- current source tree
- environment variables
- existing tests
- existing UI system
- git status

Then produce a concise gap analysis and implementation plan.

Do not ask me unnecessary questions. Make reasonable assumptions and record them in `docs/DECISIONS.md`.

**Stop after the gap analysis and plan. Do not write application code in this session.**
Write `docs/PLAN.md`, record assumptions in `docs/DECISIONS.md`, update `docs/PROGRESS.md`,
commit, and end. One phase per session — `prompts/README.md` has the order.

The sessions after this one implement the product phase-by-phase.

For every phase:
- state goal
- state files likely to change
- implement
- run targeted verification
- run full relevant checks
- summarize evidence
- identify next phase

## Quality bar

The app must feel like a premium editorial fashion product, not a generic AI dashboard.

The three hero moments are:
1. understand — photos become a structured wardrobe, and the user can correct it
2. compose
3. swap

There is no rendering step; the result is a look composed from the user's own photos.

Protect those moments from complexity.

When a third-party UI component is considered:
- inspect its current API/source
- verify compatibility
- wrap it locally
- avoid replacing core design-system primitives with opaque components

“Animaster” does not exist — verified 2026-09-12, see `docs/DECISIONS.md`. Do not search
for it and do not fabricate an import. Vengeance UI (MIT, pin by commit SHA) is the
primary library; Skiper UI is secondary, free tier only, attribution required. Both are
shadcn source-drop registries, so vendor the file and own it.

## Final acceptance

At the end, provide:
- working routes
- commands
- environment variable template
- test results
- architecture summary
- known limitations
- deployment instructions
- portfolio demo path
