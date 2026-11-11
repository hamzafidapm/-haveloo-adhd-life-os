# Haveloo ADHD Life OS — Verification Report (coordinator, 2026-11-12)

## 1. Code shi? YES — full code verified before any building

- Source used: ONLY the second user paste (02:56 PKT, ends Row 3 `fig_imp` pie
  chart). The first paste (02:52, truncated mid-Tab-7) was ignored as source.
- Transcribed to `app.py`: 1,611 lines at first save; `python3 -m py_compile` OK.
- `pyflakes`: only finding was unused `import math` (present in the user's
  original) — removed.
- Streamlit server (base, before wiring): HTTP 200, no errors in log.
- Headless AppTest run (base): NO exception, 7 tabs, 49 buttons, 14 metrics;
  DB seeded exactly (XP 680, coins 145, 13 tasks / 8 done / Big 3 = 3,
  5 habits, 60 habit logs, 42 energy logs, 7 focus sessions).
- One real bug caught by testing (not by reading): the first theme-CSS
  injection called `theme_css()` before it was defined (NameError). Fixed by
  keeping the original dark CSS for first paint and re-injecting the selected
  theme after the sidebar picker. All 6 themes re-tested after the fix.

## 2. Merged 6-theme system (ONE picker — per user correction 03:03)

| Theme | Variant | Purpose | Behaviour (real, not a label) |
|---|---|---|---|
| Cocoa | Light | Warm Comfort / Grounding | Gentle line in sidebar; top 3 prominent |
| Sage | Dark | Calm / Anxiety Relief | Hides extras + breathing cue in sidebar; hides Recently Completed |
| Apricot | Light | Mood Lift / Gentle Energy | Shows one tiny win + one tiny step from live data |
| Lavender | Light | Relax / Night Rest | Evening wind-down note in sidebar |
| Ocean | Dark | Deep Focus | Hides queue + sidebar extras; focus card with current Big 3 task |
| Rosewood | Light | Reflect / Look Back | Live "this week so far" strip from real data |

- No second Mode picker exists (the separate mood system was never built).
- Saved per user in `user_prefs` (per-account once logged in — see §5);
  switches instantly, no data lost.
- Dyslexia-friendly font + large-text options in the sidebar, work in all themes.
- Honest note under the picker: themes are supportive design only, not medical
  advice and not a substitute for professional help.

### Contrast check (scripted WCAG ratios — all pairs, all themes)

| Theme | text/bg | text/card | sub/bg | accent/card | button text/button |
|---|---|---|---|---|---|
| Cocoa | 13.69 | 15.34 | 6.06 | 5.75 | 5.85 |
| Sage | 13.20 | 11.04 | 7.93 | 5.86 | 7.65 |
| Apricot | 13.56 | 14.80 | 5.61 | 5.03 | 5.11 |
| Lavender | 12.85 | 14.59 | 4.74 | 6.17 | 6.25 |
| Ocean | 14.01 | 11.43 | 7.84 | 5.67 | 7.59 |
| Rosewood | 13.34 | 15.15 | 5.62 | 7.33 | 7.43 |

ALL >= 4.5 (WCAG AA for normal text). Lowest: Lavender subtext 4.74.
AppTest, all 6 themes, wired app: no exceptions, 17 tabs each, theme
background colour present in rendered CSS. Button counts differ by design
(Sage 194, Ocean 188 — hidden extras; others 196).

## 3. Wiring (coordinator) — what was added to app.py

- Imports: `haveloo_hubs`, `haveloo_advance`, `haveloo_auth`.
- `get_conn()` routes per account (logged-in email -> per-user file, else
  shared demo file). No query changes — all 40+ call sites already use it.
- `reset_database()` now also clears hub + advance tables (and the
  `focus_sound` / `hyperfocus_guard` / `reminder_hooks` pref keys).
  After routing it clears the CURRENT user's file — correct for the
  user-facing "Clear All Data" button; the host must never use it to wipe
  the shared accounts file.
- Module-level init after `init_db()`: hub tables + seed, advance tables +
  seed, then the auth gate (`st.stop()` when not logged in / not unlocked).
  **Changed 2026-11-12 (see §8):** seeding is now gated on login state —
  demo mode gets the full seed; a logged-in buyer gets structural defaults
  only (onboarding keys, focus-sound catalogue) and starts empty.
- Tabs: 7 -> 17 (5 hubs + 5 advance). Deepening slotted in: Fill My Day,
  guided tour + checklist, countdowns/weekly reset in Tab 1; Meals in Tab 4;
  Money deepening in Tab 5; Look Back + Vision/Year Map at the end of Tab 7.
- Final `app.py`: 2,109 lines. `py_compile` clean on all 4 code files.

## 4. Full-app verification (wired, 2026-11-12, venv streamlit 1.40.0)

| Test | Result |
|---|---|
| `py_compile` app.py + 3 modules + build_guide.py | OK |
| AppTest, gate-only (not logged in) | No exception; gate tabs only (Log in / Create account), planner hidden |
| AppTest, free-demo mode | No exception; **17 tabs, 37 metrics, 194 buttons, 136 markdown** |
| AppTest, logged-in session (pre-seeded unlocked account) | No exception; 17 tabs; per-user DB created with 13 tasks, XP 680/145, people 4, wellness 7 |
| AppTest, all 6 themes (demo mode, wired app) | No exception; 17 tabs each; theme bg in CSS |
| DB tables after demo run | 35 tables — all base + hub (14) + advance (8) + auth (accounts, app_settings) present; every seed count exact (see below) |
| Live `streamlit run` (wired app, port 8502) | HTTP 200; 0 tracebacks/exceptions in server log; server stopped, nothing left running |

Seed counts after demo run: people 4, household_tasks 4, home_inventory 4,
learn_items 4, trips 3, career_items 5, goals_board 5, money_extra 7,
recipes 3, grocery_items 3, meal_plan 3, countdowns 2, weekly_resets 1,
onboarding 6, wellness_log 7, cycle_log 3, sos_log 2, subscriptions 4,
impulse_waitlist 2, bills 4, focus_sounds 5, voice_notes 0.

## 5. Auth / unlock / sync — verified headlessly

- Create account OK; duplicate / short password (<8) / bad email rejected.
- Unlock: bad order number (`ABC-XYZ`, `123`) rejected; `4614332561`
  accepted and stored (`unlocked=1`).
- Login: wrong password fails; correct password logs in with
  `haveloo_user_email` + `haveloo_unlocked` set.
- Plaintext password NOT found in the raw auth DB file; stored value is
  PBKDF2-HMAC-SHA256 `salt$hash` (210k iterations).
- Per-user isolation: buyer file `data/user_10c37e3986af7421.db` (hash, raw
  email never in filename); a private task added by buyer does NOT appear
  in the other account's file (1 vs 0).
- Design chosen: per-user SQLite files (v1). Recommended better option:
  hosted Postgres/Supabase (AUTH_DESIGN.md option c) — plumbing for
  `HAVELOO_DATABASE_URL` is implemented; full Postgres migration is a
  remaining hosting step, NOT claimed as done.

## 6. Honest limits — read before listing

1. **No live Etsy verification.** Unlock is a format check + stored record
   for seller verification. The exact note is in the code, the app UI and
   the guide. Do NOT tell buyers Etsy checks it automatically.
2. **No deployed URL yet.** The Quick Start Guide's "Open my planner" box
   reads "YOUR APP LINK — paste your Streamlit Cloud app URL here before
   listing". Do NOT list the guide until the real URL is pasted in and the
   PDF is re-exported (`python3 build_guide.py`).
3. **Streamlit Cloud filesystem is ephemeral.** On the free tier the .db
   files (accounts + per-user data) can be lost on redeploy. For real
   multi-device sync + backups, set `HAVELOO_DATABASE_URL` to hosted
   Postgres/Supabase BEFORE the first real buyer (see HOSTING.md).
4. **Fresh accounts start EMPTY (changed 2026-11-12, verified in §8).**
   `init_db()` and the hub/advance module-level seeding only seed demo
   data when NO account is logged in (the shared free-demo file). A newly
   created + unlocked buyer account starts with 0 tasks, 0 XP, 0 coins,
   empty Big 3 and empty hub/advance tables — the only rows are the
   structural defaults (6 onboarding keys, 5 built-in focus sounds).
   The free demo keeps the full seed (XP 680, 13 tasks). "Load Demo
   Data" is hidden for logged-in buyers; "Clear All Data" still works
   and the empty defaults are re-seeded on the next rerun.
5. **AppTest could not click the signup/unlock form buttons** (AppTest
   widget-state KeyError when setting form text inputs — a harness quirk,
   not an app error). The same flows were verified directly at function
   level (29/29 worker-C tests + the coordinator's direct tests above).
   **Live browser click-through of signup -> unlock -> logout -> login
   is still required on the deployed URL before listing.**
6. **"AI" is rule-based.** Smart Insights / Breakdown / Day Planner compute
   from the user's own logs; the UI labels them rule-based. No LLM is wired.
7. **Calendar is a downloadable .ics file**, not live 2-way sync; push
   notifications are not live (checklist + copyable reminders only).
8. **Voice input needs a browser with SpeechRecognition**; typed fallback
   is shown otherwise. Soundscapes are named choices + a generated sine-tone
   beep only — no audio files, no copyrighted tracks.
9. **Explore has no map** (no geo data is collected); bar-chart summary
   only. Safe-to-Spend is computed from tracked rows only, formula shown.
10. **SOS / cycle are not medical advice**; SOS is not a crisis service
    (both screens say so).

## 7. Deploy checklist (from HOSTING.md / INTEGRATION_AUTH.md)

1. `py_compile` passes (done, §4 and §8).
2. Push `app.py`, `haveloo_hubs.py`, `haveloo_advance.py`,
   `haveloo_auth.py`, `requirements.txt` to the repo
   `github.com/hamzafidapm/haveloo-adhd-life-os` (see README.md);
   deploy on Streamlit Community Cloud (do NOT commit any `.db` file).
3. On the live URL: create host account -> unlock with a real Etsy order
   number -> log out -> log back in; create a second test account and
   confirm tasks do not leak between accounts. A fresh account must
   start EMPTY (0 tasks, 0 XP — verified headlessly in §8).
4. Decide the Postgres step (limit 3) before the first real buyer.
5. Paste the real app URL into the guide, re-export, verify with
   `pdfinfo`/`pdftotext`, then list ONLY the guide PDF on Etsy.

## 8. Empty fresh accounts — re-verification (2026-11-12, deploy prep)

### What changed in the code

| File | Change |
|---|---|
| `app.py` `init_db()` | Demo seed runs only when no account is logged in (`st.session_state.get(auth.SESSION_EMAIL_KEY)` is empty). A buyer's per-user file is never seeded. |
| `app.py` module-level init | Logged-in buyer → `hubs.seed_hub_defaults()` + `adv.seed_advance_defaults()`; demo mode → full `seed_hubs()` / `seed_advance()` as before. |
| `app.py` `reset_database(reseed=True)` | Now re-seeds base + hub + advance (was base only), so a demo restore is complete again. |
| `app.py` sidebar | "Load Demo Data" button shown in demo mode only; logged-in buyers see a note instead. "Clear All Data" unchanged for everyone. |
| `haveloo_hubs.py` | New `seed_hub_defaults()`: writes ONLY the 6 onboarding key/value defaults (tour not seen, 5 setup steps not done). No demo people, tasks, trips, recipes, money rows. Idempotent. |
| `haveloo_advance.py` | New `seed_advance_defaults()`: writes ONLY the 5 built-in focus sounds (static catalogue, not user data). No demo logs, subscriptions, bills. Idempotent. |
| `haveloo_auth.py` | Docstring in `init_user_db_schema()` updated: fresh accounts are empty; `migrate_to_user_db()` (which nothing calls) is the only way demo rows could ever enter a buyer file. |

### Test results — 59/59 checks passed

Test: `test_empty_accounts.py` (in this folder; NOT in the deploy ZIP),
run with the project venv (`/home/hatch/.venv-st`, streamlit 1.40.0)
against a throwaway copy in `/tmp/empty_test` so no real file is touched.
AppTest runs used `timeout=90` (the app needs longer than the 3 s default).

| Check | Result |
|---|---|
| `py_compile` app.py + haveloo_hubs.py + haveloo_advance.py + haveloo_auth.py + build_guide.py | OK |
| Demo mode: no exception, 17 tabs | PASS |
| Demo mode: tasks 13, XP 680 / coins 145, people 4, recipes 3, bills 4 | PASS (seed unchanged) |
| Buyer account created + unlocked with order `4614332561` | PASS |
| Buyer: no exception, 17 tabs, per-user DB `data/user_10c37e3986af7421.db` created | PASS |
| Buyer: tasks/habits/habit_logs/energy_logs/focus_sessions/dopamine_menu/impulse_vault/brain_dump all 0 | PASS (8/8) |
| Buyer: people/household_tasks/home_inventory/learn_items/trips/career_items/goals_board/money_extra/recipes/grocery_items/meal_plan/countdowns/weekly_resets all 0 | PASS (13/13) |
| Buyer: wellness_log/cycle_log/sos_log/subscriptions/impulse_waitlist/bills/voice_notes all 0 | PASS (7/7) |
| Buyer: XP 0 / coins 0 | PASS |
| Buyer: focus_sounds 5 (catalogue), onboarding 6 (defaults) | PASS |
| Buyer: tab labels exactly the expected 17 | PASS |
| Buyer: themes Apricot, Rosewood, Ocean render, 17 tabs each, no exception | PASS |
| Demo: themes Sage, Lavender render, 17 tabs each, no exception | PASS |
| Buyer: "Load Demo Data" button hidden (0 found in sidebar) | PASS |
| Buyer: "Clear All Data" click → tasks 0, XP 0/coins 0, focus_sounds 5 + onboarding 6 re-seeded, 17 tabs | PASS |
| Demo file untouched after all buyer runs: tasks 13, XP 680 | PASS |
| Live `streamlit run` (port 8503, fresh copy) | HTTP 200; 0 tracebacks in server log |

Notes on the harness: AppTest 1.40 `Tab` objects have no `.click()`, so
tabs cannot be clicked headlessly. That is a harness limit, not an app
gap — Streamlit executes the Python code of EVERY `with tabs[i]:` block
on each run (only the displayed elements are filtered to the active
tab). Proved with a probe script: a `RuntimeError` raised inside the
SECOND tab's block surfaced in `at.exception` on the first run. So the
"no exception" result on the buyer run already proves all 17 tabs'
render code executes cleanly on empty data — including Fill My Day,
Look Back, Apricot tiny-win, Rosewood week strip, charts and KPIs.
**Live browser click-through on the deployed URL is still required
before listing** (signup → unlock → logout → login, plus clicking
through tabs) — see §6 item 5 and §7.

