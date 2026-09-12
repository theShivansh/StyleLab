# Demo Check

Verify the recruiter demo path end to end with every external credential removed.

1. Confirm `APP_MODE=demo` runs with GROQ_API_KEY and DATABASE_URL unset.
2. Walk the path in `docs/DEMO-SCRIPT.md`:
   Landing → Upload 6-8 garment photos → Analysis → Review/correct → Preferences
   → Compose → Result → What If? → Swap → Save.
3. At each step record: does it render, how long it takes, any console error.
4. Check specifically:
   - analysis cards resolve independently; no single spinner over the batch
   - stages are named, not a spinner
   - low-confidence fields are hedged and correctable
   - a correction persists through regeneration
   - swap changes ONE item and leaves the others visually stable
   - every garment on screen traces to an item uploaded in this session
   - insufficient wardrobe names the gap instead of inventing an item
   - every simulated KPI is visibly labelled as demo data
   - no commerce, price, merchant link, or retailer affiliation appears anywhere
   - no claim about the person in any photo
5. Run it at 390px and 1440px.

Fail the check on any dead-end error state. Report timings — a demo that works but takes 40s fails.
