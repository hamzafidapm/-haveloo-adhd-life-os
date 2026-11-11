"""
Haveloo ADHD Life OS — Account + Unlock + Per-User Data module
================================================================

 companion to app.py (which this file does NOT edit).

THE HONEST PROBLEM — read this first
------------------------------------
app.py stores everything in ONE local SQLite file (``adhd_life_os.db``).
That file has no accounts, no per-user separation, and on hosted
Streamlit (Streamlit Community Cloud) the file lives on an ephemeral
filesystem: it is per-deployment, can be lost or reset on redeploy, and
— worst of all — every visitor would share the same file and see each
other's tasks, habits and money data.

This module does NOT pretend that problem away. What it does:

1.  Adds real accounts (email + salted/hashed password, never plaintext).
2.  Adds an Etsy-order-number unlock step that is HONEST about its limit:
    true live verification of an Etsy order number needs Etsy API access,
    which this build does NOT have. Unlock therefore does a format check
    and stores the order number for seller verification (see
    ``unlock_account``). The UI must show that note — never claim live
    Etsy API verification.
3.  Gives every account its OWN SQLite file, named from a hash of the
    email (never the raw email in the filename). After login, the app
    opens that account's file, so the same account sees the same data
    on any device. That is the v1 sync story — and its limit is stated
    in AUTH_DESIGN.md / HOSTING.md: files on Streamlit Cloud are still
    ephemeral, so the recommended better option is a hosted Postgres /
    Supabase database (this module already reads HAVELOO_DATABASE_URL
    for that next step).

DESIGN CHOICE — per-user file, not an owner_email column
--------------------------------------------------------
Two options were considered:

(a) Add an ``owner_email`` column to every core table and add
    ``WHERE owner_email = ?`` to every query in app.py. app.py has
    40+ ``get_conn()`` call sites; that change is invasive and one
    missed query leaks one user's data to another user.

(b) One SQLite file per account (chosen). app.py's queries do not
    change at all — only ``get_conn()`` has to open the logged-in
    user's file instead of the shared file. ``migrate_to_user_db()``
    copies a user's existing rows out of the shared file into their
    own file. Isolation is structural, not query-by-query.

What syncs / what does NOT sync (v1, per-user hosted SQLite file):
  SYNCS (after login, on any device): everything in the per-user DB —
  tasks, habits, habit logs, energy logs, focus sessions, dopamine
  menu, impulse vault, brain dump, XP/coins (user_stats) and prefs
  (theme, dyslexia font, large text — they live in the per-user
  user_prefs table after migration, so your theme follows you).
  DOES NOT SYNC: anything left in the old shared local .db file,
  anything in browser localStorage, and anything done in a DEMO
  session (demo data is never attached to an account).

STREAMLIT IMPORT NOTE
---------------------
This module deliberately does NOT ``import streamlit`` at the top.
The UI function ``render_auth_gate(st, conn)`` takes the ``st`` module
as an argument, so the account/password/unlock logic can be tested
headlessly (``python3 -m py_compile`` + a plain-Python test script)
without Streamlit installed. app.py passes its own ``st`` in.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration / environment
# ---------------------------------------------------------------------------

DEFAULT_AUTH_DB_PATH = "adhd_life_os.db"   # shared file that holds accounts
DEFAULT_DATA_DIR = "data"                  # per-user files live under this dir

# Core tables from app.py whose rows belong to one user. user_stats is the
# single-row (id = 1) XP/coins row; user_prefs holds theme + text options.
CORE_USER_TABLES = [
    "user_stats",
    "tasks",
    "habits",
    "habit_logs",
    "energy_logs",
    "focus_sessions",
    "dopamine_menu",
    "impulse_vault",
    "brain_dump",
    "user_prefs",
]

# Session-state keys used by app.py after integration (see INTEGRATION_AUTH.md).
SESSION_EMAIL_KEY = "haveloo_user_email"
SESSION_UNLOCKED_KEY = "haveloo_unlocked"
SESSION_DEMO_KEY = "haveloo_demo"

HONEST_UNLOCK_NOTE = (
    "Unlock is recorded for seller verification — Haveloo checks your "
    "order number against Etsy orders. Live automatic Etsy verification "
    "is not connected in this version."
)

# Etsy order numbers are digits, typically 9-11 digits. Accept 8-13 after
# stripping spaces and dashes, so a mistyped or older format is not
# rejected outright — the seller check is what confirms it.
ORDER_NUMBER_MIN_LEN = 8
ORDER_NUMBER_MAX_LEN = 13

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PASSWORD_MIN_LEN = 8
_PBKDF2_ITERATIONS = 210_000


# ---------------------------------------------------------------------------
# Storage backend: SQLite (v1, implemented) vs Postgres (next step)
# ---------------------------------------------------------------------------

def database_config() -> dict:
    """Describe which storage backend this deployment should use.

    Reads ``HAVELOO_DATABASE_URL``. If it is unset, v1 falls back to the
    local SQLite file and returns a warning explaining that limit — the
    caller (app.py / HOSTING.md) must surface it, not hide it. If it is
    set to a ``postgres://`` / ``postgresql://`` URL, the config reports
    the Postgres backend; ``open_connection()`` then tries to connect
    with psycopg2/psycopg and raises a clear error if no driver is
    installed, instead of silently falling back to SQLite (a silent
    fallback would silently lose cross-device sync).
    """
    url = (os.environ.get("HAVELOO_DATABASE_URL") or "").strip()
    if not url:
        return {
            "backend": "sqlite",
            "sqlite_path": os.environ.get("HAVELOO_AUTH_DB_PATH", DEFAULT_AUTH_DB_PATH),
            "data_dir": os.environ.get("HAVELOO_DATA_DIR", DEFAULT_DATA_DIR),
            "warning": (
                "HAVELOO_DATABASE_URL is not set — using local SQLite. "
                "On Streamlit Community Cloud the .db file lives on an "
                "ephemeral filesystem and can be lost on redeploy, and "
                "per-user files do not survive a redeploy either. For real "
                "multi-device sync and backups, set HAVELOO_DATABASE_URL "
                "to a hosted Postgres / Supabase URL (see HOSTING.md)."
            ),
        }
    if url.startswith(("postgres://", "postgresql://")):
        return {
            "backend": "postgres",
            "database_url": url,
            "data_dir": os.environ.get("HAVELOO_DATA_DIR", DEFAULT_DATA_DIR),
            "warning": None,
        }
    return {
        "backend": "unsupported",
        "database_url": url,
        "data_dir": os.environ.get("HAVELOO_DATA_DIR", DEFAULT_DATA_DIR),
        "warning": (
            "HAVELOO_DATABASE_URL has an unsupported scheme (only "
            "postgres:// / postgresql:// is supported). Falling back to "
            "local SQLite is NOT done silently — fix the URL."
        ),
    }


def storage_warning() -> str | None:
    """One-line warning for the current backend, or None if Postgres."""
    return database_config().get("warning")


def open_connection(config: dict | None = None):
    """Open a connection for the configured backend.

    SQLite: returns a sqlite3 connection to the auth DB path.
    Postgres: returns a psycopg2/psycopg connection to HAVELOO_DATABASE_URL.
    Raises RuntimeError with a plain-English message if Postgres is
    configured but no driver is installed, or if the URL is unsupported.
    """
    cfg = config or database_config()
    if cfg["backend"] == "sqlite":
        conn = sqlite3.connect(cfg["sqlite_path"], check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    if cfg["backend"] == "postgres":
        try:
            import psycopg2  # type: ignore
            return psycopg2.connect(cfg["database_url"])
        except ImportError:
            try:
                import psycopg  # type: ignore
                return psycopg.connect(cfg["database_url"])
            except ImportError:
                raise RuntimeError(
                    "HAVELOO_DATABASE_URL is set to Postgres but neither "
                    "psycopg2 nor psycopg is installed. Add "
                    "psycopg2-binary to requirements.txt (see HOSTING.md)."
                )
    raise RuntimeError(cfg.get("warning") or "Unsupported HAVELOO_DATABASE_URL.")


def get_unlock_mode() -> str:
    """How unlock behaves. v1 only supports 'recorded' (see unlock_account).

    Override with env HAVELOO_UNLOCK_MODE or the app_settings key
    'unlock_mode'. Any unknown value falls back to 'recorded' — there is
    no mode in v1 that claims live Etsy verification.
    """
    mode = (os.environ.get("HAVELOO_UNLOCK_MODE") or "recorded").strip().lower()
    return mode if mode in ("recorded",) else "recorded"


def demo_enabled() -> bool:
    """Whether the free demo is offered. Disable with HAVELOO_DEMO_ENABLED=0."""
    return (os.environ.get("HAVELOO_DEMO_ENABLED") or "1").strip() != "0"


# ---------------------------------------------------------------------------
# Password hashing — PBKDF2-HMAC-SHA256, per-user random salt, never plaintext
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: bytes | None = None) -> str:
    """Hash a password. Returns ``salt_hex$hash_hex``.

    A fresh 16-byte random salt is generated unless one is passed in
    (used by verify_password). The stored value is a one-way hash — it
    cannot be reversed back into the password.
    """
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a plaintext password against a stored ``salt$hash`` value.

    Returns False (never raises) for a malformed stored value, so a
    corrupt row cannot crash login.
    """
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        expected = hash_password(password, salt=bytes.fromhex(salt_hex))
        return hmac.compare_digest(expected, stored)
    except (ValueError, TypeError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Auth tables (accounts + app_settings) — created in the shared/auth DB
# ---------------------------------------------------------------------------

def init_auth_tables(conn) -> None:
    """Create the accounts + app_settings tables if they do not exist.

    ``accounts``: one row per buyer account.
      - password_hash holds ``salt$hash`` only — NEVER a plaintext password.
      - unlocked = 1 once an Etsy order number has been recorded (see
        unlock_account for the honest limit on what that proves).
      - etsy_order_number / unlocked_at record what was supplied, so the
        seller can check it against Etsy orders.
    ``app_settings``: host-controlled key/value settings (e.g. demo
    on/off, unlock mode). Deliberately separate from user data.
    """
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            unlocked INTEGER NOT NULL DEFAULT 0,
            etsy_order_number TEXT,
            unlocked_at TEXT
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()


# Postgres DDL for the same two tables, for the hosted-DB step.
# (SQLite AUTOINCREMENT / INTEGER PRIMARY KEY syntax differs; use this
# when init_auth_tables is ever ported to a Postgres connection.)
POSTGRES_AUTH_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    unlocked INTEGER NOT NULL DEFAULT 0,
    etsy_order_number TEXT,
    unlocked_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_setting(conn, key: str, default: str | None = None) -> str | None:
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    except Exception:
        return default
    return row[0] if row else default


def set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(normalize_email(email)))


def normalize_order_number(raw: str) -> str:
    """Strip spaces and dashes from an Etsy order number."""
    return re.sub(r"[\s\-]", "", (raw or "").strip())


def validate_order_number(raw: str) -> tuple[bool, str, str]:
    """Validate an Etsy order-number format.

    Returns (ok, normalized, message). This is a FORMAT check only —
    it proves the value looks like an Etsy order number, not that the
    order exists. Existence is checked by the seller (see unlock_account).
    """
    norm = normalize_order_number(raw)
    if not norm:
        return False, "", "Please enter your Etsy order number."
    if not norm.isdigit():
        return False, "", "That does not look like an Etsy order number — it should be digits only."
    if not (ORDER_NUMBER_MIN_LEN <= len(norm) <= ORDER_NUMBER_MAX_LEN):
        return (
            False,
            "",
            f"Etsy order numbers are usually 9–11 digits (this one has {len(norm)}). "
            "Please check the number in your Etsy purchase email and try again.",
        )
    return True, norm, "Order number format looks good."


# ---------------------------------------------------------------------------
# Accounts: create / login / logout / unlock
# ---------------------------------------------------------------------------

def count_accounts(conn) -> int:
    row = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
    return int(row[0]) if row else 0


def accounts_exist(conn) -> bool:
    return count_accounts(conn) > 0


def get_account(conn, email: str):
    """Return the account row for an email, or None."""
    return conn.execute(
        "SELECT * FROM accounts WHERE email = ?", (normalize_email(email),)
    ).fetchone()


def create_account(conn, email: str, password: str) -> tuple[bool, str]:
    """Create an account. Returns (ok, message).

    Validates email format and password length (>= 8 chars), rejects a
    duplicate email, and stores ONLY the salted hash — the plaintext
    password is never written to the database.
    """
    email = normalize_email(email)
    if not is_valid_email(email):
        return False, "Please enter a valid email address (for example, you@example.com)."
    if len(password or "") < _PASSWORD_MIN_LEN:
        return False, "Your password needs to be at least 8 characters long."
    if get_account(conn, email) is not None:
        return False, "An account with this email already exists — please log in instead."
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO accounts (email, password_hash, created_at, unlocked) "
        "VALUES (?, ?, ?, 0)",
        (email, hash_password(password), now),
    )
    conn.commit()
    return True, "Account created. Now unlock it with your Etsy order number (once only)."


def login_account(conn, email: str, password: str, session_state=None) -> tuple[bool, str]:
    """Check email + password. On success, fills session_state and returns
    (True, message). On failure returns (False, message) and leaves any
    existing session untouched. ``session_state`` defaults to a plain
    dict when none is passed (handy for headless tests); app.py passes
    ``st.session_state``.
    """
    email = normalize_email(email)
    row = get_account(conn, email)
    if row is None:
        return False, "No account with that email yet — please create one first."
    stored = row["password_hash"]
    if not verify_password(password or "", stored):
        return False, "That password does not match — please try again."
    state = session_state if session_state is not None else {}
    state[SESSION_EMAIL_KEY] = email
    state[SESSION_UNLOCKED_KEY] = bool(row["unlocked"])
    state.pop(SESSION_DEMO_KEY, None)
    return True, "Welcome back — you are logged in."


def logout(session_state=None) -> None:
    """Clear the login session. ``session_state`` defaults to a plain dict
    when none is passed; app.py passes ``st.session_state``."""
    state = session_state if session_state is not None else {}
    for key in (SESSION_EMAIL_KEY, SESSION_UNLOCKED_KEY, SESSION_DEMO_KEY):
        state.pop(key, None)


def is_logged_in(session_state) -> bool:
    return bool(session_state.get(SESSION_EMAIL_KEY))


def current_user_email(session_state) -> str | None:
    return session_state.get(SESSION_EMAIL_KEY)


def is_unlocked(session_state) -> bool:
    return bool(session_state.get(SESSION_UNLOCKED_KEY))


def unlock_account(conn, email: str, etsy_order_number: str) -> tuple[bool, str]:
    """Unlock an account with an Etsy order number. Returns (ok, message).

    HONEST LIMIT — read before changing this function:
    True live verification of an Etsy order number needs Etsy API
    access (an Etsy developer app + the seller's OAuth token), which
    this build does NOT have. This function therefore does NOT verify
    the order against Etsy. It does three things only:

    (a) format-checks the order number (digits, 8–13 chars — see
        validate_order_number);
    (b) stores the email + order number + date on the account row;
    (c) marks unlocked = 1.

    The seller then checks the stored order number against real Etsy
    orders and can revoke access if it does not match. The UI text in
    render_auth_gate() and the Quick Start Guide say exactly this —
    do NOT change this function to claim live Etsy API verification
    unless that verification is actually built and tested.
    """
    email = normalize_email(email)
    ok, norm, msg = validate_order_number(etsy_order_number)
    if not ok:
        return False, msg
    row = get_account(conn, email)
    if row is None:
        return False, "No account with that email yet — please create one first."
    if row["unlocked"]:
        return True, "This account is already unlocked — just log in on any device."
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE accounts SET unlocked = 1, etsy_order_number = ?, unlocked_at = ? "
        "WHERE email = ?",
        (norm, now, email),
    )
    conn.commit()
    return (
        True,
        "Unlocked — thank you! " + HONEST_UNLOCK_NOTE,
    )


# ---------------------------------------------------------------------------
# Per-user data files — ONE approach (see module docstring for why)
# ---------------------------------------------------------------------------

def user_db_path(email: str, base_dir: str | None = None) -> str:
    """File path of one account's private SQLite database.

    Derived from a SHA-256 hash of the lower-cased email — the raw email
    NEVER appears in the filename (filenames can leak in logs and
    directory listings). Example: data/user_9f2c…a1.db
    """
    base = base_dir or os.environ.get("HAVELOO_DATA_DIR", DEFAULT_DATA_DIR)
    digest = hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:16]
    return os.path.join(base, f"user_{digest}.db")


def init_user_db_schema(conn) -> None:
    """Create the core user tables in a per-user DB, with the same columns
    app.py uses. No demo seed here — a fresh account starts completely
    empty (2026-11-12): app.py only seeds demo data into the shared
    free-demo file, never into a logged-in account's file. The only way
    demo rows could ever enter a buyer file is migrate_to_user_db(),
    which nothing in the app calls."""
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            xp INTEGER NOT NULL DEFAULT 0,
            coins INTEGER NOT NULL DEFAULT 0,
            last_active_date TEXT
        );
        INSERT OR IGNORE INTO user_stats (id, xp, coins, last_active_date)
        VALUES (1, 0, 0, NULL);

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            energy_req TEXT NOT NULL,
            est_minutes INTEGER NOT NULL DEFAULT 25,
            micro_steps TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'Todo',
            xp_reward INTEGER NOT NULL DEFAULT 50,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            routine TEXT NOT NULL,
            xp_value INTEGER NOT NULL DEFAULT 20
        );

        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            UNIQUE(habit_id, log_date),
            FOREIGN KEY(habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS energy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL,
            time_block TEXT NOT NULL,
            energy_level INTEGER NOT NULL,
            focus_level INTEGER NOT NULL,
            mood TEXT NOT NULL,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS focus_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_title TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            distractions_caught INTEGER NOT NULL DEFAULT 0,
            xp_earned INTEGER NOT NULL DEFAULT 30,
            session_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dopamine_menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            course TEXT NOT NULL,
            cost_coins INTEGER NOT NULL DEFAULT 0,
            energy_boost INTEGER NOT NULL DEFAULT 3
        );

        CREATE TABLE IF NOT EXISTS impulse_vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            urge_level INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            cooldown_hours INTEGER NOT NULL DEFAULT 48,
            status TEXT NOT NULL DEFAULT 'Cooling Off'
        );

        CREATE TABLE IF NOT EXISTS brain_dump (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thought TEXT NOT NULL,
            tag TEXT NOT NULL,
            created_at TEXT NOT NULL,
            triaged INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS user_prefs (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()


def get_user_conn(email: str, base_dir: str | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the logged-in account's private DB.

    app.py's integration is a one-line change: after the auth gate,
    ``get_conn()`` returns this connection instead of the shared file.
    All existing queries then read/write only that account's data.
    """
    path = user_db_path(email, base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_user_db_schema(conn)
    return conn


def migrate_to_user_db(source_conn, email: str, base_dir: str | None = None) -> dict:
    """Copy one user's rows from the old shared DB into their own file.

    ``source_conn`` is a connection to the shared ``adhd_life_os.db``
    (the file app.py used before accounts existed). Every row in each
    core table is copied verbatim (same ids, so habit_logs still point
    at the right habits). Tables missing from the source are skipped,
    not treated as an error. The source rows are NOT deleted — the
    coordinator deletes or archives the shared file only after checking
    the copy (see INTEGRATION_AUTH.md). Returns {table: rows_copied}.
    """
    path = user_db_path(email, base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dest = sqlite3.connect(path, check_same_thread=False)
    dest.row_factory = sqlite3.Row
    try:
        init_user_db_schema(dest)
        copied: dict[str, int] = {}
        for table in CORE_USER_TABLES:
            try:
                rows = source_conn.execute(f"SELECT * FROM {table}").fetchall()
            except Exception:
                copied[table] = 0
                continue
            if not rows:
                copied[table] = 0
                continue
            cols = [d[0] for d in source_conn.execute(
                f"SELECT * FROM {table} LIMIT 0"
            ).description]
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(f'"{c}"' for c in cols)
            dest.execute(f"DELETE FROM {table}")
            dest.executemany(
                f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})",
                [tuple(r[c] for c in cols) for r in rows],
            )
            copied[table] = len(rows)
        dest.commit()
        return copied
    finally:
        dest.close()


# ---------------------------------------------------------------------------
# JSON backup / restore (per account)
# ---------------------------------------------------------------------------

def export_user_data(conn, email: str, base_dir: str | None = None) -> dict:
    """Export one account's data as a plain dict (JSON-serialisable).

    ``conn`` is the auth/main connection and is used to check the
    account exists; the data itself is read from the account's own DB
    file. The export contains no password and no password hash.
    """
    if get_account(conn, email) is None:
        return {"email": normalize_email(email), "error": "No account with that email."}
    path = user_db_path(email, base_dir)
    data: dict = {
        "email": normalize_email(email),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "app": "Haveloo ADHD Life OS",
        "tables": {},
    }
    if not os.path.exists(path):
        data["note"] = "No per-user data file yet — nothing to export."
        return data
    user_conn = sqlite3.connect(path, check_same_thread=False)
    user_conn.row_factory = sqlite3.Row
    try:
        for table in CORE_USER_TABLES:
            try:
                rows = user_conn.execute(f"SELECT * FROM {table}").fetchall()
            except Exception:
                data["tables"][table] = []
                continue
            data["tables"][table] = [dict(r) for r in rows]
    finally:
        user_conn.close()
    return data


def import_user_data(conn, email: str, data: dict, base_dir: str | None = None) -> tuple[bool, str]:
    """Restore a JSON export (from export_user_data) into an account's DB.

    Only the allow-listed CORE_USER_TABLES are written, and only columns
    that exist in the target table — unknown tables/columns in the file
    are ignored, never executed. Existing rows in each imported table
    are replaced by the file's rows. Returns (ok, message).
    """
    if get_account(conn, email) is None:
        return False, "No account with that email yet — please create one first."
    if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
        return False, "That file does not look like a Haveloo export — nothing was imported."
    user_conn = get_user_conn(email, base_dir)
    try:
        for table, rows in data["tables"].items():
            if table not in CORE_USER_TABLES or not isinstance(rows, list):
                continue
            existing_cols = [
                r[1] for r in user_conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            if not existing_cols:
                continue
            user_conn.execute(f"DELETE FROM {table}")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cols = [c for c in row.keys() if c in existing_cols]
                if not cols:
                    continue
                placeholders = ", ".join("?" for _ in cols)
                col_list = ", ".join(f'"{c}"' for c in cols)
                user_conn.execute(
                    f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})",
                    [row[c] for c in cols],
                )
        user_conn.commit()
    finally:
        user_conn.close()
    return True, "Your backup was restored into this account."


# ---------------------------------------------------------------------------
# Streamlit UI — the auth gate. `st` is passed in by app.py (see note at top).
# ---------------------------------------------------------------------------

def render_auth_gate(st, conn) -> bool:
    """Render the login / signup / unlock screens. Returns True when the
    caller (app.py) may render the planner tabs.

    True means one of:
      * logged in AND unlocked, or
      * free DEMO mode (only while demo is enabled — see demo_enabled()).

    Logged in but NOT unlocked returns False after showing the unlock
    form — the planner stays hidden until the order number is recorded.
    Every button here performs a real database write and shows a toast;
    there are no dead buttons.

    Place this call in app.py BEFORE the tabs render (see
    INTEGRATION_AUTH.md for the exact insertion point).
    """
    # --- already logged in + unlocked: show account chip + log out ---
    if is_logged_in(st.session_state) and is_unlocked(st.session_state):
        with st.sidebar:
            st.success(f"Logged in as {current_user_email(st.session_state)}")
            if st.button("Log out", key="haveloo_logout", use_container_width=True):
                logout(st.session_state)
                st.toast("Logged out. See you soon!", icon="👋")
                st.rerun()
        return True

    # --- logged in but not unlocked yet: unlock screen only ---
    if is_logged_in(st.session_state):
        email = current_user_email(st.session_state)
        st.header("🔓 Unlock your planner")
        st.write(
            f"Hi **{email}** — one last step. Unlock with the Etsy order "
            "number from your purchase email. It takes about 2 minutes, "
            "once only. After that, just log in on any device."
        )
        with st.form("haveloo_unlock_form"):
            order_no = st.text_input(
                "Etsy order number",
                placeholder="e.g. 4614332561",
                help="Find it in your Etsy purchase confirmation email.",
            )
            if st.form_submit_button("Unlock my planner", type="primary", use_container_width=True):
                ok, msg = unlock_account(conn, email, order_no)
                if ok:
                    st.session_state[SESSION_UNLOCKED_KEY] = True
                    st.toast(msg, icon="🔓")
                    st.rerun()
                else:
                    st.error(msg)
        with st.expander("How unlocking works"):
            st.write(HONEST_UNLOCK_NOTE)
            st.write(
                "If your order number does not match a real Etsy order, "
                "Haveloo can remove access. No codes to copy, no keys to keep."
            )
        if st.button("Log out", key="haveloo_logout_unlock", use_container_width=True):
            logout(st.session_state)
            st.rerun()
        return False

    # --- not logged in: demo banner (if enabled) + login / create account ---
    st.header("🧠 Haveloo ADHD Life OS")
    st.caption("Your neuro-adaptive planner — tasks, focus, habits and calm, in one place.")

    if demo_enabled():
        st.info(
            "🆓 **FREE DEMO — your data is only in this demo.** "
            "Try everything with sample data. Nothing you do in the demo "
            "is saved to an account, and demo data does not move to your "
            "account later. Create an account below to keep your own data."
        )
        if st.button("Try the free demo", key="haveloo_try_demo", use_container_width=True):
            st.session_state[SESSION_DEMO_KEY] = True
            st.toast("Demo mode — sample data only, nothing is saved to an account.", icon="🆓")
            st.rerun()
        if st.session_state.get(SESSION_DEMO_KEY):
            st.warning("You are in the FREE DEMO — sample data only. Create an account to keep your own data.")
            return True

    # No accounts exist yet (fresh install): say so, and let the first
    # visitor create the first account — that is also how the host's own
    # first account is created before listing.
    if not accounts_exist(conn):
        st.caption("No accounts exist on this planner yet — create the first one below.")

    tab_login, tab_signup = st.tabs(["Log in", "Create account"])
    with tab_login:
        with st.form("haveloo_login_form"):
            email = st.text_input("Email", placeholder="you@example.com", key="haveloo_login_email")
            password = st.text_input("Password", type="password", key="haveloo_login_pw")
            if st.form_submit_button("Log in", type="primary", use_container_width=True):
                ok, msg = login_account(conn, email, password, st.session_state)
                if ok:
                    st.toast(msg, icon="👋")
                    st.rerun()
                else:
                    st.error(msg)
    with tab_signup:
        st.write("Create your account with your email and a password (at least 8 characters).")
        with st.form("haveloo_signup_form"):
            email = st.text_input("Email", placeholder="you@example.com", key="haveloo_signup_email")
            password = st.text_input("Password", type="password", key="haveloo_signup_pw")
            confirm = st.text_input("Password again", type="password", key="haveloo_signup_pw2")
            if st.form_submit_button("Create my account", type="primary", use_container_width=True):
                if password != confirm:
                    st.error("The two passwords do not match — please type them again.")
                else:
                    ok, msg = create_account(conn, email, password)
                    if ok:
                        st.session_state[SESSION_EMAIL_KEY] = normalize_email(email)
                        st.session_state[SESSION_UNLOCKED_KEY] = False
                        st.toast(msg, icon="🎉")
                        st.rerun()
                    else:
                        st.error(msg)

    with st.expander("How unlocking works"):
        st.write(
            "After creating your account, unlock it with your Etsy order "
            "number — about 2 minutes, once only, then just log in on any "
            "other device. No codes to copy, no keys to keep."
        )
        st.write(HONEST_UNLOCK_NOTE)
    return False


def render_demo_banner(st) -> None:
    """Small banner for the planner screens while in demo mode."""
    if st.session_state.get(SESSION_DEMO_KEY):
        st.warning(
            "🆓 FREE DEMO — your data is only in this demo. "
            "Create an account to keep your own data on any device."
        )
