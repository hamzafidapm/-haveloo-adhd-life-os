import json
import sqlite3
import time
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import haveloo_hubs as hubs  # Tier 1 hubs + Money/Meals deepening + planner systems
import haveloo_advance as adv  # Tier 2 advance features (rule-based Smart Planner etc.)
import haveloo_auth as auth  # Accounts, Etsy-order unlock, per-user data

# ==============================================================================
# 1. PAGE CONFIGURATION & CUSTOM NEURO-FRIENDLY STYLING
# ==============================================================================
st.set_page_config(
    page_title="ADHD Life OS | Neuro-Adaptive Command Center",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    /* High-clarity, low-clutter cards and badges */
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px 20px;
        color: #f8fafc;
        margin-bottom: 12px;
    }
    .metric-title {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94a3b8;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #38bdf8;
    }
    .metric-sub {
        font-size: 0.80rem;
        color: #cbd5e1;
        margin-top: 4px;
    }
    .task-card {
        background-color: #111827;
        border-left: 5px solid #38bdf8;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .task-card-done {
        background-color: #0f172a;
        border-left: 5px solid #10b981;
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 10px;
        opacity: 0.78;
    }
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-energy-low { background-color: #064e3b; color: #6ee7b7; }
    .badge-energy-med { background-color: #78350f; color: #fcd34d; }
    .badge-energy-high { background-color: #7f1d1d; color: #fca5a5; }
    .badge-cat { background-color: #1e3a8a; color: #93c5fd; }
    .stProgress > div > div > div > div {
        background-image: linear-gradient(to right, #38bdf8, #818cf8, #c084fc);
    }
</style>
"""
# First paint uses the original dark CUSTOM_CSS (defined above), matching the
# original look. The picker in the sidebar re-injects the selected theme's CSS
# (later injection wins), so switching is instant and no data is lost.
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

DB_PATH = "adhd_life_os.db"

# ==============================================================================
# HAVELOO THEMES — ONE picker, 6 themes. Each theme IS a mood/relief mode:
# its colours AND its behaviour match its purpose. No second "mode" picker.
# Light themes use dark text, dark themes use light text (contrast-checked,
# WCAG >= 4.5 for body text — see VERIFICATION.md). Themes are supportive
# design only: they do not treat anxiety or low mood and are not medical
# advice or a substitute for professional help (note shown under the picker).
# ==============================================================================
THEMES = {
    "Cocoa": {
        "label": "Cocoa — Light",
        "variant": "Light",
        "purpose": "Warm Comfort / Grounding — cozy and grounding for low, heavy days.",
        "bg": "#F7EFE6", "card": "#FFFDF8", "card2": "#F3E7D8",
        "text": "#2E2118", "subtext": "#6B5646",
        "accent": "#8A5A33", "accent2": "#C08552", "border": "#E3D3C0",
        "button_bg": "#8A5A33", "button_text": "#FFFFFF",
        "chart": "plotly_white",
        "behavior": {"top3_prominent": True, "gentle_line": True},
    },
    "Sage": {
        "label": "Sage — Dark",
        "variant": "Dark",
        "purpose": "Calm / Anxiety Relief — low stimulation, slow breathing, gentle wording.",
        "bg": "#1C2A22", "card": "#24382D", "card2": "#2E4636",
        "text": "#EAF3EC", "subtext": "#A9C3B2",
        "accent": "#8FBC9B", "accent2": "#6FA287", "border": "#3A4F43",
        "button_bg": "#8FBC9B", "button_text": "#14231B",
        "chart": "plotly_dark",
        "behavior": {"hide_extras": True, "breathing_cue": True},
    },
    "Apricot": {
        "label": "Apricot — Light",
        "variant": "Light",
        "purpose": "Mood Lift / Gentle Energy — warm and gently energising for low-energy days.",
        "bg": "#FFF1E2", "card": "#FFFDF8", "card2": "#FBE3C8",
        "text": "#33231A", "subtext": "#7A5A44",
        "accent": "#B4501F", "accent2": "#E9A23B", "border": "#F0D3B8",
        "button_bg": "#B4501F", "button_text": "#FFFFFF",
        "chart": "plotly_white",
        "behavior": {"tiny_win": True},
    },
    "Lavender": {
        "label": "Lavender — Light",
        "variant": "Light",
        "purpose": "Relax / Night Rest — soft and soothing for evening wind-down.",
        "bg": "#F2EDFA", "card": "#FFFDFE", "card2": "#E7DEF5",
        "text": "#2C2340", "subtext": "#6E6390",
        "accent": "#6A4FB0", "accent2": "#A78BDB", "border": "#DDD3F0",
        "button_bg": "#6A4FB0", "button_text": "#FFFFFF",
        "chart": "plotly_white",
        "behavior": {"evening_note": True},
    },
    "Ocean": {
        "label": "Ocean — Dark",
        "variant": "Dark",
        "purpose": "Deep Focus — minimal distraction, calmest layout, focus first.",
        "bg": "#0F2233", "card": "#16324A", "card2": "#1C3D59",
        "text": "#E6F0F7", "subtext": "#9DB8CC",
        "accent": "#5FB4D9", "accent2": "#3E8FB5", "border": "#24455E",
        "button_bg": "#5FB4D9", "button_text": "#0A1A26",
        "chart": "plotly_dark",
        "behavior": {"minimal": True},
    },
    "Rosewood": {
        "label": "Rosewood — Light",
        "variant": "Light",
        "purpose": "Reflect / Look Back — kind weekly and monthly review, wins and reflection.",
        "bg": "#F9ECEC", "card": "#FFFDFC", "card2": "#F3DCDC",
        "text": "#33201F", "subtext": "#7A5550",
        "accent": "#8E3B34", "accent2": "#C07A6A", "border": "#EAD0CC",
        "button_bg": "#8E3B34", "button_text": "#FFFFFF",
        "chart": "plotly_white",
        "behavior": {"look_back": True},
    },
}
DEFAULT_THEME = "Sage"  # dark, matches the original app look on first paint


def theme_css(theme_name: str, dyslexia_font: bool = False, large_text: bool = False) -> str:
    """Full per-theme stylesheet. Dark text on light themes, light text on dark
    themes. Dyslexia-friendly font and large-text scaling apply in every theme."""
    t = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    font = "'OpenDyslexic', 'Comic Sans MS', Verdana, sans-serif" if dyslexia_font else "inherit"
    size = "112%" if large_text else "100%"
    return f"""
<style>
    .stApp {{ background-color: {t['bg']}; color: {t['text']}; font-size: {size}; }}
    .stApp, .stMarkdown, p, li, span {{ font-family: {font}; }}
    h1, h2, h3, h4 {{ color: {t['text']}; }}
    .metric-card {{
        background: {t['card']};
        border: 1px solid {t['border']};
        border-radius: 12px;
        padding: 16px 20px;
        color: {t['text']};
        margin-bottom: 12px;
    }}
    .metric-title {{
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: {t['subtext']};
        margin-bottom: 4px;
    }}
    .metric-value {{ font-size: 1.75rem; font-weight: 700; color: {t['accent']}; }}
    .metric-sub {{ font-size: 0.80rem; color: {t['subtext']}; margin-top: 4px; }}
    .task-card {{
        background-color: {t['card']};
        border-left: 5px solid {t['accent']};
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
        color: {t['text']};
    }}
    .task-card-done {{
        background-color: {t['card2']};
        border-left: 5px solid {t['accent2']};
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 10px;
        opacity: 0.85;
        color: {t['text']};
    }}
    .badge {{
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 6px;
    }}
    .badge-energy-low {{ background-color: #064e3b; color: #6ee7b7; }}
    .badge-energy-med {{ background-color: #78350f; color: #fcd34d; }}
    .badge-energy-high {{ background-color: #7f1d1d; color: #fca5a5; }}
    .badge-cat {{ background-color: #1e3a8a; color: #93c5fd; }}
    .stProgress > div > div > div > div {{
        background-image: linear-gradient(to right, {t['accent']}, {t['accent2']});
    }}
    section[data-testid="stSidebar"] {{ background-color: {t['card']}; }}
    section[data-testid="stSidebar"] * {{ color: {t['text']}; }}
    section[data-testid="stSidebar"] .stCaption, section[data-testid="stSidebar"] small {{ color: {t['subtext']}; }}
    div[data-testid="stMetricValue"] {{ color: {t['accent']}; }}
    div[data-testid="stMetricLabel"] {{ color: {t['subtext']}; }}
    .stButton > button {{ background-color: {t['button_bg']}; color: {t['button_text']}; border: 1px solid {t['border']}; }}
    .stButton > button:hover {{ filter: brightness(1.08); color: {t['button_text']}; }}
    .stButton > button:disabled {{ opacity: 0.55; }}
</style>
"""

# Pre-built micro-step templates to bypass executive dysfunction
MICRO_STEP_TEMPLATES = {
    "Custom (Enter my own steps)": [],
    "🧹 Desk / Room Reset (Anti-Doompile)": [
        "Set a 5-minute timer and put on upbeat music",
        "Grab a trash bag and collect ONLY obvious trash",
        "Gather all dishes/cups and put them in the kitchen sink",
        "Put laundry into the hamper (do not fold yet)",
        "Clear one 12-inch square workspace on the desk",
    ],
    "💻 Deep Work / Study Ignition": [
        "Close all unrelated browser tabs and put phone in another room",
        "Open the exact document or codebase needed",
        "Write down ONE tiny deliverable for the next 20 minutes",
        "Set a 25-minute timer and start with the easiest sub-part",
        "Log session and claim Dopamine Coins",
    ],
    "🧾 Bills & Admin Dread Buster": [
        "Open banking/email portal and gather login credentials",
        "List the exact 1-3 items needing payment or reply",
        "Complete the fastest item first for momentum",
        "Automate or calendar-block the remaining item",
        "Reward yourself immediately with an Appetizer from Dopamine Menu",
    ],
    "🧺 Laundry Friction-Breaker": [
        "Dump clothes straight into washer (skip sorting unless delicate)",
        "Add detergent and press Start",
        "Set an alarm on phone labeled 'Move Laundry'",
        "Transfer to dryer as soon as alarm rings",
        "Dump clean clothes onto bed so you fold before sleep",
    ],
}


# ==============================================================================
# 2. DATABASE LAYER & AUTOMATIC DEMO SEEDING
# ==============================================================================
def get_conn() -> sqlite3.Connection:
    """Open the planner database for the current visitor.

    Routed per account (haveloo_auth): a logged-in account gets its own
    private file, so data follows the account to any device. Before login
    (or in free-demo mode) the shared demo file is used. Every one of the
    40+ call sites already goes through this function, so no query changes.
    """
    email = st.session_state.get(auth.SESSION_EMAIL_KEY)
    if email:
        return auth.get_user_conn(email)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
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

    # Seed realistic demo data if database is completely brand new — but
    # ONLY for the shared free-demo file. A logged-in buyer account must
    # start completely EMPTY (2026-11-12 change): no demo tasks, habits,
    # logs, XP or coins. init_db() runs on every Streamlit rerun, and
    # get_conn() routes a logged-in account to its own file, so this
    # check is what keeps buyer files empty while the demo stays seeded.
    task_count = cur.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    energy_count = cur.execute("SELECT COUNT(*) FROM energy_logs").fetchone()[0]
    _is_buyer = bool(st.session_state.get(auth.SESSION_EMAIL_KEY))
    if task_count == 0 and energy_count == 0 and not _is_buyer:
        seed_demo_data(conn)

    conn.close()

def seed_demo_data(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    today = date.today()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # User XP & Coins
    cur.execute(
        "UPDATE user_stats SET xp = 680, coins = 145, last_active_date = ? WHERE id = 1",
        (today.isoformat(),),
    )

    # Seed Tasks (Active Big 3, Next, Parking Lot, and Historical Completed)
    sample_tasks = [
        (
            "Finish Q4 Project Proposal Outline",
            "Work / Study",
            "NOW (Big 3)",
            "High",
            45,
            json.dumps(
                [
                    {"step": "Open blank doc and paste rubric headers", "done": True},
                    {"step": "Bullet-point 3 core goals (messy draft)", "done": True},
                    {"step": "Fill in timeline milestones", "done": False},
                    {"step": "Send draft to teammate for quick sanity check", "done": False},
                ]
            ),
            "Todo",
            80,
            now_str,
            None,
        ),
        (
            "Clear Kitchen Counter & Load Dishwasher",
            "Home / Admin",
            "NOW (Big 3)",
            "Low",
            15,
            json.dumps(
                [
                    {"step": "Put on favorite podcast", "done": True},
                    {"step": "Throw away wrappers & recyclables", "done": False},
                    {"step": "Load mugs and plates into dishwasher", "done": False},
                ]
            ),
            "Todo",
            40,
            now_str,
            None,
        ),
        (
            "15-Min Mobility & Kettlebell Reset",
            "Health",
            "NOW (Big 3)",
            "Medium",
            15,
            json.dumps(
                [
                    {"step": "Put on workout shoes", "done": False},
                    {"step": "Do 3 rounds of swings + goblet squats", "done": False},
                ]
            ),
            "Todo",
            45,
            now_str,
            None,
        ),
        (
            "Organize Tax Receipts Folder",
            "Finance",
            "Next Up",
            "Medium",
            30,
            json.dumps(
                [
                    {"step": "Download last 2 bank PDFs", "done": False},
                    {"step": "Drop into 2026 Tax folder", "done": False},
                ]
            ),
            "Todo",
            55,
            now_str,
            None,
        ),
        (
            "Prototype Sound-Design Loop for Side Project",
            "Creative",
            "Parking Lot",
            "High",
            60,
            json.dumps([{"step": "Load synth patch & record 8 bars", "done": False}]),
            "Todo",
            70,
            now_str,
            None,
        ),
    ]

    # Completed historical tasks across categories for rich Radar & Velocity charts
    completed_history = [
        ("Submit Monthly Expense Report", "Finance", "NOW (Big 3)", "Medium", 30, 60, 1),
        ("Deep Clean Desk & Cable Management", "Home / Admin", "NOW (Big 3)", "Low", 25, 50, 2),
        ("Write Python Data Parser Script", "Work / Study", "NOW (Big 3)", "High", 50, 90, 2),
        ("30-Min Zone 2 Run", "Health", "NOW (Big 3)", "Medium", 30, 50, 3),
        ("Sketch Storyboard Thumbnails", "Creative", "Next Up", "Low", 25, 45, 4),
        ("Refill Prescription & Vitamins", "Health", "NOW (Big 3)", "Low", 10, 35, 5),
        ("Cancel Unused Streaming Subscription", "Finance", "Next Up", "Low", 10, 40, 6),
        ("Prepare Client Slide Deck", "Work / Study", "NOW (Big 3)", "High", 45, 85, 7),
    ]

    cur.executemany(
        """
        INSERT INTO tasks (title, category, priority, energy_req, est_minutes, micro_steps, status, xp_reward, created_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_tasks,
    )

    for title, cat, prio, en, mins, xp, days_ago in completed_history:
        dt = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """
            INSERT INTO tasks (title, category, priority, energy_req, est_minutes, micro_steps, status, xp_reward, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, '[]', 'Done', ?, ?, ?)
            """,
            (title, cat, prio, en, mins, xp, dt, dt),
        )

    # Seed Habits
    habits = [
        ("Take Morning Meds + Full Glass of Water", "Meds & Care", 25),
        ("5-Min Morning Brain Dump & Top 3 Pick", "Morning Launch", 25),
        ("No-Phone First 20 Minutes", "Morning Launch", 20),
        ("Midday Posture, Hydration & Protein Check", "Midday Reset", 20),
        ("Plug Phone Across Room Before Bed", "Evening Wind-Down", 25),
    ]
    cur.executemany("INSERT INTO habits (name, routine, xp_value) VALUES (?, ?, ?)", habits)

    # Seed 14 days of realistic habit logs (with intentional missed days to show Bounce-Back metric)
    habit_ids = [r[0] for r in cur.execute("SELECT id FROM habits").fetchall()]
    for day_offset in range(13, 0, -1):
        d_str = (today - timedelta(days=day_offset)).isoformat()
        for idx, hid in enumerate(habit_ids):
            # Realistic ADHD pattern: high consistency on meds, occasional dip on day 5 & 9, strong bounce-back
            if day_offset in (5, 9) and idx in (2, 4):
                continue
            if day_offset == 6 and idx == 2:
                continue
            cur.execute(
                "INSERT OR IGNORE INTO habit_logs (habit_id, log_date) VALUES (?, ?)",
                (hid, d_str),
            )

    # Seed 14 days of Energy & Focus logs across time blocks
    time_blocks = ["Morning", "Afternoon", "Evening"]
    moods = ["Dialed In", "Steady", "Scattered", "Hyperfocused", "Low Battery"]
    for day_offset in range(13, -1, -1):
        d_str = (today - timedelta(days=day_offset)).isoformat()
        for tb in time_blocks:
            if tb == "Morning":
                en = 7 + (day_offset % 3)
                foc = 8 if day_offset % 4 != 0 else 6
                mood = moods[0] if foc >= 8 else moods[1]
            elif tb == "Afternoon":
                en = 5 + (day_offset % 3)
                foc = 5 + (day_offset % 2)
                mood = moods[2] if foc <= 5 else moods[1]
            else:
                en = 6 + (day_offset % 2)
                foc = 7 if day_offset % 3 == 0 else 5
                mood = moods[3] if foc >= 7 else moods[4]
            cur.execute(
                """
                INSERT INTO energy_logs (log_date, time_block, energy_level, focus_level, mood, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (d_str, tb, min(en, 10), min(foc, 10), mood, ""),
            )

    # Seed Focus Sessions
    focus_seed = [
        ("Python Data Parser Script", 45, 1, 65, 1),
        ("Q4 Proposal Outline", 25, 2, 35, 1),
        ("Monthly Expense Report", 25, 0, 45, 2),
        ("Client Slide Deck", 50, 1, 70, 4),
        ("Reading Technical Docs", 20, 3, 25, 5),
        ("Deep Clean Desk", 25, 0, 40, 6),
        ("Inbox Zero Sprint", 15, 1, 25, 8),
    ]
    for title, mins, dist, xp, days_ago in focus_seed:
        d_str = (today - timedelta(days=days_ago)).isoformat()
        cur.execute(
            """
            INSERT INTO focus_sessions (task_title, duration_minutes, distractions_caught, xp_earned, session_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, mins, dist, xp, d_str),
        )

    # Seed Dopamine Menu
    menu_items = [
        ("10 Jumping Jacks + Cold Water Splash", "Appetizer (5m Free Boost)", 0, 4),
        ("Play 1 Favorite High-BPM Song Loud", "Appetizer (5m Free Boost)", 0, 5),
        ("Step Outside in Sunlight for 5 Mins", "Appetizer (5m Free Boost)", 0, 4),
        ("Brown-Noise / Lo-Fi Beats Headphones", "Side Dish (Body-Double)", 0, 3),
        ("Iced Matcha / Specialty Coffee", "Side Dish (Body-Double)", 15, 4),
        ("20-Min Walk + Audiobook", "Entrée (30m Recharge)", 10, 5),
        ("Guilt-Free Gaming / Episode Block (45m)", "Dessert (Coin Reward)", 60, 5),
        ("Order Takeout Instead of Cooking", "Dessert (Coin Reward)", 120, 4),
    ]
    cur.executemany(
        "INSERT INTO dopamine_menu (item_name, course, cost_coins, energy_boost) VALUES (?, ?, ?, ?)",
        menu_items,
    )

    # Seed Impulse-Buy Vault
    impulse_items = [
        (
            "Mechanical Keyboard Keycap Set",
            89.00,
            "Tech / Desk",
            8,
            (datetime.now() - timedelta(hours=60)).strftime("%Y-%m-%d %H:%M:%S"),
            48,
            "Resisted & Saved",
        ),
        (
            "LED Galaxy Projector Lamp",
            45.00,
            "Home Decor",
            7,
            (datetime.now() - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S"),
            48,
            "Resisted & Saved",
        ),
        (
            "Noise-Canceling Earbuds Upgrade",
            149.00,
            "Tech / Desk",
            9,
            (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d %H:%M:%S"),
            48,
            "Cooling Off",
        ),
    ]
    cur.executemany(
        """
        INSERT INTO impulse_vault (item_name, price, category, urge_level, added_at, cooldown_hours, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        impulse_items,
    )

    # Seed Brain Dump
    dumps = [
        ("Look up ergonomic footrest before back hurts again", "Shopping / Research", now_str, 0),
        ("Text Alex back about Friday dinner", "Social", now_str, 0),
        ("Idea: Automate weekly invoice PDF naming", "Work / Automation", now_str, 0),
    ]
    cur.executemany(
        "INSERT INTO brain_dump (thought, tag, created_at, triaged) VALUES (?, ?, ?, ?)",
        dumps,
    )

    conn.commit()


def reset_database(reseed: bool = False) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(
        """
        DELETE FROM tasks;
        DELETE FROM habits;
        DELETE FROM habit_logs;
        DELETE FROM energy_logs;
        DELETE FROM focus_sessions;
        DELETE FROM dopamine_menu;
        DELETE FROM impulse_vault;
        DELETE FROM brain_dump;
        DELETE FROM people;
        DELETE FROM household_tasks;
        DELETE FROM home_inventory;
        DELETE FROM learn_items;
        DELETE FROM trips;
        DELETE FROM career_items;
        DELETE FROM goals_board;
        DELETE FROM money_extra;
        DELETE FROM recipes;
        DELETE FROM grocery_items;
        DELETE FROM meal_plan;
        DELETE FROM countdowns;
        DELETE FROM weekly_resets;
        DELETE FROM onboarding;
        DELETE FROM wellness_log;
        DELETE FROM cycle_log;
        DELETE FROM sos_log;
        DELETE FROM subscriptions;
        DELETE FROM impulse_waitlist;
        DELETE FROM bills;
        DELETE FROM voice_notes;
        DELETE FROM focus_sounds;
        DELETE FROM user_prefs WHERE key IN ('focus_sound', 'hyperfocus_guard', 'reminder_hooks');
        UPDATE user_stats SET xp = 0, coins = 0, last_active_date = NULL WHERE id = 1;
        """
    )
    conn.commit()
    if reseed:
        # Demo restore only. The "Load Demo Data" button is shown in demo
        # mode only (see the sidebar), so a buyer can never refill their
        # own planner with sample data. Restores the full demo: base +
        # hub + advance seed data.
        seed_demo_data(conn)
        hubs.seed_hubs(conn)
        adv.seed_advance(conn)
    conn.close()


# ==============================================================================
# 3. GAMIFICATION & BEHAVIORAL METRICS HELPERS
# ==============================================================================
def award_xp_and_coins(xp_delta: int, coin_delta: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE user_stats
        SET xp = MAX(0, xp + ?),
            coins = MAX(0, coins + ?),
            last_active_date = ?
        WHERE id = 1
        """,
        (xp_delta, coin_delta, date.today().isoformat()),
    )
    conn.commit()
    conn.close()


def get_user_stats() -> dict:
    conn = get_conn()
    row = conn.execute("SELECT xp, coins, last_active_date FROM user_stats WHERE id = 1").fetchone()
    conn.close()
    xp = row["xp"] if row else 0
    coins = row["coins"] if row else 0
    level = 1 + (xp // 250)
    xp_in_level = xp % 250
    return {
        "xp": xp,
        "coins": coins,
        "level": level,
        "xp_in_level": xp_in_level,
        "xp_for_next": 250,
    }


def get_pref(key: str, default: str) -> str:
    """Read a saved per-user preference (theme, text options). Falls back to
    default when nothing is stored yet. The auth module later scopes these
    per account; for now they are stored once per database."""
    try:
        conn = get_conn()
        row = conn.execute("SELECT value FROM user_prefs WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception:
        return default


def set_pref(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO user_prefs (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def calculate_bounce_back_score() -> tuple[float, float]:
    """
    Calculates:
    1) 14-day overall habit consistency (%)
    2) Bounce-Back Rate (% of missed habit-days followed by a completed check-in the very next day)
    """
    conn = get_conn()
    habits = pd.read_sql_query("SELECT id FROM habits", conn)
    logs = pd.read_sql_query("SELECT habit_id, log_date FROM habit_logs", conn)
    conn.close()

    if habits.empty:
        return 0.0, 100.0

    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    log_set = set(zip(logs["habit_id"], logs["log_date"])) if not logs.empty else set()

    total_slots = len(habits) * len(days)
    completed_slots = sum(1 for hid in habits["id"] for d in days if (hid, d) in log_set)
    consistency = (completed_slots / total_slots * 100) if total_slots > 0 else 0.0

    misses = 0
    recoveries = 0
    for hid in habits["id"]:
        for i in range(len(days) - 1):
            if (hid, days[i]) not in log_set:
                misses += 1
                if (hid, days[i + 1]) in log_set:
                    recoveries += 1

    bounce_back = (recoveries / misses * 100) if misses > 0 else 100.0
    return round(consistency, 1), round(bounce_back, 1)


# ==============================================================================
# 4. INITIALIZE APP & SIDEBAR HUD
# ==============================================================================
init_db()

# --- Tier 1 hub tables (haveloo_hubs) ---
# Demo mode: full demo seed. Logged-in buyer: structural defaults only
# (onboarding tour/checklist keys) — the buyer starts with empty hubs.
_hub_conn = get_conn()
hubs.init_hub_tables(_hub_conn)
if st.session_state.get(auth.SESSION_EMAIL_KEY):
    hubs.seed_hub_defaults(_hub_conn)
else:
    hubs.seed_hubs(_hub_conn)
_hub_conn.close()

# --- Tier 2 advance tables (haveloo_advance) ---
# Demo mode: full demo seed. Logged-in buyer: focus-sound catalogue only.
_adv_conn = get_conn()
adv.init_advance_tables(_adv_conn)
if st.session_state.get(auth.SESSION_EMAIL_KEY):
    adv.seed_advance_defaults(_adv_conn)
else:
    adv.seed_advance(_adv_conn)
_adv_conn.close()

# --- Haveloo accounts: the gate runs BEFORE any planner data renders. ---
# Not logged in (and not in free demo) -> only the gate is shown.
_auth_conn = auth.open_connection()
auth.init_auth_tables(_auth_conn)
if not auth.render_auth_gate(st, _auth_conn):
    st.stop()
auth.render_demo_banner(st)

if "timer_running" not in st.session_state:
    st.session_state.timer_running = False
if "timer_end_ts" not in st.session_state:
    st.session_state.timer_end_ts = None
if "timer_duration" not in st.session_state:
    st.session_state.timer_duration = 25
if "timer_task" not in st.session_state:
    st.session_state.timer_task = "Deep Focus Sprint"
if "distractions_count" not in st.session_state:
    st.session_state.distractions_count = 0

stats = get_user_stats()
consistency_pct, bounce_back_pct = calculate_bounce_back_score()

# Load saved theme + text options (persisted per user in user_prefs).
if "haveloo_theme" not in st.session_state:
    _saved_theme = get_pref("theme", DEFAULT_THEME)
    st.session_state["haveloo_theme"] = _saved_theme if _saved_theme in THEMES else DEFAULT_THEME
if "dyslexia_font" not in st.session_state:
    st.session_state["dyslexia_font"] = get_pref("dyslexia_font", "0") == "1"
if "large_text" not in st.session_state:
    st.session_state["large_text"] = get_pref("large_text", "0") == "1"

with st.sidebar:
    st.title("🧠 ADHD Life OS")
    st.caption("Neuro-Adaptive Execution & Dopamine Engine")

    # ---- ONE theme picker: each theme IS a mood (colours + behaviour) ----
    st.subheader("🎨 Theme — how do you want to feel?")
    st.caption("One picker. Each theme's colours and behaviour match its purpose.")
    picked_theme = st.radio(
        "Theme",
        options=list(THEMES.keys()),
        index=list(THEMES.keys()).index(st.session_state.get("haveloo_theme", DEFAULT_THEME)),
        format_func=lambda k: f"{THEMES[k]['label']} · {THEMES[k]['purpose'].split(' — ')[0]}",
        key="theme_radio",
        label_visibility="collapsed",
    )
    if picked_theme != st.session_state.get("haveloo_theme", DEFAULT_THEME):
        st.session_state["haveloo_theme"] = picked_theme
        set_pref("theme", picked_theme)
        st.rerun()
    st.caption(THEMES[picked_theme]["purpose"])
    st.caption(
        "Themes are supportive design only — they don't treat anxiety or low mood, "
        "and aren't medical advice or a substitute for professional help."
    )

    # ---- Text & reading options (work in every theme) ----
    dys_new = st.checkbox(
        "Dyslexia-friendly font", value=st.session_state.get("dyslexia_font", False),
        key="dyslexia_chk",
    )
    if dys_new != st.session_state.get("dyslexia_font", False):
        st.session_state["dyslexia_font"] = dys_new
        set_pref("dyslexia_font", "1" if dys_new else "0")
        st.rerun()
    large_new = st.checkbox(
        "Large text", value=st.session_state.get("large_text", False), key="large_text_chk",
    )
    if large_new != st.session_state.get("large_text", False):
        st.session_state["large_text"] = large_new
        set_pref("large_text", "1" if large_new else "0")
        st.rerun()

    # ---- Per-theme sidebar moments (real behaviour, not labels) ----
    if picked_theme == "Sage":
        st.info("🌿 **Slow breath:** in for 4… hold for 4… out for 6. One small step is enough.")
    elif picked_theme == "Cocoa":
        st.info("🤎 **Gentle start:** just today's top 3. The rest can wait.")
    elif picked_theme == "Lavender":
        st.info("🌙 **Evening wind-down:** soft light, slow pace. Tomorrow's list will keep.")

    st.divider()

    # Level & XP Progress
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">Neuro-Level & XP</div>
            <div class="metric-value">Level {stats['level']}</div>
            <div class="metric-sub">{stats['xp']} Total XP • {stats['xp_in_level']}/{stats['xp_for_next']} to Level {stats['level'] + 1}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(stats["xp_in_level"] / stats["xp_for_next"])

    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        st.metric("🪙 Dopamine Coins", stats["coins"])
    with col_sb2:
        st.metric("🔄 Bounce-Back", f"{bounce_back_pct}%")

    st.divider()

    if picked_theme != "Ocean":
        # Rapid Brain Dump Capture (Always accessible from any screen)
        st.subheader("⚡ Quick Brain Dump")
        st.caption("Offload intrusive thoughts instantly so you stay on task.")
        with st.form("sidebar_brain_dump_form", clear_on_submit=True):
            quick_thought = st.text_input("What popped into your head?", placeholder="e.g., Buy dog food, reply to Sarah...")
            quick_tag = st.selectbox(
                "Tag",
                ["Task Idea", "Shopping / Research", "Social", "Work / Automation", "Random"],
            )
            submitted_dump = st.form_submit_button("Capture Thought (+5 XP)", use_container_width=True)
            if submitted_dump and quick_thought.strip():
                conn = get_conn()
                conn.execute(
                    "INSERT INTO brain_dump (thought, tag, created_at, triaged) VALUES (?, ?, ?, 0)",
                    (quick_thought.strip(), quick_tag, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                conn.commit()
                conn.close()
                award_xp_and_coins(5, 2)
                st.toast("Captured to Brain Dump! +5 XP", icon="⚡")
                st.rerun()

    st.divider()

    if picked_theme != "Ocean":
        # Daily Energy & Focus Pulse Check-In
        st.subheader("🔋 Quick Energy Check-In")
        with st.form("sidebar_energy_form", clear_on_submit=True):
            tb_now = st.selectbox("Time Block", ["Morning", "Afternoon", "Evening"])
            en_val = st.slider("Energy Level", 1, 10, 7)
            foc_val = st.slider("Focus Clarity", 1, 10, 6)
            mood_val = st.selectbox("Current State", ["Dialed In", "Steady", "Scattered", "Hyperfocused", "Low Battery"])
            if st.form_submit_button("Log State (+10 XP)", use_container_width=True):
                conn = get_conn()
                conn.execute(
                    """
                    INSERT INTO energy_logs (log_date, time_block, energy_level, focus_level, mood, note)
                    VALUES (?, ?, ?, ?, ?, '')
                    """,
                    (date.today().isoformat(), tb_now, en_val, foc_val, mood_val),
                )
                conn.commit()
                conn.close()
                award_xp_and_coins(10, 5)
                st.toast("Energy & Focus logged! +10 XP", icon="🔋")
                st.rerun()

    st.divider()
    if picked_theme not in ("Ocean", "Sage"):
        with st.expander("⚙️ Database & Demo Controls"):
            st.caption("Start with a clean slate or restore sample analytics data.")
            c_rst1, c_rst2 = st.columns(2)
            if c_rst1.button("Clear All Data", use_container_width=True):
                reset_database(reseed=False)
                st.rerun()
            # "Load Demo Data" is demo-mode only: a buyer account must
            # never be able to refill their own planner with sample data.
            if not st.session_state.get(auth.SESSION_EMAIL_KEY):
                if c_rst2.button("Load Demo Data", use_container_width=True):
                    reset_database(reseed=True)
                    st.rerun()
            else:
                c_rst2.caption("Demo data is only available in the free demo.")


# Apply the selected theme now (this injection overrides the first-paint
# Sage CSS above), so switching is instant and no data is lost.
CURRENT_THEME = st.session_state.get("haveloo_theme", DEFAULT_THEME)
THEME = THEMES[CURRENT_THEME]
PLOTLY_TEMPLATE = THEME["chart"]
st.markdown(
    theme_css(
        CURRENT_THEME,
        st.session_state.get("dyslexia_font", False),
        st.session_state.get("large_text", False),
    ),
    unsafe_allow_html=True,
)


# ==============================================================================
# 5. MAIN NAVIGATION TABS
# ==============================================================================
tabs = st.tabs(
    [
        "🎯 Command Center",
        "⏱️ Focus & Time-Blindness",
        "🍨 Dopamine Menu",
        "🌱 Zero-Guilt Habits",
        "🛡️ Impulse-Buy Vault",
        "📥 Brain Dump Triage",
        "📊 Executive Analytics",
        "👥 People",
        "🏠 Household",
        "📚 Learn",
        "🌍 Explore",
        "💼 Career",
        "🧠 Smart Planner",
        "🎙️ Voice & Focus Pro",
        "🆘 SOS & Daily Care",
        "💳 Money Guard",
        "🖨️ Print & Backup",
    ]
)


# ------------------------------------------------------------------------------
# TAB 1: COMMAND CENTER (RULE OF 3 + MICRO-STEP SPLITTER)
# ------------------------------------------------------------------------------
with tabs[0]:
    st.header("🎯 Today's Command Center")
    st.caption(
        "Anti-Paralysis Design: Keep a maximum of **3 active tasks** in 'NOW (Big 3)'. "
        "Break daunting tasks into 2-minute micro-steps."
    )

    # ---- First-run guided tour + setup checklist (Haveloo hubs) ----
    hubs.render_guided_tour(st)
    hubs.render_onboarding_checklist(st)

    conn = get_conn()
    tasks_df = pd.read_sql_query("SELECT * FROM tasks ORDER BY id DESC", conn)
    conn.close()

    todo_df = tasks_df[tasks_df["status"] == "Todo"]
    done_df = tasks_df[tasks_df["status"] == "Done"]
    now_tasks = todo_df[todo_df["priority"] == "NOW (Big 3)"]
    next_tasks = todo_df[todo_df["priority"] == "Next Up"]
    parking_tasks = todo_df[todo_df["priority"] == "Parking Lot"]

    # Top KPI Strip
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔥 NOW (Big 3 Slots)", f"{len(now_tasks)} / 3", delta="Optimal Load" if len(now_tasks) <= 3 else "Overloaded!")
    k2.metric("📋 Queued (Next / Parking)", len(next_tasks) + len(parking_tasks))
    k3.metric("✅ Completed Tasks", len(done_df))
    k4.metric("⚡ Available XP Pool", f"{int(todo_df['xp_reward'].sum())} XP")

    if len(now_tasks) > 3:
        st.warning(
            "⚠️ **Overwhelm Alert:** You have more than 3 tasks in **NOW (Big 3)**. "
            "Demote extra tasks to 'Next Up' to protect your working memory."
        )

    # ---- Theme behaviour in the Command Center (real, from live data) ----
    if CURRENT_THEME == "Apricot":
        _win = done_df.iloc[0]["title"] if not done_df.empty else None
        _step = None
        if not now_tasks.empty:
            _s = json.loads(now_tasks.iloc[0]["micro_steps"]) if now_tasks.iloc[0]["micro_steps"] else []
            _step = next((s["step"] for s in _s if not s.get("done")), None)
        _win_txt = f"🏆 One tiny win already: {_win}." if _win else "🏆 One tiny win: you opened this planner — that counts."
        st.success(_win_txt + (f"  👉 One tiny step now: {_step}" if _step else ""))
    if CURRENT_THEME == "Rosewood":
        _week_ago = (date.today() - timedelta(days=7)).isoformat()
        _done_week = done_df[done_df["completed_at"].fillna("") >= _week_ago] if not done_df.empty else done_df
        st.info(
            f"🌹 **This week so far:** {len(_done_week)} tasks finished this week • "
            f"{len(done_df)} total done • kind, never judgy — small steps count."
        )
    if CURRENT_THEME == "Ocean":
        _active = now_tasks.iloc[0]["title"] if not now_tasks.empty else "No active task yet"
        st.info(
            f"🌊 **Deep Focus:** only your Big 3 is showing. Right now: **{_active}**. "
            "Start a sprint in the Focus tab when ready."
        )

    # ---- Fill My Day (rule-based, from live energy + free minutes) ----
    _fmd_conn = get_conn()
    hubs.render_fill_my_day(st, _fmd_conn)
    _fmd_conn.close()

    col_left, col_right = st.columns([1.45, 1.0], gap="large")

    with col_left:
        st.subheader("🔥 Active Focus: NOW (Big 3)")
        if now_tasks.empty:
            st.info("Your Big 3 is clear! Promote a task from 'Next Up' or add a new micro-stepped task.")
        else:
            for _, row in now_tasks.iterrows():
                steps = json.loads(row["micro_steps"]) if row["micro_steps"] else []
                done_steps = sum(1 for s in steps if s.get("done"))
                total_steps = len(steps)
                pct = int((done_steps / total_steps) * 100) if total_steps > 0 else 0

                energy_badge_cls = (
                    "badge-energy-low"
                    if row["energy_req"] == "Low"
                    else ("badge-energy-med" if row["energy_req"] == "Medium" else "badge-energy-high")
                )

                with st.container(border=True):
                    top_r1, top_r2 = st.columns([3.5, 1.5])
                    with top_r1:
                        st.markdown(f"#### {row['title']}")
                        st.markdown(
                            f"<span class='badge badge-cat'>{row['category']}</span>"
                            f"<span class='badge {energy_badge_cls}'>⚡ {row['energy_req']} Energy</span>"
                            f"<span class='badge' style='background:#312e81;color:#c7d2fe;'>⏱️ {row['est_minutes']}m • +{row['xp_reward']} XP</span>",
                            unsafe_allow_html=True,
                        )
                    with top_r2:
                        if st.button("✅ Complete", key=f"complete_now_{row['id']}", type="primary", use_container_width=True):
                            conn = get_conn()
                            conn.execute(
                                "UPDATE tasks SET status = 'Done', completed_at = ? WHERE id = ?",
                                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(row["id"])),
                            )
                            conn.commit()
                            conn.close()
                            coins_earned = max(10, int(row["xp_reward"] // 2))
                            award_xp_and_coins(int(row["xp_reward"]), coins_earned)
                            st.balloons()
                            st.toast(f"Task crushed! +{row['xp_reward']} XP & +{coins_earned} Coins!", icon="🎉")
                            st.rerun()

                        if st.button("⬇️ Defer to Next", key=f"defer_{row['id']}", use_container_width=True):
                            conn = get_conn()
                            conn.execute("UPDATE tasks SET priority = 'Next Up' WHERE id = ?", (int(row["id"]),))
                            conn.commit()
                            conn.close()
                            st.rerun()

                    # Interactive Micro-Steps Checklist
                    if steps:
                        st.progress(pct / 100.0, text=f"Micro-Step Momentum: {done_steps}/{total_steps} ({pct}%)")
                        updated_steps = []
                        changed = False
                        for s_idx, s_obj in enumerate(steps):
                            checked = st.checkbox(
                                s_obj["step"],
                                value=bool(s_obj.get("done", False)),
                                key=f"step_{row['id']}_{s_idx}",
                            )
                            if checked != bool(s_obj.get("done", False)):
                                changed = True
                                if checked:
                                    award_xp_and_coins(5, 2)
                                    st.toast("Micro-step done! +5 XP", icon="✨")
                            updated_steps.append({"step": s_obj["step"], "done": checked})

                        if changed:
                            conn = get_conn()
                            conn.execute(
                                "UPDATE tasks SET micro_steps = ? WHERE id = ?",
                                (json.dumps(updated_steps), int(row["id"])),
                            )
                            conn.commit()
                            conn.close()
                            st.rerun()

        st.divider()
        if CURRENT_THEME != "Ocean":
            st.subheader("📋 Next Up & Parking Lot")
            queued_df = todo_df[todo_df["priority"] != "NOW (Big 3)"]
            if queued_df.empty:
                st.caption("No tasks waiting in queue.")
            else:
                for _, q_row in queued_df.iterrows():
                    qc1, qc2, qc3 = st.columns([3.5, 1.2, 0.8])
                    qc1.markdown(
                        f"**{q_row['title']}**  \n"
                        f"<small>{q_row['priority']} • {q_row['category']} • {q_row['energy_req']} Energy • {q_row['est_minutes']}m</small>",
                        unsafe_allow_html=True,
                    )
                    if qc2.button("🔥 Move to NOW", key=f"promote_{q_row['id']}", use_container_width=True):
                        conn = get_conn()
                        conn.execute("UPDATE tasks SET priority = 'NOW (Big 3)' WHERE id = ?", (int(q_row["id"]),))
                        conn.commit()
                        conn.close()
                        st.rerun()
                    if qc3.button("🗑️", key=f"del_task_{q_row['id']}", use_container_width=True):
                        conn = get_conn()
                        conn.execute("DELETE FROM tasks WHERE id = ?", (int(q_row["id"]),))
                        conn.commit()
                        conn.close()
                        st.rerun()

    with col_right:
        st.subheader("🧩 Task + Micro-Step Creator")
        st.caption("Use an ADHD Ignition Template or write tiny 2-minute steps.")

        selected_template = st.selectbox("Auto-Split Template", list(MICRO_STEP_TEMPLATES.keys()))
        default_steps_text = "\n".join(MICRO_STEP_TEMPLATES[selected_template])

        with st.form("create_task_form", clear_on_submit=True):
            new_title = st.text_input("Task Name", placeholder="e.g., Clean off dining table")
            c_t1, c_t2 = st.columns(2)
            new_cat = c_t1.selectbox(
                "Life Domain",
                ["Work / Study", "Health", "Home / Admin", "Creative", "Finance"],
            )
            new_prio = c_t2.selectbox(
                "Priority Bucket",
                ["NOW (Big 3)" if len(now_tasks) < 3 else "Next Up", "NOW (Big 3)", "Next Up", "Parking Lot"],
            )
            c_t3, c_t4 = st.columns(2)
            new_energy = c_t3.selectbox("Energy Required", ["Low", "Medium", "High"])
            new_mins = c_t4.number_input("Est. Minutes", min_value=5, max_value=240, value=25, step=5)

            steps_raw = st.text_area(
                "Micro-Steps (one tiny action per line)",
                value=default_steps_text,
                height=130,
                placeholder="Step 1: Open laptop\nStep 2: Write 3 bullet points...",
            )
            xp_calc = min(150, max(25, int(new_mins * 1.5)))
            submitted_task = st.form_submit_button(f"➕ Add Task (+{xp_calc} XP on completion)", type="primary", use_container_width=True)

            if submitted_task and new_title.strip():
                step_lines = [line.strip() for line in steps_raw.splitlines() if line.strip()]
                steps_json = json.dumps([{"step": s, "done": False} for s in step_lines])
                conn = get_conn()
                conn.execute(
                    """
                    INSERT INTO tasks (title, category, priority, energy_req, est_minutes, micro_steps, status, xp_reward, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'Todo', ?, ?)
                    """,
                    (
                        new_title.strip(),
                        new_cat,
                        new_prio,
                        new_energy,
                        int(new_mins),
                        steps_json,
                        xp_calc,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                conn.commit()
                conn.close()
                st.toast("Task added with micro-steps!", icon="🧩")
                st.rerun()

        if CURRENT_THEME != "Sage":
            with st.expander(f"🏆 Recently Completed ({len(done_df)})"):
                if done_df.empty:
                    st.caption("Complete a task to see your trophy log.")
                else:
                    for _, d_row in done_df.head(8).iterrows():
                        st.markdown(f"✅ ~~{d_row['title']}~~ *(+{d_row['xp_reward']} XP • {d_row['category']})*")

    # ---- Countdowns + Weekly Reset (Haveloo hubs) ----
    _cd_conn = get_conn()
    hubs.render_countdowns_weekly_reset(st, _cd_conn)
    _cd_conn.close()


    # ------------------------------------------------------------------------------
# TAB 2: TIME-BLINDNESS & FOCUS STUDIO
# ------------------------------------------------------------------------------
with tabs[1]:
    st.header("⏱️ Time-Blindness & Body-Double Focus Studio")
    st.caption(
        "Combat time-blindness with visual countdowns, the **5-Minute 'Just Start' Rule**, "
        "and a non-judgmental **Distraction Catcher**."
    )

    f_col1, f_col2 = st.columns([1.2, 1.0], gap="large")

    with f_col1:
        with st.container(border=True):
            st.subheader("🎯 Configure Focus Sprint")
            active_titles = now_tasks["title"].tolist() if not now_tasks.empty else []
            task_choice = st.selectbox(
                "Target Task",
                active_titles + ["Custom Focus Sprint", "Inbox & Admin Clear"],
            )
            if task_choice == "Custom Focus Sprint":
                task_choice = st.text_input("Custom Sprint Label", value="Deep Work Block")

            preset_cols = st.columns(4)
            if preset_cols[0].button("⚡ 5m Just Start", use_container_width=True):
                st.session_state.timer_duration = 5
            if preset_cols[1].button("🌱 15m Mini", use_container_width=True):
                st.session_state.timer_duration = 15
            if preset_cols[2].button("🍅 25m Pomodoro", use_container_width=True):
                st.session_state.timer_duration = 25
            if preset_cols[3].button("🔥 45m Hyperfocus", use_container_width=True):
                st.session_state.timer_duration = 45

            duration_mins = st.slider(
                "Sprint Length (Minutes)",
                min_value=5,
                max_value=90,
                value=int(st.session_state.timer_duration),
                step=5,
            )
            st.session_state.timer_duration = duration_mins

            b_start, b_stop, b_log = st.columns(3)
            if b_start.button("▶️ Start Visual Timer", type="primary", use_container_width=True):
                st.session_state.timer_running = True
                st.session_state.timer_end_ts = time.time() + (duration_mins * 60)
                st.session_state.timer_task = task_choice
                st.session_state.distractions_count = 0
                st.rerun()

            if b_stop.button("⏹️ Reset Timer", use_container_width=True):
                st.session_state.timer_running = False
                st.session_state.timer_end_ts = None
                st.rerun()

            if b_log.button("💾 Log Completed Sprint", use_container_width=True):
                xp_sprint = max(15, int(duration_mins * 1.5))
                coins_sprint = max(5, duration_mins // 3)
                conn = get_conn()
                conn.execute(
                    """
                    INSERT INTO focus_sessions (task_title, duration_minutes, distractions_caught, xp_earned, session_date)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        task_choice,
                        int(duration_mins),
                        int(st.session_state.distractions_count),
                        xp_sprint,
                        date.today().isoformat(),
                    ),
                )
                conn.commit()
                conn.close()
                award_xp_and_coins(xp_sprint, coins_sprint)
                st.session_state.timer_running = False
                st.session_state.distractions_count = 0
                st.balloons()
                st.toast(f"Focus session logged! +{xp_sprint} XP & +{coins_sprint} Coins", icon="🔥")
                st.rerun()

        # Live Timer Display & Distraction Catcher
        if st.session_state.timer_running and st.session_state.timer_end_ts:
            remaining = max(0, int(st.session_state.timer_end_ts - time.time()))
            mins_left = remaining // 60
            secs_left = remaining % 60
            total_secs = st.session_state.timer_duration * 60
            elapsed_pct = min(1.0, max(0.0, (total_secs - remaining) / max(1, total_secs)))

            st.markdown(
                f"""
                <div class="metric-card" style="text-align:center;">
                    <div class="metric-title">ACTIVE SPRINT: {st.session_state.timer_task}</div>
                    <div class="metric-value" style="font-size:3rem;">{mins_left:02d}:{secs_left:02d}</div>
                    <div class="metric-sub">Distractions Caught & Redirected: {st.session_state.distractions_count}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.progress(elapsed_pct)

            dc1, dc2 = st.columns(2)
            if dc1.button("🐿️ Squirrel! (Log Distraction & Refocus)", use_container_width=True):
                st.session_state.distractions_count += 1
                st.toast("Distraction noticed without judgment! Back to your sprint.", icon="🐿️")
                st.rerun()
            if dc2.button("🔄 Refresh Clock", use_container_width=True):
                st.rerun()

    with f_col2:
        st.subheader("📜 Recent Focus Sprints")
        conn = get_conn()
        sessions_df = pd.read_sql_query("SELECT * FROM focus_sessions ORDER BY id DESC LIMIT 12", conn)
        conn.close()

        if sessions_df.empty:
            st.info("No focus sessions logged yet. Start a 5-minute sprint!")
        else:
            total_focus_mins = int(sessions_df["duration_minutes"].sum())
            avg_dist = round(sessions_df["distractions_caught"].mean(), 1)
            m1, m2 = st.columns(2)
            m1.metric("Recent Focus Minutes", f"{total_focus_mins} min")
            m2.metric("Avg Distractions / Sprint", avg_dist)
            st.dataframe(
                sessions_df[["session_date", "task_title", "duration_minutes", "distractions_caught", "xp_earned"]].rename(
                    columns={
                        "session_date": "Date",
                        "task_title": "Task",
                        "duration_minutes": "Mins",
                        "distractions_caught": "Distractions",
                        "xp_earned": "XP",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )


# ------------------------------------------------------------------------------
# TAB 3: DOPAMINE MENU & REWARD SHOP
# ------------------------------------------------------------------------------
with tabs[2]:
    st.header("🍨 Dopamine Menu & Guilt-Free Reward Shop")
    st.caption(
        "When your brain is starved of stimulation, don't doomscroll—pick a healthy **Appetizer** "
        "for a quick neurological boost, or cash in your earned **Dopamine Coins** for **Desserts**."
    )

    conn = get_conn()
    menu_df = pd.read_sql_query("SELECT * FROM dopamine_menu ORDER BY cost_coins ASC", conn)
    conn.close()

    dm_col1, dm_col2 = st.columns([1.6, 1.0], gap="large")

    with dm_col1:
        course_filter = st.radio(
            "Filter by Stimulation Course",
            [
                "All Courses",
                "Appetizer (5m Free Boost)",
                "Side Dish (Body-Double)",
                "Entrée (30m Recharge)",
                "Dessert (Coin Reward)",
            ],
            horizontal=True,
        )

        filtered_menu = menu_df if course_filter == "All Courses" else menu_df[menu_df["course"] == course_filter]

        for _, item in filtered_menu.iterrows():
            with st.container(border=True):
                mc1, mc2, mc3 = st.columns([3.2, 1.2, 1.2])
                mc1.markdown(
                    f"**{item['item_name']}**  \n"
                    f"<small>{item['course']} • ⚡ Boost Rating: {'⭐' * int(item['energy_boost'])}</small>",
                    unsafe_allow_html=True,
                )
                cost = int(item["cost_coins"])
                mc2.markdown(f"**{'FREE' if cost == 0 else f'🪙 {cost} Coins'}**")

                btn_label = "⚡ Activate" if cost == 0 else "🎁 Redeem"
                disabled = stats["coins"] < cost
                if mc3.button(btn_label, key=f"redeem_{item['id']}", disabled=disabled, use_container_width=True):
                    if cost > 0:
                        award_xp_and_coins(0, -cost)
                        st.toast(f"Redeemed '{item['item_name']}' for {cost} Coins! Enjoy guilt-free!", icon="🍨")
                    else:
                        award_xp_and_coins(5, 0)
                        st.toast(f"Activated '{item['item_name']}'! +5 XP for healthy regulation!", icon="⚡")
                    st.rerun()

    with dm_col2:
        st.subheader("➕ Add Custom Dopamine Item")
        with st.form("add_dopamine_form", clear_on_submit=True):
            d_name = st.text_input("Activity or Reward", placeholder="e.g., 15-min Lego build, Fancy latte")
            d_course = st.selectbox(
                "Menu Course",
                [
                    "Appetizer (5m Free Boost)",
                    "Side Dish (Body-Double)",
                    "Entrée (30m Recharge)",
                    "Dessert (Coin Reward)",
                ],
            )
            d_cost = st.number_input("Coin Cost (0 for healthy free boosters)", min_value=0, max_value=500, value=0, step=5)
            d_boost = st.slider("Dopamine Boost Strength", 1, 5, 4)
            if st.form_submit_button("Save to Menu", type="primary", use_container_width=True):
                if d_name.strip():
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO dopamine_menu (item_name, course, cost_coins, energy_boost) VALUES (?, ?, ?, ?)",
                        (d_name.strip(), d_course, int(d_cost), int(d_boost)),
                    )
                    conn.commit()
                    conn.close()
                    st.toast("Added to your Dopamine Menu!", icon="🍨")
                    st.rerun()


# ------------------------------------------------------------------------------
# TAB 4: ZERO-GUILT HABITS & ROUTINES
# ------------------------------------------------------------------------------
with tabs[3]:
    st.header("🌱 Zero-Guilt Habits & Meds Anchor")
    st.caption(
        "Traditional streak trackers trigger 'all-or-nothing' shame when you miss one day. "
        "We measure **Bounce-Back Resilience**—how reliably you return after an off day."
    )

    h_kpi1, h_kpi2, h_kpi3 = st.columns(3)
    h_kpi1.metric("14-Day Routine Consistency", f"{consistency_pct}%")
    h_kpi2.metric("🔄 Bounce-Back Resilience", f"{bounce_back_pct}%", delta="Resets Shame")
    h_kpi3.metric("Today's Date", date.today().strftime("%b %d, %Y"))

    conn = get_conn()
    habits_df = pd.read_sql_query("SELECT * FROM habits ORDER BY routine, id", conn)
    today_iso = date.today().isoformat()
    today_logs = set(
        r[0]
        for r in conn.execute("SELECT habit_id FROM habit_logs WHERE log_date = ?", (today_iso,)).fetchall()
    )
    conn.close()

    hb_col1, hb_col2 = st.columns([1.6, 1.0], gap="large")

    with hb_col1:
        routines = ["Meds & Care", "Morning Launch", "Midday Reset", "Evening Wind-Down"]
        for routine in routines:
            r_habits = habits_df[habits_df["routine"] == routine]
            if r_habits.empty:
                continue
            st.subheader(f"✨ {routine}")
            for _, h_row in r_habits.iterrows():
                hid = int(h_row["id"])
                is_done = hid in today_logs
                hc1, hc2, hc3 = st.columns([3.5, 1.2, 0.6])
                checked = hc1.checkbox(
                    f"{h_row['name']} (+{h_row['xp_value']} XP)",
                    value=is_done,
                    key=f"habit_chk_{hid}",
                )
                if checked != is_done:
                    conn = get_conn()
                    if checked:
                        conn.execute(
                            "INSERT OR IGNORE INTO habit_logs (habit_id, log_date) VALUES (?, ?)",
                            (hid, today_iso),
                        )
                        conn.commit()
                        conn.close()
                        award_xp_and_coins(int(h_row["xp_value"]), 10)
                        st.toast(f"Routine anchored! +{h_row['xp_value']} XP", icon="🌱")
                    else:
                        conn.execute(
                            "DELETE FROM habit_logs WHERE habit_id = ? AND log_date = ?",
                            (hid, today_iso),
                        )
                        conn.commit()
                        conn.close()
                        award_xp_and_coins(-int(h_row["xp_value"]), -10)
                    st.rerun()

                hc2.caption("Completed Today" if is_done else "Pending")
                if hc3.button("🗑️", key=f"del_hab_{hid}"):
                    conn = get_conn()
                    conn.execute("DELETE FROM habits WHERE id = ?", (hid,))
                    conn.commit()
                    conn.close()
                    st.rerun()

    with hb_col2:
        st.subheader("➕ Add Routine Anchor")
        with st.form("add_habit_form", clear_on_submit=True):
            h_name = st.text_input("Micro-Habit Name", placeholder="e.g., Take afternoon meds, Stretch 3 mins")
            h_routine = st.selectbox("Anchor Window", ["Meds & Care", "Morning Launch", "Midday Reset", "Evening Wind-Down"])
            h_xp = st.slider("XP Reward", 10, 50, 25, step=5)
            if st.form_submit_button("Add Habit Anchor", type="primary", use_container_width=True):
                if h_name.strip():
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO habits (name, routine, xp_value) VALUES (?, ?, ?)",
                        (h_name.strip(), h_routine, int(h_xp)),
                    )
                    conn.commit()
                    conn.close()
                    st.toast("New habit anchor added!", icon="🌱")
                    st.rerun()

    # ---- Meals & groceries (Haveloo hubs) ----
    st.divider()
    _meals_conn = get_conn()
    hubs.render_meals(st, _meals_conn)
    _meals_conn.close()


# ------------------------------------------------------------------------------
# TAB 5: IMPULSE-BUY COOLING-OFF VAULT
# ------------------------------------------------------------------------------
with tabs[4]:
    st.header("🛡️ Impulse-Buy Cooling-Off Vault")
    st.caption(
        "Dopamine-seeking impulse shopping hits hard. Lock temptations in this vault for **48–72 hours**. "
        "When the urge fades, move the price into your **Money Saved** total and earn bonus XP."
    )

    conn = get_conn()
    vault_df = pd.read_sql_query("SELECT * FROM impulse_vault ORDER BY id DESC", conn)
    conn.close()

    saved_total = float(vault_df[vault_df["status"] == "Resisted & Saved"]["price"].sum()) if not vault_df.empty else 0.0
    spent_total = float(vault_df[vault_df["status"] == "Bought"]["price"].sum()) if not vault_df.empty else 0.0
    pending_df = vault_df[vault_df["status"] == "Cooling Off"] if not vault_df.empty else pd.DataFrame()
    pending_total = float(pending_df["price"].sum()) if not pending_df.empty else 0.0

    v1, v2, v3 = st.columns(3)
    v1.metric("💰 Total Impulse Money Saved", f"${saved_total:,.2f}", delta="Kept in Your Account")
    v2.metric("⏳ Currently Cooling Off", f"${pending_total:,.2f}", delta=f"{len(pending_df)} items locked")
    v3.metric("🛍️ Mindfully Purchased", f"${spent_total:,.2f}")

    iv_col1, iv_col2 = st.columns([1.5, 1.0], gap="large")

    with iv_col1:
        st.subheader("⏳ Active Cooldown Locker")
        if pending_df.empty:
            st.success("No impulse temptations currently waiting in the vault!")
        else:
            now_dt = datetime.now()
            for _, v_row in pending_df.iterrows():
                added_dt = datetime.strptime(v_row["added_at"], "%Y-%m-%d %H:%M:%S")
                unlock_dt = added_dt + timedelta(hours=int(v_row["cooldown_hours"]))
                hrs_left = (unlock_dt - now_dt).total_seconds() / 3600.0

                with st.container(border=True):
                    vc1, vc2 = st.columns([2.8, 1.7])
                    with vc1:
                        st.markdown(f"#### {v_row['item_name']} — **${v_row['price']:,.2f}**")
                        st.caption(
                            f"Category: {v_row['category']} • Initial Urge: {v_row['urge_level']}/10 • "
                            f"Cooldown: {v_row['cooldown_hours']}h"
                        )
                        if hrs_left > 0:
                            st.warning(f"🔒 **LOCKED:** {hrs_left:.1f} hours remaining before you're allowed to buy.")
                        else:
                            st.success("🔓 **COOLDOWN COMPLETE:** Still want it, or did the dopamine urge pass?")

                    with vc2:
                        if st.button("💪 Resisted! Save Money (+50 XP)", key=f"resist_{v_row['id']}", type="primary", use_container_width=True):
                            conn = get_conn()
                            conn.execute(
                                "UPDATE impulse_vault SET status = 'Resisted & Saved' WHERE id = ?",
                                (int(v_row["id"]),),
                            )
                            conn.commit()
                            conn.close()
                            award_xp_and_coins(50, 25)
                            st.balloons()
                            st.toast(f"Saved ${v_row['price']:,.2f}! +50 XP & +25 Coins!", icon="🛡️")
                            st.rerun()

                        if st.button("🛍️ Bought Mindfully", key=f"buy_{v_row['id']}", use_container_width=True):
                            conn = get_conn()
                            conn.execute(
                                "UPDATE impulse_vault SET status = 'Bought' WHERE id = ?",
                                (int(v_row["id"]),),
                            )
                            conn.commit()
                            conn.close()
                            st.rerun()

    with iv_col2:
        st.subheader("🔒 Lock an Impulse Temptation")
        with st.form("add_impulse_form", clear_on_submit=True):
            i_name = st.text_input("What do you want to buy right now?", placeholder="e.g., Espresso machine, RGB lights")
            i_price = st.number_input("Price ($)", min_value=1.0, max_value=10000.0, value=45.0, step=5.0)
            i_cat = st.selectbox("Category", ["Tech / Desk", "Clothes / Gear", "Home Decor", "Hobby / Craft", "Food / Treats"])
            i_urge = st.slider("Urge Intensity (1 = mild, 10 = MUST BUY NOW)", 1, 10, 8)
            i_cool = st.selectbox("Cooldown Lock Period", [24, 48, 72, 168], index=1)
            if st.form_submit_button("🔒 Lock in Vault (+15 XP)", type="primary", use_container_width=True):
                if i_name.strip():
                    conn = get_conn()
                    conn.execute(
                        """
                        INSERT INTO impulse_vault (item_name, price, category, urge_level, added_at, cooldown_hours, status)
                        VALUES (?, ?, ?, ?, ?, ?, 'Cooling Off')
                        """,
                        (
                            i_name.strip(),
                            float(i_price),
                            i_cat,
                            int(i_urge),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            int(i_cool),
                        ),
                    )
                    conn.commit()
                    conn.close()
                    award_xp_and_coins(15, 10)
                    st.toast("Locked in vault! Future-you thanks you (+15 XP)", icon="🛡️")
                    st.rerun()

    # ---- Money deepening: Budget Battery, Savings Jars, Debt, Subs, Safe-to-Spend ----
    st.divider()
    _money_conn = get_conn()
    hubs.render_money_deepening(st, _money_conn)
    _money_conn.close()


# ------------------------------------------------------------------------------
# TAB 6: BRAIN DUMP & COGNITIVE TRIAGE
# ------------------------------------------------------------------------------
with tabs[5]:
    st.header("📥 Brain Dump & Cognitive Triage")
    st.caption(
        "Promote captured thoughts into actionable tasks or dismiss noise so your working memory stays light."
    )

    conn = get_conn()
    dumps_df = pd.read_sql_query("SELECT * FROM brain_dump WHERE triaged = 0 ORDER BY id DESC", conn)
    conn.close()

    if dumps_df.empty:
        st.success("Brain Dump inbox is completely triaged! Use the sidebar Quick Brain Dump anytime.")
    else:
        for _, d_row in dumps_df.iterrows():
            with st.container(border=True):
                dc1, dc2, dc3, dc4 = st.columns([3.2, 1.1, 1.1, 0.8])
                dc1.markdown(f"**{d_row['thought']}**  \n<small>Tag: {d_row['tag']} • Captured: {d_row['created_at']}</small>", unsafe_allow_html=True)

                if dc2.button("🔥 → NOW", key=f"bd_now_{d_row['id']}", use_container_width=True):
                    conn = get_conn()
                    conn.execute(
                        """
                        INSERT INTO tasks (title, category, priority, energy_req, est_minutes, micro_steps, status, xp_reward, created_at)
                        VALUES (?, 'Work / Study', 'NOW (Big 3)', 'Medium', 20, '[]', 'Todo', 40, ?)
                        """,
                        (d_row["thought"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    )
                    conn.execute("UPDATE brain_dump SET triaged = 1 WHERE id = ?", (int(d_row["id"]),))
                    conn.commit()
                    conn.close()
                    award_xp_and_coins(10, 5)
                    st.rerun()

                if dc3.button("📋 → Queue", key=f"bd_q_{d_row['id']}", use_container_width=True):
                    conn = get_conn()
                    conn.execute(
                        """
                        INSERT INTO tasks (title, category, priority, energy_req, est_minutes, micro_steps, status, xp_reward, created_at)
                        VALUES (?, 'Home / Admin', 'Next Up', 'Low', 15, '[]', 'Todo', 30, ?)
                        """,
                        (d_row["thought"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    )
                    conn.execute("UPDATE brain_dump SET triaged = 1 WHERE id = ?", (int(d_row["id"]),))
                    conn.commit()
                    conn.close()
                    award_xp_and_coins(10, 5)
                    st.rerun()

                if dc4.button("🗑️", key=f"bd_del_{d_row['id']}", use_container_width=True):
                    conn = get_conn()
                    conn.execute("UPDATE brain_dump SET triaged = 1 WHERE id = ?", (int(d_row["id"]),))
                    conn.commit()
                    conn.close()
                    st.rerun()


# ------------------------------------------------------------------------------
# TAB 7: EXECUTIVE ANALYTICS & VISUAL INSIGHTS (6 INTERACTIVE CHARTS)
# ------------------------------------------------------------------------------
with tabs[6]:
    st.header("📊 Executive Analytics & Neuro-Pattern Insights")
    st.caption(
        "Discover your biological peak focus windows, life-domain balance, routine adherence, "
        "distraction patterns, and financial impulse shield performance."
    )

    conn = get_conn()
    en_df = pd.read_sql_query("SELECT * FROM energy_logs", conn)
    all_tasks_df = pd.read_sql_query("SELECT * FROM tasks", conn)
    foc_df = pd.read_sql_query("SELECT * FROM focus_sessions", conn)
    hab_df = pd.read_sql_query("SELECT * FROM habits", conn)
    hlog_df = pd.read_sql_query("SELECT * FROM habit_logs", conn)
    imp_df = pd.read_sql_query("SELECT * FROM impulse_vault", conn)
    conn.close()

    # ROW 1: Energy & Focus Trends + Biological Peak Window
    r1_c1, r1_c2 = st.columns([1.4, 1.0], gap="medium")

    with r1_c1:
        st.subheader("1️⃣ 14-Day Energy vs. Focus Trajectory")
        if en_df.empty:
            st.info("Log energy & focus states in the sidebar to populate this trend chart.")
        else:
            daily_en = (
                en_df.groupby("log_date", as_index=False)[["energy_level", "focus_level"]]
                .mean()
                .sort_values("log_date")
            )
            fig_en = go.Figure()
            fig_en.add_trace(
                go.Scatter(
                    x=daily_en["log_date"],
                    y=daily_en["energy_level"],
                    mode="lines+markers",
                    name="Energy Level",
                    line=dict(color="#38bdf8", width=3),
                    fill="tozeroy",
                    fillcolor="rgba(56, 189, 248, 0.12)",
                )
            )
            fig_en.add_trace(
                go.Scatter(
                    x=daily_en["log_date"],
                    y=daily_en["focus_level"],
                    mode="lines+markers",
                    name="Focus Clarity",
                    line=dict(color="#c084fc", width=3),
                )
            )
            fig_en.update_layout(
                template=PLOTLY_TEMPLATE,
                height=340,
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis=dict(range=[0, 10.5], title="Score (1–10)"),
                xaxis=dict(title="Date"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_en, use_container_width=True)

    with r1_c2:
        st.subheader("2️⃣ Peak Biological Focus Window")
        if en_df.empty:
            st.info("No time-block logs available yet.")
        else:
            tb_order = ["Morning", "Afternoon", "Evening"]
            tb_avg = (
                en_df.groupby("time_block", as_index=False)[["energy_level", "focus_level"]]
                .mean()
            )
            tb_avg["time_block"] = pd.Categorical(tb_avg["time_block"], categories=tb_order, ordered=True)
            tb_avg = tb_avg.sort_values("time_block")

            fig_tb = go.Figure(
                data=[
                    go.Bar(name="Avg Energy", x=tb_avg["time_block"], y=tb_avg["energy_level"], marker_color="#38bdf8"),
                    go.Bar(name="Avg Focus", x=tb_avg["time_block"], y=tb_avg["focus_level"], marker_color="#a855f7"),
                ]
            )
            fig_tb.update_layout(
                barmode="group",
                template=PLOTLY_TEMPLATE,
                height=340,
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis=dict(range=[0, 10.5], title="Avg Score"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_tb, use_container_width=True)

    # ROW 2: Life Domain Balance Radar + Habit Consistency Heatmap
    r2_c1, r2_c2 = st.columns([1.0, 1.4], gap="medium")

    with r2_c1:
        st.subheader("3️⃣ Life-Domain Balance Radar")
        categories = ["Work / Study", "Health", "Home / Admin", "Creative", "Finance"]
        done_only = all_tasks_df[all_tasks_df["status"] == "Done"] if not all_tasks_df.empty else pd.DataFrame()
        cat_counts = [
            int((done_only["category"] == c).sum()) if not done_only.empty else 0
            for c in categories
        ]
        if sum(cat_counts) == 0:
            st.info("Complete tasks across domains to see your balance radar.")
        else:
            fig_radar = go.Figure(
                data=go.Scatterpolar(
                    r=cat_counts + [cat_counts[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    fillcolor="rgba(16, 185, 129, 0.25)",
                    line=dict(color="#10b981", width=2.5),
                    name="Completed Tasks",
                )
            )
            fig_radar.update_layout(
                template=PLOTLY_TEMPLATE,
                height=350,
                margin=dict(l=35, r=35, t=25, b=25),
                polar=dict(radialaxis=dict(visible=True, range=[0, max(cat_counts) + 1])),
            )
            st.plotly_chart(fig_radar, use_container_width=True)

    with r2_c2:
        st.subheader("4️⃣ 14-Day Habit & Bounce-Back Heatmap")
        if hab_df.empty:
            st.info("Add habits to track adherence patterns.")
        else:
            last_14_days = [(date.today() - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
            log_pairs = set(zip(hlog_df["habit_id"], hlog_df["log_date"])) if not hlog_df.empty else set()

            z_matrix = []
            y_labels = []
            for _, h_r in hab_df.iterrows():
                y_labels.append(h_r["name"][:28])
                z_matrix.append([1 if (int(h_r["id"]), d) in log_pairs else 0 for d in last_14_days])

            fig_heat = go.Figure(
                data=go.Heatmap(
                    z=z_matrix,
                    x=[d[5:] for d in last_14_days],
                    y=y_labels,
                    colorscale=[[0, "#1e293b"], [1, "#10b981"]],
                    showscale=False,
                    xgap=3,
                    ygap=3,
                )
            )
            fig_heat.update_layout(
                template=PLOTLY_TEMPLATE,
                height=350,
                margin=dict(l=20, r=20, t=20, b=20),
                xaxis=dict(title="Date (MM-DD)"),
            )
            st.plotly_chart(fig_heat, use_container_width=True)

    # ROW 3: Focus Sprints vs Distractions + Impulse-Buy Financial Shield
    r3_c1, r3_c2 = st.columns([1.2, 1.0], gap="medium")

    with r3_c1:
        st.subheader("5️⃣ Focus Minutes vs. Distractions Caught")
        if foc_df.empty:
            st.info("Complete focus sprints to visualize deep-work output.")
        else:
            foc_grouped = (
                foc_df.groupby("session_date", as_index=False)[["duration_minutes", "distractions_caught"]]
                .sum()
                .sort_values("session_date")
            )
            fig_foc = go.Figure()
            fig_foc.add_trace(
                go.Bar(
                    x=foc_grouped["session_date"],
                    y=foc_grouped["duration_minutes"],
                    name="Focus Minutes",
                    marker_color="#38bdf8",
                )
            )
            fig_foc.add_trace(
                go.Scatter(
                    x=foc_grouped["session_date"],
                    y=foc_grouped["distractions_caught"],
                    name="Distractions Caught",
                    mode="lines+markers",
                    yaxis="y2",
                    line=dict(color="#f59e0b", width=3),
                )
            )
            fig_foc.update_layout(
                template=PLOTLY_TEMPLATE,
                height=340,
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis=dict(title="Focus Minutes"),
                yaxis2=dict(title="Distractions", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_foc, use_container_width=True)

    with r3_c2:
        st.subheader("6️⃣ Impulse-Buy Financial Shield ($)")
        if imp_df.empty:
            st.info("Log impulse temptations in the Vault to track money saved.")
        else:
            imp_summary = imp_df.groupby("status", as_index=False)["price"].sum()
            color_map = {
                "Resisted & Saved": "#10b981",
                "Cooling Off": "#f59e0b",
                "Bought": "#ef4444",
            }
            fig_imp = px.pie(
                imp_summary,
                names="status",
                values="price",
                hole=0.52,
                color="status",
                color_discrete_map=color_map,
            )
            fig_imp.update_traces(textinfo="label+value", texttemplate="%{label}<br>$%{value:,.0f}")
            fig_imp.update_layout(
                template=PLOTLY_TEMPLATE,
                height=340,
                margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False,
            )
            st.plotly_chart(fig_imp, use_container_width=True)

    # ---- Look Back + Vision Board / Year Map (Haveloo hubs) ----
    st.divider()
    _lb_conn = get_conn()
    hubs.render_look_back(st, _lb_conn)
    st.divider()
    hubs.render_vision_yearmap(st, _lb_conn)
    _lb_conn.close()


# ------------------------------------------------------------------------------
# TAB 8: PEOPLE
# ------------------------------------------------------------------------------
with tabs[7]:
    st.header("👥 People")
    st.caption("Stay in touch without the guilt — catch-up nudges, birthdays, gift ideas.")
    _conn = get_conn()
    hubs.render_people(st, _conn)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 9: HOUSEHOLD
# ------------------------------------------------------------------------------
with tabs[8]:
    st.header("🏠 Household")
    st.caption("Cleaning that repeats, chores, declutter zones and home inventory.")
    _conn = get_conn()
    hubs.render_household(st, _conn)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 10: LEARN
# ------------------------------------------------------------------------------
with tabs[9]:
    st.header("📚 Learn")
    st.caption("Bookshelf, courses and skill roadmaps — progress you can see.")
    _conn = get_conn()
    hubs.render_learn(st, _conn)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 11: EXPLORE
# ------------------------------------------------------------------------------
with tabs[10]:
    st.header("🌍 Explore")
    st.caption("Trips, itineraries, packing lists and the bucket list.")
    _conn = get_conn()
    hubs.render_explore(st, _conn, template=PLOTLY_TEMPLATE)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 12: CAREER
# ------------------------------------------------------------------------------
with tabs[11]:
    st.header("💼 Career")
    st.caption("Side hustles, income streams, CV notes and networking follow-ups.")
    _conn = get_conn()
    hubs.render_career(st, _conn)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 13: SMART PLANNER (rule-based insights, breakdown, day plan, calendar)
# ------------------------------------------------------------------------------
with tabs[12]:
    st.header("🧠 Smart Planner")
    st.caption("Smart suggestion — based on your logged data. Rule-based, not a live AI model.")
    _conn = get_conn()
    adv.render_smart_insights(st, _conn)
    st.divider()
    adv.render_ai_breakdown(st, _conn)
    st.divider()
    adv.render_ai_day_planner(st, _conn)
    st.divider()
    adv.render_calendar_export(st, _conn)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 14: VOICE & FOCUS PRO
# ------------------------------------------------------------------------------
with tabs[13]:
    st.header("🎙️ Voice & Focus Pro")
    _conn = get_conn()
    adv.render_voice_add(st, _conn)
    st.divider()
    adv.render_focus_pro(st, _conn)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 15: SOS & DAILY CARE
# ------------------------------------------------------------------------------
with tabs[14]:
    st.header("🆘 SOS & Daily Care")
    _conn = get_conn()
    adv.render_sos(st, _conn)
    st.divider()
    adv.render_cycle_sleep(st, _conn)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 16: MONEY GUARD
# ------------------------------------------------------------------------------
with tabs[15]:
    st.header("💳 Money Guard")
    _conn = get_conn()
    adv.render_subscriptions_bills(st, _conn)
    _conn.close()


# ------------------------------------------------------------------------------
# TAB 17: PRINT & BACKUP
# ------------------------------------------------------------------------------
with tabs[16]:
    st.header("🖨️ Print & Backup")
    _conn = get_conn()
    adv.render_print_export(st, _conn)
    _conn.close()
