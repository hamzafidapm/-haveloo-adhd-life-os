# Haveloo ADHD Life OS — Auth Integration Notes for the Coordinator

How to wire `haveloo_auth.py` into `app.py`. **Do NOT edit `app.py`
in this module's task** — these are exact insertion points for the
coordinator's edit pass. Line numbers refer to the verified base
`app.py` (7 tabs, ~1,700 lines) as read 2026-11-12.

## 0. Files involved

| File | Role |
|---|---|
| `app.py` | Planner UI + data (unchanged in this task) |
| `haveloo_auth.py` | Accounts, unlock, per-user DB, JSON backup/restore, auth gate UI |
| `HOSTING.md` | Deploy steps + env vars |
| `AUTH_DESIGN.md` | Why per-user files (v1) and Postgres (recommended next step) |
| `Quick_Start_Guide.pdf` | The ONLY Etsy deliverable file |

## 1. Imports — top of app.py (after the existing imports, ~line 10)

```python
import haveloo_auth as auth
```

`haveloo_auth` does not import Streamlit at the top level, so this
import is safe and cannot create a circular import.

## 2. Connection routing — replace `get_conn()` (~line 275)

Current code:

```python
DB_PATH = "adhd_life_os.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
```

Change to route to the logged-in account's file, falling back to the
shared file only in demo mode or before login:

```python
DB_PATH = "adhd_life_os.db"

def get_conn() -> sqlite3.Connection:
    email = st.session_state.get(auth.SESSION_EMAIL_KEY)
    if email:
        return auth.get_user_conn(email)
    if st.session_state.get(auth.SESSION_DEMO_KEY):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
```

Why this works with zero other query changes: every one of the 40+
call sites already goes through `get_conn()`, and a per-user file has
exactly the same tables/columns as the shared file
(`init_user_db_schema` mirrors `init_db`'s DDL). No query needs a
`WHERE owner_email = ?` — isolation is structural (separate file),
not query-by-query. Do NOT add an `owner_email` column as well; pick
one approach (this one) and keep it.

## 3. Auth tables + gate — in §4 "INITIALIZE APP" (after `init_db()`, ~line 780)

Current code calls `init_db()` at module level. Directly after it,
insert:

```python
_auth_conn = auth.open_connection()          # SQLite by default; Postgres if HAVELOO_DATABASE_URL is set
auth.init_auth_tables(_auth_conn)

if not auth.render_auth_gate(st, _auth_conn):
    st.stop()                                # not logged in, or logged in but not unlocked yet
auth.render_demo_banner(st)
```

Placement rules:

- **Before** the sidebar HUD, the theme loading, and `st.tabs(...)`.
  The gate must be the first thing a visitor sees; no planner data
  (tasks, XP, charts) may render before it returns True.
- `st.stop()` is the correct guard: it halts the rest of the script
  run for this visitor while leaving the gate UI visible.
- Keep `_auth_conn` open for the run (it is the accounts connection).
  Do NOT close it before the gate renders — `render_auth_gate`
  writes to it on signup/unlock.
- The `render_auth_gate` return contract: True = logged in + unlocked,
  or free demo mode. False = show gate only (login/signup form, or
  unlock form for a logged-in-but-locked account).

## 4. Session-state keys (do not rename — the guide and the module agree on them)

| Key | Meaning |
|---|---|
| `haveloo_user_email` | Logged-in account email (lower-cased). Absent = not logged in. |
| `haveloo_unlocked` | True once the account's Etsy order number is recorded. |
| `haveloo_demo` | True while the visitor is in the free demo (sample data only). |

`render_auth_gate` sets/clears all three. `logout()` clears all three.
No other code should write these keys.

## 5. Theme / prefs: global `user_prefs` → per-account prefs

Current state in base `app.py`: `get_pref` / `set_pref` read/write the
`user_prefs` table in whatever file `get_conn()` opens, and the header
comment says "The auth module later scopes these per account".

After step 2 above, that scoping happens automatically: `get_conn()`
opens the logged-in account's file, so `user_prefs` in that file IS
that account's prefs. Theme, dyslexia font and large text therefore
follow the account to any device. **No change to `get_pref` /
`set_pref` is needed.** What must NOT happen: do not keep a separate
global prefs file, and do not copy prefs between accounts.

Two consequences to keep in mind:

- A fresh account starts with no prefs row, so `get_pref("theme",
  DEFAULT_THEME)` falls back to Sage — correct behaviour.
- `migrate_to_user_db()` copies `user_prefs` too, so a buyer who used
  the shared file before accounts existed keeps their theme.

## 6. Demo mode behaviour

- Demo is offered only while `demo_enabled()` is true (env
  `HAVELOO_DEMO_ENABLED`, default on; set `0` to hide it).
- Demo uses the shared `adhd_life_os.db` with its existing seed data.
  Demo data is NEVER copied into an account — if a demo visitor later
  creates an account, they start with a fresh per-user file (or the
  coordinator may offer a one-time "keep demo data" copy; that is a
  product decision, not in this module).
- The demo banner (`render_demo_banner`) must render on planner
  screens so a demo visitor never mistakes sample data for their own.

## 7. First-run migration (one-time, host only)

If the shared file already has real user rows from before accounts
existed (it does on the current deployment — seed/demo data):

```python
import sqlite3, haveloo_auth as auth
src = sqlite3.connect("adhd_life_os.db")
src.row_factory = sqlite3.Row
print(auth.migrate_to_user_db(src, "buyer@example.com"))
# -> {'user_stats': 1, 'tasks': 13, 'habits': 5, ...}  (counts copied)
```

Run once per buyer email, verify the counts, and only then archive
(or delete) the shared file's user rows. Do NOT delete the shared
file itself — it still holds the `accounts` table. `reset_database()`
in app.py clears the shared file only; after integration it must
never be pointed at a per-user file.

## 8. Backup / restore UI (add to the sidebar, optional but recommended)

Add inside the sidebar (near the Database & Demo Controls expander):

```python
import json
data = auth.export_user_data(_auth_conn, st.session_state[auth.SESSION_EMAIL_KEY])
st.download_button("Download my backup (JSON)", json.dumps(data, indent=2),
                   file_name="haveloo-adhd-backup.json")
```

Restore: a file uploader + `auth.import_user_data(_auth_conn, email,
json.load(file))`. Both functions validate the email against
`accounts` and only touch allow-listed tables. Never expose the
password hash in an export — `export_user_data` never includes it.

## 9. Deploy checklist order (same as HOSTING.md §7)

1. `python3 -m py_compile haveloo_auth.py app.py` passes.
2. Headless auth tests pass (see test commands in the build report).
3. Deploy per HOSTING.md; note the real Streamlit URL.
4. Create host account → unlock with a real Etsy order number →
   log out → log back in (end to end, on the live URL).
5. Create a second test account; confirm its tasks do not appear in
   the first account and vice versa.
6. Paste the real app URL into the Quick Start Guide placeholder and
   re-export the PDF. Never list the guide with the placeholder in it.
7. Decide the Postgres step (AUTH_DESIGN.md option c) before the
   first real buyer, or accept the v1 redeploy risk in writing.
