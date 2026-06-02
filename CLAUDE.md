# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
cd C:\Users\vince\Documents\projects\HugosHomepage
venv\Scripts\activate
python app.py
```

Runs Waitress on port 5000. In production it's a Windows Service via NSSM. `init_db()` auto-creates all `data/` dirs and JSON files on startup. The site is exposed at vwerkle.com via Cloudflare Tunnel.

## Stack

- **Backend:** Python / Flask 3, Waitress, Jinja2 templates
- **Frontend:** Inline CSS, vanilla JS — no build step, no JS framework
- **Data:** Flat JSON files in `data/` — no database

## Architecture

`app.py` is the entry point. It registers all blueprints and starts Waitress. Route `/` redirects to `misc.landing`.

### Blueprints

| Blueprint | Prefix | Module |
|-----------|--------|--------|
| `misc_bp` | (none) | `blueprints/misc/routes.py` |
| `madness_bp` | `/dness` | `blueprints/pools/madness/routes.py` |
| `random_pool_bp` | `/random-pool` | `blueprints/pools/random_team.py` |
| `moonshot_bp` | `/moonshot` | `blueprints/pools/moonshot.py` |
| `worldcup_bp` | `/worldcup` | `blueprints/pools/worldcup/routes.py` |
| `reservations_bp` | `/reservations` | `blueprints/reservations/` |
| `moneyline_bp` | `/moneyline` | `blueprints/moneyline/` |

### Data patterns

All persistence is flat JSON in `data/`. Each blueprint has its own subdirectory. Files are read/written on every request — no caching layer.

- `data/madness/` — NCAA pick'em: `users.json`, `picks.json`, `daily_spreads.json`
- `data/worldcup/` — World Cup pool: `users.json`, `picks.json`, `games.json`, `config.json`
- `data/misc/` — Source-of-truth text files `Recipes.txt` and `Restaurants.txt` parsed on each request; JSON sidecars are write-only cache
- `data/reservations/` — `config.json` (gitignored), `active_jobs.json`, `history.json`
- `data/moneyline/` — `daily_game.json` (today's decrypted game), `API_REFERENCE.md` (full decryption + scoring docs)

### Auth

Session-based, `secret_key = 'vincent'`. Passwords stored plaintext in `users.json`. Admin gated by `user == 'hugo'` check. Each pool (madness, worldcup) has its own independent session key (`session['wc_user']`, `session['user']`).

### World Cup pool specifics

- Games pulled from football-data.org via admin "Sync" — stored in `games.json` with keys like `fd_12345`
- `is_locked()` compares kickoff UTC string to current time (minute-level precision)
- Picks flow: user stages picks in `localStorage` (`wc_picks_2026`) → clicks "Submit All" → `POST /worldcup/picks/submit` (JSON) → server saves non-locked picks only
- `user_picks` (server picks) passed to Jinja for locked-game display; `DATES_GAMES` JSON blob passed for the JS tray
- Leaderboard hides pre-kickoff picks from other users (`cell.hidden=True`, shows ⚽ if pick exists)

### Recipes.txt format

Custom line-by-line format parsed in `make_json_recipes()`:
- `-Category` — top-level category
- `+Subcategory` — subcategory
- Bare line — title (first), notes (second), image filename (third), date (fourth)
- `#tag1, tag2` — tags
- `>1` — tier (1=best, 3=default)

### Moneyline game (`/moneyline`)

A daily number-guessing game cloned from fromthethink.com/moneyline. 8 rounds per day. No login, no server-side scores — all state in `localStorage`.

**Gameplay change from original:** Instead of Higher/Lower buttons, the player types their actual guess for the number. Scored 0–100 per round based on closeness.

**Scoring (client-side, `static/moneyline/moneyline.js`):**
- *Percentage questions* (question text contains "percent" or "%"): `score = max(0, min(99, 100 - absDiff * 3))` — scored on absolute percentage-point difference. Being 1.7pp off on a 6.7% question → 95 pts.
- *Regular numbers*: `score = max(0, min(99, 100 - pctError * mult))` where `mult` = 1.0 (actual ≤ 50), 1.5 (≤ 500), 2.0 (> 500). Softens penalty for small-number questions like "how many rounds."

**Question source:** `https://timeline-production-6c18.up.railway.app/api/moneyline/daily-game`
- Response has `game_number`, `date` (YYYY-MM-DD), and encrypted `data` field
- AES-256-CBC: key = `SHA256("XkaKm30N51IGGlofzK6pWb9MmyXhdLCr" + date)`, IV = first 16 bytes of decoded ciphertext
- Decrypted payload: `{ rounds: [{ round_number, category, question, line_value, actual_value }] }`
- `line_value` is the original over/under threshold — ignored in our version
- Full decryption recipe + failure mode guide: `data/moneyline/API_REFERENCE.md`

**Scheduler (`blueprints/moneyline/scheduler.py`):** Fetches + decrypts at 5:00 AM ET daily → `data/moneyline/daily_game.json`. On-demand fetch if cache is missing or stale. Uses `pycryptodome` (installed in venv).

**localStorage key:** `moneyline-vwerkle-v1` — stores `{ gameNumber, results, finished, totalScore }`. Replay blocked by matching `gameNumber` to today's game. Clearing localStorage resets progress.

**Share format:**
```
🏈 Moneyline #15
487/800

🟩🟥🟨🟩🟩🟨🟩🟥

vwerkle.com/moneyline
```

### Reservations

Hugo-login gated. Polls Resy (direct API) and OpenTable (Firefox Playwright — Chromium is Cloudflare-blocked) for hard-to-get Philly restaurants. Sends SMS via Twilio on success. Scheduler runs a background thread; snipes at midnight and on calculated release dates (28/30/60 days for Resy, 1st of month for OT). Credentials in `data/reservations/config.json` (gitignored).
