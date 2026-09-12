# Test Layout

Recommended final layout:

```text
tests/
├── unit/
├── integration/
├── e2e/
├── ai/
│   ├── fixtures/
│   ├── mock-groq/
│   └── evaluator/
├── contract/
├── accessibility/
└── performance/
```

All tests must support an offline/mock path for CI.
AI provider integration tests are separate and opt-in.
