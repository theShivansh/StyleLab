# Architecture — STYLELAB

## 1. High-level architecture

```text
                    Next.js Web
                        |
                  typed API client
                        |
                     FastAPI
                        |
       +----------------+----------------+
       |                |                |
    Profile        AI Orchestrator    Analytics
       |                |
   Postgres       +-----+------+------+
                  |            |
              Groq LLM     Catalogue
                  |            |
              Groq Vision   Ranker
                  |            |
                  +-----+------+ 
                        |
                   Outfit JSON
                        |
                   VTO Adapter
                        |
                 Async Job Worker
                        |
                  Object Storage
```

## 2. Groq AI architecture

### Model roles

`GROQ_TEXT_MODEL`
- default candidate: `openai/gpt-oss-120b`
- purpose: outfit orchestration, explanations, structured ranking

`GROQ_VISION_MODEL`
- default candidate: `qwen/qwen3.8-27b`
- purpose: image understanding, garment/style visual interpretation

Model IDs are configuration values so they can be changed without changing domain code.

### Output strategy

Prefer Groq Structured Outputs with JSON Schema for production paths where the selected model supports strict mode.

Schema pipeline:

```text
prompt
→ Groq
→ JSON Schema
→ Pydantic validation
→ business validation
→ database SKU validation
→ domain object
```

Business validation remains mandatory even when schema validity is guaranteed.

## 3. Image input

For user-provided images:
- validate size/type
- store privately
- generate a short-lived access URL when needed
- pass image reference to vision/VTO provider
- never log raw image data

Groq vision models currently support image inputs; keep the image analysis role separate from the VTO rendering role.

## 4. AI orchestration

Preferred sequence:

1. normalize style preferences
2. retrieve deterministic catalogue candidates
3. analyze visual context when needed
4. ask Groq to rank known candidates
5. validate structured output
6. resolve IDs against database
7. calculate final deterministic score
8. launch VTO
9. persist result

## 5. VTO provider

VTO is intentionally separate from Groq.

```ts
interface VirtualTryOnProvider {
  createJob(input: TryOnInput): Promise<TryOnJob>
  getJob(jobId: string): Promise<TryOnStatus>
  cancelJob?(jobId: string): Promise<void>
}
```

Use:
- `MockVirtualTryOnProvider` for local/demo
- a real image-generation/VTO provider in production when credentials are available

This prevents the project from being coupled to one image vendor.

## 6. Commerce adapter

```ts
interface CommerceAdapter {
  searchProducts(input: ProductQuery): Promise<Product[]>
  getProduct(id: string): Promise<Product | null>
  getProductUrl(id: string): string
}
```

MVP:
`MockCommerceAdapter`

Future:
retailer, Shopify, headless commerce, or internal catalog adapters.

## 7. Async jobs

```text
POST generate
→ job created
→ worker queue
→ AI/VTO
→ output validation
→ object storage
→ job completed
```

Frontend:
polling for MVP
SSE/WebSocket later.

## 8. Reliability

- provider timeout
- bounded retry
- exponential backoff
- idempotency keys
- circuit breaking where useful
- demo fallback
- curated fallback outfit
- explicit error codes

## 9. Observability

Record:
- request ID
- job ID
- provider
- model
- duration
- token usage where available
- retry count
- status
- error class

Do not record:
- raw image content
- secrets
- unnecessary personal/sensitive attributes

## 10. Security boundaries

- authentication/authorization
- signed/private image access
- upload validation
- rate limiting
- row ownership
- environment secrets
- sanitized provider errors
- validated AI output

## 11. Performance

Frontend:
- SSR static content
- image optimization
- lazy-load heavy modules
- cache demo results

AI:
- async jobs
- deterministic candidate prefiltering
- bounded output tokens
- cache repeatable recommendation requests where safe
