# Constructor Scout — Lovable UI

A web UI for the Constructor Scout agent. Lovable builds the **frontend**
(React/Vite/TS/Tailwind/shadcn). The actual scanning runs in the **Python API**
(`constructor_scout/api.py`), because it crawls the live web and calls Claude —
which can't run inside Lovable's Supabase edge functions.

```
┌────────────────────┐   HTTPS    ┌──────────────────────────┐
│  Lovable frontend  │ ─────────► │  Python API (FastAPI)    │
│  (this folder)     │ ◄───────── │  constructor_scout/api.py│
└────────────────────┘   JSON     └──────────────────────────┘
                                     │  discovery + crawl + Claude
                                     ▼
                                   the open web
```

## 1. Run the API (the brain)

```bash
cd constructor_scout
pip install -e ".[api]"
export ANTHROPIC_API_KEY=sk-ant-...        # optional; tailors the copy
uvicorn constructor_scout.api:app --host 0.0.0.0 --port 8000
```

For Lovable to reach it, the API must be **publicly reachable** — deploy it
(Render/Railway/Fly/your VM) or expose localhost with `ngrok http 8000`. It
needs open outbound internet to discover and crawl sites.

## 2. Build the UI in Lovable

1. Open [lovable.dev](https://lovable.dev), create a project, and paste
   [`LOVABLE_PROMPT.md`](./LOVABLE_PROMPT.md).
2. Replace/add the generated files with the ones in [`src/`](./src):
   `types.ts`, `lib/api.ts`, `pages/Index.tsx`, and `components/*`.
3. In **Project Settings → Environment variables**, set
   `VITE_API_BASE_URL` to your deployed API URL (e.g.
   `https://scout-api.onrender.com` or your ngrok URL).

## 3. Run locally (optional, outside Lovable)

These files assume a standard Vite + shadcn project with the `@/` alias and
these deps installed: `@tanstack/react-query`, `lucide-react`, `sonner`, and the
shadcn components `button input label card table badge separator`. Then:

```bash
cp .env.example .env       # set VITE_API_BASE_URL
npm run dev
```

## API reference

| Method | Path                  | Body                                                  | Returns        |
|--------|-----------------------|-------------------------------------------------------|----------------|
| POST   | `/api/region`         | `{country, verticals?, per_vertical?, max_sites?}`    | `{job_id}`     |
| POST   | `/api/deep`           | `{domain}`                                             | `{job_id}`     |
| POST   | `/api/scan`           | `{url}`                                                | `{job_id}`     |
| GET    | `/api/job/{id}`       | —                                                     | job + `result` |
| GET    | `/health`             | —                                                     | `{ok, llm}`    |

Jobs are async: POST returns a `job_id`, then poll `/api/job/{id}` until
`status` is `"done"` (`result` populated) or `"error"`. `stage` reports
progress. See `src/lib/api.ts` for the polling client.

> **Heads-up:** the in-memory job store is single-process — fine for one rep /
> a demo. For multi-user use, swap it for Redis/a queue.
