"""
Wikidata SPARQL ingestion for FIFA Men's World Cup data (1990-2026).
Caches raw results to data/wc_grid/raw/ -- never re-fetches if cache exists.

Usage:
    python -m ingestion.wc_grid.fetch          # fetch 2018 only
    python -m ingestion.wc_grid.fetch 2018 2022
    python -m ingestion.wc_grid.fetch all      # fetch all editions
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
RAW_DIR = Path("data/wc_grid/raw")
USER_AGENT = "WCImmaculateGrid/1.0 (vincentwerkle@gmail.com; educational project)"

# Tournament QIDs and their "team at this WC" class QIDs
TOURNAMENTS = {
    1990: {"tournament": "Q132529",  "team_class": "Q12202543"},
    1994: {"tournament": "Q101751",  "team_class": "Q25165455"},
    1998: {"tournament": "Q101730",  "team_class": "Q16515674"},
    2002: {"tournament": "Q47735",   "team_class": "Q20379572"},
    2006: {"tournament": "Q37285",   "team_class": "Q12038181"},
    2010: {"tournament": "Q176883",  "team_class": "Q12641786"},
    2014: {"tournament": "Q79859",   "team_class": "Q20436354"},
    2018: {"tournament": "Q170645",  "team_class": "Q54812340"},
    2022: {"tournament": "Q284163",  "team_class": "Q111535559"},
    2026: {"tournament": "Q5020214", "team_class": "Q133699200"},
}

AWARD_QIDS = {
    "golden_boot":  "Q15916917",
    "golden_glove": "Q17351855",
}

CONFEDERATION_QIDS = {
    "UEFA":     "Q35572",
    "CONMEBOL": "Q58733",
    "CAF":      "Q168360",
    "AFC":      "Q83276",
    "CONCACAF": "Q160549",
    "OFC":      "Q180344",
}

GK_POSITION_QID = "Q201330"


def _sparql(query: str, cache_key: str, force: bool = False) -> dict:
    """Execute a SPARQL query against Wikidata, caching the result to disk."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = RAW_DIR / f"{cache_key}.json"

    if cache_file.exists() and not force:
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    # Wikidata enforces 1 req/min during outage; 70s is safe under all conditions.
    time.sleep(70)
    params = urllib.parse.urlencode({"query": query.strip(), "format": "json"})
    url = f"{SPARQL_ENDPOINT}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
        },
    )

    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                wait = 90 * (attempt + 1)
                print(f"    Rate limited (429), waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
        except urllib.error.URLError:
            if attempt < 4:
                time.sleep(30)
            else:
                raise

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    return data


def fetch_squads(year: int, force: bool = False) -> dict:
    """All players in all squads for a given World Cup year."""
    tc = TOURNAMENTS[year]["team_class"]
    query = f"""
SELECT ?team ?teamLabel ?player ?playerLabel ?country ?countryLabel WHERE {{
  ?team wdt:P31 wd:{tc} .
  ?team wdt:P17 ?country .
  ?team wdt:P710 ?player .
  ?player wdt:P31 wd:Q5 .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
"""
    return _sparql(query, f"squads_{year}", force=force)


def fetch_player_positions(year: int, force: bool = False) -> dict:
    """Football positions for players in a given WC (to identify GKs)."""
    tc = TOURNAMENTS[year]["team_class"]
    query = f"""
SELECT DISTINCT ?player ?position WHERE {{
  ?team wdt:P31 wd:{tc} .
  ?team wdt:P710 ?player .
  ?player wdt:P413 ?position .
}}
"""
    return _sparql(query, f"positions_{year}", force=force)


def fetch_goals(year: int, force: bool = False) -> dict:
    """Goals scored per player at a tournament (via qualifier on P710 statement)."""
    tc = TOURNAMENTS[year]["team_class"]
    query = f"""
SELECT ?player ?goals WHERE {{
  ?team wdt:P31 wd:{tc} .
  ?team p:P710 ?stmt .
  ?stmt ps:P710 ?player ;
        pq:P1351 ?goals .
}}
"""
    return _sparql(query, f"goals_{year}", force=force)


def fetch_award_winners(award_key: str, force: bool = False) -> dict:
    """All-time winners of a specific WC award (Golden Boot, Golden Glove)."""
    award_qid = AWARD_QIDS[award_key]
    query = f"""
SELECT DISTINCT ?player ?playerLabel ?tournament ?tournamentLabel WHERE {{
  ?player p:P166 ?stmt .
  ?stmt ps:P166 wd:{award_qid} .
  OPTIONAL {{ ?stmt pq:P805 ?tournament }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
"""
    return _sparql(query, f"award_{award_key}", force=force)


def fetch_tournament_winners(force: bool = False) -> dict:
    """Winning country per tournament via P1346 on the tournament item."""
    t_list = " ".join(f"wd:{v['tournament']}" for v in TOURNAMENTS.values())
    query = f"""
SELECT ?tournament ?winnerNation WHERE {{
  VALUES ?tournament {{ {t_list} }}
  ?tournament wdt:P1346 ?winnerTeam .
  ?winnerTeam wdt:P17 ?winnerNation .
}}
"""
    return _sparql(query, "tournament_winners", force=force)


def fetch_nation_confederations(force: bool = False) -> dict:
    """Confederation for every national football team's country via P463."""
    conf_list = " ".join(f"wd:{qid}" for qid in CONFEDERATION_QIDS.values())
    query = f"""
SELECT DISTINCT ?country ?confederation WHERE {{
  VALUES ?confederation {{ {conf_list} }}
  ?nationalTeam wdt:P31 wd:Q6979593 ;
                wdt:P17 ?country ;
                wdt:P463 ?confederation .
}}
"""
    return _sparql(query, "nation_confederations", force=force)


def fetch_finalists(force: bool = False) -> dict:
    """Countries that played in a WC Final (winners + runners-up)."""
    t_list = " ".join(f"wd:{v['tournament']}" for v in TOURNAMENTS.values())
    query = f"""
SELECT ?tournament ?finalistTeam ?finalistNation WHERE {{
  VALUES ?tournament {{ {t_list} }}
  ?final wdt:P361 ?tournament ;
         wdt:P31 wd:Q17299750 .
  ?final wdt:P1923 ?finalistTeam .
  ?finalistTeam wdt:P17 ?finalistNation .
}}
"""
    return _sparql(query, "finalists", force=force)


def fetch_all(years: list[int], force: bool = False) -> None:
    for year in years:
        print(f"  Squads {year}...")
        r = fetch_squads(year, force=force)
        n = len(r.get("results", {}).get("bindings", []))
        print(f"    {n} rows")

        print(f"  Positions {year}...")
        fetch_player_positions(year, force=force)

        print(f"  Goals {year}...")
        fetch_goals(year, force=force)

    print("  Award: Golden Boot...")
    fetch_award_winners("golden_boot", force=force)

    print("  Award: Golden Glove...")
    fetch_award_winners("golden_glove", force=force)

    print("  Tournament winners...")
    fetch_tournament_winners(force=force)

    print("  Confederation memberships...")
    fetch_nation_confederations(force=force)

    print("  WC Finalists...")
    fetch_finalists(force=force)

    print(f"Done. Raw data in {RAW_DIR}/")


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    if not args or args == ["all"]:
        years = list(TOURNAMENTS.keys()) if args == ["all"] else [2018]
    else:
        years = [int(a) for a in args]

    print(f"Fetching years: {years}  (force={force})")
    fetch_all(years, force=force)
