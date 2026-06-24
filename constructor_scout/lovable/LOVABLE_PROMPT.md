# Paste this into Lovable

Use this prompt to generate the Constructor Scout UI in Lovable. The app is a
**frontend only** — it talks to a separate Python API (see
`constructor_scout/api.py`). After Lovable scaffolds the project, drop in the
files from this `lovable/src/` folder (they already match Lovable's stack:
Vite + React + TypeScript + Tailwind + shadcn/ui + @tanstack/react-query).

---

Build a lead-generation tool called **Constructor Scout** for a Constructor.io
sales rep. It calls an external HTTP API (base URL from the
`VITE_API_BASE_URL` env var) to scan retail/ecommerce websites for
product-discovery gaps. It is a single-page app, clean and professional, with a
light/dark friendly theme using shadcn/ui components.

The flow has three steps on one page:

1. **Region form.** A card where the user enters a country (e.g. "United
   Kingdom"), optional comma-separated verticals, and a max-sites number.
   Submitting calls `POST {API}/api/region` with `{ country, verticals?,
   per_vertical, max_sites }`, which returns `{ job_id }`. Then poll
   `GET {API}/api/job/{job_id}` every ~1.5s until `status` is `"done"` (or
   `"error"`). Show a spinner with the current `stage` text while running.

2. **Ranked shortlist.** When the region job finishes, `result` contains
   `{ country, scanned, shortlist: [...] }`. Render a table ranked by `gaps`
   (most discovery gaps first) with columns: rank, domain (badge "existing" if
   `existing_customer`), gaps, opportunity, platform, incumbent, top_gap, and a
   "Deep scan" button per row.

3. **Deep-dive brief.** Clicking "Deep scan" calls `POST {API}/api/deep` with
   `{ domain }`, polls the same job endpoint, and shows the result: a header
   with platform/incumbent/priority/opportunity, an executive `summary`, then a
   list of findings each rendered as **Problem** (`finding.problem`, plus
   italic `finding.example`) → **Solution (Constructor.io)** (`finding.capability`
   + `finding.solution` + a docs link), color-coded by `severity`
   (critical=red, high=orange, medium=amber, low=blue), with an evidence box.
   Finally a "Suggested outreach" card with the email subject/body and a
   copy-to-clipboard button. Include a "Back to shortlist" button.

Use `@tanstack/react-query` `useMutation` for the two scan actions, `sonner`
for toasts on error, and `lucide-react` icons. Keep all API logic in
`src/lib/api.ts` and types in `src/types.ts`. Read the API base URL from
`import.meta.env.VITE_API_BASE_URL`, defaulting to `http://localhost:8000`.

Do not build any backend or Supabase — this app only consumes the external API.
```
