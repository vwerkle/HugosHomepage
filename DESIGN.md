# WC Grid — Design Document

World Cup Immaculate Grid clone. Daily 3×3 guessing game where each cell needs a footballer who satisfies both its row and column criterion.

---

## Data Model

### Entities (produced by `ingestion/wc_grid/transform.py`)

| Entity | Key fields |
|--------|-----------|
| `players` | `id`, `name`, `search` (accent-stripped), `weight` (career WC squad appearances), `is_gk` |
| `nations` | `id`, `name`, `confederation` (UEFA/CONMEBOL/CAF/AFC/CONCACAF/OFC) |
| `appearances` | `player_id`, `tournament_year`, `nation_id`, `goals`, `is_gk` |
| `achievements` | `player_id`, `achievement`, `tournament_year` |

### Achievement keys

| Key | Meaning |
|-----|---------|
| `won_wc` | In the squad of the WC-winning nation that year |
| `golden_boot` | Won the tournament's top scorer award |
| `golden_glove` | Won the tournament's best goalkeeper award |
| `played_3plus_wcs` | Appeared in 3+ WC squads across all editions |
| `career_goals_5plus` | 5+ career WC goals (sparse — not reliably captured) |

---

## Criterion Catalog

| Type | Example value | Label |
|------|--------------|-------|
| `nation` | `Q183` (Germany) | "Played for Germany" |
| `tournament` | `2018` | "In the 2018 World Cup" |
| `confederation` | `UEFA` | "UEFA (Europe)" |
| `achievement` | `won_wc` | "Won the World Cup" |
| `is_gk` | `True` | "Goalkeeper" |

### Grid generation rules
- Nation/confederation criteria go on **one axis only** (rows XOR cols)
- Tournament/achievement/is_gk criteria go on **the other axis**
- No criterion appears on both axes
- No more than 1 confederation or 1 achievement type per axis
- All 9 cells must have ≥3 valid players

### Rarity scoring
Score per correct guess = `round(99 × (1 - rank / (total - 1)))` where `rank` is the player's position sorted by `weight` ascending among all valid players in that cell. Most obscure = 99, most famous = 1. Total max = 891 (9 × 99).

---

## Data Pipeline

```
Wikipedia (squads page HTML)
  ↓  ingestion/wc_grid/fetch_wikipedia.py
data/wc_grid/raw/   (HTML cache + SPARQL-style JSONs)
  ↓  ingestion/wc_grid/transform.py
data/wc_grid/entities.json
  ↓  ingestion/wc_grid/generate_grids.py
wc-grid/public/data/bundle.json
  ↓  npm run build (in wc-grid/)
static/wc-grid/     (served by Flask at /wc-grid)
```

### Player IDs
- Wikipedia-sourced data uses `WP_<accent_stripped_name>` IDs (e.g., `WP_kylian_mbappe`)
- If Wikidata SPARQL becomes available, QIDs (e.g., `Q180057`) can replace these; a re-run of the pipeline regenerates the bundle

### Wikidata SPARQL (future / when available)
The Wikidata SPARQL endpoint (`https://query.wikidata.org/sparql`) was rate-limited at ingestion time (active outage). `ingestion/wc_grid/fetch.py` is a full SPARQL-based alternative to `fetch_wikipedia.py`. Running it when the endpoint recovers will produce richer data (Wikidata QID-based player IDs, more reliable GK/goal data).

---

## Bundle Format

`wc-grid/public/data/bundle.json` (static, included in Vite build):

```json
{
  "players": [
    { "id": "WP_...", "name": "Kylian Mbappé", "search": "kylian mbappe", "weight": 2 }
  ],
  "grids": {
    "2026-06-02": {
      "rows": [{"type": "tournament", "value": 2018, "label": "In the 2018 World Cup"}],
      "cols": [{"type": "nation", "value": "Q183", "label": "Played for Germany"}],
      "cells": [{"valid": ["WP_manuel_neuer", ...], "rarity": [85, ...]}]
    }
  },
  "meta": { "generated": "...", "grid_count": 400, "player_count": 5575 }
}
```

---

## Frontend State (localStorage)

Key: `wc-grid-vwerkle-v1`

```json
{
  "date": "2026-06-02",
  "cellStates": [{"status": "correct", "playerId": "WP_...", "playerName": "...", "rarityScore": 72}],
  "usedPlayerIds": ["WP_..."],
  "finished": false,
  "totalScore": 0
}
```
