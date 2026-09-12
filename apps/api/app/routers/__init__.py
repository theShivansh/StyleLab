"""HTTP routes.

Thin by design: parse, delegate, serialise. No route builds a query, calls a provider, or
decides what a failure means — those live in `repositories/`, `adapters/` and `services/`
respectively. A route that grows business logic is a rule that cannot be tested without a
web server.

Every wardrobe route takes `CurrentUser` and passes it down as the first argument. That is
the ownership boundary, and it is visible in every signature on purpose.
"""
