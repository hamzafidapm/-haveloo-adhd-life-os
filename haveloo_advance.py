"""Haveloo ADHD Life OS — Advance module (Tier 2).

``haveloo_advance.py`` — Tier 2 advance features + Haveloo strengths that the
base ``app.py`` lacks. It is a NEW module: it does NOT edit ``app.py`` and does
NOT import it. Every render function takes ``st`` (the Streamlit module) as its
first argument plus an open ``sqlite3`` connection, so this file can be
imported and unit-tested without Streamlit installed.

Honesty rules baked into this module (do not weaken them):
  * The "smart" features are RULE-BASED. They are computed from the user's own
    logged data (energy / focus / habit / task / cycle logs). The UI labels
    them "Smart suggestion — based on your logged data" and NEVER claims a
    live LLM / AI model ran.
  * No live URL is invented. Calendar export is a real ``.ics`` file the user
    downloads and imports into Google / Apple Calendar. Live 2-way calendar
    sync and push notifications are NOT live in this build — the UI says so.
  * Focus soundscapes use NO copyrighted tracks and NO downloaded MP3s. The
    only audio generated here is a short sine-tone beep (built in code as a
    WAV data-URI) for the end of a timer. Soundscape choices are stored as
    built-in entries with no external audio URL.
  * SOS and cycle notes are supportive tools, not medical advice and not a
    crisis service. The UI says so every time.
  * All wording is Haveloo's own original wording. No competitor branding or
    competitor text is copied.

Connection ownership: the caller opens the connection (``get_conn()`` pattern
from ``app.py``) and closes it. Functions in this module COMMIT after each
write but never close the connection they were given.
"""

import base64
import io
import json
import math
import re
import sqlite3
import struct
import uuid
import wave
from datetime import date, datetime, time, timedelta

import pandas as pd

__all__ = [
    "init_advance_tables",
    "seed_advance",
    "build_ics",
    "breakdown_steps",
    "build_day_plan",
    "compute_insights",
    "export_backup",
    "restore_backup",
    "render_smart_insights",
    "render_ai_breakdown",
    "render_ai_day_planner",
    "render_calendar_export",
    "render_voice_add",
    "render_focus_pro",
    "render_sos",
    "render_cycle_sleep",
    "render_subscriptions_bills",
    "render_print_export",
]

# ---------------------------------------------------------------------------
# 1. ADVANCE TABLES
# ---------------------------------------------------------------------------

ADVANCE_DDL = """
CREATE TABLE IF NOT EXISTS wellness_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL UNIQUE,
    sleep_hours REAL NOT NULL DEFAULT 0,
    water_glasses INTEGER NOT NULL DEFAULT 0,
    medicine_taken INTEGER NOT NULL DEFAULT 0,
    exercise_minutes INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cycle_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_date TEXT NOT NULL,
    end_date TEXT,
    flow TEXT NOT NULL DEFAULT 'Medium',
    mood TEXT NOT NULL DEFAULT '',
    energy INTEGER NOT NULL DEFAULT 5,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sos_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    feeling TEXT NOT NULL DEFAULT '',
    what_helped TEXT NOT NULL DEFAULT '',
    minutes_used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
    next_renewal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS impulse_waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL,
    wait_hours INTEGER NOT NULL DEFAULT 48,
    status TEXT NOT NULL DEFAULT 'waiting'
);

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    due_day INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'unpaid'
);

CREATE TABLE IF NOT EXISTS voice_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    triaged INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS focus_sounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'rain',
    url TEXT NOT NULL DEFAULT '',
    is_builtin INTEGER NOT NULL DEFAULT 1
);

-- user_prefs is a base-app table; created here only if the advance module is
-- ever initialised before app.py runs, so reminder / guard / sound choices
-- always have somewhere honest to live.
CREATE TABLE IF NOT EXISTS user_prefs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

ADVANCE_TABLES = [
    "wellness_log",
    "cycle_log",
    "sos_log",
    "subscriptions",
    "impulse_waitlist",
    "bills",
    "voice_notes",
    "focus_sounds",
]

# Tables included in a JSON backup (advance + base tables the app owns).
BACKUP_TABLES = ADVANCE_TABLES + [
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

BUILTIN_SOUNDS = [
    ("Gentle Rain", "rain"),
    ("White Noise", "white_noise"),
    ("Brown Noise", "brown_noise"),
    ("Soft Lo-Fi", "lofi"),
    ("Silence", "silence"),
]

SOUND_DESCRIPTIONS = {
    "rain": "Steady rain sound — masks background noise. Good for reading and admin.",
    "white_noise": "Even, flat hiss — masks sudden sounds. Good when the house is noisy.",
    "brown_noise": "Deeper, softer hiss than white noise — many people find it calmer for long focus blocks.",
    "lofi": "Slow, warm instrumental loops — gentle rhythm without lyrics to follow.",
    "silence": "No sound at all. Just the timer and your own thoughts.",
}


def init_advance_tables(conn: sqlite3.Connection) -> None:
    """Create all Tier 2 tables if they do not exist yet."""
    conn.executescript(ADVANCE_DDL)
    conn.commit()


def seed_advance(conn: sqlite3.Connection) -> None:
    """Seed small realistic demo rows — ONLY into tables that are empty.

    Idempotent: calling it twice changes nothing, because every table is
    checked for existing rows first. Dates are relative to today so the demo
    always looks current, and amounts match the scale of the base demo data
    (a household budget in dollars, a 28-day cycle, a 48-hour waitlist).
    """
    init_advance_tables(conn)
    cur = conn.cursor()
    today = date.today()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _count(table: str) -> int:
        return cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    if _count("wellness_log") == 0:
        wellness_rows = [
            # (days_ago, sleep_hours, water_glasses, medicine_taken, exercise_minutes)
            (6, 7.5, 6, 1, 20),
            (5, 6.0, 5, 1, 0),
            (4, 8.0, 7, 1, 30),
            (3, 7.0, 6, 0, 15),
            (2, 6.5, 4, 1, 0),
            (1, 7.5, 8, 1, 25),
            (0, 7.0, 5, 1, 15),
        ]
        cur.executemany(
            "INSERT INTO wellness_log (log_date, sleep_hours, water_glasses,"
            " medicine_taken, exercise_minutes, notes) VALUES (?, ?, ?, ?, ?, '')",
            [
                ((today - timedelta(days=d)).isoformat(), s, w, m, e)
                for d, s, w, m, e in wellness_rows
            ],
        )

    if _count("cycle_log") == 0:
        cycle_rows = [
            ((today - timedelta(days=62)).isoformat(), (today - timedelta(days=57)).isoformat(), "Medium", "Steady", 6),
            ((today - timedelta(days=34)).isoformat(), (today - timedelta(days=29)).isoformat(), "Heavy", "Low Battery", 4),
            ((today - timedelta(days=6)).isoformat(), (today - timedelta(days=1)).isoformat(), "Medium", "Scattered", 5),
        ]
        cur.executemany(
            "INSERT INTO cycle_log (start_date, end_date, flow, mood, energy, notes)"
            " VALUES (?, ?, ?, ?, ?, '')",
            cycle_rows,
        )

    if _count("sos_log") == 0:
        sos_rows = [
            ((datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"), "Overwhelmed by too many open tabs", "Slow breathing + closed extra tabs", 2),
            ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), "Stuck starting a big task", "Broke it into one tiny first step", 2),
        ]
        cur.executemany(
            "INSERT INTO sos_log (created_at, feeling, what_helped, minutes_used)"
            " VALUES (?, ?, ?, ?)",
            sos_rows,
        )

    if _count("subscriptions") == 0:
        sub_rows = [
            ("Music Streaming", 10.99, "monthly", (today + timedelta(days=5)).isoformat(), "active"),
            ("Cloud Storage 200 GB", 2.99, "monthly", (today + timedelta(days=12)).isoformat(), "active"),
            ("Video Streaming", 15.49, "monthly", (today + timedelta(days=3)).isoformat(), "active"),
            ("Meal Planning App", 29.99, "yearly", (today + timedelta(days=40)).isoformat(), "active"),
        ]
        cur.executemany(
            "INSERT INTO subscriptions (name, price, billing_cycle, next_renewal, status)"
            " VALUES (?, ?, ?, ?, ?)",
            sub_rows,
        )

    if _count("impulse_waitlist") == 0:
        wait_rows = [
            ("Ceramic Pour-Over Coffee Set", 42.00,
             (datetime.now() - timedelta(hours=50)).strftime("%Y-%m-%d %H:%M:%S"), 48, "waiting"),
            ("LED Desk Lamp", 35.00,
             (datetime.now() - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S"), 48, "waiting"),
        ]
        cur.executemany(
            "INSERT INTO impulse_waitlist (item_name, price, added_at, wait_hours, status)"
            " VALUES (?, ?, ?, ?, ?)",
            wait_rows,
        )

    if _count("bills") == 0:
        bill_rows = [
            ("Rent", 1200.00, 1, "unpaid"),
            ("Internet", 65.00, 10, "unpaid"),
            ("Electric", 85.00, 15, "paid"),
            ("Phone", 45.00, 20, "unpaid"),
        ]
        cur.executemany(
            "INSERT INTO bills (name, amount, due_day, status) VALUES (?, ?, ?, ?)",
            bill_rows,
        )

    if _count("focus_sounds") == 0:
        cur.executemany(
            "INSERT INTO focus_sounds (name, kind, url, is_builtin) VALUES (?, ?, '', 1)",
            BUILTIN_SOUNDS,
        )

    conn.commit()


def seed_advance_defaults(conn: sqlite3.Connection) -> None:
    """Seed ONLY the static catalogue for a fresh buyer account.

    The only rows written are the built-in focus sounds (Gentle Rain,
    White Noise, Brown Noise, Soft Lo-Fi, Silence) — a fixed option list,
    not user data. No demo rows: no wellness logs, cycle logs, SOS logs,
    subscriptions, impulse-waitlist items or bills. Idempotent: nothing
    is written when focus_sounds already has rows.
    """
    init_advance_tables(conn)
    cur = conn.cursor()
    if cur.execute("SELECT COUNT(*) FROM focus_sounds").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO focus_sounds (name, kind, url, is_builtin) VALUES (?, ?, '', 1)",
            BUILTIN_SOUNDS,
        )
    conn.commit()


# ---------------------------------------------------------------------------
# 2. SMALL SHARED HELPERS (no Streamlit dependency — headless-testable)
# ---------------------------------------------------------------------------

def _award_xp(conn: sqlite3.Connection, xp_delta: int, coin_delta: int) -> None:
    """Add XP / coins to user_stats id=1 using the caller's connection.

    Mirrors ``award_xp_and_coins`` from app.py, but reuses the passed
    connection instead of opening a second one (avoids locking the DB the
    caller already holds). The caller commits.
    """
    conn.execute(
        "UPDATE user_stats SET xp = MAX(0, xp + ?), coins = MAX(0, coins + ?),"
        " last_active_date = ? WHERE id = 1",
        (xp_delta, coin_delta, date.today().isoformat()),
    )


def _read(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    """Read a query into a DataFrame; return an empty frame if the table is
    missing (e.g. advance module initialised before the base tables)."""
    try:
        return pd.read_sql_query(sql, conn, params=params)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()


def _set_pref(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO user_prefs (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _get_pref(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    try:
        row = conn.execute("SELECT value FROM user_prefs WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return default
    return row[0] if row else default


def beep_data_uri(freq_hz: int = 880, seconds: float = 0.8) -> str:
    """Generate a short gentle sine-tone beep as a WAV data-URI, in code.

    No audio file is bundled or downloaded. Used only as the end-of-timer
    sound in Focus Pro. 880 Hz (A5), soft attack/decay so it is not startling.
    """
    sample_rate = 22050
    n_samples = int(sample_rate * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            envelope = min(1.0, i / (sample_rate * 0.05), (n_samples - i) / (sample_rate * 0.15))
            sample = int(12000 * envelope * math.sin(2 * math.pi * freq_hz * t))
            frames += struct.pack("<h", sample)
        wav.writeframes(bytes(frames))
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:audio/wav;base64,{encoded}"


# --- .ics (RFC 5545) generation: pure, no Streamlit -------------------------

def _ics_escape(text: str) -> str:
    """Escape text for an .ics line (commas, semicolons, newlines)."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ics_fold(line: str) -> str:
    """Fold a long .ics line at 75 octets (continuation lines start with a space)."""
    if len(line) <= 75:
        return line
    parts = [line[:75]]
    rest = line[75:]
    while rest:
        parts.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(parts)


def build_ics(events: list) -> str:
    """Build a real RFC 5545 ``.ics`` calendar file as text.

    Each event is a dict with ``title`` (str), ``start`` / ``end``
    (``datetime``), and optional ``description`` / ``location`` (str).
    Times are written as floating local time (no timezone), which Google and
    Apple Calendar both import directly.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Haveloo//ADHD Life OS//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for ev in events:
        start = ev["start"].strftime("%Y%m%dT%H%M%S")
        end = ev["end"].strftime("%Y%m%dT%H%M%S")
        uid = f"{uuid.uuid4()}@haveloo"
        lines.append("BEGIN:VEVENT")
        lines.append(_ics_fold(f"UID:{uid}"))
        lines.append(f"DTSTAMP:{stamp}")
        lines.append(f"DTSTART:{start}")
        lines.append(f"DTEND:{end}")
        lines.append(_ics_fold(f"SUMMARY:{_ics_escape(ev['title'])}"))
        if ev.get("description"):
            lines.append(_ics_fold(f"DESCRIPTION:{_ics_escape(ev['description'])}"))
        if ev.get("location"):
            lines.append(_ics_fold(f"LOCATION:{_ics_escape(ev['location'])}"))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# --- Rule-based task breakdown: pure, no Streamlit ---------------------------

BREAKDOWN_TEMPLATES = {
    "cleaning": [
        "Set a 5-minute timer and put on music you like",
        "Grab a bag and collect only obvious rubbish",
        "Clear one small surface — just one, not the whole room",
        "Put things that belong elsewhere into one pile by the door",
        "Wipe the cleared surface and stop — you can continue tomorrow",
    ],
    "email": [
        "Open the inbox and sort by sender, not by date",
        "Delete or archive 5 messages you never need to open",
        "Reply to the single most urgent message (2 minutes max)",
        "Draft the next reply as bullet points, not perfect sentences",
        "Close the inbox and note any follow-ups as one task",
    ],
    "study": [
        "Open only the one page or file you need",
        "Write down the single thing you want to understand in one sentence",
        "Read or watch for 10 minutes, then write 3 bullet notes",
        "Do one tiny practice question or example",
        "Close the book and say out loud what you just learned",
    ],
    "admin": [
        "Gather the login, link or paper you need in one place",
        "Write down the exact 1–3 things this task needs",
        "Do the fastest one first for momentum",
        "Set a reminder for anything that needs waiting",
        "File or note what you finished so you do not re-check it",
    ],
    "health": [
        "Put on shoes or clothes you can move in",
        "Drink a full glass of water first",
        "Do the smallest version — 5 minutes counts",
        "Note how you feel afterwards in one line",
        "Put what you need for tomorrow where you will see it",
    ],
    "finance": [
        "Open the one account or bill this is about",
        "Write down the exact amount and the due date",
        "Pay or schedule the smallest item first",
        "Move any leftover question into one note",
        "Close the tab — checking again will not change the number",
    ],
    "creative": [
        "Open a blank page and set a 10-minute timer",
        "Make the ugliest first version on purpose",
        "Pick the one part you like and keep only that",
        "Add one small detail, then stop",
        "Save it with today's date so you can find it again",
    ],
    "cooking": [
        "Pick the recipe and read it once, all the way through",
        "Put every ingredient on the counter before you start",
        "Do the longest-cooking step first",
        "Cook in 10-minute bursts with a timer",
        "Clean one thing while something cooks",
    ],
    "laundry": [
        "Put the clothes straight into the machine — skip sorting unless delicate",
        "Add detergent and press Start",
        "Set a phone alarm labelled 'Move Laundry'",
        "Move it to the dryer as soon as the alarm rings",
        "Fold straight from the dryer or dump it on the bed to fold before sleep",
    ],
    "call": [
        "Write the 3 points you need to say on a sticky note",
        "Dial the number before you can talk yourself out of it",
        "Say the first point, then listen — you do not need a script",
        "Note the answer or next step in one line",
        "Cross it off immediately so your brain lets it go",
    ],
    "shopping": [
        "Write the list before opening any shop or app",
        "Check what you already have — cross off duplicates",
        "Buy only the first 3 items, then stop and re-check",
        "Put anything extra on the 48-hour waitlist instead",
        "Put the receipt in one place when you get home",
    ],
    "writing": [
        "Write the messiest first paragraph — nobody will see it",
        "Use bullet points for the next 3 ideas",
        "Turn the best bullet into one full sentence",
        "Read it out loud once and fix only what sounds wrong",
        "Save it and walk away for 10 minutes before re-reading",
    ],
}

_BREAKDOWN_KEYWORDS = {
    "cleaning": ["clean", "tidy", "desk", "room", "kitchen", "vacuum", "dishes", "declutter"],
    "email": ["email", "inbox", "reply", "message"],
    "study": ["study", "learn", "read", "course", "exam", "revise", "homework"],
    "admin": ["admin", "form", "paperwork", "tax", "bill", "appointment", "book"],
    "health": ["exercise", "workout", "walk", "gym", "run", "doctor", "meds", "stretch"],
    "finance": ["budget", "pay", "money", "bank", "invoice", "expense", "save"],
    "creative": ["draw", "paint", "design", "write a story", "craft", "sew", "crochet", "music"],
    "cooking": ["cook", "meal", "recipe", "dinner", "lunch", "bake"],
    "laundry": ["laundry", "wash", "fold", "clothes"],
    "call": ["call", "phone", "text back", "ring"],
    "shopping": ["shop", "buy", "order", "grocery", "groceries"],
    "writing": ["write", "draft", "report", "essay", "blog", "proposal"],
}


def breakdown_steps(title: str) -> list:
    """Split a task title into 2-minute micro-steps (rule-based only).

    Matches the title against a keyword template library; falls back to a
    generic splitter that turns the title into five small, startable steps.
    No model or external service is involved.
    """
    text = (title or "").strip().lower()
    for key, words in _BREAKDOWN_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", text) for w in words):
            return list(BREAKDOWN_TEMPLATES[key])
    clean = (title or "this task").strip()
    return [
        f"Get ready for '{clean}': gather what you need in one place",
        "Do the easiest 2-minute piece first — just start, it does not need to be perfect",
        "Set a 5-minute timer and work only until it rings",
        "Finish one small visible piece, then pause and check what is left",
        "Put things away and write down the next tiny step for tomorrow",
    ]


# --- Rule-based day planner: pure, no Streamlit -------------------------------

def build_day_plan(task_rows: list, start: time, free_minutes: int,
                   energy_level: int | None = None) -> list:
    """Order tasks into timed blocks with 5-minute breaks (rule-based only).

    ``task_rows``: dicts with ``title``, ``est_minutes``, ``priority``,
    ``energy_req``. Ordering: Big 3 first; then tasks whose energy demand
    matches the user's current energy (low energy → low-demand tasks first);
    then shortest first. Blocks stop when ``free_minutes`` runs out. Breaks
    are 5 minutes between blocks, never after the last one.
    Returns a list of dicts: ``title``, ``start`` / ``end`` (datetime),
    ``minutes``, ``break_after`` (minutes, 0 on the last block).
    """
    def _energy_rank(row: dict) -> int:
        req = (row.get("energy_req") or "Medium").lower()
        if energy_level is None:
            return {"low": 0, "medium": 1, "high": 2}.get(req, 1)
        if energy_level <= 4:
            return {"low": 0, "medium": 1, "high": 2}.get(req, 1)
        if energy_level >= 8:
            return {"high": 0, "medium": 1, "low": 2}.get(req, 1)
        return {"medium": 0, "low": 1, "high": 2}.get(req, 1)

    def _priority_rank(row: dict) -> int:
        return 0 if (row.get("priority") or "") == "NOW (Big 3)" else 1

    ordered = sorted(
        task_rows,
        key=lambda r: (_priority_rank(r), _energy_rank(r), int(r.get("est_minutes") or 25)),
    )
    plan = []
    cursor = datetime.combine(date.today(), start)
    used = 0
    for row in ordered:
        mins = max(5, int(row.get("est_minutes") or 25))
        break_after = 5 if plan else 0  # break BEFORE this block if not first
        if used + break_after + mins > free_minutes and plan:
            break
        if used + mins > free_minutes and plan:
            break
        cursor += timedelta(minutes=break_after)
        used += break_after
        block_start = cursor
        cursor += timedelta(minutes=mins)
        used += mins
        plan.append({
            "title": row.get("title", "Untitled task"),
            "start": block_start,
            "end": cursor,
            "minutes": mins,
            "break_after": 0,  # filled in below for all but the last block
        })
    for block in plan[:-1]:
        block["break_after"] = 5
    return plan


# --- Cycle x focus observation (shared by insights + cycle tab) ---------------

def cycle_focus_note(conn: sqlite3.Connection) -> str | None:
    """Compare average focus on cycle days vs other days (observation only).

    Returns a one-line note, or None when there is not enough data. This is a
    simple average comparison, not medical advice and not a diagnosis.
    """
    cycles = _read(conn, "SELECT start_date, end_date FROM cycle_log WHERE end_date IS NOT NULL")
    energy = _read(conn, "SELECT log_date, focus_level FROM energy_logs")
    if cycles.empty or energy.empty or "focus_level" not in energy.columns:
        return None
    cycle_days = set()
    for _, row in cycles.iterrows():
        try:
            start = date.fromisoformat(str(row["start_date"])[:10])
            end = date.fromisoformat(str(row["end_date"])[:10])
        except ValueError:
            continue
        day = start
        while day <= end:
            cycle_days.add(day.isoformat())
            day += timedelta(days=1)
    if not cycle_days:
        return None
    energy["on_cycle"] = energy["log_date"].astype(str).str[:10].isin(cycle_days)
    on_cycle = energy[energy["on_cycle"]]["focus_level"]
    off_cycle = energy[~energy["on_cycle"]]["focus_level"]
    if on_cycle.empty or off_cycle.empty:
        return None
    on_avg = round(float(on_cycle.mean()), 1)
    off_avg = round(float(off_cycle.mean()), 1)
    diff = round(on_avg - off_avg, 1)
    direction = "lower" if diff < 0 else ("higher" if diff > 0 else "about the same")
    return (
        f"On cycle days your average logged focus was {on_avg}/10 (n={len(on_cycle)}) "
        f"vs {off_avg}/10 on other days (n={len(off_cycle)}) — {direction} by {abs(diff)} point(s). "
        "This is an observation from your own logs, not medical advice."
    )


def estimate_next_cycle_start(conn: sqlite3.Connection) -> date | None:
    """Next cycle start estimate: last start + 28 days (estimate only)."""
    cycles = _read(conn, "SELECT start_date FROM cycle_log ORDER BY start_date DESC LIMIT 1")
    if cycles.empty:
        return None
    try:
        last = date.fromisoformat(str(cycles.iloc[0]["start_date"])[:10])
    except ValueError:
        return None
    return last + timedelta(days=28)


# --- Smart insights (rule-based, computed from real logged data) -------------

def compute_insights(conn: sqlite3.Connection) -> list:
    """Compute rule-based insights from the user's own logged data.

    Returns a list of dicts: ``title``, ``body``, ``evidence``. Every number
    shown comes from a real query over energy_logs / focus_sessions /
    habit_logs / tasks / cycle_log. Empty data produces honest
    "not enough data yet" cards instead of invented numbers.
    """
    insights = []

    energy = _read(conn, "SELECT * FROM energy_logs")
    focus = _read(conn, "SELECT * FROM focus_sessions")
    tasks = _read(conn, "SELECT * FROM tasks")
    habits = _read(conn, "SELECT * FROM habits")
    habit_logs = _read(conn, "SELECT * FROM habit_logs")

    # (a) Best focus time-block.
    if not energy.empty and "time_block" in energy.columns and "focus_level" in energy.columns:
        grouped = energy.groupby("time_block")["focus_level"].agg(["mean", "count"])
        best_block = grouped["mean"].idxmax()
        best_avg = round(float(grouped.loc[best_block, "mean"]), 1)
        detail = ", ".join(
            f"{block}: {round(float(r['mean']), 1)} (n={int(r['count'])})"
            for block, r in grouped.iterrows()
        )
        insights.append({
            "title": "Your best focus time-block",
            "body": f"Your highest average focus is in the {best_block} "
                    f"({best_avg}/10). Try putting your hardest task there tomorrow.",
            "evidence": f"Average focus by time-block — {detail}.",
        })
    else:
        insights.append({
            "title": "Your best focus time-block",
            "body": "Not enough energy check-ins yet. Log your energy in the sidebar "
                    "for a few days and this will fill in.",
            "evidence": "Needs energy_logs rows with a time_block and focus_level.",
        })

    # (b) Energy vs focus correlation.
    if not energy.empty and "energy_level" in energy.columns and "focus_level" in energy.columns and len(energy) >= 5:
        corr = float(energy["energy_level"].corr(energy["focus_level"]))
        if corr >= 0.6:
            note = "They move together strongly — when your energy is up, your focus usually follows."
        elif corr >= 0.3:
            note = "They move together a little — energy helps focus, but it is not the whole story."
        elif corr <= -0.3:
            note = "They move in opposite directions in your logs — high-energy times are not always your focused times."
        else:
            note = "They barely move together in your logs — focus depends on more than energy alone."
        insights.append({
            "title": "Energy vs focus",
            "body": f"Correlation between your logged energy and focus is {corr:.2f}. {note}",
            "evidence": f"Pearson r = {corr:.2f} across {len(energy)} energy check-ins.",
        })
    else:
        insights.append({
            "title": "Energy vs focus",
            "body": "Log at least 5 energy check-ins and this comparison will appear.",
            "evidence": f"Only {len(energy)} energy check-in(s) logged so far.",
        })

    # (c) Most-completed task category.
    if not tasks.empty and "status" in tasks.columns and "category" in tasks.columns:
        done = tasks[tasks["status"] == "Done"]
        if not done.empty:
            top_cat = done["category"].value_counts()
            best_cat = top_cat.index[0]
            insights.append({
                "title": "Where you finish most",
                "body": f"You complete the most tasks in {best_cat} "
                        f"({int(top_cat.iloc[0])} finished). That is a strength — use it "
                        "as your warm-up category on hard days.",
                "evidence": "Completed tasks by category: " + ", ".join(
                    f"{cat}: {int(n)}" for cat, n in top_cat.items()
                ) + ".",
            })
        else:
            insights.append({
                "title": "Where you finish most",
                "body": "No completed tasks yet — finish one task and this will show your strongest area.",
                "evidence": f"{len(tasks)} task(s) logged, 0 completed.",
            })
    else:
        insights.append({
            "title": "Where you finish most",
            "body": "No tasks logged yet.",
            "evidence": "The tasks table is empty.",
        })

    # (d) Habit with the lowest consistency + one concrete suggestion.
    if not habits.empty and not habit_logs.empty:
        today = date.today()
        days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
        log_set = set(zip(habit_logs["habit_id"], habit_logs["log_date"].astype(str)))
        worst_name, worst_pct = None, 101.0
        for _, habit in habits.iterrows():
            done_count = sum(1 for d in days if (int(habit["id"]), d) in log_set)
            pct = done_count / len(days) * 100
            if pct < worst_pct:
                worst_name, worst_pct = habit["name"], pct
        suggestions = {
            "Meds & Care": "Put the bottle next to something you already do every morning, like the kettle.",
            "Morning Launch": "Shrink it to 2 minutes — open the planner is enough to count.",
            "Midday Reset": "Tie it to lunch: same time, same place, every day.",
            "Evening Wind-Down": "Do it right after dinner, before you sit down to relax.",
        }
        routine = None
        try:
            routine = habits[habits["name"] == worst_name].iloc[0]["routine"]
        except Exception:
            routine = None
        tip = suggestions.get(routine, "Make it smaller: a 2-minute version still counts.")
        insights.append({
            "title": "Habit that needs the kindest help",
            "body": f"'{worst_name}' is your lowest-consistency habit at {worst_pct:.0f}% "
                    f"over the last 14 days. No shame — try this: {tip}",
            "evidence": f"14-day completion for '{worst_name}': {worst_pct:.0f}%. "
                        "Other habits scored higher over the same 14 days.",
        })
    else:
        insights.append({
            "title": "Habit that needs the kindest help",
            "body": "Add a habit and check it in for a few days — this will then point to the one that needs support.",
            "evidence": "Needs habits + habit_logs rows.",
        })

    # (e) Cycle x focus note, only when cycle data exists.
    note = cycle_focus_note(conn)
    if note:
        insights.append({
            "title": "Cycle x focus — an observation",
            "body": note,
            "evidence": "Computed from cycle_log dates joined to energy_logs focus_level.",
        })

    # Bonus: focus-session volume, when sessions exist.
    if not focus.empty and "duration_minutes" in focus.columns:
        total_mins = int(focus["duration_minutes"].sum())
        insights.append({
            "title": "Your focus minutes so far",
            "body": f"You have logged {total_mins} focus minutes across "
                    f"{len(focus)} session(s). Even short sprints count.",
            "evidence": f"Sum of focus_sessions.duration_minutes = {total_mins}.",
        })

    return insights


# --- JSON backup / restore (stdlib + Streamlit only at the UI layer) ---------

def export_backup(conn: sqlite3.Connection) -> dict:
    """Export every backed-up table as ``{table: [row-dicts]}`` (JSON-safe)."""
    payload = {"app": "Haveloo ADHD Life OS", "exported_at": datetime.now().isoformat(), "tables": {}}
    for table in BACKUP_TABLES:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            cols = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
            payload["tables"][table] = [dict(zip(cols, row)) for row in rows]
        except sqlite3.OperationalError:
            payload["tables"][table] = []
    return payload


def restore_backup(conn: sqlite3.Connection, payload: dict) -> dict:
    """Restore a backup produced by :func:`export_backup`.

    Each table in the payload is emptied and re-filled inside one transaction.
    Returns ``{table: row_count_restored}``. Raises ValueError on bad input.
    """
    if not isinstance(payload, dict) or "tables" not in payload:
        raise ValueError("That file is not a Haveloo ADHD Life OS backup.")
    counts = {}
    tables = payload["tables"]
    if not isinstance(tables, dict):
        raise ValueError("That file is not a Haveloo ADHD Life OS backup.")
    cur = conn.cursor()
    for table, rows in tables.items():
        if table not in BACKUP_TABLES or not isinstance(rows, list):
            continue
        cur.execute(f"DELETE FROM {table}")
        if not rows:
            counts[table] = 0
            continue
        cols = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in cols)
        cur.executemany(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            [tuple(r.get(c) for c in cols) for r in rows],
        )
        counts[table] = len(rows)
    conn.commit()
    return counts


# ===========================================================================
# 3. RENDER FUNCTIONS — each takes `st` first plus `conn`.
#    Every action button writes to the DB, shows a toast, and reruns.
#    Pure navigation buttons (e.g. breathing "Next step") only advance the
#    on-screen step and are labelled as such in INTEGRATION_ADVANCE.md.
# ===========================================================================

def render_smart_insights(st, conn) -> None:
    """Rule-based insights computed from the user's own logged data."""
    st.subheader("Smart Insights")
    st.caption("Smart suggestion — based on your logged data. "
               "These are simple rules run over your own logs, not a live AI model.")
    for insight in compute_insights(conn):
        with st.container(border=True):
            st.markdown(f"**{insight['title']}**")
            st.write(insight["body"])
            st.caption(insight["evidence"])


def render_ai_breakdown(st, conn) -> None:
    """Smart Task Breakdown (rule-based): split a task into 2-minute steps."""
    st.subheader("Smart Task Breakdown")
    st.caption("Smart breakdown (rule-based) — steps come from a keyword template "
               "library, not from a live AI model.")
    todos = _read(conn, "SELECT id, title, category FROM tasks WHERE status = 'Todo' ORDER BY id DESC")
    options = ["— Type a task below instead —"] + (
        [f"{row['title']}  ({row['category']})" for _, row in todos.iterrows()]
        if not todos.empty else []
    )
    picked = st.selectbox("Pick one of your open tasks", options, key="adv_break_pick")
    typed = st.text_input("Or type a task", placeholder="e.g. Clean off my desk and reply to emails",
                          key="adv_break_typed")
    if picked.startswith("—"):
        title = typed.strip()
        task_id = None
    else:
        title = picked.rsplit("  (", 1)[0].strip()
        task_id = None
        try:
            match = todos[todos["title"] == title]
            task_id = int(match.iloc[0]["id"]) if not match.empty else None
        except Exception:
            task_id = None

    if st.button("Break it down into tiny steps", key="adv_break_go", use_container_width=True):
        if not title:
            st.warning("Pick a task or type one first.")
        else:
            st.session_state["adv_break_steps"] = breakdown_steps(title)
            st.session_state["adv_break_title"] = title
            st.session_state["adv_break_task_id"] = task_id
            st.toast("Steps ready — tick them off, then save them to the task.", icon="🧩")

    steps = st.session_state.get("adv_break_steps", [])
    if steps:
        st.markdown(f"**Micro-steps for:** {st.session_state.get('adv_break_title', '')}")
        checked = []
        for i, step in enumerate(steps):
            done = st.checkbox(step, key=f"adv_break_step_{i}")
            checked.append({"step": step, "done": bool(done)})
        st.session_state["adv_break_checked"] = checked
        done_count = sum(1 for c in checked if c["done"])
        st.progress(done_count / max(1, len(checked)),
                    text=f"{done_count}/{len(checked)} tiny steps ticked")
        if st.button("Save these steps to the task  (+10 XP)", key="adv_break_save",
                     type="primary", use_container_width=True):
            task_id = st.session_state.get("adv_break_task_id")
            if task_id:
                conn.execute("UPDATE tasks SET micro_steps = ? WHERE id = ?",
                             (json.dumps(checked), int(task_id)))
                _award_xp(conn, 10, 0)
                conn.commit()
                st.toast("Steps saved to your task! +10 XP", icon="🧩")
                st.rerun()
            else:
                conn.execute(
                    "INSERT INTO tasks (title, category, priority, energy_req, est_minutes,"
                    " micro_steps, status, xp_reward, created_at)"
                    " VALUES (?, 'Home / Admin', 'Next Up', 'Low', 25, ?, 'Todo', 30, ?)",
                    (st.session_state.get("adv_break_title", "Untitled task"),
                     json.dumps(checked),
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                _award_xp(conn, 10, 0)
                conn.commit()
                st.toast("Task created with micro-steps! +10 XP", icon="🧩")
                st.rerun()


def render_ai_day_planner(st, conn) -> None:
    """Smart Day Planner (rule-based): order today's tasks into timed blocks."""
    st.subheader("Smart Day Planner")
    st.caption("Smart suggestion — based on your logged data. The plan is built by "
               "simple rules (Big 3 first, then energy match, then shortest first), "
               "not by a live AI model.")
    latest = _read(conn, "SELECT energy_level FROM energy_logs ORDER BY id DESC LIMIT 1")
    energy_now = int(latest.iloc[0]["energy_level"]) if not latest.empty else None
    if energy_now is not None:
        st.info(f"Your latest logged energy is **{energy_now}/10** — the plan orders tasks to match it.")
    else:
        st.info("No energy check-in logged yet — log one in the sidebar and the plan will match your energy.")

    col_a, col_b = st.columns(2)
    start_time = col_a.time_input("Day starts at", value=time(9, 0), key="adv_plan_start")
    free_minutes = col_b.number_input("Free minutes today", min_value=15, max_value=720,
                                      value=180, step=15, key="adv_plan_free")
    todos = _read(conn, "SELECT title, est_minutes, priority, energy_req FROM tasks"
                        " WHERE status = 'Todo' ORDER BY id")
    task_rows = todos.to_dict("records") if not todos.empty else []
    if not task_rows:
        st.info("No open tasks to plan. Add a task in the Command Center first.")
        return

    if st.button("Build my day plan", key="adv_plan_go", type="primary", use_container_width=True):
        plan = build_day_plan(task_rows, start_time, int(free_minutes), energy_now)
        st.session_state["adv_day_plan"] = [
            {**b, "start": b["start"].isoformat(), "end": b["end"].isoformat()} for b in plan
        ]
        st.toast(f"Day plan built: {len(plan)} block(s) in {int(free_minutes)} free minutes.", icon="📅")

    plan = st.session_state.get("adv_day_plan", [])
    if plan:
        st.markdown("**Your timed plan** (5-minute breaks between blocks)")
        for block in plan:
            start = datetime.fromisoformat(block["start"]).strftime("%H:%M")
            end = datetime.fromisoformat(block["end"]).strftime("%H:%M")
            st.markdown(f"• **{start}–{end}** — {block['title']} ({block['minutes']} min)")
            if block.get("break_after"):
                st.caption("↳ 5-minute break — stretch, water, breathe.")
        top3 = plan[:3]
        if st.button("Save the top 3 as my Big 3  (+10 XP)", key="adv_plan_big3",
                     use_container_width=True):
            titles = [b["title"] for b in top3]
            conn.execute("UPDATE tasks SET priority = 'Next Up' WHERE priority = 'NOW (Big 3)' AND status = 'Todo'")
            for title in titles:
                conn.execute("UPDATE tasks SET priority = 'NOW (Big 3)' WHERE title = ? AND status = 'Todo'",
                             (title,))
            _award_xp(conn, 10, 0)
            conn.commit()
            st.toast("Top 3 saved as your Big 3! +10 XP", icon="🎯")
            st.rerun()


def render_calendar_export(st, conn) -> None:
    """Real .ics download + honest notification hooks (no fake live sync)."""
    st.subheader("Calendar Export & Reminders")
    st.caption("Download a real .ics file and import it into Google or Apple Calendar. "
               "Live 2-way calendar sync and push notifications need the hosted version "
               "plus your opt-in — they are NOT live in this build.")
    plan = st.session_state.get("adv_day_plan", [])
    events = []
    if plan:
        st.markdown("**From your Smart Day Plan:**")
        for block in plan:
            start = datetime.fromisoformat(block["start"])
            end = datetime.fromisoformat(block["end"])
            st.markdown(f"• **{start.strftime('%H:%M')}–{end.strftime('%H:%M')}** — {block['title']}")
            events.append({"title": block["title"], "start": start, "end": end,
                           "description": "Planned in Haveloo ADHD Life OS (rule-based day plan)."})
    else:
        st.info("No day plan saved yet — build one in the Smart Day Planner, "
                "or pick times for your Big 3 below.")
        big3 = _read(conn, "SELECT title, est_minutes FROM tasks"
                           " WHERE status = 'Todo' AND priority = 'NOW (Big 3)' ORDER BY id")
        for _, row in big3.iterrows():
            start = st.time_input(f"Start time — {row['title']}",
                                  value=time(9, 0), key=f"adv_ics_{row['title'][:20]}")
            start_dt = datetime.combine(date.today(), start)
            events.append({"title": str(row["title"]), "start": start_dt,
                           "end": start_dt + timedelta(minutes=int(row["est_minutes"] or 25)),
                           "description": "Big 3 task from Haveloo ADHD Life OS."})
    if events:
        ics_text = build_ics(events)
        st.download_button("Download .ics calendar file", data=ics_text,
                           file_name="haveloo-day-plan.ics", mime="text/calendar",
                           use_container_width=True, key="adv_ics_download")
        st.caption("Import: Google Calendar → Settings → Import & export → Select file. "
                   "Apple Calendar → File → Import.")
    st.divider()
    st.markdown("**Phone reminder hooks (copy these — no live push yet)**")
    first_title = events[0]["title"] if events else "your top task"
    reminder_text = (
        f"Haveloo reminder: {first_title} — start with the tiniest 2-minute step. "
        "One small step counts. (Set this as a phone alarm or calendar alert.)"
    )
    st.code(reminder_text, language="text")
    hook_options = st.multiselect(
        "Which reminders do you want to set on your phone?",
        ["Morning plan alarm", "Big 3 midday check-in", "Evening wind-down alarm",
         "Medicine reminder", "Bill due-day reminder"],
        default=_get_pref(conn, "reminder_hooks", "").split("|") if _get_pref(conn, "reminder_hooks") else [],
        key="adv_hooks_pick",
    )
    if st.button("Save my reminder choices", key="adv_hooks_save", use_container_width=True):
        _set_pref(conn, "reminder_hooks", "|".join(hook_options))
        conn.commit()
        st.toast("Reminder choices saved. Set them as phone alarms — live push is not in this build.", icon="🔔")
        st.rerun()


VOICE_WIDGET_HTML = """
<div style="font-family: sans-serif;">
  <p id="voice-status">Tap "Start listening" and speak your task. Your words stay in this browser until you save them below.</p>
  <button id="voice-start" style="padding:8px 16px; border-radius:8px; cursor:pointer;">🎙️ Start listening</button>
  <button id="voice-stop" style="padding:8px 16px; border-radius:8px; cursor:pointer;">⏹️ Stop</button>
  <button id="voice-copy" style="padding:8px 16px; border-radius:8px; cursor:pointer;">📋 Copy transcript</button>
  <p><textarea id="voice-out" rows="3" style="width:100%;" readonly placeholder="Your spoken words will appear here..."></textarea></p>
</div>
<script>
(function () {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var status = document.getElementById('voice-status');
  var out = document.getElementById('voice-out');
  if (!SR) {
    status.textContent = 'Voice input is not supported in this browser. Please type your task in the box below instead — that works everywhere.';
    document.getElementById('voice-start').disabled = true;
    return;
  }
  var rec = new SR();
  rec.lang = 'en-US';
  rec.interimResults = true;
  rec.continuous = false;
  rec.onresult = function (e) {
    var text = '';
    for (var i = 0; i < e.results.length; i++) { text += e.results[i][0].transcript; }
    out.value = text;
    status.textContent = 'Heard: "' + text + '" — copy it or type it into the box below, then press Save.';
  };
  rec.onerror = function (e) {
    status.textContent = 'Voice input had a problem (' + e.error + '). Please type your task below instead.';
  };
  rec.onend = function () { status.textContent += ' (Listening stopped.)'; };
  document.getElementById('voice-start').onclick = function () { out.value = ''; rec.start(); status.textContent = 'Listening... speak now.'; };
  document.getElementById('voice-stop').onclick = function () { try { rec.stop(); } catch (e) {} };
  document.getElementById('voice-copy').onclick = function () {
    if (navigator.clipboard) { navigator.clipboard.writeText(out.value); status.textContent = 'Copied — paste it into the box below.'; }
  };
})();
</script>
"""


def render_voice_add(st, conn) -> None:
    """Voice task input (browser speech recognition) with a typed fallback.

    The transcript is NEVER captured automatically: the widget only shows the
    words on screen, and the user confirms them in the Streamlit form below
    before anything is saved.
    """
    st.subheader("Voice Task Add")
    st.caption("Speak it, check it, then save it. Nothing is saved until you press "
               "the Save button below.")
    st.components.v1.html(VOICE_WIDGET_HTML, height=230)
    st.markdown("**Type or paste your task here (this fallback always works):**")
    with st.form("adv_voice_form", clear_on_submit=True):
        text = st.text_input("Task or thought", placeholder="e.g. Call the dentist tomorrow morning",
                             key="adv_voice_text")
        tag = st.selectbox("Tag", ["Task Idea", "Shopping / Research", "Social",
                                  "Work / Automation", "Random"], key="adv_voice_tag")
        submitted = st.form_submit_button("Save to Brain Dump  (+5 XP)", use_container_width=True)
        if submitted and text.strip():
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO brain_dump (thought, tag, created_at, triaged) VALUES (?, ?, ?, 0)",
                         (text.strip(), tag, now_str))
            conn.execute("INSERT INTO voice_notes (text, created_at, triaged) VALUES (?, ?, 0)",
                         (text.strip(), now_str))
            _award_xp(conn, 5, 2)
            conn.commit()
            st.toast("Saved to Brain Dump! +5 XP", icon="🎙️")
            st.rerun()
    recent = _read(conn, "SELECT * FROM voice_notes ORDER BY id DESC LIMIT 5")
    if not recent.empty:
        st.markdown("**Recent voice notes**")
        for _, row in recent.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"“{row['text']}”  \n<small>{row['created_at']}</small>", unsafe_allow_html=True)
            if c2.button("🗑️", key=f"adv_voice_del_{int(row['id'])}"):
                conn.execute("DELETE FROM voice_notes WHERE id = ?", (int(row["id"]),))
                conn.commit()
                st.toast("Voice note deleted.", icon="🗑️")
                st.rerun()


def render_focus_pro(st, conn) -> None:
    """Focus Pro: soundscapes, hyperfocus guard, body doubling, focus mode."""
    st.subheader("Focus Pro")
    st.caption("Soundscapes here are simple built-in choices — no audio files are "
               "bundled and no copyrighted tracks are used. The only sound this "
               "build makes is a short gentle beep when a timer ends.")
    sounds = _read(conn, "SELECT name, kind FROM focus_sounds ORDER BY id")
    sound_names = sounds["name"].tolist() if not sounds.empty else [n for n, _ in BUILTIN_SOUNDS]
    saved_kind = _get_pref(conn, "focus_sound", "")
    default_idx = 0
    if saved_kind:
        for i, name in enumerate(sound_names):
            kind = sounds[sounds["name"] == name].iloc[0]["kind"] if not sounds.empty else ""
            if kind == saved_kind:
                default_idx = i
                break
    choice = st.selectbox("Soundscape", sound_names, index=default_idx, key="adv_sound_pick")
    kind = ""
    if not sounds.empty:
        match = sounds[sounds["name"] == choice]
        kind = str(match.iloc[0]["kind"]) if not match.empty else ""
    st.caption(SOUND_DESCRIPTIONS.get(kind, "A quiet focus background."))
    if st.button("Set as my soundscape", key="adv_sound_save", use_container_width=True):
        _set_pref(conn, "focus_sound", kind)
        conn.commit()
        st.toast(f"Soundscape saved: {choice}. (No audio plays in this build — pick it to set the mood for your session.)", icon="🎧")
        st.rerun()
    st.components.v1.html(
        f'<p>Timer-end beep preview (a short gentle tone, generated in code):</p>'
        f'<audio controls src="{beep_data_uri()}"></audio>',
        height=90,
    )

    st.divider()
    st.markdown("**Hyperfocus guard**")
    guard_on = st.checkbox("Remind me to take a break every 50 minutes",
                           value=_get_pref(conn, "hyperfocus_guard", "0") == "1",
                           key="adv_guard_chk")
    if st.button("Save hyperfocus guard setting", key="adv_guard_save", use_container_width=True):
        _set_pref(conn, "hyperfocus_guard", "1" if guard_on else "0")
        conn.commit()
        st.toast("Hyperfocus guard " + ("on — take a 5-minute break every 50 minutes." if guard_on else "off."), icon="⏰")
        st.rerun()
    if guard_on:
        st.warning("⏰ **Guard is on:** if you have been focusing for 50 minutes, "
                   "stand up, drink water, and rest your eyes for 5 minutes.")

    st.divider()
    st.markdown("**Body Doubling — you are not focusing alone**")
    focus_mode = st.checkbox("Focus Mode — hide everything except the timer and the current task",
                             value=bool(st.session_state.get("adv_focus_mode", False)),
                             key="adv_focus_mode_chk")
    st.session_state["adv_focus_mode"] = bool(focus_mode)

    todos = _read(conn, "SELECT title FROM tasks WHERE status = 'Todo' ORDER BY id DESC")
    task_options = todos["title"].tolist() if not todos.empty else ["General focus session"]
    bd_task = st.selectbox("Session task", task_options, key="adv_bd_task")
    with st.container(border=True):
        st.markdown("👥 **Someone is here with you.** A quiet presence, no judgment — "
                    "just you and this task, together for 25 minutes.")
        started = st.session_state.get("adv_bd_start")
        if started:
            elapsed = int((datetime.now() - datetime.fromisoformat(started)).total_seconds() // 60)
            st.markdown(f"Session running: **{elapsed} min** elapsed of 25.")
            st.progress(min(1.0, elapsed / 25.0))
        col_b1, col_b2 = st.columns(2)
        if col_b1.button("▶️ Start 25-min session", key="adv_bd_start", use_container_width=True):
            st.session_state["adv_bd_start"] = datetime.now().isoformat()
            st.toast("Body-doubling session started — someone is here with you.", icon="👥")
            st.rerun()
        if col_b2.button("✅ Finish & log session  (+30 XP)", key="adv_bd_finish",
                         type="primary", use_container_width=True):
            if started:
                elapsed = max(1, int((datetime.now() - datetime.fromisoformat(started)).total_seconds() // 60))
            else:
                elapsed = 25
            xp = max(15, int(elapsed * 1.5))
            conn.execute(
                "INSERT INTO focus_sessions (task_title, duration_minutes, distractions_caught,"
                " xp_earned, session_date) VALUES (?, ?, 0, ?, ?)",
                (bd_task, elapsed, xp, date.today().isoformat()),
            )
            _award_xp(conn, xp, max(5, elapsed // 3))
            conn.commit()
            st.session_state["adv_bd_start"] = None
            st.toast(f"Body-doubling session logged: {elapsed} min! +{xp} XP", icon="👥")
            st.rerun()

    if not focus_mode:
        st.divider()
        st.markdown("**Quick boosts while you focus**")
        menu = _read(conn, "SELECT item_name FROM dopamine_menu WHERE cost_coins = 0 ORDER BY id LIMIT 1")
        pending = _read(conn, "SELECT COUNT(*) AS n FROM impulse_vault WHERE status = 'Cooling Off'")
        if not menu.empty:
            free_item = str(menu.iloc[0]["item_name"])
            if st.button(f"⚡ Activate free boost: {free_item}  (+5 XP)", key="adv_fp_boost",
                         use_container_width=True):
                _award_xp(conn, 5, 0)
                conn.commit()
                st.toast(f"Activated '{free_item}'! +5 XP", icon="⚡")
                st.rerun()
        pending_n = int(pending.iloc[0]["n"]) if not pending.empty else 0
        st.caption(f"🛡️ {pending_n} item(s) cooling off in your Impulse-Buy Vault — "
                   "open the Vault tab to check them.")
    else:
        st.caption("Focus Mode is on — only the timer and your current task are shown here.")


SOS_STEPS = [
    ("Breathe in slowly for 4 counts.", "Feel your feet on the floor. You are here, right now."),
    ("Hold gently for 4 counts.", "Nothing else needs you for these two minutes."),
    ("Breathe out slowly for 6 counts.", "Let your shoulders drop as you breathe out."),
    ("One last slow breath — in for 4, out for 6.", "Now pick the tiniest next step. One small step is enough."),
]


def render_sos(st, conn) -> None:
    """SOS / Overwhelm button — a 2-minute guided reset, then log what helped."""
    st.subheader("SOS — Feeling Overwhelmed?")
    st.caption("SOS is a calming tool, not a crisis service. If you are in crisis, "
               "please contact your local emergency services or a trusted person right away.")
    feeling = st.selectbox(
        "What is happening right now?",
        ["Overwhelmed by too many things at once", "Stuck starting a big task",
         "Anxious and cannot settle", "Angry or frustrated", "Tired and low"],
        key="adv_sos_feeling",
    )
    if st.button("🆘 Start my 2-minute reset", key="adv_sos_start", type="primary",
                 use_container_width=True):
        cur = conn.cursor()
        cur.execute("INSERT INTO sos_log (created_at, feeling, what_helped, minutes_used)"
                    " VALUES (?, ?, '', 0)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), feeling))
        st.session_state["adv_sos_id"] = int(cur.lastrowid)
        st.session_state["adv_sos_active"] = True
        st.session_state["adv_sos_step"] = 0
        conn.commit()
        st.toast("Reset started — just breathe. Two minutes, one step at a time.", icon="🆘")
        st.rerun()

    if st.session_state.get("adv_sos_active"):
        step = int(st.session_state.get("adv_sos_step", 0))
        title, hint = SOS_STEPS[min(step, len(SOS_STEPS) - 1)]
        with st.container(border=True):
            st.markdown(f"### Step {step + 1} of {len(SOS_STEPS)}")
            st.markdown(f"**{title}**")
            st.caption(hint)
            st.progress((step + 1) / len(SOS_STEPS))
            if step < len(SOS_STEPS) - 1:
                # Navigation only: advances the on-screen breathing step.
                if st.button("Next breath →", key="adv_sos_next", use_container_width=True):
                    st.session_state["adv_sos_step"] = step + 1
                    st.rerun()
            else:
                helped = st.selectbox(
                    "What helped most?",
                    ["Slow breathing", "Breaking it into one tiny step",
                     "Closing extra tabs / clearing the space", "Drinking water",
                     "Stepping away for a minute", "Something else"],
                    key="adv_sos_helped",
                )
                if st.button("I feel calmer — save this reset  (+15 XP)", key="adv_sos_save",
                             type="primary", use_container_width=True):
                    sos_id = st.session_state.get("adv_sos_id")
                    if sos_id:
                        conn.execute("UPDATE sos_log SET what_helped = ?, minutes_used = 2 WHERE id = ?",
                                     (helped, int(sos_id)))
                    _award_xp(conn, 15, 5)
                    conn.commit()
                    st.session_state["adv_sos_active"] = False
                    st.session_state["adv_sos_step"] = 0
                    st.toast("Reset saved. Well done for pausing. +15 XP", icon="💚")
                    st.rerun()
    past = _read(conn, "SELECT * FROM sos_log WHERE what_helped != '' ORDER BY id DESC LIMIT 5")
    if not past.empty:
        st.markdown("**What helped you before**")
        for _, row in past.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"• {row['created_at'][:10]} — *{row['feeling']}* → **{row['what_helped']}**")
            if c2.button("🗑️", key=f"adv_sos_del_{int(row['id'])}"):
                conn.execute("DELETE FROM sos_log WHERE id = ?", (int(row["id"]),))
                conn.commit()
                st.toast("SOS entry deleted.", icon="🗑️")
                st.rerun()


def render_cycle_sleep(st, conn) -> None:
    """Cycle tracker + sleep / water / medicine log."""
    st.subheader("Cycle, Sleep & Daily Care")
    st.caption("Estimates and observations only — not medical advice. If something "
               "worries you about your health, please talk to a doctor.")
    col_c, col_w = st.columns(2, gap="large")

    with col_c:
        st.markdown("**Cycle tracker**")
        with st.form("adv_cycle_form", clear_on_submit=True):
            start_d = st.date_input("Cycle start date", value=date.today(), key="adv_cycle_start")
            end_d = st.date_input("Cycle end date", value=date.today(), key="adv_cycle_end")
            flow = st.selectbox("Flow", ["Light", "Medium", "Heavy"], key="adv_cycle_flow")
            mood = st.selectbox("Mood during cycle", ["Steady", "Scattered", "Low Battery",
                                                      "Dialed In", "Hyperfocused"], key="adv_cycle_mood")
            energy = st.slider("Energy during cycle (1–10)", 1, 10, 5, key="adv_cycle_energy")
            saved = st.form_submit_button("Log this cycle", type="primary", use_container_width=True)
            if saved:
                conn.execute(
                    "INSERT INTO cycle_log (start_date, end_date, flow, mood, energy, notes)"
                    " VALUES (?, ?, ?, ?, ?, '')",
                    (start_d.isoformat(), end_d.isoformat(), flow, mood, int(energy)),
                )
                conn.commit()
                st.toast("Cycle logged.", icon="🌙")
                st.rerun()
        nxt = estimate_next_cycle_start(conn)
        if nxt:
            st.info(f"Next start estimate: **{nxt.strftime('%b %d, %Y')}** "
                    "(last start + 28 days — estimate only, not medical advice).")
        note = cycle_focus_note(conn)
        if note:
            st.caption("Cycle x focus — an observation: " + note)
        cycles = _read(conn, "SELECT * FROM cycle_log ORDER BY start_date DESC LIMIT 3")
        if not cycles.empty:
            for _, row in cycles.iterrows():
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"• {row['start_date']} → {row['end_date'] or '…'} "
                            f"({row['flow']}, {row['mood']}, energy {row['energy']}/10)")
                if c2.button("🗑️", key=f"adv_cycle_del_{int(row['id'])}"):
                    conn.execute("DELETE FROM cycle_log WHERE id = ?", (int(row["id"]),))
                    conn.commit()
                    st.toast("Cycle entry deleted.", icon="🗑️")
                    st.rerun()

    with col_w:
        st.markdown("**Today — sleep, water & medicine**")
        today_iso = date.today().isoformat()
        existing = _read(conn, "SELECT * FROM wellness_log WHERE log_date = ?", (today_iso,))
        ex = existing.iloc[0] if not existing.empty else None
        with st.form("adv_wellness_form", clear_on_submit=True):
            sleep = st.slider("Sleep last night (hours)", 0.0, 12.0,
                              float(ex["sleep_hours"]) if ex is not None else 7.0, 0.5,
                              key="adv_w_sleep")
            water = st.number_input("Glasses of water", min_value=0, max_value=20,
                                    value=int(ex["water_glasses"]) if ex is not None else 6,
                                    key="adv_w_water")
            meds = st.checkbox("Medicine taken today",
                               value=bool(ex["medicine_taken"]) if ex is not None else False,
                               key="adv_w_meds")
            exercise = st.number_input("Exercise (minutes)", min_value=0, max_value=300,
                                       value=int(ex["exercise_minutes"]) if ex is not None else 15,
                                       key="adv_w_ex")
            notes = st.text_input("One-line note (optional)", key="adv_w_notes")
            saved_w = st.form_submit_button("Save today's log  (+10 XP)", type="primary",
                                            use_container_width=True)
            if saved_w:
                conn.execute(
                    "INSERT INTO wellness_log (log_date, sleep_hours, water_glasses,"
                    " medicine_taken, exercise_minutes, notes) VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(log_date) DO UPDATE SET sleep_hours = excluded.sleep_hours,"
                    " water_glasses = excluded.water_glasses,"
                    " medicine_taken = excluded.medicine_taken,"
                    " exercise_minutes = excluded.exercise_minutes, notes = excluded.notes",
                    (today_iso, float(sleep), int(water), 1 if meds else 0, int(exercise), notes),
                )
                _award_xp(conn, 10, 0)
                conn.commit()
                st.toast("Today's care log saved! +10 XP", icon="💧")
                st.rerun()
        last7 = _read(conn, "SELECT * FROM wellness_log ORDER BY log_date DESC LIMIT 7")
        if not last7.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("Avg sleep (7d)", f"{float(last7['sleep_hours'].mean()):.1f} h")
            m2.metric("Avg water (7d)", f"{float(last7['water_glasses'].mean()):.1f} glasses")
            m3.metric("Medicine days (7d)", f"{int(last7['medicine_taken'].sum())} / {len(last7)}")
            st.caption(f"Exercise in the last 7 days: {int(last7['exercise_minutes'].sum())} minutes total.")


def render_subscriptions_bills(st, conn) -> None:
    """Subscription tracker + bill reminders + 48-hour impulse waitlist."""
    st.subheader("Money Guard — Subscriptions, Bills & Waitlist")
    today = date.today()

    st.markdown("**Subscriptions**")
    with st.form("adv_sub_form", clear_on_submit=True):
        s1, s2 = st.columns(2)
        name = s1.text_input("Subscription name", placeholder="e.g. Music Streaming", key="adv_sub_name")
        price = s2.number_input("Price ($)", min_value=0.0, value=9.99, step=0.5, key="adv_sub_price")
        s3, s4 = st.columns(2)
        cycle = s3.selectbox("Billing", ["monthly", "yearly"], key="adv_sub_cycle")
        renewal = s4.date_input("Next renewal", value=today + timedelta(days=30), key="adv_sub_renewal")
        if st.form_submit_button("Add subscription", type="primary", use_container_width=True):
            if name.strip():
                conn.execute(
                    "INSERT INTO subscriptions (name, price, billing_cycle, next_renewal, status)"
                    " VALUES (?, ?, ?, ?, 'active')",
                    (name.strip(), float(price), cycle, renewal.isoformat()),
                )
                conn.commit()
                st.toast(f"Subscription '{name.strip()}' added.", icon="💳")
                st.rerun()
    subs = _read(conn, "SELECT * FROM subscriptions ORDER BY next_renewal")
    monthly_total = 0.0
    if not subs.empty:
        for _, row in subs.iterrows():
            if row["status"] == "active":
                monthly_total += float(row["price"]) / 12.0 if row["billing_cycle"] == "yearly" else float(row["price"])
        st.metric("Monthly subscription total (active)", f"${monthly_total:,.2f}")
        for _, row in subs.iterrows():
            try:
                renew = date.fromisoformat(str(row["next_renewal"])[:10])
                days_left = (renew - today).days
            except ValueError:
                days_left = None
            c1, c2, c3 = st.columns([3, 1.5, 1])
            warn = " ⚠️ renews soon!" if (days_left is not None and 0 <= days_left <= 7 and row["status"] == "active") else ""
            c1.markdown(f"**{row['name']}** — ${float(row['price']):,.2f} / {row['billing_cycle']} "
                        f"· renews {row['next_renewal']}{warn} · *{row['status']}*")
            if row["status"] == "active":
                if c2.button("Cancel", key=f"adv_sub_cancel_{int(row['id'])}", use_container_width=True):
                    conn.execute("UPDATE subscriptions SET status = 'cancelled' WHERE id = ?",
                                 (int(row["id"]),))
                    conn.commit()
                    st.toast(f"'{row['name']}' cancelled — that money stays with you.", icon="💳")
                    st.rerun()
            else:
                if c2.button("Reactivate", key=f"adv_sub_react_{int(row['id'])}", use_container_width=True):
                    conn.execute("UPDATE subscriptions SET status = 'active' WHERE id = ?",
                                 (int(row["id"]),))
                    conn.commit()
                    st.toast(f"'{row['name']}' reactivated.", icon="💳")
                    st.rerun()
            if c3.button("🗑️", key=f"adv_sub_del_{int(row['id'])}"):
                conn.execute("DELETE FROM subscriptions WHERE id = ?", (int(row["id"]),))
                conn.commit()
                st.toast("Subscription deleted.", icon="🗑️")
                st.rerun()

    st.divider()
    st.markdown("**Bill reminders**")
    with st.form("adv_bill_form", clear_on_submit=True):
        b1, b2, b3 = st.columns([2, 1, 1])
        b_name = b1.text_input("Bill", placeholder="e.g. Internet", key="adv_bill_name")
        b_amount = b2.number_input("Amount ($)", min_value=0.0, value=50.0, step=5.0, key="adv_bill_amount")
        b_day = b3.number_input("Due day (1–31)", min_value=1, max_value=31, value=1, key="adv_bill_day")
        if st.form_submit_button("Add bill", type="primary", use_container_width=True):
            if b_name.strip():
                conn.execute("INSERT INTO bills (name, amount, due_day, status) VALUES (?, ?, ?, 'unpaid')",
                             (b_name.strip(), float(b_amount), int(b_day)))
                conn.commit()
                st.toast(f"Bill '{b_name.strip()}' added.", icon="🧾")
                st.rerun()
    bills = _read(conn, "SELECT * FROM bills ORDER BY due_day")
    if not bills.empty:
        for _, row in bills.iterrows():
            c1, c2, c3 = st.columns([3, 1.5, 1])
            c1.markdown(f"**{row['name']}** — ${float(row['amount']):,.2f} · due day {int(row['due_day'])} "
                        f"· *{row['status']}*")
            if row["status"] == "unpaid":
                if c2.button("Mark paid", key=f"adv_bill_paid_{int(row['id'])}", use_container_width=True):
                    conn.execute("UPDATE bills SET status = 'paid' WHERE id = ?", (int(row["id"]),))
                    conn.commit()
                    st.toast(f"'{row['name']}' marked paid.", icon="✅")
                    st.rerun()
            else:
                if c2.button("Mark unpaid", key=f"adv_bill_unpaid_{int(row['id'])}", use_container_width=True):
                    conn.execute("UPDATE bills SET status = 'unpaid' WHERE id = ?", (int(row["id"]),))
                    conn.commit()
                    st.toast(f"'{row['name']}' marked unpaid.", icon="🧾")
                    st.rerun()
            if c3.button("🗑️", key=f"adv_bill_del_{int(row['id'])}"):
                conn.execute("DELETE FROM bills WHERE id = ?", (int(row["id"]),))
                conn.commit()
                st.toast("Bill deleted.", icon="🗑️")
                st.rerun()

    st.divider()
    st.markdown("**Impulse waitlist — 48 hours before you decide**")
    with st.form("adv_wait_form", clear_on_submit=True):
        w1, w2 = st.columns([2, 1])
        w_name = w1.text_input("What do you want to buy?", placeholder="e.g. Ceramic pour-over set",
                               key="adv_wait_name")
        w_price = w2.number_input("Price ($)", min_value=0.0, value=30.0, step=5.0, key="adv_wait_price")
        w_hours = st.selectbox("Wait before deciding", [24, 48, 72], index=1, key="adv_wait_hours")
        if st.form_submit_button("Add to waitlist", type="primary", use_container_width=True):
            if w_name.strip():
                conn.execute(
                    "INSERT INTO impulse_waitlist (item_name, price, added_at, wait_hours, status)"
                    " VALUES (?, ?, ?, ?, 'waiting')",
                    (w_name.strip(), float(w_price),
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(w_hours)),
                )
                conn.commit()
                st.toast(f"'{w_name.strip()}' is on the waitlist for {w_hours}h.", icon="⏳")
                st.rerun()
    waiting = _read(conn, "SELECT * FROM impulse_waitlist WHERE status = 'waiting' ORDER BY added_at")
    if not waiting.empty:
        now_dt = datetime.now()
        for _, row in waiting.iterrows():
            added = datetime.strptime(str(row["added_at"]), "%Y-%m-%d %H:%M:%S")
            unlock = added + timedelta(hours=int(row["wait_hours"]))
            hours_left = (unlock - now_dt).total_seconds() / 3600.0
            with st.container(border=True):
                c1, c2, c3 = st.columns([2.5, 1.2, 1.2])
                c1.markdown(f"**{row['item_name']}** — ${float(row['price']):,.2f}")
                if hours_left > 0:
                    c1.caption(f"⏳ {hours_left:.1f} hours left of the {int(row['wait_hours'])}h wait.")
                else:
                    c1.caption("🔓 Wait is over — do you still want it?")
                if c2.button("Still want it", key=f"adv_wait_buy_{int(row['id'])}",
                             disabled=hours_left > 0, use_container_width=True):
                    conn.execute("UPDATE impulse_waitlist SET status = 'bought' WHERE id = ?",
                                 (int(row["id"]),))
                    conn.commit()
                    st.toast(f"OK — '{row['item_name']}' bought after the full wait. Mindful choice.", icon="🛍️")
                    st.rerun()
                if c3.button("Skipped it  (+20 XP)", key=f"adv_wait_skip_{int(row['id'])}",
                             use_container_width=True):
                    conn.execute("UPDATE impulse_waitlist SET status = 'skipped' WHERE id = ?",
                                 (int(row["id"]),))
                    _award_xp(conn, 20, 10)
                    conn.commit()
                    st.toast(f"Skipped '{row['item_name']}' — ${float(row['price']):,.2f} saved! +20 XP", icon="💪")
                    st.rerun()
    else:
        st.caption("Waitlist is clear — nothing waiting for a decision.")


def render_print_export(st, conn) -> None:
    """Weekly summary (printable) + JSON backup download + JSON restore."""
    st.subheader("Print & Backup")
    st.caption("Print with your browser (Ctrl/Cmd + P) once the summary is on screen. "
               "The backup is a plain JSON file with all of your planner data.")
    if st.button("Build my weekly summary", key="adv_print_build", type="primary",
                 use_container_width=True):
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        done = _read(conn, "SELECT * FROM tasks WHERE status = 'Done' AND completed_at >= ?",
                     (week_ago,))
        focus = _read(conn, "SELECT * FROM focus_sessions WHERE session_date >= ?", (week_ago,))
        wellness = _read(conn, "SELECT * FROM wellness_log WHERE log_date >= ?", (week_ago,))
        saved = _read(conn, "SELECT * FROM impulse_waitlist WHERE status = 'skipped'")
        coins_row = conn.execute("SELECT xp, coins FROM user_stats WHERE id = 1").fetchone()
        lines = [
            "# Haveloo ADHD Life OS — My Week",
            f"Week of {week_ago} to {date.today().isoformat()}",
            "",
            f"**Tasks finished this week:** {len(done)}",
        ]
        if not done.empty:
            for title in done["title"].tolist():
                lines.append(f"- {title}")
        total_focus = int(focus["duration_minutes"].sum()) if not focus.empty else 0
        lines.append("")
        lines.append(f"**Focus minutes this week:** {total_focus} across {len(focus)} session(s)")
        if not wellness.empty:
            lines.append(f"**Average sleep (7d):** {float(wellness['sleep_hours'].mean()):.1f} hours")
            lines.append(f"**Medicine days (7d):** {int(wellness['medicine_taken'].sum())} / {len(wellness)}")
        saved_total = float(saved["price"].sum()) if not saved.empty else 0.0
        lines.append(f"**Money saved by skipping waitlist items:** ${saved_total:,.2f}")
        if coins_row:
            lines.append(f"**Total XP:** {coins_row[0]} · **Dopamine Coins:** {coins_row[1]}")
        lines.append("")
        lines.append("Kind note: small steps count. One tiny win is still a win.")
        st.session_state["adv_weekly_summary"] = "\n".join(lines)
        st.toast("Weekly summary built from your real data.", icon="🖨️")
    summary = st.session_state.get("adv_weekly_summary", "")
    if summary:
        st.markdown(summary)
        st.components.v1.html(
            '<button onclick="window.print()" style="padding:8px 16px; border-radius:8px;'
            ' cursor:pointer;">🖨️ Print this page</button>',
            height=60,
        )
    st.divider()
    st.markdown("**Backup — download everything**")
    backup = export_backup(conn)
    st.download_button("Download full backup (JSON)", data=json.dumps(backup, indent=2),
                       file_name="haveloo-adhd-backup.json", mime="application/json",
                       use_container_width=True, key="adv_backup_download")
    st.markdown("**Restore — from a backup file**")
    st.caption("Restoring REPLACES the current data in every table with the backup's data. "
               "Download a fresh backup first if you want a safety copy.")
    uploaded = st.file_uploader("Choose a Haveloo backup (.json)", type=["json"],
                                key="adv_restore_file")
    if uploaded is not None:
        try:
            payload = json.loads(uploaded.read().decode("utf-8"))
            tables = payload.get("tables", {})
            preview = ", ".join(f"{t}: {len(r)} row(s)" for t, r in tables.items() if r)
            st.info("This backup contains — " + (preview or "no rows"))
            if st.button("Restore this backup (replaces current data)", key="adv_restore_go",
                         type="primary", use_container_width=True):
                counts = restore_backup(conn, payload)
                restored = sum(counts.values())
                st.toast(f"Backup restored: {restored} row(s) across {len(counts)} table(s).", icon="♻️")
                st.rerun()
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(f"That file could not be restored: {exc}")
