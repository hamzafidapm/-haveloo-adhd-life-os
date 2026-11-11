# INTEGRATION_HUBS.md — wiring `haveloo_hubs.py` into `app.py`

Module: `haveloo_hubs.py` (same folder as `app.py`). **Do NOT edit `app.py`
in this module's task** — these are exact insertion points for the
coordinator's edit pass. Line numbers refer to the verified base `app.py`
(7 tabs, 1,892 lines) as read 2026-11-12. `app.py` itself was NOT changed.

Verified 2026-11-12: `python3 -m py_compile haveloo_hubs.py` passes.
Headless tests (temp SQLite DB in `/tmp`, no Streamlit) pass — see
"Verification" at the bottom. **Not yet verified: a live `streamlit run`
smoke test** — Streamlit is not installed in this VM, so the parent /
coordinator must run the app once and click through the new tabs before
delivery.

## 0. How the module is built (so the integration stays correct)

- The module does **not** import `app.py` and does **not** import Streamlit
  at module level (Streamlit is not installed in this VM). Every render
  function takes `st` as its first argument plus an open `sqlite3`
  connection: `render_people(st, conn)`. Plotly is imported lazily inside
  `render_explore` only, with an `st.bar_chart` fallback.
- Connection ownership: the **caller opens and closes** the connection
  (the `get_conn()` pattern from `app.py`). Module functions **COMMIT after
  each write but never close** the connection they were given — except
  `render_guided_tour` / `render_onboarding_checklist`, which accept
  `conn=None` and then open (and close) the DB file next to this module
  themselves. Prefer passing `conn` from `app.py` for those two as well.
- XP/coins inside the module go through its own `award_hub_xp(conn, xp,
  coins)`, which reuses the passed connection and mirrors
  `app.py::award_xp_and_coins` exactly. Do NOT swap in
  `award_xp_and_coins` inside these functions — that opens a second
  connection to a DB the caller already holds.
- Every button in every render function does a real DB write + `st.toast`
  + `st.rerun`. There are no dead buttons and no placeholder copy.
- Pure, headless-testable helpers (no `st`): `order_day_plan(tasks,
  energy_label)`, `calculate_bounce_back_hub(conn)` (a copy of
  `app.py::calculate_bounce_back_score`, not an import), `award_hub_xp`,
  `_debt_info(row)`.
- All wording is Haveloo's own original wording. No competitor branding or
  text is copied, and no live URL is invented anywhere in the module.
  The Explore hub deliberately has **no map**: it is a list + bar-chart
  summary, because the planner collects no geo data — a real map would need
  location data the app does not have.

## 1. Import — after line 9 of app.py

```python
import streamlit as st
import haveloo_hubs as hubs   # <-- ADD: Tier 1 hubs + Money/Meals deepening
```

## 2. Initialise + seed — immediately after line 776 (`init_db()`)

```python
init_db()

# --- Tier 1 hub tables (haveloo_hubs) ---
_hub_conn = get_conn()
hubs.init_hub_tables(_hub_conn)
hubs.seed_hubs(_hub_conn)   # seeds ONLY empty tables; safe to run every launch
_hub_conn.close()
```

`seed_hubs()` is idempotent (verified: seeding twice changes no counts).
Seed sizes: 4 people, 4 household tasks, 4 inventory items, 4 learn items,
3 trips, 5 career items, 5 goals_board rows (1 vision + 4 year-map
quarters), 7 money_extra rows (1 budget, 2 savings jars, 2 debts, 2
subscriptions), 3 recipes, 3 grocery items, 3 meal-plan days, 2 countdowns,
1 weekly-reset log row, 6 onboarding rows (tour flag + 5 checklist steps).
Demo persona matches `app.py` (Alex, Q4 proposal, Etsy shop, Lake District).

## 3. New tabs — extend the `st.tabs([...])` list at lines 953–966

The 7 base tabs stay first. Append these 5 labels, in this order — they
become **tabs 8–12** (`tabs[7]`–`tabs[11]`):

```python
tabs = st.tabs(
    [
        "🎯 Command Center",
        "⏱️ Focus & Time-Blindness",
        "🍨 Dopamine Menu",
        "🌱 Zero-Guilt Habits",
        "🛡️ Impulse-Buy Vault",
        "📥 Brain Dump Triage",
        "📊 Executive Analytics",
        "👥 People",        # <-- ADD (tab 8)
        "🏠 Household",     # <-- ADD (tab 9)
        "📚 Learn",         # <-- ADD (tab 10)
        "🌍 Explore",       # <-- ADD (tab 11)
        "💼 Career",        # <-- ADD (tab 12)
    ]
)
```

This matches `INTEGRATION_ADVANCE.md`: the advance module's tabs are
numbered on the assumption that these 5 hub tabs sit at `tabs[7]`–
`tabs[11]`, with the advance tabs following at `tabs[12]`–`tabs[16]`
(tabs 13–17). Do not renumber the advance tabs.

## 4. Tab bodies — append AFTER the Tab 7 block that starts at line 1670

(`with tabs[6]:`, file ends at line 1892.) Add these blocks at the end of
`app.py`, in this order. Each block opens its own connection and closes it,
following the pattern already used inside the Tab 7 block.

```python
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
```

## 5. Where the deepening / planner-system renders go

These are NOT separate tabs — they slot into existing tabs, so the tab
count stays at 12 (+ 5 advance tabs = 17 total). Suggested homes:

| Render function | Suggested home | Why |
|---|---|---|
| `hubs.render_money_deepening(st, conn)` | New section inside Tab 5 (Impulse-Buy Vault, `with tabs[4]:`, from line 1505), after the vault columns — or its own sub-header in Tab 5 | Money lives with the vault; Budget Battery / Savings Jars / Debt / Subscriptions / Safe-to-Spend extend it |
| `hubs.render_meals(st, conn)` | New section inside Tab 4 (Zero-Guilt Habits, `with tabs[3]:`, from line 1415) or Tab 1 side column | Meals are a daily routine; habits tab is the closest home. Do NOT put it in the Dopamine Menu tab (food rewards ≠ meal planning) |
| `hubs.render_fill_my_day(st, conn)` | Top of Tab 1 (Command Center, `with tabs[0]:`, from line 969), above "Active Focus: NOW (Big 3)" | It writes the Big 3, so it must sit where the Big 3 is visible |
| `hubs.render_look_back(st, conn)` | Bottom of Tab 7 (Executive Analytics, `with tabs[6]:`, from line 1670), after Row 3 charts | It is the month/year review companion to the analytics charts |
| `hubs.render_guided_tour(st)` | Very top of Tab 1 (Command Center), before the KPI strip | First-run onboarding; the expander stays collapsed once `tour_seen = 1` |
| `hubs.render_onboarding_checklist(st)` | Directly under `render_guided_tour` in Tab 1 | Same first-run flow; checkboxes persist in the `onboarding` table |
| `hubs.render_countdowns_weekly_reset(st, conn)` | Bottom of Tab 1 (Command Center), after the task creator column | Countdowns + Weekly Reset are day-planning tools; Weekly Reset moves Big 3 tasks, so it belongs with them |
| `hubs.render_vision_yearmap(st, conn)` | Bottom of Tab 7 (Executive Analytics), after `render_look_back` | Vision board + year map are the forward-looking companion to Look Back |

All of the above accept `(st, conn)` except `render_guided_tour` and
`render_onboarding_checklist`, which accept `(st, conn=None)` — pass the
open `conn` when calling them from `app.py` (e.g.
`hubs.render_guided_tour(st, _conn)`).

## 6. Session state keys

**No new `st.session_state` keys are needed.** The module reads only
existing keys indirectly (the theme comes in through `PLOTLY_TEMPLATE`,
passed to `render_explore`) and stores onboarding answers in the
`onboarding` DB table, not in session state:

| `onboarding` key | Meaning |
|---|---|
| `tour_seen` | `"1"` once the quiz has been submitted |
| `quiz_struggle`, `quiz_energy`, `quiz_goal`, `quiz_theme` | Guided-tour answers |
| `onboarding_step_1` … `onboarding_step_5` | Setup checklist ticks (`"1"`/`"0"`) |
| `emergency_contacts` | Household emergency-contacts note (Household tab) |

## 7. Tables

### Created by `init_hub_tables` (14 tables)

| Table | Purpose |
|---|---|
| `people` | People hub (catch-up, birthdays, gift ideas) |
| `household_tasks` | Cleaning schedule / chore chart / declutter zones |
| `home_inventory` | Home inventory + low-stock flags |
| `learn_items` | Bookshelf / courses / skill roadmaps |
| `trips` | Explore hub (itineraries, packing JSON, bucket flag) |
| `career_items` | Side hustles / income / contacts / CV notes |
| `goals_board` | Vision board (`kind='vision'`) + year map (`kind='yearmap'`, `detail` = Q1–Q4) |
| `money_extra` | Budget Battery + Savings Jars + Debts + Subscriptions (`kind` column; debt rate/min-payment in `extra_json`) |
| `recipes` | Recipe book with calories + macros |
| `grocery_items` | Auto grocery list (built from planned recipes) |
| `meal_plan` | Weekly meal plan (`day` UNIQUE, `recipe_id`) |
| `countdowns` | Countdown events |
| `weekly_resets` | Weekly Reset log (`reset_date`, `moved_count`) |
| `onboarding` | Guided-tour answers, checklist, emergency-contacts note |

### Reused from `app.py` (read; written only where noted)

| Table | Used by | Write? |
|---|---|---|
| `tasks` | `render_fill_my_day` (reads Todo, writes Big 3 priorities), `render_countdowns_weekly_reset` (Weekly Reset demotes old Big 3), `render_look_back` (counts Done) | Yes — priority updates only, never deletes tasks |
| `energy_logs` | `render_fill_my_day` (latest row sets the energy label), `render_look_back` (top mood) | No |
| `impulse_vault` | `render_money_deepening` (Cooling Off list + Resisted action), `render_look_back` (money saved) | Yes — status `Cooling Off` → `Resisted & Saved` only |
| `user_stats` | `award_hub_xp` (XP/coins, same formula as `app.py`) | Yes — XP/coins only |
| `habits`, `habit_logs` | `calculate_bounce_back_hub` (14-day consistency + bounce-back, copied logic) | No |
| `focus_sessions` | `render_look_back` (focus minutes) | No |

### No-collision note for the coordinator

`haveloo_advance.py` (Tier 2) creates its own `subscriptions`,
`impulse_waitlist` and `bills` tables. This module's subscription audit
lives in `money_extra` (`kind='subscription'`) and its impulse list reuses
`app.py`'s `impulse_vault` — different tables, no collision. Do not merge
them: the advance module's Money Guard and this module's Money deepening
are separate features that happen to share a theme.

## 8. Known limits (honest)

- **Explore has no map.** The bar chart summarises trips by status; a real
  world map needs geo data the planner does not collect. Nothing in the UI
  claims a map exists.
- **Safe-to-Spend is not a bank balance.** It is `total monthly budgets −
  spent so far − subscriptions`, computed only from rows tracked in this
  module. The formula is shown in a caption under the number.
- **Debt orders need 2+ debts.** With fewer than two debts the module says
  so instead of showing a meaningless comparison.
- **"Decide for me" writes to today's plan.** The random pick is saved into
  `meal_plan` for today, so the choice survives a reload.
- **Weekly Reset only moves tasks created before today.** A Big 3 task
  created today is never demoted by the reset.
- **Live `streamlit run` check still outstanding** (Streamlit is not
  installed in this VM). The coordinator must run the app and click every
  new tab/button once before delivery.

## 9. Verification

Commands run 2026-11-12 (test script at `/tmp/test_haveloo_hubs.py`,
temp DB `/tmp/haveloo_hubs_test.db` — both outside the workspace, not
deliverables):

```
cd ~/workspace/adhd-planner/streamlit-app
python3 -m py_compile haveloo_hubs.py        # PASSED
python3 /tmp/test_haveloo_hubs.py            # ALL HEADLESS TESTS PASSED
```

Results:

- Seed row counts (all > 0): people 4, household_tasks 4, home_inventory 4,
  learn_items 4, trips 3, career_items 5, goals_board 5, money_extra 7,
  recipes 3, grocery_items 3, meal_plan 3, countdowns 2, weekly_resets 1,
  onboarding 6.
- Idempotency: running `seed_hubs` a second time changed no table's count.
- `order_day_plan`: Low energy → short/low-energy tasks first
  (`Tidy desk`, `Email replies`, `Big report`); High energy → highest XP
  first (`Big report`, `Email replies`, `Tidy desk`).
- Debt ordering: snowball = smallest balance first, avalanche = highest
  interest first; a swapped fixture proves the two orders can differ.
- `calculate_bounce_back_hub`: 13/14 habit-days → consistency 92.9%,
  bounce-back 100.0% (missed day recovered next day).
- `award_hub_xp`: xp 680 → 705, coins 145 → 155 for +25 XP / +10 coins.
- Stub-`st` smoke test: all 13 render functions execute end-to-end
  (`render_people`, `render_household`, `render_learn`, `render_explore`,
  `render_career`, `render_money_deepening`, `render_meals`,
  `render_fill_my_day`, `render_look_back`, `render_guided_tour`,
  `render_onboarding_checklist`, `render_countdowns_weekly_reset`,
  `render_vision_yearmap`). Buttons return False in the stub, so this
  proves the render paths run without errors — it does NOT prove the live
  button writes; that needs the live `streamlit run` check above.
- `app.py` was not edited. No stray files left behind (a 0-byte
  `adhd_life_os.db` created by the stub test's default-connection path was
  removed; the folder contains no `.db` file from this task).
