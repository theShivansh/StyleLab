# packages/

Shared TypeScript types only, and only when something is **genuinely** shared between
`apps/web` and another TS consumer.

Intentionally empty right now. There is one TS consumer, so a shared package would be
indirection with nothing on the other side of it. `apps/web/src/lib/schemas/` holds the
wire schemas until a second consumer exists.

Do not create a third app here. See the repository layout in `CLAUDE.md`.
