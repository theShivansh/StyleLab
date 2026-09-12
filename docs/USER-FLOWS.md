# User Flows — STYLELAB

## Flow 1 — Demo

```text
Landing
  ↓
Explore Demo
  ↓
Sample Profile
  ↓
Preselected garments
  ↓
Compose
  ↓
Pre-generated result
  ↓
Remix
  ↓
Save/Shop
```

Goal:
Let a recruiter/interviewer understand the product in <90 seconds.

## Flow 2 — Real user

```text
Landing
↓
Create My Look
↓
Upload image
↓
Photo validation
├─ invalid → retry guidance
└─ valid
↓
Occasion
↓
Vibe
↓
Fit preference
↓
Product selection
↓
Compose
↓
Generation state
↓
Result
├─ Remix
├─ Save
├─ Share
└─ Shop
```

## Flow 3 — Remix

```text
Result
↓
What If?
↓
choose slot
↓
show compatible alternatives
↓
select item
↓
async regeneration
↓
updated result
↓
compare/save/shop
```

## Flow 4 — Failure

```text
Generate
↓
provider failure
↓
show friendly explanation
↓
Retry
or
Use curated look
```

Never strand the user on a dead-end error.

## Flow 5 — Delete photo

```text
Profile/Privacy
↓
Delete uploaded photo
↓
confirmation
↓
remove source asset
↓
invalidate related private preview where appropriate
↓
confirmation state
```

## Flow 6 — 7-day planner

```text
Style profile
↓
Generate week
↓
7 cards
↓
open day
↓
view outfit
↓
save/shop/remix
```
