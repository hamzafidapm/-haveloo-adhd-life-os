# Haveloo ADHD Life OS — Build Plan (Streamlit code, user-sent)

Status 2026-11-12 02:53 PKT: BLOCKED — Part 1 only received, Part 2 missing.
Do NOT build the finished product on Part 1 alone; it ends mid-file.

UPDATE 2026-11-12 ~03:05 PKT — STEP 1 VERIFIED, BUILD IN PROGRESS:
- Second paste (02:56) IS the full code: transcribed to app.py (1887 lines after
  theme work), py_compile OK, pyflakes clean except unused `math` import (removed),
  Streamlit server HTTP 200 with no errors, AppTest headless run: NO exception,
  7 tabs, 49 buttons, 14 metrics, DB seeded exactly (XP 680, coins 145, 13 tasks /
  8 done / Big 3 = 3, 5 habits, 60 habit logs, 42 energy logs, 7 focus sessions).
- MERGED 6-THEME SYSTEM implemented (correction 03:03 — ONE picker, themes ARE
  the modes): Cocoa Light Warm Comfort, Sage Dark Calm/Anxiety Relief, Apricot
  Light Mood Lift, Lavender Light Relax/Night Rest, Ocean Dark Deep Focus,
  Rosewood Light Reflect/Look Back. Each has own palette + real behaviour
  (Sage hides extras + breathing cue, Ocean hides queue/sidebar extras + focus
  card, Apricot tiny win/step, Rosewood week strip, Cocoa gentle line, Lavender
  evening note). Contrast checked by script: ALL themes pass WCAG >= 4.5
  (lowest Lavender sub/bg 4.74). AppTest all 6 themes: no exceptions, 7 tabs,
  theme bg present in CSS. Dyslexia font + large text options in sidebar, work
  in all themes. Honest not-medical-advice note under picker. No second Mode
  picker (separate mood system was never built — nothing to remove).
- requirements.txt written (streamlit 1.40.0, pandas 2.2.2, plotly 5.24.1).
- Delegated 2026-11-12 ~03:06 PKT to 3 builders (modules + integration notes,
  app.py NOT edited by them): (A) haveloo_hubs.py Tier 1 hubs + Money/Meals +
  Fill My Day + Look Back + tour/onboarding + countdowns/weekly reset/vision;
  (B) haveloo_advance.py Tier 2 AI rule-based + calendar .ics + voice + Focus Pro
  + SOS/Cycle/Sleep + subscriptions/bills/waitlist + print/backup; (C)
  haveloo_auth.py account/unlock/per-user DB + HOSTING.md + AUTH_DESIGN.md +
  Quick_Start_Guide.pdf. Coordinator to wire modules in + verify after they return.
- WORKER C DONE 03:13 PKT (verified by coordinator): haveloo_auth.py (36.6 KB,
  py_compile OK), HOSTING.md, AUTH_DESIGN.md, INTEGRATION_AUTH.md,
  Quick_Start_Guide.pdf (2 pp, Letter, placeholder "YOUR APP LINK" present 1x,
  pdfinfo OK), build_guide.py. 29/29 headless auth tests passed (incl. plaintext
  password NOT in DB file, unlock format check + stored record, no live Etsy API
  claim). Per-user DB chosen: data/user_<sha256(email)[:16]>.db. Live Streamlit
  auth UI NOT yet tested in a browser — coordinator must test login→unlock→
  logout→login on the deployed URL.
- WORKER B DONE 03:14 PKT (verified by coordinator): haveloo_advance.py
  (1,640 lines, py_compile OK, 10 render_* functions, 0 http strings),
  INTEGRATION_ADVANCE.md. Headless tests passed (seed counts exact + idempotent,
  .ics has BEGIN:VCALENDAR + VEVENT, backup/restore 81 rows). 3 deliberate
  non-DB buttons documented (Break it down / Build my day plan compute to
  session_state, Save writes DB; SOS Next breath advances on-screen step).
  reset_database() in app.py does NOT yet clear advance tables — coordinator to
  add the DELETEs when wiring. Worker A (hubs) still running at 03:14 PKT;
  haveloo_hubs.py file already present (97,554 bytes) but its report not yet
  received — do NOT touch it until worker A reports.
- WORKER A DONE 03:15 PKT. COORDINATOR WIRING + VERIFICATION COMPLETE
  2026-11-12 ~03:20 PKT — see VERIFICATION.md in the same folder. app.py now
  2,109 lines, 17 tabs, all modules wired (imports, routed get_conn(),
  reset_database extended, hub/advance init+seed, auth gate before any
  planner data, deepening slotted into Tabs 1/4/5/7). Verified: py_compile
  clean; AppTest gate-only (planner hidden), demo mode 17 tabs / 37 metrics /
  194 buttons, logged-in 17 tabs + per-user DB with 13 tasks; all 6 themes
  clean on wired app; live streamlit run HTTP 200, 0 tracebacks; auth direct
  tests pass (incl. per-user isolation + no plaintext password in DB).
  Quick Start Guide PDF (2 pp) has the "YOUR APP LINK" placeholder — do NOT
  list until the real Streamlit Cloud URL is pasted in and the PDF re-exported.
  Remaining before listing: deploy, live browser signup→unlock→logout→login
  click-through, second-account leak check, Postgres decision.

## What Part 1 contains (verified from pasted code)
- Stack: Python, Streamlit, SQLite (`adhd_life_os.db`), pandas, Plotly.
- Page: "ADHD Life OS | Neuro-Adaptive Command Center", dark theme, custom CSS cards/badges.
- DB tables: user_stats (xp/coins/level = 1 + xp//250), tasks, habits, habit_logs,
  energy_logs, focus_sessions, dopamine_menu, impulse_vault, brain_dump.
- Demo seed: xp 680, coins 145, 5 tasks (Big 3 + Next + Parking), 8 completed tasks,
  5 habits, 14 days habit/energy logs, 7 focus sessions, 8 dopamine items, 3 impulse items.
- 7 tabs:
  1. Command Center — Big 3 (max 3), micro-step splitter + templates, Next/Parking, creator.
  2. Focus & Time-Blindness — 5/15/25/45 min presets, visual timer, distraction catcher.
  3. Dopamine Menu — Appetizer / Side / Entree / Dessert, coins redeem.
  4. Zero-Guilt Habits — Bounce-Back score (not streak-shame), 14-day consistency.
  5. Impulse-Buy Vault — 24/48/72/168h cooldown, saved total, resist +50 XP.
  6. Brain Dump Triage — promote to NOW / Queue / dismiss.
  7. Executive Analytics — STARTED only: Chart 1 Energy vs Focus 14-day, Chart 2 Peak
     Biological Focus Window (Morning/Afternoon/Evening).

## What is MISSING (end of pasted code)
- Pasted code ends mid-Tab 7, after the Peak Focus chart, at a lone `#` comment.
- Missing: Analytics charts 3-6 (per header "6 INTERACTIVE CHARTS"), any further tabs/
  sections, file end. Charts likely intended: life-domain balance, routine adherence,
  distraction patterns, impulse-shield performance (per Tab 7 caption).
- Missing from repo: `requirements.txt` (streamlit/pandas/plotly versions), README,
  any auth / hosting config. None was sent.
- Action needed from user: send the REST of the .py file as a FILE UPLOAD (.py or ZIP),
  not pasted text — paste truncates. Then verify with `python -m py_compile` + a
  Streamlit smoke run before any feature work.

## Build scope once full code arrives (user-confirmed)
### Tier 1 — match FrameworkPlanningCo (listing 4599889742)
- 5 new hubs as new tabs/sections: People, Household, Learn, Explore, Career.
  Each needs its own DB table(s) + seed data + UI, same dark styling, no dead buttons.
- Foggy-day mode + Low-battery mode: one-tap filter hiding everything except today's
  top 3 / must-dos.
- Fill My Day (smart): place tasks by energy + time available; unfinished carries over.
- Look Back: auto month/year review (tasks done, mood, money saved, wins).
- Guided tour + 2-min onboarding quiz (ADHD type, energy, goals) that configures the app.
- Money deepening: Budget Battery, Savings Jars, Debt snowball/avalanche, Impulse List,
  Sub Audit, Safe-to-Spend. Meals deepening: recipes with photos, calories/macros,
  auto grocery list, "Decide for me".
- Competitor features to add: focus timer with soundscapes, countdowns, weekly reset,
  vision board + year map, gift ideas bank, cleaning/chore/inventory, world map + trips,
  side hustle + CV, text size up to 5x, calm mode (no animations), quiet hours.

### Tier 2 — beat the competitor (advance)
- AI features (rule-based first, no fake AI claims): AI Task Breakdown, AI Day Planner,
  AI Insights (mood/sleep/energy/cycle correlations from logged data).
- Real notifications / calendar hooks: Google/Apple Calendar export (.ics) first;
  live 2-way sync only if credentials/hosting allow — do NOT claim it until verified.
- Voice task add: browser speech input where supported; fallback to quick-add.
- Focus Pro: soundscapes (rain/white noise/lo-fi via hosted audio, not bundled
  copyrighted tracks), Hyperfocus guard (break reminders), Body Doubling timer.
- Impulse Waitlist 48h + Subscription Tracker with alerts + Bill Reminders.

### Haveloo's own strengths — KEEP, do not drop
- Rewards/Points/Streaks (XP, coins, levels), Pomodoro Pro, SOS button, Task Breakdown,
  Cycle x ADHD insights, Sleep/Water/Medicine tracking, Print/PDF Export.
- Professional polish: consistent fonts (readable sans + dyslexia-friendly option),
  no typos/placeholders, Sage Calm theme option alongside the existing dark theme,
  mobile-responsive layout, every button wired, KPIs recomputed from real data.

## Delivery — EXACTLY like FrameworkPlanningCo (user-confirmed 2026-11-12)
- Etsy listing file = ONLY 1 PDF: Quick Start Guide (Haveloo branding).
- Guide contains an "Open my planner" link to the HOSTED Haveloo app.
- Buyer flow (2 min, once only): create account (email + password) → unlock with
  Etsy order number → then just log in on any other device. No codes/keys to copy.
- Lifetime access, free updates, no subscription.
- HONEST LIMIT — to resolve during build, not to hide: true automatic verification
  of an Etsy order number needs Etsy API access / seller-side order lookup. V1 must
  state clearly how unlock is checked (e.g. order-number format + stored record for
  seller verification) and must NOT claim live Etsy API verification until it is
  actually built and tested. Same for cross-device sync: current code is local
  SQLite only — sync needs a hosted DB per account (not a local .db file), plus
  hosted deployment (e.g. Streamlit Cloud). The hosted app, not the .py file,
  is what the buyer opens.
- Excel ZIP delivery is REPLACED by this flow unless the user later says to keep
  Excel as a bonus. Do not ship both flows without asking.

## Verification before delivery
- `python -m py_compile` clean; Streamlit smoke run, all tabs open, no dead buttons.
- KPIs / charts recomputed from seed data; timer counts down; add/complete flows work.
- Login → unlock → logout → login flow tested end-to-end on the hosted link.
- Quick Start Guide PDF: link clickable, steps match the real app screens.
