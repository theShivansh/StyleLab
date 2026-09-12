# PHASE — Turn Design References into Production UI

Act as a principal product designer + frontend engineer.

The user may provide screenshots, generated concept images, or Figma exports.

Your task:
1. inspect the reference carefully
2. identify layout hierarchy
3. identify reusable primitives
4. translate visual tokens into local CSS variables
5. reproduce the information architecture, not just the pixels
6. preserve responsive intent
7. add proper interaction states
8. implement accessible semantics
9. implement reduced-motion variants
10. avoid copying proprietary branding/logos

Use:
- Tailwind
- shadcn
- local design-system components
- Skiper UI where beneficial
- Vengeance UI where beneficial

Do not:
- make every element a glass card
- overuse animation
- hardcode desktop-only dimensions
- create an enormous single component
- sacrifice accessibility for visual fidelity

Deliver:
- components
- responsive states
- tokens
- interactions
- tests
- screenshot QA

Run `/ui-audit` after implementation.
