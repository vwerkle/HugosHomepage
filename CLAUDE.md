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

### Data patterns

All persistence is flat JSON in `data/`. Each blueprint has its own subdirectory. Files are read/written on every request — no caching layer.

- `data/madness/` — NCAA pick'em: `users.json`, `picks.json`, `daily_spreads.json`
- `data/worldcup/` — World Cup pool: `users.json`, `picks.json`, `games.json`, `config.json`
- `data/misc/` — Source-of-truth text files `Recipes.txt` and `Restaurants.txt` parsed on each request; JSON sidecars are write-only cache
- `data/reservations/` — `config.json` (gitignored), `active_jobs.json`, `history.json`

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

### Reservations

Hugo-login gated. Polls Resy (direct API) and OpenTable (Firefox Playwright — Chromium is Cloudflare-blocked) for hard-to-get Philly restaurants. Sends SMS via Twilio on success. Scheduler runs a background thread; snipes at midnight and on calculated release dates (28/30/60 days for Resy, 1st of month for OT). Credentials in `data/reservations/config.json` (gitignored).
