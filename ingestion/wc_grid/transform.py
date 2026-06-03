"""
Transform raw Wikipedia-fetched squad data into normalized entity tables.
Input:  data/wc_grid/raw/squads_v2_{year}.json  (v2 format from fetch_wikipedia.py)
        data/wc_grid/raw/match_data_{year}.json  (match-level data)
        data/wc_grid/raw/award_*.json, tournament_winners.json, nation_confederations.json
Output: data/wc_grid/entities.json

Usage:
    python -m ingestion.wc_grid.transform          # 2026 only (default)
    python -m ingestion.wc_grid.transform 2026
    python -m ingestion.wc_grid.transform all      # all available years
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


def _strip_accents(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


def _load(filename: str) -> dict | None:
    p = RAW_DIR / filename
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _qid(uri: str) -> str:
    return uri.split("/")[-1]


def _rows(data: dict) -> list[dict]:
    return data.get("results", {}).get("bindings", [])


def _val(row: dict, key: str) -> str | None:
    b = row.get(key)
    return b["value"] if b else None


def _player_id(name: str) -> str:
    return f"WP_{_strip_accents(name).replace(' ', '_').replace('.', '').replace(chr(39), '')}"


def build_entities(years: list[int]) -> dict:
    """Build normalized entity tables from cached fetch data."""

    # ---- confederation map: country_qid → confederation name ----
    conf_data = _load("nation_confederations.json")
    country_to_conf: dict[str, str] = {}
    if conf_data:
        for row in _rows(conf_data):
            c_qid = _qid(_val(row, "country"))
            conf_qid = _qid(_val(row, "confederation"))
            conf_name = CONFEDERATION_QIDS.get(conf_qid)
            if conf_name:
                country_to_conf[c_qid] = conf_name

    # ---- tournament winner nations ----
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

    # ---- award winners (golden boot / glove) ----
    award_winners: dict[str, set] = {}
    for key in ("golden_boot", "golden_glove"):
        data = _load(f"award_{key}.json")
        if data:
            for row in _rows(data):
                p_qid = _qid(_val(row, "player"))
                award_winners.setdefault(p_qid, set()).add(key)

    # ---- main pass: squads ----
    players: dict[str, dict] = {}
    nations: dict[str, dict] = {}
    appearances: list[dict] = []
    achievements: list[dict] = []
    seen_appearances: set[tuple] = set()

    for year in years:
        # Try v2 format first (produced by fetch_wikipedia.py)
        squad_v2 = _load(f"squads_v2_{year}.json")
        if squad_v2 and squad_v2.get("format") == "squad_v2":
            _process_squad_v2(squad_v2, year, players, nations, appearances,
                              achievements, seen_appearances, country_to_conf, winner_by_year)
        else:
            print(f"  WARNING: no squad data for {year}, skipping")
            continue

        # Load match-level data (goals, finals, etc.)
        match_data = _load(f"match_data_{year}.json")
        if match_data:
            _process_match_data(match_data, year, players, achievements)

    # ---- post-pass: award achievements ----
    for p_id, award_set in award_winners.items():
        if p_id not in players:
            continue
        for award in award_set:
            achievements.append({
                "player_id": p_id,
                "achievement": award,
                "tournament_year": None,
            })

    # ---- derived: played in 3+ WCs (if multi-year data present) ----
    if len(years) > 1:
        wc_count: dict[str, set] = {}
        for app in appearances:
            wc_count.setdefault(app["player_id"], set()).add(app["tournament_year"])
        for p_id, years_set in wc_count.items():
            if len(years_set) >= 3:
                achievements.append({
                    "player_id": p_id,
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


def _process_squad_v2(
    squad_v2: dict,
    year: int,
    players: dict,
    nations: dict,
    appearances: list,
    achievements: list,
    seen_appearances: set,
    country_to_conf: dict,
    winner_by_year: dict,
) -> None:
    """Process a v2-format squad JSON into entity tables."""
    for p in squad_v2.get("players", []):
        p_id = p["id"]
        n_id = p["nation_id"]
        n_name = p["nation_name"]
        pos = p.get("position", "DF")
        is_gk = (pos == "GK")

        # Register nation
        if n_id not in nations:
            nations[n_id] = {
                "id": n_id,
                "name": n_name,
                "confederation": country_to_conf.get(n_id, "UNKNOWN"),
            }

        # Register player
        if p_id not in players:
            players[p_id] = {
                "id": p_id,
                "name": p["name"],
                "search": _strip_accents(p["name"]),
                "weight": 0,
                "is_gk": is_gk,
                "position": pos,
                "is_captain": p.get("is_captain", False),
            }
        else:
            # Update weight (career appearances) and captain flag if set
            if p.get("is_captain"):
                players[p_id]["is_captain"] = True
        players[p_id]["weight"] += 1

        # Deduplicate appearances
        app_key = (p_id, year, n_id)
        if app_key in seen_appearances:
            continue
        seen_appearances.add(app_key)
        appearances.append({
            "player_id": p_id,
            "tournament_year": year,
            "nation_id": n_id,
            "goals": p.get("goals", 0),
            "is_gk": is_gk,
        })

        # "Won the WC" achievement
        if winner_by_year.get(year) == n_id:
            achievements.append({
                "player_id": p_id,
                "achievement": "won_wc",
                "tournament_year": year,
            })


def _process_match_data(
    match_data: dict,
    year: int,
    players: dict,
    achievements: list,
) -> None:
    """Convert match-level data (goals, finals) into achievements."""
    # Goal scorers → scored_wc_goal
    scored_ids: set[str] = set()
    for scorer in match_data.get("scorers", []):
        p_id = _player_id(scorer["name"])
        if p_id in players and p_id not in scored_ids:
            scored_ids.add(p_id)
            achievements.append({
                "player_id": p_id,
                "achievement": "scored_wc_goal",
                "tournament_year": year,
            })

    # Final players → played_in_final
    for fp in match_data.get("final_players", []):
        p_id = _player_id(fp["name"])
        if p_id in players:
            achievements.append({
                "player_id": p_id,
                "achievement": "played_in_final",
                "tournament_year": year,
            })

    # Final scorers → scored_in_final
    for fs in match_data.get("final_scorers", []):
        p_id = _player_id(fs["name"])
        if p_id in players:
            achievements.append({
                "player_id": p_id,
                "achievement": "scored_in_final",
                "tournament_year": year,
            })

    # Semifinal players → played_in_semis
    for sp in match_data.get("semi_players", []):
        p_id = _player_id(sp["name"])
        if p_id in players:
            achievements.append({
                "player_id": p_id,
                "achievement": "played_in_semis",
                "tournament_year": year,
            })

    # Penalty scorers → scored_penalty
    for pp in match_data.get("penalty_scorers", []):
        p_id = _player_id(pp["name"])
        if p_id in players:
            achievements.append({
                "player_id": p_id,
                "achievement": "scored_penalty",
                "tournament_year": year,
            })


if __name__ == "__main__":
    args = sys.argv[1:]
    all_years = [2026]  # default: 2026 only

    if not args:
        years = [2026]
    elif args[0] == "all":
        years = sorted(TOURNAMENTS_META.keys())
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
        for n in unknown_conf[:5]:
            print(f"    {n['name']} ({n['id']})")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entities, f, indent=2, ensure_ascii=False)
    print(f"Wrote {OUT_FILE}")
