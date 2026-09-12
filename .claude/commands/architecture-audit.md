# Architecture Audit

Act as a staff engineer reviewing a production candidate.

Audit:
- boundaries
- dependency direction
- type safety
- API contracts
- AI/provider abstractions
- domain logic isolation
- persistence ownership
- error handling
- observability
- security
- testability

Look for:
- business logic inside UI
- vendor lock-in
- unvalidated LLM data
- hidden side effects
- duplicated schemas
- brittle state management

Make only justified changes and document major architectural decisions.
