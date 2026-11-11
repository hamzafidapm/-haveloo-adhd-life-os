# Haveloo ADHD Life OS — Streamlit App

The Haveloo ADHD Life OS planner as a hosted web app: 17 tabs (Command
Center, Focus & Time-Blindness, Dopamine Menu, Zero-Guilt Habits,
Impulse-Buy Vault, Brain Dump Triage, Executive Analytics, People,
Household, Learn, Explore, Career, Smart Planner, Voice & Focus Pro,
SOS & Daily Care, Money Guard, Print & Backup), 6 merged themes (one
picker — Cocoa, Sage, Apricot, Lavender, Ocean, Rosewood), accounts
with Etsy-order unlock, and a free demo mode.

Delivery works exactly like the competitor (FrameworkPlanningCo): the
Etsy listing contains **only one file — `Quick_Start_Guide.pdf`**. The
buyer opens the planner from the "Open my planner" link in the guide,
creates an account (email + password), unlocks it once with their Etsy
order number, then logs in on any device. No codes to copy, no keys to
keep.

> **No live app URL exists yet.** Do not invent one. The URL is created
> by the deploy steps below, then pasted into the guide (step 7). The
> guide in this repo still has its clearly-marked placeholder — **do
> NOT list it on Etsy until step 7 is done.**

## Files in this repo

| File | What it is |
|---|---|
| `app.py` | The planner (2,109+ lines) |
| `haveloo_hubs.py` | Tier 1 hubs: People, Household, Learn, Explore, Career |
| `haveloo_advance.py` | Tier 2 advance: Smart Planner, Voice & Focus Pro, SOS, Money Guard, Print & Backup |
| `haveloo_auth.py` | Accounts, Etsy-order unlock, per-user data, Postgres plumbing |
| `requirements.txt` | `streamlit==1.40.0`, `pandas==2.2.2`, `plotly==5.24.1` |
| `build_guide.py` | Re-exports `Quick_Start_Guide.pdf` (needs `reportlab`) |
| `Quick_Start_Guide.pdf` | The ONLY Etsy deliverable — placeholder URL until step 7 |
| `VERIFICATION.md` | Test results, incl. empty fresh accounts (§8, 59/59 checks) |
| `HOSTING.md` | Full hosting guide, Supabase steps, honest limits |
| `AUTH_DESIGN.md`, `BUILD_PLAN.md`, `INTEGRATION_*.md` | Design + build notes |

## Deploy — 7 steps (Streamlit Community Cloud)

GitHub account: **hamzafidapm**. Repo: **haveloo-adhd-life-os**.

### Step 1 — Create the GitHub repo (you do this — 2 minutes)

1. Go to **https://github.com/new** and sign in as **hamzafidapm**.
2. Repository name: `haveloo-adhd-life-os` (if GitHub says the name is
   taken, use the fallback `haveloo-adhd-life-os-app`).
3. Choose **Public** → **Create repository**.
4. Give the Muse GitHub App access to it: open
   **https://github.com/apps/meta-muse-ai/installations/new** and
   select `haveloo-adhd-life-os` (or "All repositories" if you already
   chose that).
5. Tell Muse the repo is created + selected. Muse then pushes all the
   files from this package with the GitHub connector (`push_files`,
   owner `hamzafidapm`, repo `haveloo-adhd-life-os`, branch `main`)
   and verifies the push by reading the file list back from GitHub.

Why this is a manual step: GitHub OAuth for Muse IS connected as
hamzafidapm (verified 2026-11-12 03:32 PKT), but the connector's
`create_repository` fails with 403 "Resource not accessible by
integration" — the GitHub App cannot create repos, only push to repos
it has been given access to. Do not retry the connector create; the
repo must be created at github.com/new. No password or token is needed
from you for the push itself.

Result: **https://github.com/hamzafidapm/haveloo-adhd-life-os**

### Step 2 — Deploy on Streamlit Community Cloud

1. Go to **https://share.streamlit.io** and sign in with GitHub
   (as hamzafidapm).
2. **Create app** → Repository: `hamzafidapm/haveloo-adhd-life-os` →
   Branch: `main` → Main file path: `app.py` → **Deploy**.
3. First deploy takes a few minutes. Later pushes to `main` redeploy
   automatically — do not redeploy casually (see "Data loss warning"
   below).

### Step 3 — Open the live URL

Copy the exact URL Streamlit shows (it will look like
`https://haveloo-adhd-life-os.streamlit.app`). Open it in a browser
and confirm the login screen loads.

### Step 4 — Host account test (on the live URL)

1. Create the host account (your own email + a password of 8+
   characters).
2. Unlock it with a **real Etsy order number** from the Haveloo shop.
3. Log out, then log back in — it must work.
4. Confirm the new account starts **completely empty** (0 tasks,
   0 XP, empty Big 3). This is the intended behaviour since 2026-11-12:
   buyers never see sample data; only the free demo has sample data.

### Step 5 — Second-account leak check (on the live URL)

1. Create a second test account, unlock it with another real order
   number, add a task with a unique name (e.g. `LEAK-TEST-123`).
2. Log out, log in as the first account — that task must NOT be there.
3. Log in as the second account — the task must still be there.

### Step 6 — Decide Postgres before the first real buyer

See **HOSTING.md §6** for the exact Supabase free-tier steps
(create project → copy the URI → set `HAVELOO_DATABASE_URL` in
Streamlit Secrets → add `psycopg2-binary` → create tables from
`POSTGRES_AUTH_DDL` + the ported user schema → redeploy → re-test).

**Honest warning:** the Postgres *plumbing* exists in the code, but
the per-user *migration* (porting the planner tables to Postgres) is
NOT built yet. Until it is, buyer data lives in per-user SQLite files
that Streamlit Cloud's ephemeral filesystem can lose on redeploy.
Until the migration is done, tell buyers to keep the in-app JSON
backup (Export in the account area) and do not redeploy casually.

### Step 7 — Paste the real URL into the guide, then list on Etsy

1. Open `build_guide.py` and find this line (the placeholder box,
   around line 118):

   ```python
   [Paragraph("YOUR APP LINK — paste your Streamlit Cloud app URL here before listing",
              placeholder_style)],
   ```

   Replace the placeholder text with your real URL as a clickable
   link, keeping the same `Paragraph(...)` shape:

   ```python
   [Paragraph('<link href="https://haveloo-adhd-life-os.streamlit.app">https://haveloo-adhd-life-os.streamlit.app</link>',
              placeholder_style)],
   ```

   (Use your actual Streamlit URL, not the example above, if it differs.)
2. Re-export the guide (system `python3` has reportlab installed):

   ```bash
   python3 build_guide.py
   ```

3. Verify the new PDF before listing:

   ```bash
   pdfinfo Quick_Start_Guide.pdf        # must say 2 pages
   pdftotext Quick_Start_Guide.pdf - | grep -i "streamlit.app"   # your URL must appear
   pdftotext Quick_Start_Guide.pdf - | grep -i "YOUR APP LINK"   # must print NOTHING
   ```

4. List **ONLY `Quick_Start_Guide.pdf`** on Etsy. Nothing else goes
   in the listing file.

## .gitignore — use exactly this

```gitignore
# Buyer data — NEVER commit a database file. A committed .db would
# publish buyers' emails, password hashes and order numbers to GitHub,
# and every redeploy would overwrite the live file with the committed copy.
data/
*.db
*.sqlite3

# Python bytecode / caches
__pycache__/
*.pyc

# Streamlit secrets (never commit)
.streamlit/secrets.toml
```

## Data loss warning (read this)

Streamlit Community Cloud has an **ephemeral filesystem**: files the
app writes while running (the auth `.db` and per-user
`data/user_*.db` files) are NOT guaranteed to survive a redeploy, a
reboot, or a move to another machine. Accounts, unlocks and all user
data can be lost on a redeploy in v1. Decide the Postgres step (step 6)
before the first real buyer, or accept the v1 risk in writing and tell
buyers to keep JSON backups.

## Honest limits

- **No live Etsy verification.** Unlock is a format check (digits,
  8–13 chars) + a stored record for seller verification. The app and
  the guide say exactly this. Do not tell buyers Etsy checks it
  automatically.
- **"AI" is rule-based** (Smart Insights / Breakdown / Day Planner
  compute from the user's own logs). No LLM is wired.
- **Calendar is a downloadable `.ics` file**, not live 2-way sync;
  push notifications are not live.
- **Voice input** needs a browser with SpeechRecognition; typed
  fallback exists. Soundscapes are named choices + a generated
  sine-tone beep only.
- **SOS / cycle are not medical advice**; SOS is not a crisis service.
- **Free demo mode** keeps the sample data (XP 680, 13 tasks, Alex's
  planner) with a visible FREE DEMO banner. Demo and buyer accounts
  are fully separate.

## Routes that are NOT the deploy path

- **Vercel** — blocked with a 403 on this user's team scope
  (`team_QFQmiAxdSCyzMC6W026AGrFe`, hamzafidapm) and cannot run a
  Streamlit Python server anyway. Do not retry it.
- **Cloudflare Pages** — static hosting only; cannot run the
  Streamlit Python server.
