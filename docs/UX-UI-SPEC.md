# UX/UI Specification — STYLELAB

## Brand

STYLELAB ✦

Tagline:
“Your wardrobe, recomposed by AI.”

Tone:
confident, editorial, playful, intelligent.

## Visual direction

Editorial fashion × AI lab × personal archive.

### Color tokens

```text
background: #FAF9F7
surface: #FFFFFF
surface-muted: #F2F1EF
text-primary: #111111
text-secondary: #6D6D6D
accent: #FF3F7F
accent-soft: #FFE7F0
border: rgba(0,0,0,0.08)
```

Use pink selectively.

## Typography

Prefer a premium geometric/display family available through the project, with Inter/Manrope-style utility text.

Display:
large, compressed-feeling headings

Body:
high readability

## Key screens

### 1. Landing

Hero:
YOUR WARDROBE.
RECOMPOSED.

CTA:
Create my look

Secondary:
Explore demo

Sections:
- signature interaction
- how it works
- sample looks
- trust/privacy
- final CTA

### 2. Onboarding

Step:
Photo → Occasion → Vibe → Fit → Continue

Allow skip/demo where appropriate.

### 3. Composer

Desktop:
large preview + right-side recommendation tray

Mobile:
large preview + bottom sheets

Key controls:
- top
- bottom
- shoes
- layer
- compose

### 4. Generation

Do not show a generic spinner.

Show:
Reading your style
Matching silhouettes
Building outfit
Rendering your look
Almost ready

### 5. Result

Primary visual:
composed look, built from the user's own garment photos

Secondary:
Style Match (labelled a heuristic)
outfit item list, each tracing to an owned item
rationale
save
share

Primary interaction:
Swap

### 6. Swap

“What if?”

Tabs:
Top / Bottom / Shoes / Layer

Candidates:
3–5 strong alternatives

Interaction:
replace one item → update look → show new result

### 7. Planner

7-day cards
with occasion labels and quick swap/save actions.

## Motion

Use three levels:
functional 100–180ms
spatial 250–500ms
hero 600–1200ms

Animation should communicate:
- hierarchy
- state changes
- causality
- reveal

Do not animate everything.

## Library strategy

Verified 2026-09-12 — see `docs/DECISIONS.md` for evidence. Both approved libraries are
**shadcn source-drop registries, not npm packages**: `shadcn add` writes a `.tsx` file
into this repo and there is no runtime dependency afterwards. Read every file before
committing it, and record the upstream name + commit SHA in a header comment.

**Vengeance UI** — primary. Animated CTA, image interaction, text, loader, showcase.
MIT, public repo (`github.com/Ashutoshx7/VengeanceUI`), registry served from that repo.
Pin by commit SHA, never `main`. Do not link the vendor site from our README or demo
script — its docs pages carry crypto-token promotion.

**Skiper UI** — secondary. Cards, carousels, hero/showcase, where it is clearly better
than the Vengeance UI equivalent. Free components only. It has **no public source
repository**, so vendor the file and own it from that moment. Attribution to Skiper UI
is required by its free licence — put it in the app colophon. Never add the paid tier:
a licence key validated on every install is not acceptable in a portfolio build.

**"Animaster"** — rejected. No package, no repository, no docs; promo content only.
Do not import it, and do not substitute `animista.net` for it — that emits CSS
keyframes, not React components.

Any library not named above is unverified. Identify the exact package/repository,
confirm it is installable and maintained, and record the finding in `docs/DECISIONS.md`
before writing the import. Never write an import for a library whose source has not
been inspected.

Wrap vendor components with local design-system components so the app remains replaceable.

Example:

```text
components/motion/GenerateButton.tsx
components/motion/LookReveal.tsx
components/wardrobe/GarmentCard.tsx
components/composer/RemixSheet.tsx
```

## Accessibility

- visible keyboard focus
- semantic buttons
- meaningful labels
- sufficient contrast
- 44px touch targets
- reduced motion
- alt text
- no hover-only critical actions
