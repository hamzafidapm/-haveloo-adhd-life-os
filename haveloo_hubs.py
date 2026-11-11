"""Haveloo ADHD Life OS — Hubs module (Tier 1 hubs + Money/Meals deepening).

Companion to app.py. This module NEVER imports app.py and never edits it.
Every render function takes the Streamlit module as its first argument (`st`)
plus the data it needs, so the functions can be called from app.py like:

    from haveloo_hubs import init_hub_tables, seed_hubs, render_people
    render_people(st, conn)

The module uses only its own sqlite3 / json / datetime imports (plotly is
imported lazily, inside render_explore, so importing this file never needs
Streamlit or Plotly installed). All wording is Haveloo's own original wording;
no competitor branding or text is copied, and no live URL is invented.

Tables created here (see init_hub_tables): people, household_tasks,
home_inventory, learn_items, trips, career_items, goals_board, money_extra,
recipes, grocery_items, meal_plan, countdowns, weekly_resets, onboarding.
Tables reused from app.py (read-only except where noted): tasks, energy_logs,
impulse_vault, user_stats, habits, habit_logs, focus_sessions.
"""

import json
import os
import random
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

THEME_NAMES = ["Cocoa", "Sage", "Apricot", "Lavender", "Ocean", "Rosewood"]

THEME_PURPOSES = {
    "Cocoa": "Warm Comfort / Grounding — cozy and grounding for low, heavy days.",
    "Sage": "Calm / Anxiety Relief — low stimulation, slow breathing, gentle wording.",
    "Apricot": "Mood Lift / Gentle Energy — warm and gently energising for low-energy days.",
    "Lavender": "Relax / Night Rest — soft and soothing for evening wind-down.",
    "Ocean": "Deep Focus — minimal distraction, calmest layout, focus first.",
    "Rosewood": "Reflect / Look Back — kind weekly and monthly review, wins and reflection.",
}

WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

FREQUENCY_DAYS = {"Daily": 1, "Weekly": 7, "Monthly": 30}

ONBOARDING_STEPS = [
    ("onboarding_step_1", "Pick your theme — Cocoa, Sage, Apricot, Lavender, Ocean or Rosewood."),
    ("onboarding_step_2", "Add your Big 3 for today in the Command Center."),
    ("onboarding_step_3", "Log your energy once (sidebar check-in)."),
    ("onboarding_step_4", "Lock one impulse buy in the Vault for 48 hours."),
    ("onboarding_step_5", "Set up one savings jar in the Money hub."),
]

DB_FILENAME = "adhd_life_os.db"


def _default_conn() -> sqlite3.Connection:
    """Connection to the app database next to this file.

    Used only by render_guided_tour / render_onboarding_checklist when the
    caller does not pass a connection. app.py should pass its own conn.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_FILENAME)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_conn(conn):
    """Return (conn, close_after). If conn is None, open the default one."""
    if conn is None:
        return _default_conn(), True
    return conn, False


# ---------------------------------------------------------------------------
# Small DB helpers
# ---------------------------------------------------------------------------

def _rows(conn, sql, params=()):
    """SELECT helper returning a list of plain dicts (works with or without
    sqlite3.Row row_factory). Returns [] if the table does not exist yet."""
    try:
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def _one(conn, sql, params=()):
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _count(conn, table):
    row = _one(conn, "SELECT COUNT(*) AS n FROM %s" % table)
    return int(row["n"]) if row else 0


def _today_iso():
    return date.today().isoformat()


def _days_between(date_str, ref=None):
    """Whole days from date_str ('YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS') to ref
    (default today). Returns None when the date cannot be parsed."""
    if not date_str:
        return None
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    ref = ref or date.today()
    return (ref - d).days


def award_hub_xp(conn, xp_delta, coin_delta=0):
    """Same XP/coins update as app.py award_xp_and_coins, but on the passed
    connection (no new connection, no import of app.py)."""
    conn.execute(
        """
        UPDATE user_stats
        SET xp = MAX(0, xp + ?),
            coins = MAX(0, coins + ?),
            last_active_date = ?
        WHERE id = 1
        """,
        (int(xp_delta), int(coin_delta), _today_iso()),
    )
    conn.commit()


def calculate_bounce_back_hub(conn):
    """Copy of app.py calculate_bounce_back_score logic (14-day habit
    consistency + bounce-back rate), computed here from the passed connection
    so this module never imports app.py.

    Returns (consistency_pct, bounce_back_pct).
    """
    habits = _rows(conn, "SELECT id FROM habits")
    logs = _rows(conn, "SELECT habit_id, log_date FROM habit_logs")
    if not habits:
        return 0.0, 100.0
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    log_set = set((r["habit_id"], r["log_date"]) for r in logs)
    total_slots = len(habits) * len(days)
    completed = sum(
        1 for h in habits for d in days if (h["id"], d) in log_set
    )
    consistency = (completed / total_slots * 100) if total_slots else 0.0
    misses = 0
    recoveries = 0
    for h in habits:
        for i in range(len(days) - 1):
            if (h["id"], days[i]) not in log_set:
                misses += 1
                if (h["id"], days[i + 1]) in log_set:
                    recoveries += 1
    bounce_back = (recoveries / misses * 100) if misses else 100.0
    return round(consistency, 1), round(bounce_back, 1)


# ---------------------------------------------------------------------------
# 1. Schema
# ---------------------------------------------------------------------------

def init_hub_tables(conn):
    """CREATE TABLE IF NOT EXISTS for every hub table.

    The first ten tables are the Tier 1 hub tables. The last four support the
    named features: meal_plan (weekly meal plan), countdowns (countdown
    events), weekly_resets (weekly reset log), onboarding (guided-tour answers
    + setup checklist + emergency-contacts note, key/value like user_prefs).
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            relation TEXT NOT NULL,
            birthday TEXT,
            last_contact TEXT,
            catchup_days INTEGER NOT NULL DEFAULT 14,
            gift_ideas TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS household_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            area TEXT NOT NULL,
            frequency TEXT NOT NULL,
            last_done TEXT,
            assigned_to TEXT,
            status TEXT NOT NULL DEFAULT 'Active'
        );

        CREATE TABLE IF NOT EXISTS home_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL,
            location TEXT,
            qty INTEGER NOT NULL DEFAULT 0,
            low_at INTEGER NOT NULL DEFAULT 2
        );

        CREATE TABLE IF NOT EXISTS learn_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            progress_pct INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Not started',
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            destination TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'Planned',
            packing_list_json TEXT NOT NULL DEFAULT '[]',
            bucket INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS career_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Active',
            next_step TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS goals_board (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            detail TEXT,
            target_date TEXT,
            status TEXT NOT NULL DEFAULT 'Not started'
        );

        CREATE TABLE IF NOT EXISTS money_extra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            target REAL,
            extra_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            calories INTEGER NOT NULL DEFAULT 0,
            protein_g REAL NOT NULL DEFAULT 0,
            carbs_g REAL NOT NULL DEFAULT 0,
            fat_g REAL NOT NULL DEFAULT 0,
            ingredients TEXT,
            steps TEXT,
            tags TEXT
        );

        CREATE TABLE IF NOT EXISTS grocery_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL,
            qty TEXT,
            checked INTEGER NOT NULL DEFAULT 0,
            source_recipe TEXT
        );

        CREATE TABLE IF NOT EXISTS meal_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            recipe_id INTEGER,
            UNIQUE(day)
        );

        CREATE TABLE IF NOT EXISTS countdowns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            event_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS weekly_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reset_date TEXT NOT NULL,
            moved_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS onboarding (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 2. Demo seed data (only into empty tables — COUNT check first)
# ---------------------------------------------------------------------------

def seed_hubs(conn):
    """Insert small realistic demo seed data, one table at a time, and only
    when that table is empty. Running seed_hubs twice changes nothing.
    Demo persona matches app.py: work/study, home, health, finance, creative;
    teammate Alex, Q4 proposal, Etsy shop, Lake District trip."""
    today = date.today()
    cur = conn.cursor()

    def empty(table):
        return cur.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0] == 0

    if empty("people"):
        cur.executemany(
            "INSERT INTO people (name, relation, birthday, last_contact, catchup_days, gift_ideas, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("Alex Morgan", "Friend", "1992-06-14",
                 (today - timedelta(days=16)).isoformat(), 14,
                 "Specialty coffee beans, plain notebook",
                 "Friday dinner — text back about the plan."),
                ("Sarah Khan", "Friend", "1990-11-28",
                 (today - timedelta(days=5)).isoformat(), 14,
                 "Crochet kit, herbal tea",
                 "Met at the craft market; loves handmade gifts."),
                ("Mum", "Family", "1968-03-02",
                 (today - timedelta(days=3)).isoformat(), 7,
                 "Photo book, cosy socks",
                 "Sunday call — ask about the garden."),
                ("Jordan Lee", "Teammate", "1993-09-21",
                 (today - timedelta(days=9)).isoformat(), 10,
                 "Desk plant, book voucher",
                 "Q4 proposal teammate; check draft feedback."),
            ],
        )

    if empty("household_tasks"):
        cur.executemany(
            "INSERT INTO household_tasks (title, area, frequency, last_done, assigned_to, status)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Wipe kitchen counters", "Kitchen", "Daily",
                 (today - timedelta(days=1)).isoformat(), "Me", "Active"),
                ("Vacuum living room", "Living Room", "Weekly",
                 (today - timedelta(days=6)).isoformat(), "Me", "Active"),
                ("Deep-clean bathroom", "Bathroom", "Monthly",
                 (today - timedelta(days=20)).isoformat(), "Me", "Active"),
                ("Take out recycling", "Kitchen", "Weekly",
                 (today - timedelta(days=2)).isoformat(), "Shared", "Active"),
            ],
        )

    if empty("home_inventory"):
        cur.executemany(
            "INSERT INTO home_inventory (item, location, qty, low_at) VALUES (?, ?, ?, ?)",
            [
                ("Dishwasher tablets", "Kitchen", 8, 10),
                ("Laundry detergent", "Utility", 2, 3),
                ("Spare light bulbs", "Hallway", 6, 2),
                ("Toilet paper rolls", "Bathroom", 12, 6),
            ],
        )

    if empty("learn_items"):
        cur.executemany(
            "INSERT INTO learn_items (title, kind, progress_pct, status, notes) VALUES (?, ?, ?, ?, ?)",
            [
                ("Atomic Habits", "book", 60, "In progress", "One chapter before bed."),
                ("Python for Data Analysis", "course", 35, "In progress",
                 "Finish module 4 this week; assignment due Friday."),
                ("Sourdough baking", "skill", 20, "In progress",
                 "Weekend bake practice; starter feeds on Saturdays."),
                ("Touch typing", "skill", 45, "In progress", "10 minutes a day, mornings."),
            ],
        )

    if empty("trips"):
        cur.executemany(
            "INSERT INTO trips (name, destination, start_date, end_date, status, packing_list_json, bucket)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("Lisbon long weekend", "Lisbon", "2026-04-10", "2026-04-13", "Visited",
                 json.dumps([{"item": "Passport", "done": True},
                             {"item": "Comfy shoes", "done": True},
                             {"item": "Camera", "done": True}]), 0),
                ("Kyoto in spring", "Kyoto", "2027-03-20", "2027-03-27", "Bucket List",
                 json.dumps([{"item": "JR Pass", "done": False},
                             {"item": "Phrasebook", "done": False}]), 1),
                ("Lake District reset", "Lake District", "2026-12-05", "2026-12-07", "Planned",
                 json.dumps([{"item": "Walking boots", "done": False},
                             {"item": "Rain jacket", "done": False},
                             {"item": "Thermos", "done": False}]), 0),
            ],
        )

    if empty("career_items"):
        cur.executemany(
            "INSERT INTO career_items (title, kind, amount, status, next_step, notes) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Haveloo Etsy shop", "side_hustle", 120, "Active",
                 (today + timedelta(days=7)).isoformat(),
                 "Crochet patterns; list the Pippin pattern next."),
                ("Freelance writing", "side_hustle", 250, "Active",
                 (today + timedelta(days=3)).isoformat(),
                 "Send the invoice for the October article."),
                ("Monthly newsletter", "income", 40, "Active",
                 (today + timedelta(days=5)).isoformat(),
                 "Paid subscribers; send the November issue."),
                ("Maya — craft fair organiser", "contact", 0, "Active",
                 (today + timedelta(days=2)).isoformat(),
                 "Email about a stall at the December fair."),
                ("CV refresh", "cv", 0, "In progress",
                 (today + timedelta(days=14)).isoformat(),
                 "Add the Q4 project and the freelance work."),
            ],
        )

    if empty("goals_board"):
        cur.executemany(
            "INSERT INTO goals_board (title, kind, detail, target_date, status) VALUES (?, ?, ?, ?, ?)",
            [
                ("Calm mornings, one small win a day", "vision", "Health", None, "Active"),
                ("Finish the Q4 proposal", "yearmap", "Q1", None, "Done"),
                ("Grow the Etsy shop to its first 10 sales", "yearmap", "Q2", None, "In progress"),
                ("Take a real holiday — Lake District", "yearmap", "Q3", None, "Not started"),
                ("Launch the Christmas crochet collection", "yearmap", "Q4", None, "Not started"),
            ],
        )

    if empty("money_extra"):
        # One budget, two savings jars, two debts (so both payoff orders can
        # be shown), two subscriptions — 7 rows.
        cur.executemany(
            "INSERT INTO money_extra (kind, name, amount, target, extra_json) VALUES (?, ?, ?, ?, ?)",
            [
                ("budget_battery", "Groceries — November", 235, 400, "{}"),
                ("savings_jar", "Holiday fund", 350, 800, "{}"),
                ("savings_jar", "New laptop", 200, 1200, "{}"),
                ("debt", "Credit card", 850, 850,
                 json.dumps({"interest_rate": 19.9, "min_payment": 35})),
                ("debt", "Student loan", 4200, 4200,
                 json.dumps({"interest_rate": 4.5, "min_payment": 120})),
                ("subscription", "Video streaming", 12.99, None, "{}"),
                ("subscription", "Cloud storage", 2.99, None, "{}"),
            ],
        )

    if empty("recipes"):
        cur.executemany(
            "INSERT INTO recipes (name, calories, protein_g, carbs_g, fat_g, ingredients, steps, tags)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("One-pan lemon chicken", 520, 38, 42, 22,
                 "chicken breast, lemon, rice, green beans, olive oil",
                 "Season the chicken. Pan-fry 6 minutes a side. Cook the rice. Serve with green beans.",
                 "quick, high-protein"),
                ("Overnight oats", 340, 12, 52, 9,
                 "oats, milk, yoghurt, berries, honey",
                 "Mix oats, milk and yoghurt in a jar. Chill overnight. Top with berries and honey.",
                 "breakfast, no-cook"),
                ("Veggie lentil soup", 380, 18, 55, 8,
                 "red lentils, carrots, onion, tomatoes, cumin",
                 "Soften onion and carrots. Add lentils, tomatoes and cumin. Simmer 25 minutes.",
                 "veggie, batch-cook"),
            ],
        )

    if empty("grocery_items"):
        cur.executemany(
            "INSERT INTO grocery_items (item, qty, checked, source_recipe) VALUES (?, ?, ?, ?)",
            [
                ("chicken breast", "500 g", 0, "One-pan lemon chicken"),
                ("oats", "1 pack", 0, "Overnight oats"),
                ("red lentils", "500 g", 0, "Veggie lentil soup"),
            ],
        )

    if empty("meal_plan"):
        cur.executemany(
            "INSERT INTO meal_plan (day, recipe_id) VALUES (?, ?)",
            [("Monday", 1), ("Tuesday", 2), ("Wednesday", 3)],
        )

    if empty("countdowns"):
        cur.executemany(
            "INSERT INTO countdowns (event, event_date, created_at) VALUES (?, ?, ?)",
            [
                ("Lake District trip", "2026-12-05", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                ("Christmas Day", "2026-12-25", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ],
        )

    if empty("weekly_resets"):
        cur.execute(
            "INSERT INTO weekly_resets (reset_date, moved_count) VALUES (?, ?)",
            ((today - timedelta(days=7)).isoformat(), 2),
        )

    if empty("onboarding"):
        cur.executemany(
            "INSERT INTO onboarding (key, value) VALUES (?, ?)",
            [("tour_seen", "0")]
            + [(key, "0") for key, _ in ONBOARDING_STEPS],
        )

    conn.commit()


def seed_hub_defaults(conn):
    """Seed ONLY the structural defaults for a fresh buyer account.

    No demo persona rows: no sample people, household tasks, inventory,
    learn items, trips, career items, goals, money rows, recipes, grocery
    items, meal plans, countdowns or weekly resets. The only rows written
    are the onboarding key/value defaults (tour not seen, setup steps not
    done), so the guided tour and onboarding checklist work on an empty
    account. Idempotent: nothing is written when the onboarding table
    already has rows.
    """
    init_hub_tables(conn)
    cur = conn.cursor()
    if cur.execute("SELECT COUNT(*) FROM onboarding").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO onboarding (key, value) VALUES (?, ?)",
            [("tour_seen", "0")]
            + [(key, "0") for key, _ in ONBOARDING_STEPS],
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers shared by the render functions
# ---------------------------------------------------------------------------

def _delete_row(st, conn, table, row_id, label):
    conn.execute("DELETE FROM %s WHERE id = ?" % table, (int(row_id),))
    conn.commit()
    st.toast("%s deleted." % label, icon="🗑️")
    st.rerun()


def _pack_items(raw):
    """Normalise a packing_list_json value to a list of {item, done} dicts."""
    try:
        data = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    out = []
    for entry in data if isinstance(data, list) else []:
        if isinstance(entry, dict):
            out.append({"item": str(entry.get("item", "")), "done": bool(entry.get("done", False))})
        elif isinstance(entry, str) and entry.strip():
            out.append({"item": entry.strip(), "done": False})
    return out


def _debt_info(row):
    try:
        extra = json.loads(row.get("extra_json") or "{}")
    except ValueError:
        extra = {}
    return {
        "rate": float(extra.get("interest_rate", 0) or 0),
        "min_payment": float(extra.get("min_payment", 0) or 0),
    }


# ---------------------------------------------------------------------------
# 3a. Tier 1 hub tabs — People
# ---------------------------------------------------------------------------

def render_people(st, conn):
    """People hub: catch-up nudges, birthdays, gift ideas bank."""
    with st.container(border=True):
        st.subheader("👥 People — stay in touch without the guilt")
        people = _rows(conn, "SELECT * FROM people ORDER BY name")
        today = date.today()

        # --- Upcoming birthdays (next 30 days, year-wrap aware) ---
        upcoming = []
        for p in people:
            if not p.get("birthday"):
                continue
            try:
                b = datetime.strptime(p["birthday"][:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            this_year = b.replace(year=today.year)
            if this_year < today:
                this_year = b.replace(year=today.year + 1)
            in_days = (this_year - today).days
            if in_days <= 30:
                upcoming.append((in_days, p["name"], this_year.strftime("%b %d")))
        if upcoming:
            st.caption("🎂 Birthdays coming up: " + "; ".join(
                "%s in %d day%s (%s)" % (n, d, "" if d == 1 else "s", when)
                for d, n, when in sorted(upcoming)
            ))

        if not people:
            st.info("No people saved yet — add someone you want to keep in touch with.")
        for p in people:
            days_since = _days_between(p.get("last_contact"))
            due = days_since is not None and days_since >= int(p.get("catchup_days") or 14)
            with st.container(border=True):
                c1, c2, c3 = st.columns([3.2, 1.3, 0.9])
                with c1:
                    st.markdown("**%s** · %s" % (p["name"], p["relation"]))
                    st.caption(
                        "Birthday: %s • Last contact: %s (%s) • Catch up every %d days"
                        % (
                            p.get("birthday") or "—",
                            p.get("last_contact") or "never",
                            "never" if days_since is None else "%d days ago" % days_since,
                            int(p.get("catchup_days") or 14),
                        )
                    )
                    if p.get("gift_ideas"):
                        st.caption("🎁 Gift ideas bank: %s" % p["gift_ideas"])
                    if p.get("notes"):
                        st.caption(p["notes"])
                with c2:
                    if due:
                        st.warning("💬 Time to catch up — %d days since you last spoke." % days_since)
                    else:
                        st.success("All good — no nudge needed yet.")
                with c3:
                    if st.button("✅ Caught up", key="hub_people_caught_%s" % p["id"], use_container_width=True):
                        conn.execute(
                            "UPDATE people SET last_contact = ? WHERE id = ?",
                            (_today_iso(), int(p["id"])),
                        )
                        conn.commit()
                        award_hub_xp(conn, 10, 5)
                        st.toast("Nice — caught up with %s! +10 XP" % p["name"], icon="💬")
                        st.rerun()
                    if st.button("🗑️", key="hub_people_del_%s" % p["id"], use_container_width=True):
                        _delete_row(st, conn, "people", p["id"], p["name"])

        with st.form("hub_people_add", clear_on_submit=True):
            st.markdown("**Add a person**")
            f1, f2 = st.columns(2)
            name = f1.text_input("Name", placeholder="e.g., Alex Morgan")
            relation = f2.selectbox("Relation", ["Friend", "Family", "Teammate", "Neighbour", "Other"])
            f3, f4 = st.columns(2)
            birthday = f3.date_input("Birthday", value=date(1992, 6, 14))
            catchup = f4.number_input("Catch up every (days)", min_value=1, max_value=365, value=14)
            gift = st.text_input("Gift ideas (comma-separated)", placeholder="e.g., coffee beans, notebook")
            notes = st.text_input("Notes", placeholder="e.g., Text back about Friday dinner")
            if st.form_submit_button("➕ Add person", type="primary", use_container_width=True):
                if name.strip():
                    conn.execute(
                        "INSERT INTO people (name, relation, birthday, last_contact, catchup_days, gift_ideas, notes)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (name.strip(), relation, birthday.isoformat(), _today_iso(),
                         int(catchup), gift.strip(), notes.strip()),
                    )
                    conn.commit()
                    st.toast("Added %s to your People hub!" % name.strip(), icon="👥")
                    st.rerun()


# ---------------------------------------------------------------------------
# 3b. Tier 1 hub tabs — Household
# ---------------------------------------------------------------------------

def render_household(st, conn):
    """Household hub: repeating cleaning schedule, chore chart, declutter
    zones, home inventory with low-stock flags, emergency contacts note."""
    with st.container(border=True):
        st.subheader("🏠 Household — cleaning, chores, inventory")
        tasks = _rows(conn, "SELECT * FROM household_tasks ORDER BY area, title")
        today = date.today()

        st.markdown("**Cleaning schedule (repeats — mark done to reset the clock)**")
        if not tasks:
            st.info("No household tasks yet — add your first cleaning task below.")
        for t in tasks:
            days_since = _days_between(t.get("last_done"))
            freq_days = FREQUENCY_DAYS.get(t.get("frequency"), 7)
            overdue = days_since is None or days_since >= freq_days
            with st.container(border=True):
                c1, c2, c3 = st.columns([3.0, 1.4, 1.1])
                with c1:
                    st.markdown("**%s** · %s · %s" % (t["title"], t["area"], t["frequency"]))
                    st.caption(
                        "Assigned to: %s • Last done: %s • Status: %s"
                        % (t.get("assigned_to") or "Me", t.get("last_done") or "never", t["status"])
                    )
                with c2:
                    if overdue:
                        st.warning("Due now — %s since last done."
                                   % ("never done" if days_since is None else "%d days ago" % days_since))
                    else:
                        st.caption("Next due in %d day%s." % (freq_days - days_since, "" if freq_days - days_since == 1 else "s"))
                with c3:
                    if st.button("✅ Mark done", key="hub_home_done_%s" % t["id"], use_container_width=True):
                        conn.execute(
                            "UPDATE household_tasks SET last_done = ? WHERE id = ?",
                            (_today_iso(), int(t["id"])),
                        )
                        conn.commit()
                        award_hub_xp(conn, 10, 5)
                        st.toast("Done! %s reset — +10 XP" % t["title"], icon="🧹")
                        st.rerun()
                    if st.button("⏸️ Pause" if t["status"] == "Active" else "▶️ Resume",
                                 key="hub_home_pause_%s" % t["id"], use_container_width=True):
                        conn.execute(
                            "UPDATE household_tasks SET status = ? WHERE id = ?",
                            ("Paused" if t["status"] == "Active" else "Active", int(t["id"])),
                        )
                        conn.commit()
                        st.toast("Updated %s." % t["title"], icon="🏠")
                        st.rerun()
                    if st.button("🗑️", key="hub_home_del_%s" % t["id"], use_container_width=True):
                        _delete_row(st, conn, "household_tasks", t["id"], t["title"])

        # --- Chore chart: tasks per person ---
        if tasks:
            counts = Counter((t.get("assigned_to") or "Me") for t in tasks)
            st.markdown("**Chore chart — tasks per person**")
            st.bar_chart(dict(counts))

        # --- Declutter zones: one button per area marks every task there done ---
        areas = sorted(set((t.get("area") or "General") for t in tasks))
        if areas:
            st.markdown("**Declutter zones**")
            cols = st.columns(len(areas))
            for col, area in zip(cols, areas):
                n_here = sum(1 for t in tasks if (t.get("area") or "General") == area)
                if col.button("✨ %s clear (%d)" % (area, n_here), key="hub_zone_%s" % area.replace(" ", "_")):
                    conn.execute(
                        "UPDATE household_tasks SET last_done = ? WHERE area = ?",
                        (_today_iso(), area),
                    )
                    conn.commit()
                    award_hub_xp(conn, 15, 5)
                    st.toast("Zone clear! Every %s task marked done. +15 XP" % area, icon="✨")
                    st.rerun()

        with st.form("hub_home_add", clear_on_submit=True):
            st.markdown("**Add a household task**")
            f1, f2 = st.columns(2)
            title = f1.text_input("Task", placeholder="e.g., Wipe kitchen counters")
            area = f2.selectbox("Area / zone", ["Kitchen", "Living Room", "Bathroom", "Bedroom", "Hallway", "Utility", "Garden"])
            f3, f4 = st.columns(2)
            freq = f3.selectbox("Repeats", ["Daily", "Weekly", "Monthly"])
            who = f4.text_input("Assigned to", value="Me")
            if st.form_submit_button("➕ Add household task", type="primary", use_container_width=True):
                if title.strip():
                    conn.execute(
                        "INSERT INTO household_tasks (title, area, frequency, last_done, assigned_to, status)"
                        " VALUES (?, ?, ?, ?, ?, 'Active')",
                        (title.strip(), area, freq, _today_iso(), who.strip() or "Me"),
                    )
                    conn.commit()
                    st.toast("Added %s!" % title.strip(), icon="🏠")
                    st.rerun()

    with st.container(border=True):
        st.subheader("📦 Home inventory — low-stock alerts")
        items = _rows(conn, "SELECT * FROM home_inventory ORDER BY item")
        if not items:
            st.info("Inventory is empty — add the household things you run out of.")
        for it in items:
            low = int(it["qty"]) <= int(it["low_at"])
            c1, c2, c3, c4 = st.columns([2.6, 1.2, 1.0, 0.7])
            with c1:
                st.markdown("**%s** · %s" % (it["item"], it.get("location") or "—"))
            with c2:
                if low:
                    st.warning("⚠️ Low stock: %d left (reorder at %d)" % (it["qty"], it["low_at"]))
                else:
                    st.caption("%d in stock" % it["qty"])
            with c3:
                if st.button("➕ 1", key="hub_inv_plus_%s" % it["id"], use_container_width=True):
                    conn.execute("UPDATE home_inventory SET qty = qty + 1 WHERE id = ?", (int(it["id"]),))
                    conn.commit()
                    st.toast("Added 1 × %s." % it["item"], icon="📦")
                    st.rerun()
                if st.button("➖ 1", key="hub_inv_minus_%s" % it["id"], use_container_width=True):
                    conn.execute(
                        "UPDATE home_inventory SET qty = MAX(0, qty - 1) WHERE id = ?", (int(it["id"]),)
                    )
                    conn.commit()
                    st.toast("Used 1 × %s." % it["item"], icon="📦")
                    st.rerun()
            with c4:
                if st.button("🗑️", key="hub_inv_del_%s" % it["id"], use_container_width=True):
                    _delete_row(st, conn, "home_inventory", it["id"], it["item"])
        with st.form("hub_inv_add", clear_on_submit=True):
            f1, f2, f3, f4 = st.columns([2.2, 1.4, 1.0, 1.0])
            item = f1.text_input("Item", placeholder="e.g., Dishwasher tablets")
            loc = f2.text_input("Location", placeholder="e.g., Kitchen")
            qty = f3.number_input("Qty", min_value=0, value=1)
            low_at = f4.number_input("Low at", min_value=0, value=2)
            if st.form_submit_button("➕ Add to inventory", type="primary", use_container_width=True):
                if item.strip():
                    conn.execute(
                        "INSERT INTO home_inventory (item, location, qty, low_at) VALUES (?, ?, ?, ?)",
                        (item.strip(), loc.strip(), int(qty), int(low_at)),
                    )
                    conn.commit()
                    st.toast("Added %s to inventory!" % item.strip(), icon="📦")
                    st.rerun()

    with st.container(border=True):
        st.subheader("🚨 Emergency contacts note")
        st.caption("Kept in your own planner only — never shared anywhere.")
        saved = _one(conn, "SELECT value FROM onboarding WHERE key = 'emergency_contacts'")
        note = st.text_area(
            "Who to call in an emergency",
            value=(saved["value"] if saved else ""),
            placeholder="e.g., Mum — 07...; Neighbour Sam — 07...; Doctor — ...",
            key="hub_emergency_note",
        )
        if st.button("💾 Save emergency contacts", key="hub_emergency_save"):
            conn.execute(
                "INSERT INTO onboarding (key, value) VALUES ('emergency_contacts', ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (note.strip(),),
            )
            conn.commit()
            st.toast("Emergency contacts saved.", icon="🚨")
            st.rerun()


# ---------------------------------------------------------------------------
# 3c. Tier 1 hub tabs — Learn
# ---------------------------------------------------------------------------

def render_learn(st, conn):
    """Learn hub: bookshelf, courses, skill roadmaps with progress sliders,
    timetable / assignment notes."""
    with st.container(border=True):
        st.subheader("📚 Learn — bookshelf, courses & skill roadmaps")
        items = _rows(conn, "SELECT * FROM learn_items ORDER BY kind, title")
        for kind, heading in [
            ("book", "📖 Bookshelf"),
            ("course", "🎓 Courses"),
            ("skill", "🗺️ Skill roadmaps"),
        ]:
            st.markdown("**%s**" % heading)
            group = [i for i in items if i["kind"] == kind]
            if not group:
                st.caption("Nothing here yet — add one below.")
            for it in group:
                with st.container(border=True):
                    c1, c2 = st.columns([2.6, 1.6])
                    with c1:
                        st.markdown("**%s**" % it["title"])
                        st.caption("Status: %s • %s" % (it["status"], it.get("notes") or ""))
                        st.progress(min(100, max(0, int(it["progress_pct"]))) / 100.0,
                                    text="%d%% complete" % int(it["progress_pct"]))
                    with c2:
                        new_prog = st.slider(
                            "Progress %", 0, 100, int(it["progress_pct"]),
                            key="hub_learn_prog_%s" % it["id"],
                        )
                        b1, b2, b3 = st.columns(3)
                        if b1.button("💾 Save", key="hub_learn_save_%s" % it["id"], use_container_width=True):
                            conn.execute(
                                "UPDATE learn_items SET progress_pct = ? WHERE id = ?",
                                (int(new_prog), int(it["id"])),
                            )
                            conn.commit()
                            award_hub_xp(conn, 5, 0)
                            st.toast("Progress saved for %s! +5 XP" % it["title"], icon="📚")
                            st.rerun()
                        next_status = {"Not started": "In progress", "In progress": "Done", "Done": "Not started"}[it["status"]]
                        if b2.button("➡️ %s" % next_status, key="hub_learn_next_%s" % it["id"], use_container_width=True):
                            conn.execute(
                                "UPDATE learn_items SET status = ? WHERE id = ?",
                                (next_status, int(it["id"])),
                            )
                            conn.commit()
                            st.toast("%s is now %s." % (it["title"], next_status), icon="📚")
                            st.rerun()
                        if b3.button("🗑️", key="hub_learn_del_%s" % it["id"], use_container_width=True):
                            _delete_row(st, conn, "learn_items", it["id"], it["title"])
        with st.form("hub_learn_add", clear_on_submit=True):
            st.markdown("**Add something to learn**")
            f1, f2 = st.columns(2)
            title = f1.text_input("Title", placeholder="e.g., Atomic Habits")
            kind = f2.selectbox("Kind", ["book", "course", "skill"])
            f3, f4 = st.columns(2)
            prog = f3.slider("Starting progress %", 0, 100, 0)
            status = f4.selectbox("Status", ["Not started", "In progress", "Done"])
            notes = st.text_input("Timetable / assignment note",
                                  placeholder="e.g., Finish module 4 this week; assignment due Friday")
            if st.form_submit_button("➕ Add to Learn hub", type="primary", use_container_width=True):
                if title.strip():
                    conn.execute(
                        "INSERT INTO learn_items (title, kind, progress_pct, status, notes) VALUES (?, ?, ?, ?, ?)",
                        (title.strip(), kind, int(prog), status, notes.strip()),
                    )
                    conn.commit()
                    st.toast("Added %s!" % title.strip(), icon="📚")
                    st.rerun()


# ---------------------------------------------------------------------------
# 3d. Tier 1 hub tabs — Explore
# ---------------------------------------------------------------------------

def render_explore(st, conn, template="plotly_white"):
    """Explore hub: places visited / planned / bucket list, trip itineraries
    with packing checklists, and a simple bar summary. No geo data is needed
    — this is a list-and-chart summary, not a map (a real map needs location
    data the planner does not collect)."""
    with st.container(border=True):
        st.subheader("🌍 Explore — trips, itineraries & bucket list")
        trips = _rows(conn, "SELECT * FROM trips ORDER BY start_date")
        counts = Counter(t.get("status") or "Planned" for t in trips)
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ Visited", counts.get("Visited", 0))
        c2.metric("🗓️ Planned", counts.get("Planned", 0))
        c3.metric("💭 Bucket list", counts.get("Bucket List", 0))
        if trips:
            try:
                import plotly.express as px
                import pandas as pd
                chart_df = pd.DataFrame(
                    [{"Status": s, "Trips": n} for s, n in sorted(counts.items())]
                )
                fig = px.bar(chart_df, x="Status", y="Trips", template=template,
                             title="Trips by status")
                fig.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.bar_chart(dict(counts))

        if not trips:
            st.info("No trips yet — add a place you have been, or one you dream of.")
        for t in trips:
            packing = _pack_items(t.get("packing_list_json"))
            done_n = sum(1 for p in packing if p["done"])
            with st.container(border=True):
                h1, h2 = st.columns([3.2, 1.0])
                with h1:
                    st.markdown("**%s** — %s" % (t["name"], t.get("destination") or "—"))
                    st.caption(
                        "%s • %s → %s • %s"
                        % (t["status"], t.get("start_date") or "?", t.get("end_date") or "?",
                           "💭 Bucket list" if int(t.get("bucket") or 0) else "On the list")
                    )
                    if packing:
                        st.caption("Packing: %d/%d packed" % (done_n, len(packing)))
                with h2:
                    if t["status"] != "Visited":
                        if st.button("✅ Mark visited", key="hub_trip_visit_%s" % t["id"], use_container_width=True):
                            conn.execute("UPDATE trips SET status = 'Visited' WHERE id = ?", (int(t["id"]),))
                            conn.commit()
                            award_hub_xp(conn, 25, 10)
                            st.toast("Welcome back from %s! +25 XP" % (t.get("destination") or t["name"]), icon="🌍")
                            st.rerun()
                    if st.button("🗑️", key="hub_trip_del_%s" % t["id"], use_container_width=True):
                        _delete_row(st, conn, "trips", t["id"], t["name"])
                if packing:
                    st.markdown("**Packing list**")
                    changed = False
                    new_packing = []
                    for idx, p in enumerate(packing):
                        checked = st.checkbox(
                            p["item"], value=p["done"], key="hub_pack_%s_%d" % (t["id"], idx),
                        )
                        if checked != p["done"]:
                            changed = True
                        new_packing.append({"item": p["item"], "done": checked})
                    if changed:
                        conn.execute(
                            "UPDATE trips SET packing_list_json = ? WHERE id = ?",
                            (json.dumps(new_packing), int(t["id"])),
                        )
                        conn.commit()
                        st.rerun()

        st.markdown("**💭 Bucket list**")
        bucket = [t for t in trips if int(t.get("bucket") or 0) or t.get("status") == "Bucket List"]
        if not bucket:
            st.caption("Nothing on the bucket list yet.")
        for t in bucket:
            st.caption("• %s — %s" % (t["name"], t.get("destination") or "—"))

        with st.form("hub_trip_add", clear_on_submit=True):
            st.markdown("**Add a trip**")
            f1, f2 = st.columns(2)
            name = f1.text_input("Trip name", placeholder="e.g., Lake District reset")
            dest = f2.text_input("Destination", placeholder="e.g., Lake District")
            f3, f4 = st.columns(2)
            start = f3.date_input("Start date", value=date.today() + timedelta(days=30))
            end = f4.date_input("End date", value=date.today() + timedelta(days=32))
            f5, f6 = st.columns(2)
            status = f5.selectbox("Status", ["Planned", "Visited", "Bucket List"])
            bucket_flag = f6.checkbox("On my bucket list")
            packing_raw = st.text_input("Packing list (comma-separated)",
                                        placeholder="e.g., walking boots, rain jacket, thermos")
            if st.form_submit_button("➕ Add trip", type="primary", use_container_width=True):
                if name.strip():
                    packing = [{"item": x.strip(), "done": False}
                               for x in packing_raw.split(",") if x.strip()]
                    conn.execute(
                        "INSERT INTO trips (name, destination, start_date, end_date, status, packing_list_json, bucket)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (name.strip(), dest.strip(), start.isoformat(), end.isoformat(),
                         status, json.dumps(packing), 1 if bucket_flag else 0),
                    )
                    conn.commit()
                    st.toast("Added %s!" % name.strip(), icon="🌍")
                    st.rerun()


# ---------------------------------------------------------------------------
# 3e. Tier 1 hub tabs — Career
# ---------------------------------------------------------------------------

def render_career(st, conn):
    """Career hub: side hustle tracker, income streams total, personal brand /
    CV notes, networking follow-ups with next-step dates."""
    with st.container(border=True):
        st.subheader("💼 Career — side hustles, income & networking")
        items = _rows(conn, "SELECT * FROM career_items ORDER BY kind, title")
        today = date.today()
        income_rows = [i for i in items
                       if i["kind"] in ("side_hustle", "income") and i["status"] != "Closed"]
        income_total = sum(float(i["amount"] or 0) for i in income_rows)
        st.metric("💰 Active income streams total", "$%.2f / month" % income_total)
        st.caption("Total of all active side hustles and income streams (closed items excluded).")

        for kind, heading in [
            ("side_hustle", "🚀 Side hustles"),
            ("income", "💵 Income streams"),
            ("contact", "🤝 Networking follow-ups"),
            ("cv", "📄 Personal brand / CV notes"),
        ]:
            st.markdown("**%s**" % heading)
            group = [i for i in items if i["kind"] == kind]
            if not group:
                st.caption("Nothing here yet — add one below.")
            for it in group:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2.8, 1.4, 1.0])
                    with c1:
                        st.markdown("**%s**" % it["title"])
                        if it.get("notes"):
                            st.caption(it["notes"])
                        if it.get("next_step"):
                            days = _days_between(it["next_step"], today)
                            when = ("today" if days == 0 else
                                    "%d days ago — overdue" % abs(days) if days and days > 0 else
                                    "in %d days" % abs(days) if days is not None else it["next_step"])
                            st.caption("Next step: %s (%s)" % (it["next_step"], when))
                    with c2:
                        st.caption("Amount: $%.2f" % float(it["amount"] or 0))
                        st.caption("Status: %s" % it["status"])
                        if kind == "contact" and it.get("next_step"):
                            days = _days_between(it["next_step"], today)
                            if days is not None and days >= 0:
                                st.warning("📬 Follow up now — due %s." % ("today" if days == 0 else "%d days ago" % days))
                    with c3:
                        if it["status"] != "Closed":
                            if st.button("✔️ Close", key="hub_career_close_%s" % it["id"], use_container_width=True):
                                conn.execute(
                                    "UPDATE career_items SET status = 'Closed' WHERE id = ?",
                                    (int(it["id"]),),
                                )
                                conn.commit()
                                st.toast("%s closed." % it["title"], icon="💼")
                                st.rerun()
                        if st.button("🗑️", key="hub_career_del_%s" % it["id"], use_container_width=True):
                            _delete_row(st, conn, "career_items", it["id"], it["title"])

        with st.form("hub_career_add", clear_on_submit=True):
            st.markdown("**Add a career item**")
            f1, f2 = st.columns(2)
            title = f1.text_input("Title", placeholder="e.g., Haveloo Etsy shop")
            kind = f2.selectbox("Kind", ["side_hustle", "income", "contact", "cv"])
            f3, f4 = st.columns(2)
            amount = f3.number_input("Amount ($ / month, 0 if none)", min_value=0.0, value=0.0, step=10.0)
            next_step = f4.date_input("Next-step date", value=date.today() + timedelta(days=7))
            notes = st.text_input("Notes", placeholder="e.g., Send the invoice for the October article")
            if st.form_submit_button("➕ Add career item", type="primary", use_container_width=True):
                if title.strip():
                    conn.execute(
                        "INSERT INTO career_items (title, kind, amount, status, next_step, notes)"
                        " VALUES (?, ?, ?, 'Active', ?, ?)",
                        (title.strip(), kind, float(amount), next_step.isoformat(), notes.strip()),
                    )
                    conn.commit()
                    st.toast("Added %s!" % title.strip(), icon="💼")
                    st.rerun()

        with st.form("hub_career_amount", clear_on_submit=True):
            st.markdown("**Update an amount** (e.g., a side hustle earned more this month)")
            targets = [i for i in items if i["kind"] in ("side_hustle", "income")]
            if targets:
                choice = st.selectbox(
                    "Item", [i["title"] for i in targets],
                    key="hub_career_amount_pick",
                )
                new_amount = st.number_input("New amount ($ / month)", min_value=0.0, value=0.0, step=10.0)
                if st.form_submit_button("💾 Update amount", use_container_width=True):
                    row = next(i for i in targets if i["title"] == choice)
                    conn.execute(
                        "UPDATE career_items SET amount = ? WHERE id = ?",
                        (float(new_amount), int(row["id"])),
                    )
                    conn.commit()
                    st.toast("Updated %s to $%.2f." % (choice, float(new_amount)), icon="💼")
                    st.rerun()
            else:
                st.caption("Add a side hustle or income stream first.")


# ---------------------------------------------------------------------------
# 3f. Money deepening
# ---------------------------------------------------------------------------

def render_money_deepening(st, conn):
    """Money deepening: Budget Battery, Savings Jars, Debt snowball AND
    avalanche orders, Impulse List (reuses impulse_vault), Subscription Audit,
    and an honest Safe-to-Spend number with its formula shown."""
    rows = _rows(conn, "SELECT * FROM money_extra ORDER BY kind, name")
    budgets = [r for r in rows if r["kind"] == "budget_battery"]
    jars = [r for r in rows if r["kind"] == "savings_jar"]
    debts = [r for r in rows if r["kind"] == "debt"]
    subs = [r for r in rows if r["kind"] == "subscription"]

    with st.container(border=True):
        st.subheader("🔋 Budget Battery — spending vs. your monthly budget")
        if not budgets:
            st.info("No monthly budget set yet — set one below.")
        for b in budgets:
            target = float(b["target"] or 0)
            spent = float(b["amount"] or 0)
            pct = (spent / target) if target > 0 else 0.0
            st.markdown("**%s** — $%.2f spent of $%.2f" % (b["name"], spent, target))
            st.progress(min(1.0, max(0.0, pct)), text="%d%% used" % int(min(100, pct * 100)))
            if pct >= 1.0:
                st.warning("Battery empty — this budget is fully used.")
            elif pct >= 0.8:
                st.caption("Battery low — under 20% left.")
        with st.form("hub_money_budget", clear_on_submit=True):
            f1, f2 = st.columns(2)
            name = f1.text_input("Budget name", placeholder="e.g., Groceries — November")
            target = f2.number_input("Monthly budget ($)", min_value=1.0, value=400.0, step=10.0)
            if st.form_submit_button("➕ Set monthly budget", type="primary", use_container_width=True):
                if name.strip():
                    conn.execute(
                        "INSERT INTO money_extra (kind, name, amount, target, extra_json)"
                        " VALUES ('budget_battery', ?, 0, ?, '{}')",
                        (name.strip(), float(target)),
                    )
                    conn.commit()
                    st.toast("Budget set: %s — $%.2f." % (name.strip(), float(target)), icon="🔋")
                    st.rerun()
        if budgets:
            with st.form("hub_money_spend", clear_on_submit=True):
                pick = st.selectbox("Log spending against", [b["name"] for b in budgets])
                spend = st.number_input("Spent ($)", min_value=0.01, value=10.0, step=5.0)
                if st.form_submit_button("💸 Log spending", use_container_width=True):
                    row = next(b for b in budgets if b["name"] == pick)
                    conn.execute(
                        "UPDATE money_extra SET amount = amount + ? WHERE id = ?",
                        (float(spend), int(row["id"])),
                    )
                    conn.commit()
                    st.toast("Logged $%.2f against %s." % (float(spend), pick), icon="💸")
                    st.rerun()

    with st.container(border=True):
        st.subheader("🏺 Savings Jars — watch them fill up")
        if not jars:
            st.info("No savings jars yet — start one below.")
        for j in jars:
            target = float(j["target"] or 0)
            saved = float(j["amount"] or 0)
            pct = (saved / target) if target > 0 else 0.0
            st.markdown("**%s** — $%.2f saved of $%.2f" % (j["name"], saved, target))
            st.progress(min(1.0, max(0.0, pct)), text="%d%% full" % int(min(100, pct * 100)))
            if target > 0 and saved >= target:
                st.success("🎉 Jar full — %s reached its goal!" % j["name"])
        with st.form("hub_money_jar", clear_on_submit=True):
            f1, f2 = st.columns(2)
            name = f1.text_input("Jar name", placeholder="e.g., Holiday fund")
            target = f2.number_input("Goal ($)", min_value=1.0, value=800.0, step=50.0)
            if st.form_submit_button("➕ Start a savings jar", type="primary", use_container_width=True):
                if name.strip():
                    conn.execute(
                        "INSERT INTO money_extra (kind, name, amount, target, extra_json)"
                        " VALUES ('savings_jar', ?, 0, ?, '{}')",
                        (name.strip(), float(target)),
                    )
                    conn.commit()
                    st.toast("Jar started: %s." % name.strip(), icon="🏺")
                    st.rerun()
        if jars:
            with st.form("hub_money_jar_add", clear_on_submit=True):
                pick = st.selectbox("Add money to", [j["name"] for j in jars])
                add = st.number_input("Amount ($)", min_value=0.01, value=20.0, step=5.0)
                if st.form_submit_button("💰 Add money to jar", use_container_width=True):
                    row = next(j for j in jars if j["name"] == pick)
                    conn.execute(
                        "UPDATE money_extra SET amount = amount + ? WHERE id = ?",
                        (float(add), int(row["id"])),
                    )
                    conn.commit()
                    award_hub_xp(conn, 10, 5)
                    st.toast("Added $%.2f to %s! +10 XP" % (float(add), pick), icon="🏺")
                    st.rerun()

    with st.container(border=True):
        st.subheader("📉 Debt payoff — snowball AND avalanche, side by side")
        st.caption("Both orders are computed from your real debts below. "
                   "Snowball pays the smallest balance first (quick wins); "
                   "avalanche pays the highest interest first (least interest paid).")
        if len(debts) < 2:
            st.info("Add at least two debts to compare both payoff orders.")
        else:
            snowball = sorted(debts, key=lambda r: float(r["amount"] or 0))
            avalanche = sorted(debts, key=lambda r: -_debt_info(r)["rate"])
            s1, s2 = st.columns(2)
            with s1:
                st.markdown("**❄️ Snowball order (smallest balance first)**")
                for i, d in enumerate(snowball, 1):
                    st.caption("%d. %s — $%.2f (%.1f%% interest, min $%.2f/mo)"
                               % (i, d["name"], float(d["amount"] or 0),
                                  _debt_info(d)["rate"], _debt_info(d)["min_payment"]))
            with s2:
                st.markdown("**🏔️ Avalanche order (highest interest first)**")
                for i, d in enumerate(avalanche, 1):
                    st.caption("%d. %s — %.1f%% interest ($%.2f, min $%.2f/mo)"
                               % (i, d["name"], _debt_info(d)["rate"],
                                  float(d["amount"] or 0), _debt_info(d)["min_payment"]))
        for d in debts:
            info = _debt_info(d)
            c1, c2 = st.columns([3.0, 1.0])
            with c1:
                st.caption("%s — balance $%.2f • %.1f%% interest • min payment $%.2f/mo"
                           % (d["name"], float(d["amount"] or 0), info["rate"], info["min_payment"]))
            with c2:
                if st.button("🎉 Paid off!", key="hub_debt_paid_%s" % d["id"], use_container_width=True):
                    conn.execute("DELETE FROM money_extra WHERE id = ?", (int(d["id"]),))
                    conn.commit()
                    award_hub_xp(conn, 50, 25)
                    st.balloons()
                    st.toast("Debt-free on %s! +50 XP" % d["name"], icon="🎉")
                    st.rerun()
        with st.form("hub_money_debt", clear_on_submit=True):
            f1, f2 = st.columns(2)
            name = f1.text_input("Debt name", placeholder="e.g., Credit card")
            balance = f2.number_input("Balance ($)", min_value=0.0, value=500.0, step=50.0)
            f3, f4 = st.columns(2)
            rate = f3.number_input("Interest rate (%)", min_value=0.0, value=19.9, step=0.1)
            min_pay = f4.number_input("Minimum payment ($/mo)", min_value=0.0, value=35.0, step=5.0)
            if st.form_submit_button("➕ Add debt", type="primary", use_container_width=True):
                if name.strip():
                    conn.execute(
                        "INSERT INTO money_extra (kind, name, amount, target, extra_json) VALUES ('debt', ?, ?, ?, ?)",
                        (name.strip(), float(balance), float(balance),
                         json.dumps({"interest_rate": float(rate), "min_payment": float(min_pay)})),
                    )
                    conn.commit()
                    st.toast("Added debt: %s." % name.strip(), icon="📉")
                    st.rerun()

    with st.container(border=True):
        st.subheader("🛡️ Impulse List — still cooling off")
        st.caption("Same vault as the Impulse-Buy tab — items that are still cooling off.")
        vault = _rows(conn, "SELECT * FROM impulse_vault WHERE status = 'Cooling Off' ORDER BY id DESC")
        if not vault:
            st.success("Nothing cooling off right now.")
        for v in vault:
            c1, c2 = st.columns([3.0, 1.0])
            with c1:
                st.caption("• %s — $%.2f (urge %d/10, added %s)"
                           % (v["item_name"], float(v["price"]), int(v["urge_level"]), v["added_at"][:10]))
            with c2:
                if st.button("💪 Resisted", key="hub_imp_resist_%s" % v["id"], use_container_width=True):
                    conn.execute(
                        "UPDATE impulse_vault SET status = 'Resisted & Saved' WHERE id = ?",
                        (int(v["id"]),),
                    )
                    conn.commit()
                    award_hub_xp(conn, 50, 25)
                    st.toast("Saved $%.2f! +50 XP" % float(v["price"]), icon="🛡️")
                    st.rerun()

    with st.container(border=True):
        st.subheader("🧾 Subscription Audit — what quietly leaves each month")
        sub_total = sum(float(s["amount"] or 0) for s in subs)
        st.metric("Monthly subscription total", "$%.2f" % sub_total)
        st.caption("Yearly cost at this rate: $%.2f." % (sub_total * 12))
        if not subs:
            st.info("No subscriptions tracked yet.")
        for s in subs:
            c1, c2 = st.columns([3.0, 1.0])
            with c1:
                st.caption("• %s — $%.2f / month" % (s["name"], float(s["amount"] or 0)))
            with c2:
                if st.button("❌ Cancel", key="hub_sub_cancel_%s" % s["id"], use_container_width=True):
                    conn.execute("DELETE FROM money_extra WHERE id = ?", (int(s["id"]),))
                    conn.commit()
                    st.toast("Cancelled %s — $%.2f/month saved." % (s["name"], float(s["amount"] or 0)), icon="🧾")
                    st.rerun()
        with st.form("hub_money_sub", clear_on_submit=True):
            f1, f2 = st.columns(2)
            name = f1.text_input("Subscription", placeholder="e.g., Video streaming")
            cost = f2.number_input("Cost ($ / month)", min_value=0.0, value=9.99, step=1.0)
            if st.form_submit_button("➕ Add subscription", type="primary", use_container_width=True):
                if name.strip():
                    conn.execute(
                        "INSERT INTO money_extra (kind, name, amount, target, extra_json)"
                        " VALUES ('subscription', ?, ?, NULL, '{}')",
                        (name.strip(), float(cost)),
                    )
                    conn.commit()
                    st.toast("Added subscription: %s." % name.strip(), icon="🧾")
                    st.rerun()

    with st.container(border=True):
        st.subheader("✅ Safe-to-Spend")
        total_budget = sum(float(b["target"] or 0) for b in budgets)
        total_spent = sum(float(b["amount"] or 0) for b in budgets)
        safe = total_budget - total_spent - sub_total
        st.metric("Safe to spend this month", "$%.2f" % safe)
        st.caption(
            "Safe-to-Spend = total monthly budgets ($%.2f) − spent so far ($%.2f) "
            "− subscriptions ($%.2f). It only counts the budgets and subscriptions "
            "tracked here — it is not a bank balance."
            % (total_budget, total_spent, sub_total)
        )


# ---------------------------------------------------------------------------
# 3g. Meals deepening
# ---------------------------------------------------------------------------

def render_meals(st, conn):
    """Meals deepening: recipe book with calories/macros, weekly meal plan,
    auto grocery list from chosen recipes, 'Decide for me', day totals."""
    with st.container(border=True):
        st.subheader("🍽️ Meals — recipes, plan & grocery list")
        recipes = _rows(conn, "SELECT * FROM recipes ORDER BY name")
        plan = {r["day"]: r["recipe_id"] for r in _rows(conn, "SELECT day, recipe_id FROM meal_plan")}

        st.markdown("**Recipe book**")
        if not recipes:
            st.info("No recipes yet — add your first one below.")
        for r in recipes:
            with st.container(border=True):
                c1, c2 = st.columns([3.2, 0.8])
                with c1:
                    st.markdown("**%s**" % r["name"])
                    st.caption(
                        "%d kcal • Protein %.0fg • Carbs %.0fg • Fat %.0fg • %s"
                        % (int(r["calories"]), float(r["protein_g"]),
                           float(r["carbs_g"]), float(r["fat_g"]), r.get("tags") or "")
                    )
                    if r.get("ingredients"):
                        st.caption("Ingredients: %s" % r["ingredients"])
                    if r.get("steps"):
                        st.caption(r["steps"])
                with c2:
                    if st.button("🗑️", key="hub_recipe_del_%s" % r["id"], use_container_width=True):
                        _delete_row(st, conn, "recipes", r["id"], r["name"])
        with st.form("hub_recipe_add", clear_on_submit=True):
            st.markdown("**Add a recipe**")
            f1, f2 = st.columns(2)
            name = f1.text_input("Recipe name", placeholder="e.g., One-pan lemon chicken")
            tags = f2.text_input("Tags", placeholder="e.g., quick, high-protein")
            f3, f4, f5, f6 = st.columns(4)
            cal = f3.number_input("Calories", min_value=0, value=400, step=10)
            prot = f4.number_input("Protein (g)", min_value=0.0, value=25.0, step=1.0)
            carbs = f5.number_input("Carbs (g)", min_value=0.0, value=40.0, step=1.0)
            fat = f6.number_input("Fat (g)", min_value=0.0, value=15.0, step=1.0)
            ingredients = st.text_input("Ingredients (comma-separated)",
                                        placeholder="e.g., chicken breast, lemon, rice, green beans")
            steps = st.text_area("Steps", placeholder="e.g., Season the chicken. Pan-fry 6 minutes a side…")
            if st.form_submit_button("➕ Add recipe", type="primary", use_container_width=True):
                if name.strip():
                    conn.execute(
                        "INSERT INTO recipes (name, calories, protein_g, carbs_g, fat_g, ingredients, steps, tags)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (name.strip(), int(cal), float(prot), float(carbs), float(fat),
                         ingredients.strip(), steps.strip(), tags.strip()),
                    )
                    conn.commit()
                    st.toast("Added recipe: %s!" % name.strip(), icon="🍽️")
                    st.rerun()

        # --- Weekly meal plan ---
        st.markdown("**Meal plan for the week**")
        if not recipes:
            st.caption("Add a recipe first, then plan your week.")
        else:
            options = ["— No meal planned —"] + [r["name"] for r in recipes]
            with st.form("hub_meal_plan", clear_on_submit=True):
                picks = {}
                cols = st.columns(4)
                for i, day in enumerate(WEEK_DAYS):
                    current = next((r["name"] for r in recipes if r["id"] == plan.get(day)), options[0])
                    picks[day] = cols[i % 4].selectbox(
                        day, options,
                        index=options.index(current),
                        key="hub_plan_%s" % day,
                    )
                if st.form_submit_button("💾 Save week plan", type="primary", use_container_width=True):
                    conn.execute("DELETE FROM meal_plan")
                    for day, choice in picks.items():
                        if choice != options[0]:
                            rid = next(r["id"] for r in recipes if r["name"] == choice)
                            conn.execute(
                                "INSERT INTO meal_plan (day, recipe_id) VALUES (?, ?)", (day, int(rid))
                            )
                    conn.commit()
                    st.toast("Week plan saved!", icon="🍽️")
                    st.rerun()

        # --- Day totals ---
        if recipes and plan:
            day = st.selectbox("Show totals for", WEEK_DAYS, key="hub_meal_day")
            rid = plan.get(day)
            chosen = next((r for r in recipes if r["id"] == rid), None)
            if chosen:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Meal", chosen["name"])
                m2.metric("Calories", "%d kcal" % int(chosen["calories"]))
                m3.metric("Protein", "%.0f g" % float(chosen["protein_g"]))
                m4.metric("Carbs / Fat", "%.0f g / %.0f g" % (float(chosen["carbs_g"]), float(chosen["fat_g"])))
            else:
                st.caption("No meal planned for %s yet." % day)

        # --- Decide for me: random recipe -> today's plan (real DB write) ---
        if recipes:
            if st.button("🎲 Decide for me — pick tonight's meal", key="hub_decide"):
                pick = random.choice(recipes)
                today_name = date.today().strftime("%A")
                conn.execute(
                    "INSERT INTO meal_plan (day, recipe_id) VALUES (?, ?)"
                    " ON CONFLICT(day) DO UPDATE SET recipe_id = excluded.recipe_id",
                    (today_name, int(pick["id"])),
                )
                conn.commit()
                st.toast("Tonight (%s): %s — saved to your plan!" % (today_name, pick["name"]), icon="🎲")
                st.rerun()

        # --- Auto grocery list from the planned recipes ---
        if st.button("🛒 Build grocery list from this week's plan", key="hub_grocery_build"):
            planned_ids = [rid for rid in plan.values() if rid]
            added = 0
            for r in recipes:
                if r["id"] not in planned_ids or not r.get("ingredients"):
                    continue
                for raw_item in r["ingredients"].split(","):
                    item = raw_item.strip()
                    if not item:
                        continue
                    exists = _one(
                        conn,
                        "SELECT id FROM grocery_items WHERE item = ? AND checked = 0",
                        (item,),
                    )
                    if not exists:
                        conn.execute(
                            "INSERT INTO grocery_items (item, qty, checked, source_recipe) VALUES (?, '', 0, ?)",
                            (item, r["name"]),
                        )
                        added += 1
            conn.commit()
            st.toast("Grocery list built — %d new item%s added." % (added, "" if added == 1 else "s"), icon="🛒")
            st.rerun()

        st.markdown("**Grocery list**")
        groceries = _rows(conn, "SELECT * FROM grocery_items ORDER BY checked, item")
        if not groceries:
            st.caption("Grocery list is empty — build it from your plan.")
        for g in groceries:
            c1, c2 = st.columns([3.4, 0.6])
            checked = c1.checkbox(
                "%s%s" % (g["item"], (" — from %s" % g["source_recipe"]) if g.get("source_recipe") else ""),
                value=bool(g["checked"]), key="hub_groc_%s" % g["id"],
            )
            if checked != bool(g["checked"]):
                conn.execute(
                    "UPDATE grocery_items SET checked = ? WHERE id = ?",
                    (1 if checked else 0, int(g["id"])),
                )
                conn.commit()
                st.rerun()
            if c2.button("🗑️", key="hub_groc_del_%s" % g["id"], use_container_width=True):
                _delete_row(st, conn, "grocery_items", g["id"], g["item"])
        unchecked = [g for g in groceries if not g["checked"]]
        if groceries and not unchecked:
            st.success("All groceries bought! 🎉")
        if groceries and unchecked:
            if st.button("🧹 Clear bought items", key="hub_groc_clear"):
                conn.execute("DELETE FROM grocery_items WHERE checked = 1")
                conn.commit()
                st.toast("Bought items cleared from the list.", icon="🧹")
                st.rerun()


# ---------------------------------------------------------------------------
# 3h. Fill My Day (rule-based day planner)
# ---------------------------------------------------------------------------

def _energy_label(level):
    if level is None:
        return "Medium"
    if level <= 4:
        return "Low"
    if level <= 7:
        return "Medium"
    return "High"


def order_day_plan(tasks, energy_label):
    """Pure rule-based ordering (also used by the headless test).

    Low energy: low-energy, short tasks first. Otherwise: highest XP first.
    `tasks` is a list of dicts with energy_req, est_minutes, xp_reward.
    Returns the tasks in planned order."""
    rank = {"Low": 0, "Medium": 1, "High": 2}
    if energy_label == "Low":
        return sorted(
            tasks,
            key=lambda t: (rank.get(t.get("energy_req"), 1), int(t.get("est_minutes") or 25)),
        )
    return sorted(tasks, key=lambda t: -int(t.get("xp_reward") or 0))


def render_fill_my_day(st, conn):
    """Rule-based Fill My Day: orders today's Todo tasks by current energy
    and free minutes, then writes the top 3 into NOW (Big 3). Unfinished
    tasks simply stay Todo — carry-over is automatic."""
    with st.container(border=True):
        st.subheader("🗓️ Fill My Day — a plan that fits your energy")
        latest = _one(conn, "SELECT * FROM energy_logs ORDER BY id DESC LIMIT 1")
        energy = _energy_label(int(latest["energy_level"]) if latest else None)
        if latest:
            st.caption(
                "Your latest check-in: energy %d/10 (%s), mood “%s” — plan built for that."
                % (int(latest["energy_level"]), energy, latest.get("mood") or "—")
            )
        else:
            st.caption("No energy check-in yet — planning for Medium energy. Log one in the sidebar for a better fit.")
        free_minutes = st.number_input(
            "Free minutes today", min_value=5, max_value=720, value=120, step=15,
            key="hub_fill_minutes",
        )
        todos = _rows(conn, "SELECT * FROM tasks WHERE status = 'Todo' ORDER BY id")
        if not todos:
            st.success("Nothing left in Todo — your day is already clear!")
            return
        ordered = order_day_plan(todos, energy)
        plan = []
        used = 0
        for t in ordered:
            mins = int(t.get("est_minutes") or 25)
            if used + mins <= int(free_minutes):
                plan.append(t)
                used += mins
        st.markdown("**Your plan (%d minutes of your %d free)**" % (used, int(free_minutes)))
        if not plan:
            st.warning("No single task fits in %d minutes — try more free minutes, or break a task into smaller steps." % int(free_minutes))
        for i, t in enumerate(plan, 1):
            st.caption(
                "%d. %s — %d min • %s energy • +%d XP"
                % (i, t["title"], int(t.get("est_minutes") or 25), t.get("energy_req"), int(t.get("xp_reward") or 0))
            )
        skipped = [t for t in ordered if t not in plan]
        if skipped:
            st.caption("Left for another day (not enough minutes): " + ", ".join(t["title"] for t in skipped[:5]))
        if plan:
            if st.button("✅ Set my Big 3 from this plan (+10 XP)", key="hub_fill_apply", type="primary"):
                top3 = plan[:3]
                top3_ids = [int(t["id"]) for t in top3]
                conn.execute(
                    "UPDATE tasks SET priority = 'Next Up'"
                    " WHERE status = 'Todo' AND priority = 'NOW (Big 3)' AND id NOT IN (%s)"
                    % ",".join("?" * len(top3_ids)),
                    top3_ids,
                )
                for tid in top3_ids:
                    conn.execute(
                        "UPDATE tasks SET priority = 'NOW (Big 3)' WHERE id = ?", (tid,)
                    )
                conn.commit()
                award_hub_xp(conn, 10, 5)
                st.toast("Big 3 set: %s (+10 XP)" % ", ".join(t["title"] for t in top3), icon="🗓️")
                st.rerun()


# ---------------------------------------------------------------------------
# 3i. Look Back (auto review from real data only)
# ---------------------------------------------------------------------------

def render_look_back(st, conn):
    """Auto month + year review computed from REAL data only: tasks done,
    focus minutes, money saved from the vault, habit consistency (same math
    as app.py's bounce-back), top mood. No invented numbers."""
    with st.container(border=True):
        st.subheader("🌹 Look Back — your month & year, kindly")
        today = date.today()
        month_start = today.replace(day=1).isoformat()
        year_start = "%d-01-01" % today.year

        def _sum(sql, params):
            row = _one(conn, sql, params)
            return float(row["n"]) if row and row.get("n") is not None else 0.0

        done_month = int(_sum(
            "SELECT COUNT(*) AS n FROM tasks WHERE status = 'Done' AND completed_at >= ?",
            (month_start,)))
        done_year = int(_sum(
            "SELECT COUNT(*) AS n FROM tasks WHERE status = 'Done' AND completed_at >= ?",
            (year_start,)))
        focus_month = int(_sum(
            "SELECT SUM(duration_minutes) AS n FROM focus_sessions WHERE session_date >= ?",
            (month_start,)))
        focus_year = int(_sum(
            "SELECT SUM(duration_minutes) AS n FROM focus_sessions WHERE session_date >= ?",
            (year_start,)))
        saved_month = _sum(
            "SELECT SUM(price) AS n FROM impulse_vault WHERE status = 'Resisted & Saved' AND added_at >= ?",
            (month_start,))
        saved_year = _sum(
            "SELECT SUM(price) AS n FROM impulse_vault WHERE status = 'Resisted & Saved' AND added_at >= ?",
            (year_start,))
        consistency, bounce_back = calculate_bounce_back_hub(conn)

        mood_rows = _rows(
            conn,
            "SELECT mood FROM energy_logs WHERE log_date >= ? AND mood IS NOT NULL AND mood != ''",
            (month_start,),
        )
        if not mood_rows:
            mood_rows = _rows(
                conn,
                "SELECT mood FROM energy_logs WHERE mood IS NOT NULL AND mood != ''",
            )
        top_mood = Counter(r["mood"] for r in mood_rows).most_common(1)
        top_mood = top_mood[0][0] if top_mood else "not logged yet"

        m1, m2, m3 = st.columns(3)
        m1.metric("✅ Tasks done — this month", done_month)
        m2.metric("⏱️ Focus minutes — this month", focus_month)
        m3.metric("💰 Impulse money saved — this month", "$%.2f" % saved_month)
        y1, y2, y3 = st.columns(3)
        y1.metric("✅ Tasks done — this year", done_year)
        y2.metric("⏱️ Focus minutes — this year", focus_year)
        y3.metric("💰 Impulse money saved — this year", "$%.2f" % saved_year)
        h1, h2, h3 = st.columns(3)
        h1.metric("🌱 14-day habit consistency", "%.1f%%" % consistency)
        h2.metric("🔄 Bounce-back rate", "%.1f%%" % bounce_back)
        h3.metric("💛 Most common mood", top_mood)

        if done_month == 0 and focus_month == 0 and saved_month == 0:
            summary = (
                "This month is a fresh page — no tasks finished or focus minutes logged yet, "
                "and that is completely okay. One tiny step today still counts."
            )
        else:
            summary = (
                "This month you finished %d task%s, focused for %d minutes, and kept $%.2f "
                "in your pocket by resisting impulse buys. Your most common mood was “%s”, "
                "and you bounced back %.1f%% of the time after a missed habit day. "
                "Small steps, kept kindly — that is real progress."
                % (done_month, "" if done_month == 1 else "s", focus_month,
                   saved_month, top_mood, bounce_back)
            )
        st.info(summary)


# ---------------------------------------------------------------------------
# 3j. Guided tour + onboarding checklist
# ---------------------------------------------------------------------------

def _onboarding_get(conn, key, default=""):
    row = _one(conn, "SELECT value FROM onboarding WHERE key = ?", (key,))
    return row["value"] if row else default


def _onboarding_set(conn, key, value):
    conn.execute(
        "INSERT INTO onboarding (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def _starter_plan(struggle, energy_pattern, top_goal, theme):
    """Personalised starter plan text generated from the quiz answers."""
    first_tab = {
        "Starting tasks": "Command Center — pick one tiny first step and break it into micro-steps.",
        "Staying focused": "Focus & Time-Blindness — start with a 5-minute “Just Start” sprint.",
        "Forgetting things": "Brain Dump Triage — capture everything, then promote one thought to NOW.",
        "Money & impulse buys": "Impulse-Buy Vault — lock one temptation away for 48 hours.",
        "Feeling overwhelmed": "Fill My Day — let the planner order your tasks by your energy.",
    }.get(struggle, "Command Center — start with your Big 3.")
    energy_tip = {
        "Mornings are best": "Put your hardest task first thing in the morning, while your energy is highest.",
        "Afternoons dip": "Keep afternoons for low-energy admin, and save hard work for the morning.",
        "Evenings are best": "Do the hardest task in the evening, and keep mornings gentle.",
        "It changes every day": "Check in with your energy each morning, then let Fill My Day order the tasks.",
    }.get(energy_pattern, "Check your energy first, then plan around it.")
    theme_line = "You picked %s — %s" % (theme, THEME_PURPOSES.get(theme, ""))
    goal_line = ("Your top goal is “%s” — put its very first tiny step in your Big 3 today."
                 % top_goal.strip()) if top_goal and top_goal.strip() else \
        "Pick one top goal and put its very first tiny step in your Big 3 today."
    return (
        "Your starter plan:\n"
        "• Open this tab first: %s\n"
        "• Energy: %s\n"
        "• %s\n"
        "• Theme: %s"
        % (first_tab, energy_tip, goal_line, theme_line)
    )


def render_guided_tour(st, conn=None):
    """2-minute onboarding quiz in an expander. Saves answers to the
    onboarding table and shows a personalised starter plan generated from
    those answers — real text, no placeholder copy."""
    conn, close_after = _ensure_conn(conn)
    try:
        with st.container(border=True):
            st.subheader("🧭 Guided tour — your 2-minute start")
            st.caption("Four quick questions, and the planner sets itself up around you.")
            with st.expander("✨ Take the 2-minute quiz", expanded=_onboarding_get(conn, "tour_seen") != "1"):
                with st.form("hub_tour_quiz", clear_on_submit=False):
                    struggle = st.selectbox(
                        "What is your main struggle right now?",
                        ["Starting tasks", "Staying focused", "Forgetting things",
                         "Money & impulse buys", "Feeling overwhelmed"],
                    )
                    energy_pattern = st.selectbox(
                        "When is your energy usually best?",
                        ["Mornings are best", "Afternoons dip", "Evenings are best",
                         "It changes every day"],
                    )
                    top_goal = st.text_input(
                        "Your top goal for this month",
                        value=_onboarding_get(conn, "quiz_goal"),
                        placeholder="e.g., Finish the Q4 proposal",
                    )
                    theme = st.selectbox(
                        "Which theme feels right today?",
                        THEME_NAMES,
                        index=THEME_NAMES.index(_onboarding_get(conn, "quiz_theme", "Sage"))
                        if _onboarding_get(conn, "quiz_theme") in THEME_NAMES else 1,
                    )
                    if st.form_submit_button("✨ Show my starter plan", type="primary", use_container_width=True):
                        _onboarding_set(conn, "quiz_struggle", struggle)
                        _onboarding_set(conn, "quiz_energy", energy_pattern)
                        _onboarding_set(conn, "quiz_goal", top_goal.strip())
                        _onboarding_set(conn, "quiz_theme", theme)
                        _onboarding_set(conn, "tour_seen", "1")
                        award_hub_xp(conn, 15, 5)
                        st.toast("Starter plan ready! +15 XP", icon="🧭")
                        st.rerun()
            if _onboarding_get(conn, "tour_seen") == "1":
                st.success(
                    _starter_plan(
                        _onboarding_get(conn, "quiz_struggle"),
                        _onboarding_get(conn, "quiz_energy"),
                        _onboarding_get(conn, "quiz_goal"),
                        _onboarding_get(conn, "quiz_theme") or "Sage",
                    )
                )
                if st.button("🔄 Retake the quiz", key="hub_tour_retake"):
                    _onboarding_set(conn, "tour_seen", "0")
                    st.toast("Quiz reset — take it again when ready.", icon="🧭")
                    st.rerun()
    finally:
        if close_after:
            conn.close()


def render_onboarding_checklist(st, conn=None):
    """5 setup steps with checkboxes stored in the onboarding table."""
    conn, close_after = _ensure_conn(conn)
    try:
        with st.container(border=True):
            st.subheader("✅ First-week setup checklist")
            done = 0
            for key, label in ONBOARDING_STEPS:
                stored = _onboarding_get(conn, key) == "1"
                checked = st.checkbox(label, value=stored, key="hub_onb_%s" % key)
                if checked != stored:
                    _onboarding_set(conn, key, "1" if checked else "0")
                    if checked:
                        award_hub_xp(conn, 10, 5)
                        st.toast("Step done! +10 XP", icon="✅")
                    st.rerun()
                done += 1 if stored else 0
            st.progress(done / len(ONBOARDING_STEPS), text="%d of %d setup steps done" % (done, len(ONBOARDING_STEPS)))
    finally:
        if close_after:
            conn.close()


# ---------------------------------------------------------------------------
# 3k. Countdowns + Weekly Reset
# ---------------------------------------------------------------------------

def render_countdowns_weekly_reset(st, conn):
    """Countdowns (days-left computed live) + Weekly Reset button (moves
    unfinished Big 3 tasks older than today back to Next Up, logs the reset,
    awards +25 XP)."""
    with st.container(border=True):
        st.subheader("⏳ Countdowns — something to look forward to")
        events = _rows(conn, "SELECT * FROM countdowns ORDER BY event_date")
        today = date.today()
        if not events:
            st.info("No countdowns yet — add an event below.")
        for ev in events:
            try:
                target = datetime.strptime(ev["event_date"][:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            days_left = (target - today).days
            c1, c2 = st.columns([3.2, 0.8])
            with c1:
                if days_left > 1:
                    label = "%d days to go" % days_left
                elif days_left == 1:
                    label = "Tomorrow!"
                elif days_left == 0:
                    label = "Today! 🎉"
                else:
                    label = "%d days ago" % abs(days_left)
                st.markdown("**%s** — %s · %s" % (ev["event"], ev["event_date"], label))
                if days_left >= 0:
                    st.progress(min(1.0, max(0.0, 1 - days_left / 365.0)) if days_left <= 365 else 0.0)
            with c2:
                if st.button("🗑️", key="hub_cd_del_%s" % ev["id"], use_container_width=True):
                    _delete_row(st, conn, "countdowns", ev["id"], ev["event"])
        with st.form("hub_cd_add", clear_on_submit=True):
            f1, f2 = st.columns(2)
            event = f1.text_input("Event", placeholder="e.g., Lake District trip")
            when = f2.date_input("Date", value=date.today() + timedelta(days=30))
            if st.form_submit_button("➕ Add countdown", type="primary", use_container_width=True):
                if event.strip():
                    conn.execute(
                        "INSERT INTO countdowns (event, event_date, created_at) VALUES (?, ?, ?)",
                        (event.strip(), when.isoformat(),
                         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    )
                    conn.commit()
                    st.toast("Countdown added: %s!" % event.strip(), icon="⏳")
                    st.rerun()

    with st.container(border=True):
        st.subheader("🔄 Weekly Reset — a kind fresh start")
        st.caption(
            "Moves unfinished Big 3 tasks from earlier days back to Next Up, "
            "so Monday never starts with last week's guilt. Completed tasks stay done."
        )
        past = _rows(conn, "SELECT * FROM weekly_resets ORDER BY reset_date DESC LIMIT 5")
        if past:
            st.caption("Past resets: " + "; ".join(
                "%s — %d task%s moved" % (r["reset_date"], int(r["moved_count"]),
                                          "" if int(r["moved_count"]) == 1 else "s")
                for r in past
            ))
        if st.button("🔄 Run Weekly Reset (+25 XP)", key="hub_weekly_reset", type="primary"):
            cur = conn.execute(
                "UPDATE tasks SET priority = 'Next Up'"
                " WHERE status = 'Todo' AND priority = 'NOW (Big 3)'"
                " AND substr(created_at, 1, 10) < ?",
                (_today_iso(),),
            )
            moved = cur.rowcount
            conn.execute(
                "INSERT INTO weekly_resets (reset_date, moved_count) VALUES (?, ?)",
                (_today_iso(), int(moved)),
            )
            conn.commit()
            award_hub_xp(conn, 25, 10)
            st.toast("Weekly Reset done — %d task%s moved back to Next Up. +25 XP"
                     % (moved, "" if moved == 1 else "s"), icon="🔄")
            st.rerun()


# ---------------------------------------------------------------------------
# 3l. Vision board + Year map
# ---------------------------------------------------------------------------

def render_vision_yearmap(st, conn):
    """Vision board (text + category cards) + year map (one milestone per
    quarter, editable, progress shown)."""
    with st.container(border=True):
        st.subheader("🌟 Vision board — what you are moving toward")
        visions = _rows(conn, "SELECT * FROM goals_board WHERE kind = 'vision' ORDER BY id")
        if not visions:
            st.info("Vision board is empty — add your first vision below.")
        cols = st.columns(3) if visions else []
        for i, v in enumerate(visions):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown("**%s**" % v["title"])
                    st.caption(v.get("detail") or "Vision")
                    if st.button("🗑️", key="hub_vision_del_%s" % v["id"], use_container_width=True):
                        _delete_row(st, conn, "goals_board", v["id"], v["title"])
        with st.form("hub_vision_add", clear_on_submit=True):
            f1, f2 = st.columns(2)
            title = f1.text_input("Vision", placeholder="e.g., Calm mornings, one small win a day")
            category = f2.selectbox("Category", ["Health", "Work", "Home", "Creative", "Money", "Relationships"])
            if st.form_submit_button("➕ Add to vision board", type="primary", use_container_width=True):
                if title.strip():
                    conn.execute(
                        "INSERT INTO goals_board (title, kind, detail, target_date, status)"
                        " VALUES (?, 'vision', ?, NULL, 'Active')",
                        (title.strip(), category),
                    )
                    conn.commit()
                    st.toast("Added to your vision board!", icon="🌟")
                    st.rerun()

    with st.container(border=True):
        st.subheader("🗺️ Year map — one milestone per quarter")
        yearmap = {r["detail"]: r for r in _rows(conn, "SELECT * FROM goals_board WHERE kind = 'yearmap'")}
        done_q = sum(1 for r in yearmap.values() if r["status"] == "Done")
        st.progress(done_q / 4.0, text="%d of 4 quarters done" % done_q)
        for quarter in ["Q1", "Q2", "Q3", "Q4"]:
            row = yearmap.get(quarter)
            with st.container(border=True):
                c1, c2, c3 = st.columns([2.6, 1.2, 1.0])
                with c1:
                    if row:
                        st.markdown("**%s:** %s" % (quarter, row["title"]))
                        st.caption("Status: %s" % row["status"])
                    else:
                        st.markdown("**%s:** no milestone yet" % quarter)
                with c2:
                    if row:
                        new_status = st.selectbox(
                            "Status", ["Not started", "In progress", "Done"],
                            index=["Not started", "In progress", "Done"].index(row["status"]),
                            key="hub_year_status_%s" % quarter,
                        )
                        if new_status != row["status"]:
                            conn.execute(
                                "UPDATE goals_board SET status = ? WHERE id = ?",
                                (new_status, int(row["id"])),
                            )
                            conn.commit()
                            if new_status == "Done":
                                award_hub_xp(conn, 50, 25)
                                st.toast("%s milestone done! +50 XP 🎉" % quarter, icon="🗺️")
                            else:
                                st.toast("%s updated to %s." % (quarter, new_status), icon="🗺️")
                            st.rerun()
                with c3:
                    if row and st.button("🗑️", key="hub_year_del_%s" % quarter, use_container_width=True):
                        _delete_row(st, conn, "goals_board", row["id"], row["title"])
        with st.form("hub_year_add", clear_on_submit=True):
            f1, f2 = st.columns(2)
            quarter = f1.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"])
            milestone = f2.text_input("Milestone", placeholder="e.g., Launch the Christmas collection")
            if st.form_submit_button("💾 Save quarter milestone", type="primary", use_container_width=True):
                if milestone.strip():
                    existing = yearmap.get(quarter)
                    if existing:
                        conn.execute(
                            "UPDATE goals_board SET title = ?, status = 'Not started' WHERE id = ?",
                            (milestone.strip(), int(existing["id"])),
                        )
                        msg = "%s milestone updated." % quarter
                    else:
                        conn.execute(
                            "INSERT INTO goals_board (title, kind, detail, target_date, status)"
                            " VALUES (?, 'yearmap', ?, NULL, 'Not started')",
                            (milestone.strip(), quarter),
                        )
                        msg = "%s milestone saved." % quarter
                    conn.commit()
                    st.toast(msg, icon="🗺️")
                    st.rerun()
