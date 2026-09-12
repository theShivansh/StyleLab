# 7–10 Day Development Plan

## Day 0 / Foundation

- initialize repo
- inspect environment
- establish architecture
- create docs
- establish design tokens
- establish provider interfaces

Exit:
app boots + CI checks pass.

## Day 1

Landing + design system

Exit:
premium responsive landing and navigation.

## Day 2

Onboarding + composer

Exit:
user can upload/select and build an outfit draft.

## Day 3

Wardrobe domain + recommendation

Exit:
items the user owns can be filtered and ranked into valid outfit JSON.

## Day 4

Upload + async analysis pipeline

Exit:
generation job can be created, tracked, completed, and displayed.

## Day 5

Result + remix

Exit:
single-item replacement updates outfit state and visual result.

## Day 6

Analytics + persistence

Exit:
core funnel events and saved looks are recorded.

## Day 7

Demo hardening

Exit:
clean 90-second recruiter/interviewer demo.

## Days 8–10

Optional:
- 7-day planner
- share cards
- preference learning
- performance
- polish
- tests
- deployment
- case-study content

## Scope rule

If live extraction is unstable, preserve the complete product flow behind the analyzer
adapter and fall back to the deterministic analyzer. Do not sacrifice the UX architecture
to chase one model integration.
