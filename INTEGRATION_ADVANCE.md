# INTEGRATION_ADVANCE.md — wiring `haveloo_advance.py` into `app.py`

Module: `haveloo_advance.py` (same folder as `app.py`). **Do NOT edit this
module's honesty labels** ("Smart suggestion — based on your logged data",
"rule-based", "not medical advice", "NOT live in this build"). All wording
is Haveloo's own; no competitor branding or text is used, and no live URL is
invented anywhere in the module.

Verified 2026-11-12: `python3 -m py_compile haveloo_advance.py` passes.
Headless tests (temp SQLite DB in `/tmp`, no Streamlit) pass — see
"Verification" at the bottom. **Not yet verified: a live `streamlit run`
smoke test** — Streamlit is not installed in this VM, so the parent /
coordinator must run the app once and click through the new tabs before
delivery.

## 0. How the module is built (so the integration stays correct)

- The module does **not** import `app.py` and does **not** import Streamlit
  at module level. Every render function takes `st` as its first argument
  plus an open `sqlite3` connection: `render_smart_insights(st, conn)`.
- Connection ownership: the **caller opens and closes** the connection
  (the `get_conn()` pattern from `app.py`). Module functions **COMMIT after
  each write but never close** the connection they were given.
- XP/coins inside the module go through its own `_award_xp(conn, xp, coins)`,
  which reuses the passed connection. Do NOT swap in `award_xp_and_coins`
  inside these functions — that opens a second connection to a DB the
  caller already holds.
- Pure, headless-testable helpers (no `st`): `build_ics(events)`,
  `breakdown_steps(title)`, `build_day_plan(task_rows, start, free_minutes,
  energy_level)`, `compute_insights(conn)`, `cycle_focus_note(conn)`,
  `estimate_next_cycle_start(conn)`, `export_backup(conn)`,
  `restore_backup(conn, payload)`, `beep_data_uri()`.

## 1. Import — after line 9 of app.py

```python
import streamlit as st
import haveloo_advance as adv   # <-- ADD: Tier 2 advance features
```

## 2. Initialise + seed — immediately after line 776 (`init_db()`)

```python
init_db()

# --- Tier 2 advance tables (haveloo_advance) ---
_adv_conn = get_conn()
adv.init_advance_tables(_adv_conn)
adv.seed_advance(_adv_conn)   # seeds ONLY empty tables; safe to run every launch
_adv_conn.close()
```

`seed_advance()` is idempotent (verified: seeding twice changes no counts).

## 3. New tabs — extend the `st.tabs(...)` list at lines 953–966

Tab order: the 7 base tabs stay first, then the 5 Tier 1 hub tabs
(People / Household / Learn / Explore / Career — separate module), then
these 5 advance tabs in this order:

| # | Tab label | Render function(s) |
|---|-----------|--------------------|
| 8 | `🧠 Smart Planner` | `render_smart_insights`, `render_ai_breakdown`, `render_ai_day_planner`, `render_calendar_export` |
| 9 | `🎙️ Voice & Focus Pro` | `render_voice_add`, `render_focus_pro` |
| 10 | `🆘 SOS & Daily Care` | `render_sos`, `render_cycle_sleep` |
| 11 | `💳 Money Guard` | `render_subscriptions_bills` |
| 12 | `🖨️ Print & Backup` | `render_print_export` |

If the Tier 1 hub tabs are **not yet added**, these are `tabs[7]`–`tabs[11]`.
If the hub tabs **are** added as `tabs[7]`–`tabs[11]`, these are
`tabs[12]`–`tabs[16]`. Use the second numbering below (adjust down by 5 if
the hub tabs do not exist yet).

Append the five labels to the `st.tabs([...])` list at lines 953–966, then
add these blocks **after the Tab 7 block that starts at line 1670**
(`with tabs[6]:`, file ends at line 1892):

```python
# ------------------------------------------------------------------------------
# TAB 12: SMART PLANNER (rule-based insights, breakdown, day plan, calendar)
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
# TAB 13: VOICE & FOCUS PRO
# ------------------------------------------------------------------------------
with tabs[13]:
    st.header("🎙️ Voice & Focus Pro")
    _conn = get_conn()
    adv.render_voice_add(st, _conn)
    st.divider()
    adv.render_focus_pro(st, _conn)
    _conn.close()

# ------------------------------------------------------------------------------
# TAB 14: SOS & DAILY CARE
# ------------------------------------------------------------------------------
with tabs[14]:
    st.header("🆘 SOS & Daily Care")
    _conn = get_conn()
    adv.render_sos(st, _conn)
    st.divider()
    adv.render_cycle_sleep(st, _conn)
    _conn.close()

# ------------------------------------------------------------------------------
# TAB 15: MONEY GUARD
# ------------------------------------------------------------------------------
with tabs[15]:
    st.header("💳 Money Guard")
    _conn = get_conn()
    adv.render_subscriptions_bills(st, _conn)
    _conn.close()

# ------------------------------------------------------------------------------
# TAB 16: PRINT & BACKUP
# ------------------------------------------------------------------------------
with tabs[16]:
    st.header("🖨️ Print & Backup")
    _conn = get_conn()
    adv.render_print_export(st, _conn)
    _conn.close()
```

Why one connection per tab block: every render function in a block shares
it, and the block closes it — the same open/use/close shape as the base
tabs. Never pass a closed connection, and never let two blocks share one.

## 4. `session_state` keys used by the module (all prefixed `adv_`)

| Key | Purpose |
|-----|---------|
| `adv_break_steps`, `adv_break_title`, `adv_break_task_id`, `adv_break_checked` | Smart Breakdown: steps + target task |
| `adv_day_plan` | Smart Day Planner output (list of timed blocks, ISO datetimes); also read by Calendar Export |
| `adv_sos_id`, `adv_sos_active`, `adv_sos_step` | SOS reset in progress (row id, active flag, breathing step 0–3) |
| `adv_bd_start` | Body-doubling session start timestamp (ISO) |
| `adv_focus_mode` | Focus Mode toggle (hides dopamine/impulse panels in Focus Pro) |
| `adv_weekly_summary` | Printable weekly summary text built by Print & Backup |

No key collides with the base app (`timer_*`, `haveloo_theme`,
`dyslexia_font`, `large_text`, `theme_radio`).

## 5. Tables

**Created by this module** (`init_advance_tables`): `wellness_log`,
`cycle_log`, `sos_log`, `subscriptions`, `impulse_waitlist`, `bills`,
`voice_notes`, `focus_sounds`. (`user_prefs` is created `IF NOT EXISTS`
only, so reminder / guard / sound choices have a home if this module ever
initialises first.)

**Reused read-only or read/write from the base app:** `tasks` (read Todo /
Big 3; writes `micro_steps`, `priority`), `energy_logs` (read for insights
+ day-planner energy), `focus_sessions` (read for insights; Body Doubling
writes new rows), `habit_logs` + `habits` (read for insights),
`impulse_vault` (read-only count in Focus Pro), `brain_dump` (Voice Add
writes), `dopamine_menu` (read-only free boost in Focus Pro), `user_stats`
(XP/coins via `_award_xp`), `user_prefs` (keys `focus_sound`,
`hyperfocus_guard`, `reminder_hooks`).

## 6. Honest limits — do not "fix" these by claiming more

- **No live AI.** Insights, breakdown and day planner are rule-based over
  the user's own logs. The UI says so on every screen.
- **No live calendar sync / push notifications.** Calendar Export produces
  a real downloadable `.ics` file (RFC 5545, generated in code). The
  "notification hooks" section is a checklist + copyable reminder text plus
  a caption stating live 2-way sync and push need the hosted version +
  user opt-in and are NOT live.
- **No audio files.** Soundscapes are named built-in choices stored in
  `focus_sounds` (`is_builtin = 1`, empty URL). The only sound generated is
  a short sine-tone beep (WAV data-URI built in code) for the timer end.
- **Voice is not automatic capture.** The speech widget only shows the
  transcript on screen; the user confirms it in the Streamlit form before
  anything is saved. If the browser has no SpeechRecognition, the widget
  says so and the typed fallback is shown prominently.
- **SOS / cycle are not medical advice and SOS is not a crisis service.**
  Both screens carry that line; the cycle estimate is last start + 28 days,
  labelled "estimate only".
- **Buttons:** every *action* button writes to the DB, shows a toast and
  reruns. Three deliberate exceptions (navigation / compute only, no DB
  write — they visibly change the screen, so they are not dead buttons):
  `Break it down into tiny steps` and `Build my day plan` (compute into
  `session_state`; the matching Save buttons do the DB write + XP), and
  SOS `Next breath →` (advances the on-screen breathing step; the final
  save button writes `sos_log` + 15 XP).

## 7. Known follow-up for the integrator (not done here — app.py untouched)

- `reset_database()` in `app.py` (line 655) deletes only base tables. If
  "Clear All Data" should also wipe advance data, add:
  `DELETE FROM wellness_log; DELETE FROM cycle_log; DELETE FROM sos_log;
  DELETE FROM subscriptions; DELETE FROM impulse_waitlist; DELETE FROM bills;
  DELETE FROM voice_notes; DELETE FROM focus_sounds;` plus
  `DELETE FROM user_prefs WHERE key IN
  ('focus_sound','hyperfocus_guard','reminder_hooks');`
- After wiring, run a live `streamlit run app.py` smoke test and click
  every new-tab button once (see "Not yet verified" at the top).

## Verification (run 2026-11-12, this VM)

```
python3 -m py_compile haveloo_advance.py        # COMPILE_OK
python3 /tmp/test_advance.py                     # ALL HEADLESS TESTS PASSED
```

Headless test (`/tmp/test_advance.py`, temp DB `/tmp/adv_test.db`, base
tables recreated minimally + sample rows): seed counts exact
(wellness_log 7, cycle_log 3, sos_log 2, subscriptions 4, impulse_waitlist 2,
bills 4, focus_sounds 5, voice_notes 0); seeding twice changes no counts;
`.ics` contains `BEGIN:VCALENDAR` + one `VEVENT` (`DTSTART:20261112T090000`);
breakdown returns 5 steps for a cleaning task and a 5-step generic fallback;
day plan orders low-energy tasks first at low energy with 5-min breaks;
`compute_insights` returns 6 cards with evidence strings; cycle next-start
estimate and focus note present; beep is a `data:audio/wav;base64,...` URI;
backup/restore round-trip restores 81 rows across 18 tables; XP helper
moves user_stats 680/145 → 690/150 via the caller connection.
