# Haveloo ADHD Life OS — Auth & Sync Design: the better-option analysis

The user asked: account + unlock + sync is mandatory, and if there is
a better option than the current approach, do that. This note compares
the three options honestly, states which one is implemented in this
build, and what remains a hosting step.

## The problem in one paragraph

The base app (`app.py`) is a single local SQLite file,
`adhd_life_os.db`, with no accounts. On a hosted Streamlit app that
means: one shared database, every visitor sees everyone else's tasks,
habits and money data, and the file can be lost or reset when the app
redeploys. That cannot deliver cross-device sync as-is. Any design
below is judged against two questions: (1) does a buyer see only
their own data, on any device, after logging in? (2) does the data
survive a redeploy?

## Option (a) — Current local SQLite (the base app, unchanged)

- **What it is:** one `adhd_life_os.db` file next to `app.py`, all
  tables global, no accounts.
- **What syncs:** nothing. Data lives in whichever copy of the file
  the running app opens. On a laptop it is that laptop only; on
  Streamlit Cloud it is one shared file for all visitors.
- **Failure modes:** all visitors share each other's data (privacy
  failure); file lost/reset on redeploy; no way to tell whose row is
  whose; no backup per buyer.
- **Cost:** free.
- **What the user must do:** nothing — but this option cannot be sold
  as "log in on any device". It is the starting point, not the product.
- **Verdict:** not shippable for the Etsy delivery. Kept only as the
  demo/seed behaviour.

## Option (b) — Per-user hosted SQLite files (IMPLEMENTED in this build)

- **What it is:** `haveloo_auth.py` adds accounts (email + PBKDF2
  salted password hash, never plaintext) and an Etsy-order-number
  unlock (format check + stored record for seller verification —
  live Etsy API verification is NOT connected, see below). Each
  account gets its own SQLite file,
  `data/user_<sha256(email)[:16]>.db` — the raw email never appears
  in the filename. After login, `app.py` opens that account's file,
  so all 40+ existing queries work unchanged and can only ever touch
  that account's rows. `migrate_to_user_db()` copies a user's rows
  out of the old shared file; `export_user_data` /
  `import_user_data` give each buyer a JSON backup/restore.
- **What syncs:** after login, everything in the per-user DB follows
  the account to any device — tasks, habits, habit logs, energy logs,
  focus sessions, dopamine menu, impulse vault, brain dump, XP/coins,
  and prefs (theme, dyslexia font, large text live in the per-user
  `user_prefs`, so your theme follows you). As long as the file is
  still on the same hosted machine, a phone and a laptop show the
  same data.
- **Failure modes (honest):** the files still live on Streamlit
  Cloud's ephemeral filesystem. A redeploy, reboot or machine move
  can delete them — accounts, unlocks and user data included. This is
  a hosting limit, not a code bug, and no code in this module can fix
  it while storage is local files. Mitigation in v1: JSON backup per
  buyer + do not redeploy casually (see HOSTING.md §5).
- **Cost:** free (Streamlit Community Cloud free tier; no database bill).
- **What the user must do:** deploy per HOSTING.md, create the first
  account, test two accounts for isolation, paste the real app URL
  into the Quick Start Guide, and tell buyers to keep a JSON backup.
- **Verdict:** IMPLEMENTED. It is the best feasible option that
  ships with zero new paid services and zero new credentials, and it
  is honest about its one limit (redeploy loss). It is the right v1.

## Option (c) — Hosted Postgres / Supabase (RECOMMENDED better option)

- **What it is:** the same accounts + unlock + per-user rows, but the
  database is a hosted Postgres instance (Supabase or Neon free tier)
  instead of local files. `haveloo_auth.py` already reads
  `HAVELOO_DATABASE_URL` for this: set it and `open_connection()`
  connects to Postgres; unset and it falls back to SQLite with a
  warning; set-but-no-driver and it raises a clear error instead of
  silently using SQLite.
- **What syncs:** everything in (b), plus: data survives redeploys
  and reboots, the host gets real backups, the seller can inspect the
  `accounts` table in the Supabase dashboard to check order numbers,
  and many buyers can use the app at once without file-locking
  problems. This is real multi-device sync.
- **Failure modes:** needs the connection string kept secret in
  Streamlit Secrets; if the free tier is deleted or the password
  leaks and is rotated without updating Secrets, the app cannot open
  the database (fail-closed, with an error — not silent data loss).
  Free tiers have size limits (Supabase 500 MB — far more than this
  app needs: one buyer's data is kilobytes).
- **Cost:** free tier (Supabase 500 MB DB / Neon free tier). No paid
  plan needed at this scale.
- **What the user must do:** create the free project, set
  `HAVELOO_DATABASE_URL` in Streamlit Secrets, add
  `psycopg2-binary` to `requirements.txt`, create the tables once
  (auth tables: `POSTGRES_AUTH_DDL` in `haveloo_auth.py`; user tables:
  port `init_user_db_schema` — `AUTOINCREMENT` → `SERIAL`,
  `INTEGER PRIMARY KEY CHECK (id = 1)` → a plain `INTEGER PRIMARY KEY`
  with the app inserting id 1, `ON CONFLICT` already works in
  Postgres), then redeploy and re-test login → unlock → logout →
  login. Also move the per-user file logic to per-user rows
  (one shared Postgres DB, `owner_email` column or one schema per
  account) — that is the one code change still to write; the
  connection plumbing for it is already in this module.
- **Verdict:** RECOMMENDED as the next step before scaling, and the
  only option that removes the redeploy-loss risk. Not implemented
  end-to-end in this build because it needs a live hosted database
  the builder does not have here — the env-var plumbing, the
  Postgres DDL for the auth tables, and the exact migration steps
  are done so the step is a hosting task, not a redesign.

## Unlock honesty — applies to all three options

None of the options above includes live automatic Etsy verification.
True live verification needs Etsy API access (an Etsy developer app +
the seller's OAuth token + an order-lookup call), which this build
does not have. In all three options, unlock = order-number format
check (digits, 8–13 chars) + store email + order number + date for
seller verification, and the UI + guide say so in plain words. Do not
claim "verified with Etsy" anywhere until that API integration is
actually built and tested. The seller check is the enforcement:
an order number that does not match a real Etsy order can have its
access removed.

## Summary table

|  | (a) Local SQLite | (b) Per-user SQLite files — IMPLEMENTED | (c) Hosted Postgres — RECOMMENDED |
|---|---|---|---|
| Per-buyer isolation | No | Yes (separate file per account) | Yes (per-user rows) |
| Same data on phone + laptop | No | Yes, while files survive | Yes |
| Survives redeploy | No | **No — ephemeral filesystem** | Yes (+ backups) |
| Seller can check order numbers | No | Yes (accounts table) | Yes (dashboard) |
| Cost | Free | Free | Free tier |
| Status | Starting point | **Shipped in this build** | Next hosting step |
