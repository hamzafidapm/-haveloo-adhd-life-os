# Haveloo ADHD Life OS — Hosting Guide (Streamlit Community Cloud)

How to put the hosted app behind the "Open my planner" link in the
Quick Start Guide. No live URL exists yet — do NOT invent one. The URL
is created by following these steps, then pasted into the guide's
placeholder box before the Etsy listing goes live.

## 1. Repo layout

GitHub account: **hamzafidapm** (the user's own account — do not use any
other account). Repo name: **haveloo-adhd-life-os**, i.e.

**https://github.com/hamzafidapm/haveloo-adhd-life-os**

Checked 2026-11-12: no public repo exists at that URL (GitHub returns
404), so the name appears free. If GitHub says the name is taken when
creating it (e.g. a private repo with the same name exists), use the
fallback name **haveloo-adhd-life-os-app** instead.

Create the repo as **Public** (Streamlit Community Cloud works with
either, but Public is the instruction for this deploy) with exactly
these files at the repo root (this is what the deploy ZIP contains):

```
haveloo-adhd-life-os/
├── app.py                 # the planner
├── haveloo_hubs.py        # Tier 1 hubs (People, Household, Learn, Explore, Career)
├── haveloo_advance.py     # Tier 2 advance (Smart Planner, Voice & Focus Pro, SOS, Money Guard, Print)
├── haveloo_auth.py        # accounts + unlock + per-user data
├── requirements.txt       # streamlit, pandas, plotly (+ psycopg2-binary later, see §6)
├── README.md              # deploy steps (this file's short version)
├── .gitignore             # MUST exclude *.db — see §3
├── build_guide.py         # re-exports Quick_Start_Guide.pdf after the URL is pasted in
├── Quick_Start_Guide.pdf  # the ONLY Etsy deliverable (still has the placeholder URL until §7 step 6)
├── VERIFICATION.md        # test results, incl. empty fresh accounts (§8)
├── HOSTING.md             # this file
├── AUTH_DESIGN.md
├── BUILD_PLAN.md
├── INTEGRATION_AUTH.md
├── INTEGRATION_HUBS.md
└── INTEGRATION_ADVANCE.md
```

`requirements.txt` (v1 — matches the verified base):

```
streamlit==1.40.0
pandas==2.2.2
plotly==5.24.1
```

Do NOT add anything else for v1. In particular, do not add a
database driver until the Postgres step (§5) is actually done.

## 2. Deploy on Streamlit Community Cloud

1. Create the repo: go to https://github.com/new, sign in as
   **hamzafidapm**, set Repository name to `haveloo-adhd-life-os`,
   choose **Public**, click "Create repository". Then upload
   the deploy ZIP contents (upload all files at the repo root — do NOT
   upload the ZIP file itself, and do NOT upload any `.db` file).
   (GitHub OAuth for this environment IS connected — verified 03:32 PKT
   as hamzafidapm, account_id `f19b726510d84db586eb6a160c71baf4` — but
   the connector's `create_repository` FAILS with 403 "Resource not
   accessible by integration": the GitHub App cannot create repos.
   Do NOT retry it. The user must create the repo at github.com/new.)
2. Give the Muse GitHub App access to the new repo: open
   https://github.com/apps/meta-muse-ai/installations/new and select
   `haveloo-adhd-life-os` (or choose "All repositories" if that was
   already selected). Until this is done, the connector cannot push
   to the repo — do not claim repo access until it is verified with a
   read tool.
3. Once the user confirms the repo is created + selected, the finished
   package is pushed with the connector's `push_files` (owner
   `hamzafidapm`, repo `haveloo-adhd-life-os`, branch `main`), then
   verified by reading back the file list from GitHub.
2. Go to https://share.streamlit.io (sign in with GitHub as hamzafidapm).
3. "Create app" → Repository: `hamzafidapm/haveloo-adhd-life-os`,
   branch `main`, main file path `app.py`.
4. Deploy. First deploy takes a few minutes; later pushes to `main`
   redeploy automatically.
5. The app URL will look like
   `https://haveloo-adhd-life-os.streamlit.app` (or similar — copy the
   exact URL Streamlit shows). That is the URL to paste into the Quick
   Start Guide placeholder box (and only then is the guide ready to
   list on Etsy).

**Routes that are NOT the deploy path (do not retry them):**
- **Vercel** — the Vercel connector was blocked with a 403 on this
  user's team scope (`team_QFQmiAxdSCyzMC6W026AGrFe`, account
  hamzafidapm) on 2026-11-11, and Vercel cannot run a Streamlit
  Python server anyway. Streamlit Community Cloud is the path.
- **Cloudflare Pages** — static hosting only; it cannot run the
  Streamlit Python server. (Pages was used for the HTML/Excel demo
  sites, which are static — a different product.)

## 3. The .db file must NOT be committed to the repo

`.gitignore` must contain at minimum:

```
*.db
*.sqlite3
data/
__pycache__/
```

Why: the `.db` file holds real user accounts and user data. Committing
it would publish buyers' emails, password hashes and order numbers to
GitHub, and every redeploy would overwrite the live file with the
committed copy. Never commit a database file. If a `.db` was ever
committed by mistake, remove it from git history and force every
affected buyer to reset their password.

## 4. Secrets needed (v1)

None. v1 needs no API keys and no secrets, because there is no live
Etsy verification and no external service. Two OPTIONAL settings exist:

| Setting | Where | What it does |
|---|---|---|
| `HAVELOO_UNLOCK_MODE` | Streamlit Cloud → App settings → Secrets, as an env var, or `app_settings` table | v1 only accepts `recorded` (unlock = format check + stored record for seller verification). Any other value falls back to `recorded`. There is no value that turns on live Etsy verification — that does not exist yet. |
| `HAVELOO_DEMO_ENABLED` | env var | `0` hides the free demo; default `1` shows it. |
| `HAVELOO_AUTH_DB_PATH` | env var | Path of the auth DB file (default `adhd_life_os.db`). |
| `HAVELOO_DATA_DIR` | env var | Folder for per-user DB files (default `data/`). |

How to set an env var on Streamlit Cloud: App → ⋮ menu → Settings →
Secrets → add as TOML, e.g. `HAVELOO_DEMO_ENABLED = "0"`, then reboot
the app. (Secrets are exposed as environment variables to the app.)

## 5. What happens on redeploy — the ephemeral-filesystem limit (read this)

Streamlit Community Cloud gives the app an **ephemeral filesystem**:
files the app writes while running (the auth `.db` and the per-user
`data/user_*.db` files) are NOT guaranteed to survive a redeploy, a
reboot, or a move to another machine. In practice:

- Pushing a new commit to `main` redeploys the app. Data written since
  the last deploy *may* still be there, or *may* be gone — Streamlit
  does not promise either way.
- That means: accounts, unlocks and all user data can be lost on a
  redeploy in v1. This is the single biggest limit of this build, and
  it is stated here and in AUTH_DESIGN.md rather than hidden.

Mitigations in v1 (do them from day one):

1. Tell buyers in the guide to use the in-app JSON backup (Export in
   the account area — `export_user_data` / `import_user_data` in
   `haveloo_auth.py`). A backup file on the buyer's own device survives
   any redeploy.
2. Before every redeploy, download a copy of the live `.db` files if
   the app offers a download, or accept that v1 data is best-effort.
3. Do NOT redeploy casually. Batch changes.

## 6. The better option (recommended before scaling): hosted Postgres / Supabase

For real multi-device sync, backups and redeploy-proof data, move the
storage to a hosted Postgres database. Free tiers that fit this app:

- **Supabase free tier** (recommended) — hosted Postgres, 500 MB
  database, backups, dashboard to inspect the `accounts` table and
  check order numbers.
- **Neon free tier** — hosted Postgres, similar size.

### Exact steps (Supabase free tier)

1. Go to https://supabase.com/dashboard and sign in (or create a free
   account — email + password, no card needed for the free tier).
2. Click **New project**. Name: `haveloo-adhd-life-os`. Set a strong
   **Database password** (save it somewhere safe — Supabase shows it
   only once) and pick the region closest to the buyers (US East is
   the sensible default for a US Etsy audience). Click "Create new
   project" and wait 1–2 minutes for provisioning.
3. In the project, go to **Settings → Database → Connection string →
   URI**. Copy the URI. It looks like:
   `postgresql://postgres:<your-database-password>@db.<project-ref>.supabase.co:5432/postgres`
   (do NOT paste a real URI into any doc or chat — keep it in
   Streamlit Secrets only).
4. In Streamlit Cloud → your app → ⋮ menu → **Settings → Secrets**,
   add the TOML line:
   `HAVELOO_DATABASE_URL = "postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres"`
   then save and reboot the app.
5. Add one line to `requirements.txt` and push it:
   `psycopg2-binary`
6. Create the tables once in the hosted database using the
   `POSTGRES_AUTH_DDL` string in `haveloo_auth.py`, plus the per-user
   tables from `init_user_db_schema` (ported to Postgres syntax — see
   AUTH_DESIGN.md §3 for what changes: `AUTOINCREMENT` → `SERIAL`,
   `ON CONFLICT` already works in Postgres). Run the DDL in the
   Supabase dashboard SQL Editor (left menu → SQL Editor → New query
   → paste → Run).
7. Redeploy, then re-test: create an account, unlock it, add a task,
   log out, log back in — the task must still be there after a
   redeploy (push a trivial commit to `main` to force one).

### ⚠️ What is NOT done yet — read before you set the URL

The **plumbing is done, the migration is NOT done.** `haveloo_auth.py`
already reads `HAVELOO_DATABASE_URL` (`database_config()` /
`open_connection()`): if it is set, the auth connection goes to
Postgres; if it is unset, it falls back to local SQLite with a warning
(`storage_warning()`); if it is set but no Postgres driver is
installed, the app raises a clear error instead of silently using
SQLite.

But the per-user planner tables (tasks, habits, hubs, advance) are
still SQLite-only code: the `init_user_db_schema` port to Postgres,
per-user rows (one row-set per account, replacing one file per
account), and the port of every `get_conn()` call site to the Postgres
connection are a **remaining code step**. Setting the URL alone does
NOT move buyer data to Postgres — until that migration code is built
and tested, the app still writes per-user SQLite files and the
redeploy risk in §5 still applies. Do NOT claim the migration is done
until it is built, tested (same 59-check suite against Postgres) and
written up in VERIFICATION.md.

Env-var names the code reads (exact):

- `HAVELOO_DATABASE_URL` — Postgres connection string (unset = SQLite fallback + warning)
- `HAVELOO_AUTH_DB_PATH` — SQLite auth DB path (default `adhd_life_os.db`)
- `HAVELOO_DATA_DIR` — per-user SQLite files folder (default `data/`)
- `HAVELOO_UNLOCK_MODE` — `recorded` only in v1
- `HAVELOO_DEMO_ENABLED` — `0` to hide the free demo

## 7. Deploy checklist (in order)

1. [ ] Repo `github.com/hamzafidapm/haveloo-adhd-life-os` has `app.py`,
       `haveloo_hubs.py`, `haveloo_advance.py`, `haveloo_auth.py`,
       `requirements.txt`, `README.md`, `.gitignore` with `*.db` + `data/`.
2. [ ] `python3 -m py_compile haveloo_auth.py app.py` passes locally.
3. [ ] Deploy on Streamlit Cloud; note the real app URL.
4. [ ] Open the URL: create the first (host) account, unlock it with a
       real Etsy order number, log out, log back in — end to end.
5. [ ] Create a second test account; check its tasks do NOT appear in
       the first account (per-user isolation).
6. [ ] Paste the real app URL into the Quick Start Guide placeholder
       box and re-export the PDF. Do NOT list the guide on Etsy with
       the placeholder still in it.
7. [ ] Decide the Postgres step (§6) before the first real buyer, or
       accept the v1 redeploy risk in writing and tell buyers to keep
       JSON backups.
8. [ ] Upload the finished guide PDF (only file) to the Etsy listing.
