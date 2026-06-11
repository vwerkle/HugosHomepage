# Statline — Daily Match-the-Statline Game

Available at `/statline`. Each day picks one baseball player and one football player; players guess OTHER players whose career stats match the target's.

---

## How to run

Normal app startup — no extra steps. CSVs are loaded into memory when the blueprint registers.

```
cd C:\Users\vince\Documents\projects\HugosHomepage
venv\Scripts\activate
python app.py
```

Place your CSV files at `data/statline/baseball.csv` and `data/statline/football.csv` before starting. The sample CSVs at those same paths are placeholders — replace them with real exports from Baseball Reference and Pro Football Reference.

---

## CSV schemas

### baseball.csv

One row per player. Pitchers and hitters live in the same file, differentiated by `position`.

| Column | Required | Notes |
|---|---|---|
| `player_id` | ✓ | Unique identifier (e.g. Baseball Reference ID) |
| `player_name` | ✓ | Display name |
| `position` | ✓ | `SP` or `Hitter` |
| `gs` | SP only | Career games started (2000–2025) |
| `wins` | SP only | Career wins |
| `so` | SP only | Career strikeouts |
| `era` | SP only | Career ERA (float, e.g. `3.28`) |
| `ab` | Hitter only | Career at-bats |
| `h` | Hitter only | Career hits |
| `hr` | Hitter only | Career home runs |
| `sb` | Hitter only | Career stolen bases |

Leave inapplicable columns blank (not zero — blank). The engine treats blank as null and excludes the player from that stat's guess pool.

### football.csv

One row per player, position = `QB`, `RB`, or `WRTE`.

| Column | Required | Notes |
|---|---|---|
| `player_id` | ✓ | Unique identifier (e.g. PFR ID) |
| `player_name` | ✓ | Display name |
| `position` | ✓ | `QB`, `RB`, or `WRTE` |
| `pass_att` | QB only | Career pass attempts |
| `pass_yds` | QB | Career passing yards |
| `pass_td` | QB | Career passing TDs |
| `int` | QB | Career interceptions thrown |
| `carries` | RB only | Career rush attempts |
| `rush_yds` | RB | Career rushing yards |
| `rush_td` | RB | Career rushing TDs |
| `rec` | RB / WRTE | Career receptions |
| `rec_yds` | RB / WRTE | Career receiving yards |
| `rec_td` | RB / WRTE | Career receiving TDs |

RBs may have `rec`/`rec_yds`/`rec_td` filled in — they can be valid guesses for WR/TE receiving-yards categories and vice versa.

---

## Config reference (`blueprints/statline/config.py`)

| Key | Default | Purpose |
|---|---|---|
| `TIMEZONE` | `"America/New_York"` | Midnight reset timezone |
| `GAME_EPOCH` | `"2026-06-01"` | Day 0; `game_number = days_since + 1` |
| `SCORING.MAX_PER_CATEGORY` | `100` | Base points for a perfect guess |
| `SCORING.EXACT_BONUS_THRESHOLD` | `0.02` | pct_off ≤ this → add EXACT_BONUS |
| `SCORING.EXACT_BONUS` | `25` | Bonus points for near-exact guess; max/cat = 125 |
| `SCORING.ZERO_EPSILON` | `0.001` | Denominator guard when target stat == 0 |
| `AUTOCOMPLETE_MAX` | `20` | Max suggestions returned per query |
| `TARGET_THRESHOLDS` | see config | Min career totals for a player to be eligible as a daily target |
| `CSV_COLUMNS` | see config | Map logical stat names to your actual CSV column headers |

### Category definitions

Edit `SPORTS` in `config.py` to change positions, categories, or stat labels. Each category needs: `key` (logical stat name matching `CSV_COLUMNS`), `label` (display string), `fmt` (`.2f` for decimals, `d` for integers).

---

## Scoring

Per category:
- `t` = target's career value
- `R` = closest non-target player's value (best achievable; revealed after each guess)
- `best_gap = abs(R - t)`
- `gap = abs(guess_value - t)`
- `excess = max(0, gap - best_gap)`
- `pct_off = excess / abs(t)`
- `base = round(100 * max(0, 1 - pct_off))`
- If `pct_off <= 0.02`: `base += 25`

Max per category: **125**. Max per sport (3 cats): **375**. Max total (2 sports): **750**.

Guessing the best-achievable player always scores 125.

---

## How to add a sport (v2+)

1. Add a new top-level key to `SPORTS` in `config.py` with the same shape as `baseball`/`football` (label, emoji, positions list, per-position threshold + categories).
2. Add a matching entry to `CSV_COLUMNS`.
3. Drop `data/statline/{sport_key}.csv` with the documented schema.
4. Restart the app — no code changes needed.

---

## Share format

Single sport:
```
⚾ Statline #7
213/375

⚾ 🟩🟨🟩

vwerkle.com/statline
```

Combined (both sports):
```
⚾🏈 Statline #7
450/750

⚾ 🟩🟨🟩
🏈 🟥🟩🟩

vwerkle.com/statline
```

Emoji tiers: 🟩 ≥ 80% of max, 🟨 ≥ 40%, 🟥 < 40%.
