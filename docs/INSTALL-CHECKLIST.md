# Installation Checklist

## Node
- Node.js current LTS
- pnpm/npm/yarn, consistent with repo lockfile

## Python
- Python 3.12
- virtual environment
- FastAPI
- Pydantic
- SQLAlchemy
- pytest
- Groq SDK

## Frontend packages

Install only versions compatible with the existing repo:
- next
- react
- typescript
- tailwindcss
- shadcn/ui primitives
- motion
- zustand
- @tanstack/react-query
- lucide-react
- playwright
- vitest

UI libraries:
- Skiper UI, after verifying its current package/source
- Vengeance UI, after verifying its current source/install instructions

## Backend packages
- fastapi
- uvicorn
- pydantic
- sqlalchemy
- psycopg
- httpx
- groq
- pytest
- pytest-asyncio
- ruff

Do not blindly paste this list into an already configured project. Inspect lockfiles and current package APIs first.
