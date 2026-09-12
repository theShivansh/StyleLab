# FINAL AUTONOMOUS BUILD PROMPT

You are the lead product engineer, staff frontend engineer, AI engineer, backend engineer, QA engineer, security engineer, and product-minded reviewer for STYLELAB.

Read the repository instructions and the docs index.

## Mission

Deliver a polished, deployable, company-agnostic AI fashion-commerce product where the core loop genuinely works:

Compose → Visualize → Remix → Save/Shop.

## AI provider

Use Groq as the default AI provider.

Use environment-configured Groq models:
- text/orchestration: openai/gpt-oss-120b
- vision: qwen/qwen3.8-27b

Do not hardcode secrets.
Use provider interfaces.
Provide deterministic mocks for CI/demo.

## Product integrity

Ground every product recommendation in known catalogue objects.

No item the user does not own, and none belonging to another user. No attribute the
model guessed presented as an observed fact.

Use:
deterministic candidate retrieval
→ Groq ranking
→ schema validation
→ catalogue validation
→ deterministic final score.

## VTO

Keep Virtual Try-On behind an adapter.

Local/demo:
MockVirtualTryOnProvider with pre-generated assets.

Production:
configurable provider.

## UI

Build the premium STYLELAB design direction:
editorial fashion × AI lab × premium commerce.

Use Skiper UI and Vengeance UI selectively.
Use local components as the system of record.
Do not invent an Animaster import.

## Testing

Before each phase:
- inspect current state
- write/adjust tests
- implement
- run targeted tests

Before final:
- lint
- typecheck
- unit
- integration
- E2E
- accessibility
- build
- AI eval
- security/dependency check

## Final product review

Act like a skeptical PM/interviewer.

Ask:
- Is the value obvious in 10 seconds?
- Is Compose → Visualize → Remix obvious?
- Does the AI really affect the product?
- Can the system prove it rejects invalid AI output?
- Are demo metrics labeled?
- Is the product fast enough?
- Is the architecture believable?
- Can another company theoretically plug in its catalogue?

Fix deficiencies you can fix.

Then write/update:
- README
- docs/DEMO-SCRIPT.md
- docs/DECISIONS.md
- deployment notes

At the end return:
1. what was built
2. verification evidence
3. AI provider setup
4. demo credentials/setup if relevant
5. known limitations
6. next highest-value improvements
