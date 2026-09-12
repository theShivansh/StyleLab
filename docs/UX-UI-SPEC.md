# UX/UI Specification — STYLELAB

## Brand

STYLELAB ✦

Tagline:
“Your wardrobe, recomposed by AI.”

Tone:
confident, editorial, playful, intelligent.

## Visual direction

Editorial fashion × AI lab × premium commerce.

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
generated look

Secondary:
Style Match
outfit item list
total
save
shop

Primary interaction:
Remix

### 6. Remix

“What if?”

Tabs:
Top / Bottom / Shoes / Layer

Candidates:
3–5 strong alternatives

Interaction:
replace one item → update look → show new result

### 7. Planner

7-day cards
with occasion labels and quick shop/save actions.

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

Skiper UI, Vengeance UI and “Animaster” are all **unverified** until Claude inspects the
actual source. Use any of them only after identifying the exact package/repository,
confirming it is installable and currently maintained, and recording the finding in
`docs/DECISIONS.md`. If one turns out to be a copy-paste registry rather than an
installable package, record that and vendor the component instead of importing it.
Never write an import for a library whose source has not been inspected.

Subject to that gate:

Use Skiper UI for selected cards, carousels, hero/showcase interactions where it genuinely improves UX.

Use Vengeance UI for selected animated CTA, image interaction, text, loader, or showcase patterns.

Wrap vendor components with local design-system components so the app remains replaceable.

Example:

```text
components/motion/GenerateButton.tsx
components/motion/LookReveal.tsx
components/catalog/ProductCard.tsx
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
