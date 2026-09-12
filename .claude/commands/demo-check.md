# Demo Check

Verify the recruiter demo path end to end with every external credential removed.

1. Confirm `APP_MODE=demo` runs with GROQ_API_KEY, VTO_API_KEY, DATABASE_URL all unset.
2. Walk the path in `docs/DEMO-SCRIPT.md`:
   Landing → Explore demo → Style profile → Compose → Generation → Result → What If? → Swap → Save.
3. At each step record: does it render, how long it takes, any console error.
4. Check specifically:
   - generation stages are the five named stages, not a spinner
   - remix swaps ONE item and leaves the others visually stable
   - every price/URL on screen traces to seed catalogue data
   - every simulated KPI is visibly labelled as demo data
   - no retailer name, logo, or affiliation claim appears anywhere
5. Run it at 390px and 1440px.

Fail the check on any dead-end error state. Report timings — a demo that works but takes 40s fails.
