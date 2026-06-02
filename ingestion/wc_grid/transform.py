"""
Transform raw Wikidata SPARQL results into normalized entity tables.
Input:  data/wc_grid/raw/*.json
Output: data/wc_grid/entities.json

Usage:
    python -m ingestion.wc_grid.transform          # 2018 only
    python -m ingestion.wc_grid.transform 2018 2022
    python -m ingestion.wc_grid.transform all
"""

import json
import sys
import unicodedata
from pathlib import Path

RAW_DIR = Path("data/wc_grid/raw")
OUT_FILE = Path("data/wc_grid/entities.json")

TOURNAMENTS_META = {
    1990: "Q132529",
    1994: "Q101751",
    1998: "Q101730",
    2002: "Q47735",
    2006: "Q37285",
    2010: "Q176883",
    2014: "Q79859",
    2018: "Q170645",
    2022: "Q284163",
    2026: "Q5020214",
}

CONFEDERATION_QIDS = {
    "Q35572":  "UEFA",
    "Q58733":  "CONMEBOL",
    "Q168360": "CAF",
    "Q83276":  "AFC",
    "Q160549": "CONCACAF",
    "Q180344": "OFC",
}

GK_POSITION_QID = "Q201330"

# Manually verified confederation fallbacks for common edge cases
# (West Germany uses Germany's entry; Czechoslovakia → UEFA; etc.)
COUNTRY_CONF_FALLBACK: dict[str, str] = {}


def _strip_accents(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


def _qid(uri: str) -> str:
    return uri.split("/")[-1]


def _load(filename: str) -> dict | None:
    p = RAW_DIR / filename
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _rows(data: dict) -> list[dict]:
    return data.get("results", {}).get("bindings", [])


def _val(row: dict, key: str) -> str | None:
    b = row.get(key)
    return b["value"] if b else None


def build_entities(years: list[int]) -> dict:
    """Build normalized entity tables from cached Wikidata data."""

    # ---- confederation map: country_qid → confederation name ----
    conf_data = _load("nation_confederations.json")
    country_to_conf: dict[str, str] = dict(COUNTRY_CONF_FALLBACK)
    if conf_data:
        for row in _rows(conf_data):
            c_qid = _qid(_val(row, "country"))
            conf_qid = _qid(_val(row, "confederation"))
            conf_name = CONFEDERATION_QIDS.get(conf_qid)
            if conf_name:
                country_to_conf[c_qid] = conf_name

    # ---- tournament winner nations: year → country_qid ----
    win_data = _load("tournament_winners.json")
    qid_to_year = {qid: yr for yr, qid in TOURNAMENTS_META.items()}
    winner_by_year: dict[int, str] = {}
    if win_data:
        for row in _rows(win_data):
            t_qid = _qid(_val(row, "tournament"))
            year = qid_to_year.get(t_qid)
            nation_qid = _qid(_val(row, "winnerNation"))
            if year:
                winner_by_year[year] = nation_qid

    # ---- award winners: player_qid → set of achievement strings ----
    award_winners: dict[str, set] = {}
    for key in ("golden_boot", "golden_glove"):
        data = _load(f"award_{key}.json")
        if data:
            for row in _rows(data):
                p_qid = _qid(_val(row, "player"))
                award_winners.setdefault(p_qid, set()).add(key)

    # ---- GK players across all years ----
    gk_players: set[str] = set()
    for year in years:
        pos_data = _load(f"positions_{year}.json")
        if pos_data:
            for row in _rows(pos_data):
                if _qid(_val(row, "position")) == GK_POSITION_QID:
                    gk_players.add(_qid(_val(row, "player")))

    # ---- goals per player per year ----
    goals_by_player_year: dict[tuple, int] = {}
    for year in years:
        g_data = _load(f"goals_{year}.json")
        if g_data:
            for row in _rows(g_data):
                p_qid = _qid(_val(row, "player"))
                try:
                    goals = int(_val(row, "goals"))
                except (TypeError, ValueError):
                    continue
                key = (p_qid, year)
                goals_by_player_year[key] = goals_by_player_year.get(key, 0) + goals

    # ---- main pass: squads ----
    players: dict[str, dict] = {}
    nations: dict[str, dict] = {}
    appearances: list[dict] = []
    achievements: list[dict] = []

    seen_appearances: set[tuple] = set()  # deduplicate (player, year, nation)

    for year in years:
        sq_data = _load(f"squads_{year}.json")
        if not sq_data:
            print(f"  WARNING: no squad data for {year}, skipping")
            continue

        for row in _rows(sq_data):
            p_qid = _qid(_val(row, "player"))
            p_name = _val(row, "playerLabel") or p_qid
            n_qid = _qid(_val(row, "country"))
            n_name = _val(row, "countryLabel") or n_qid

            # Skip malformed results (must have a non-empty entity ID)
            if not p_qid or not n_qid:
                continue

            # Register nation
            if n_qid not in nations:
                nations[n_qid] = {
                    "id": n_qid,
                    "name": n_name,
                    "confederation": country_to_conf.get(n_qid, "UNKNOWN"),
                }

            # Register player (weight = total WC squad appearances)
            if p_qid not in players:
                players[p_qid] = {
                    "id": p_qid,
                    "name": p_name,
                    "search": _strip_accents(p_name),
                    "weight": 0,
                    "is_gk": p_qid in gk_players,
                }
            players[p_qid]["weight"] += 1

            # Deduplicate appearances (Wikidata can have duplicate rows)
            app_key = (p_qid, year, n_qid)
            if app_key in seen_appearances:
                continue
            seen_appearances.add(app_key)

            goals = goals_by_player_year.get((p_qid, year), 0)
            appearances.append({
                "player_id": p_qid,
                "tournament_year": year,
                "nation_id": n_qid,
                "goals": goals,
                "is_gk": p_qid in gk_players,
            })

            # "Won the WC" achievement
            if winner_by_year.get(year) == n_qid:
                achievements.append({
                    "player_id": p_qid,
                    "achievement": "won_wc",
                    "tournament_year": year,
                })

    # After all squads, update is_gk on player records
    for p_qid in gk_players:
        if p_qid in players:
            players[p_qid]["is_gk"] = True

    # Award achievements (attach to players in our dataset only)
    for p_qid, award_set in award_winners.items():
        if p_qid not in players:
            continue  # award winner didn't appear in any fetched tournament
        for award in award_set:
            achievements.append({
                "player_id": p_qid,
                "achievement": award,
                "tournament_year": None,
            })

    # Derived: career goals per player
    career_goals: dict[str, int] = {}
    for (p_qid, _year), g in goals_by_player_year.items():
        career_goals[p_qid] = career_goals.get(p_qid, 0) + g

    for p_qid, total in career_goals.items():
        if total >= 5 and p_qid in players:
            achievements.append({
                "player_id": p_qid,
                "achievement": "career_goals_5plus",
                "tournament_year": None,
            })

    # Derived: played in 3+ World Cups
    wc_count: dict[str, set] = {}
    for app in appearances:
        wc_count.setdefault(app["player_id"], set()).add(app["tournament_year"])
    for p_qid, years_set in wc_count.items():
        if len(years_set) >= 3:
            achievements.append({
                "player_id": p_qid,
                "achievement": "played_3plus_wcs",
                "tournament_year": None,
            })

    return {
        "players": players,
        "nations": nations,
        "appearances": appearances,
        "achievements": achievements,
        "meta": {
            "years_included": sorted(years),
            "player_count": len(players),
            "appearance_count": len(appearances),
            "achievement_count": len(achievements),
            "nations_count": len(nations),
        },
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    all_years = list(range(1990, 2027, 4))

    if not args:
        years = [2018]
    elif args[0] == "all":
        years = all_years
    else:
        years = [int(a) for a in args]

    print(f"Transforming years: {years}")
    entities = build_entities(years)
    m = entities["meta"]
    print(f"  Players:      {m['player_count']}")
    print(f"  Nations:      {m['nations_count']}")
    print(f"  Appearances:  {m['appearance_count']}")
    print(f"  Achievements: {m['achievement_count']}")

    unknown_conf = [
        n for n in entities["nations"].values()
        if n["confederation"] == "UNKNOWN"
    ]
    if unknown_conf:
        print(f"  WARNING: {len(unknown_conf)} nations with unknown confederation:")
        for n in unknown_conf[:10]:
            print(f"    {n['name']} ({n['id']})")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entities, f, indent=2, ensure_ascii=False)
    print(f"Wrote {OUT_FILE}")
