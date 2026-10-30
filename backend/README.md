# 02build AgriTech — FastAPI + Supabase backend

REST API for the AgriTech frontend (`index.html` + `script.js`). It replaces the
old Express/SQLite server and stores everything in **Supabase (Postgres)**.

| Feature | Endpoints |
| --- | --- |
| Accounts (phone + password, JWT) | `/api/auth/signup`, `/api/auth/login`, `/api/auth/me` |
| E-market listings | `GET/POST /api/market`, `GET/PATCH/DELETE /api/market/{id}` |
| Live auctions | `POST /api/market/{id}/bid`, `GET /api/market/{id}/bids` |
| Machinery & labour | `GET/POST /api/machinery`, `GET/PATCH/DELETE /api/machinery/{id}` |
| AI Plant Doctor (Gemini) | `POST /api/plant-doctor/analyze` |
| Scan history | `GET /api/scans`, `GET/DELETE /api/scans/{id}` |
| Health | `GET /api/health` |

Interactive API docs are available at **http://localhost:8000/docs**.

---

## 1. Create the Supabase project

1. Open <https://supabase.com/dashboard> and click **New project**.
2. Pick a name, a strong database password and a region close to you.
3. Wait for provisioning to finish.

### Get the connection values

Go to **Project Settings → API**:

| Value | Where it is used |
| --- | --- |
| **Project URL** (`https://xxxx.supabase.co`) | `SUPABASE_URL` |
| **service_role key** / **Secret key** (`eyJ…` or `sb_secret_…`) | `SUPABASE_SERVICE_KEY` |
| **anon public key** (optional) | `SUPABASE_ANON_KEY` |

> ⚠️ The service-role/secret key bypasses Row Level Security. Keep it on the
> server only — never commit it or put it in `script.js`.

For the schema script, open **Project Settings → Database → Connection string →
URI** and replace `[YOUR-PASSWORD]` with your database password. That URL is
`SUPABASE_DB_URL`.

---

## 2. Create the tables

Pick **one** of these options.

### Option A — SQL editor (fastest)

In the Supabase dashboard open **SQL Editor → New query**, paste the contents of
`backend/sql/001_schema.sql`, run it, then do the same with
`backend/sql/002_seed.sql`. Both files are safe to re-run.

### Option B — script (recommended for repeatable setup)

Create `backend/.env` first (step 3), then run:

```powershell
cd backend
..\.venv\Scripts\python.exe scripts\init_db.py
```

The script applies every file in `backend/sql/` in order. Use `--no-seed` to
skip the demo rows, or pass `--url "postgresql://..."` explicitly.

### What gets created

| Table | Purpose |
| --- | --- |
| `users` | app accounts: name, phone (unique), bcrypt password hash, location, role |
| `market_listings` | produce listings, `mode = direct \| auction`, current bid, owner |
| `bids` | bid history for auctions (cascade delete with the listing) |
| `machinery_listings` | equipment/labour offers and requirements |
| `scans` | saved AI Plant Doctor reports + `prevention` JSONB |

Indexes, `updated_at` triggers and RLS policies are included. RLS lets the anon
key read listings only; the API uses the service role so it can write.

---

## 3. Configure the environment

```powershell
cd backend
Copy-Item .env.example .env
```

Fill in at minimum:

```dotenv
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-or-secret-key

# generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET=some-long-random-string

# optional, enables real AI diagnosis
GEMINI_API_KEY=your-key-from-https://aistudio.google.com/apikey
```

### Supabase is optional in development

With the default `DATABASE_MODE=auto`, the API uses Supabase when the URL and
service key are set, and otherwise falls back to a **local SQLite database** at
`backend/.local/agritech.db`. That means you can run and test the whole app
(accounts, auctions, machinery, scans) before creating a Supabase project. The
data survives restarts; delete the file to reset it.

| `DATABASE_MODE` | Behaviour |
| --- | --- |
| `auto` (default) | Supabase when configured, local SQLite otherwise. Refuses local mode in production. |
| `supabase` | Require Supabase; DB routes return `503` until it is configured. |
| `local` | Always use the local SQLite file. |

The health badge in the UI shows **Local Dev DB** while the fallback is active
and **Supabase Connected** after you switch.

Other useful settings:

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_MODE` | `auto` | See table above |
| `LOCAL_DB_PATH` | `backend/.local/agritech.db` | Local SQLite file location |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | JWT lifetime (7 days) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Any vision-capable Gemini model |
| `PLANT_DOCTOR_MOCK` | `false` | `true` = canned report when no Gemini key |
| `CORS_ORIGINS` | `*` | Comma-separated origins in production |
| `SERVE_FRONTEND` | `true` | Serve `index.html`/`script.js` from FastAPI |
| `ENVIRONMENT` | `development` | `production` hides internal errors |

Verify the file is being read correctly (secrets are masked):

```powershell
python backend\scripts\check_config.py
python backend\scripts\check_config.py --require-supabase   # for deploys
```

It prints OK/MISSING for each value, flags a malformed URL or an anon key in the
service-key slot, and reports which database mode the API resolved to. Without
`--require-supabase` it exits 0 when the local fallback can serve the app.

---

## 4. Run it

From the repository root:

```powershell
# one-time
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# every time (auto-reload)
..\.venv\Scripts\python.exe backend\run.py
```

or, from `backend/`:

```powershell
..\.venv\Scripts\python.exe run.py            # dev server with auto-reload
..\.venv\Scripts\python.exe app\main.py       # plain server, no reload
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

> **Don't** run `python backend/app/main.py` as a bare script without the
> bootstrap in place — `app/main.py` uses relative imports (`from .config
> import ...`), and Python only supports those when the file is imported as
> part of the `app` package. `run.py` (and `python app/main.py`) handle this for
> you. In PyCharm, set the run configuration **Module name** to `uvicorn` with
> parameters `app.main:app --reload`, or simply run `run.py`.

Open **http://127.0.0.1:8000** — FastAPI serves the frontend and the API on the
same origin, so there are no CORS issues.

- Sign up with a phone number and a password (min. 6 characters).
- The first market/machinery rows come from `002_seed.sql` (Supabase) or the
  equivalent built-in seed rows (local mode).
- Restart the server after editing `backend/.env`; auto-reload only watches
  `backend/app/`.

If you prefer to open `index.html` directly (or host it separately), the
frontend calls `http://127.0.0.1:8000/api` automatically when loaded from
`file://`. For another host run this once in the browser console:

```js
setApiBase('https://your-api.example.com/api');
```

---

## 5. How auth works

1. `POST /api/auth/signup` normalises the phone number, hashes the password
   with **bcrypt** (SHA-256 pre-hash so long passwords work) and inserts a row
   into `users`.
2. The API returns a **JWT** (`Authorization: Bearer <token>`, 7 days).
3. Protected routes read the token, load the user from Supabase, and use
   `owner_id` checks for update/delete.
4. Passwords are never returned by any endpoint.

There is no Supabase Auth phone/OTP dependency, so signup works out of the box
without an SMS provider.

## 6. AI Plant Doctor

`POST /api/plant-doctor/analyze` accepts the frontend payload:

```json
{ "imageBase64": "…", "mimeType": "image/jpeg" }
```

It validates the image (JPEG/PNG/WEBP/HEIC, max 8 MB), asks Gemini for a
strict-JSON diagnosis, validates/repairs the response, saves it to `scans` and
returns:

```json
{
  "report": {
    "crop": "Tomato",
    "status": "Active Disease Detected",
    "badgeColor": "red",
    "diagnosis": "Early Blight",
    "confidence": 96,
    "prevention": ["…", "…", "…"],
    "organicCure": "…",
    "chemicalCure": "…",
    "provider": "gemini"
  },
  "scan": { "id": "…", "crop": "Tomato", "…": "…" }
}
```

Without `GEMINI_API_KEY` the endpoint returns **503** (or a clearly labelled
demo report when `PLANT_DOCTOR_MOCK=true`).

---

## 7. Project structure

```
backend/
├─ app/
│  ├─ main.py            # FastAPI app, CORS, error handlers, /api/health
│  ├─ config.py          # env settings (pydantic-settings)
│  ├─ database.py        # Supabase client (service role)
│  ├─ security.py        # bcrypt + JWT
│  ├─ dependencies.py    # bearer auth / current user / ownership
│  ├─ schemas.py         # request & response models
│  ├─ utils.py           # phone normalisation, search sanitising
│  ├─ routers/
│  │  ├─ auth.py
│  │  ├─ market.py
│  │  ├─ machinery.py
│  │  ├─ plant_doctor.py
│  │  └─ scans.py
│  └─ services/plant_doctor.py
├─ sql/
│  ├─ 001_schema.sql
│  └─ 002_seed.sql
├─ scripts/init_db.py
├─ tests/                # 46 tests, in-memory Supabase fake (no network)
├─ requirements.txt
└─ .env.example
```

---

## 8. Tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
..\.venv\Scripts\python.exe -m pytest
```

The suite exercises auth, market CRUD, auction bidding, ownership checks,
machinery, plant-doctor validation and scan history with an in-memory fake, so
it runs without Supabase credentials.

---

## 9. Deployment

- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (from `backend/`).
- Set `ENVIRONMENT=production`, a strong `JWT_SECRET`, and
  `CORS_ORIGINS=https://your-frontend.example.com`.
- Keep `SUPABASE_SERVICE_KEY` in the platform's secret manager.
- Apply the SQL schema to your production Supabase project before the first deploy.
- Set `DATABASE_MODE=supabase` (or keep `auto` with credentials present).
  Production refuses to start on the local SQLite fallback.
- Set `SERVE_FRONTEND=false` if the frontend is hosted elsewhere.

---

## 10. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Badge says **Local Dev DB** | Expected until Supabase is configured. Fill `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (or set `DATABASE_MODE=supabase` to stop using the fallback). |
| `503 Supabase is not configured` | Only in `DATABASE_MODE=supabase`/production: set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`, then run `python backend\scripts\check_config.py` |
| `500 Database request failed` | Wrong service key, or the schema was never applied |
| `relation "public.market_listings" does not exist` | Run `sql/001_schema.sql` |
| Badge says **Backend Offline** | Start uvicorn on port 8000 or run `setApiBase(...)` |
| `502 AI provider request failed` | Invalid/expired `GEMINI_API_KEY` or the model name |
| `503 AI Plant Doctor is not configured` | Add `GEMINI_API_KEY` or set `PLANT_DOCTOR_MOCK=true` |
| Browser blocks API calls when opening `index.html` via `file://` | Open the app at `http://127.0.0.1:8000` instead |

The old `server.js` and `agritech.db` in the repository root belong to the
previous Express/SQLite backend. `index.html` no longer loads them; you can
delete them once you have confirmed the new API works.
