# Implement Phase

Read the phase prompt supplied by the user and all relevant docs.

Work as the primary implementation agent.

Rules:
- inspect before editing
- preserve good existing code
- prefer reusable primitives
- test pure domain logic
- keep vendor integrations behind adapters
- verify after meaningful milestones

At completion:
- run checks
- summarize changed files
- summarize tests
- list known limitations
