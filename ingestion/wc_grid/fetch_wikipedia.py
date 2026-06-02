"""
Alternative ingestion via Wikipedia (MediaWiki API) + hardcoded awards.
Produces the same raw cache files as fetch.py but without Wikidata SPARQL.
Use this when the Wikidata SPARQL endpoint is unavailable.

Generates:
  data/wc_grid/raw/squads_{year}.json    (same schema as SPARQL fetcher)
  data/wc_grid/raw/positions_{year}.json
  data/wc_grid/raw/goals_{year}.json
  data/wc_grid/raw/tournament_winners.json
  data/wc_grid/raw/award_golden_boot.json
  data/wc_grid/raw/award_golden_glove.json
  data/wc_grid/raw/nation_confederations.json

Usage:
    python -m ingestion.wc_grid.fetch_wikipedia 2018
    python -m ingestion.wc_grid.fetch_wikipedia all
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

RAW_DIR = Path("data/wc_grid/raw")
USER_AGENT = "WCGrid/1.0 (vincentwerkle@gmail.com; educational project)"

# ── Wikidata QIDs for nations (for transform.py compatibility) ────────────
# Maps nation name (as it appears in Wikipedia squad pages) → Wikidata QID + confederation
NATIONS: dict[str, dict] = {
    "Algeria": {"qid": "Q262", "confederation": "CAF"},
    "Argentina": {"qid": "Q414", "confederation": "CONMEBOL"},
    "Australia": {"qid": "Q408", "confederation": "AFC"},
    "Belgium": {"qid": "Q31", "confederation": "UEFA"},
    "Brazil": {"qid": "Q155", "confederation": "CONMEBOL"},
    "Cameroon": {"qid": "Q1009", "confederation": "CAF"},
    "Chile": {"qid": "Q298", "confederation": "CONMEBOL"},
    "Colombia": {"qid": "Q739", "confederation": "CONMEBOL"},
    "Costa Rica": {"qid": "Q800", "confederation": "CONCACAF"},
    "Croatia": {"qid": "Q224", "confederation": "UEFA"},
    "Czech Republic": {"qid": "Q213", "confederation": "UEFA"},
    "Czechia": {"qid": "Q213", "confederation": "UEFA"},
    "Denmark": {"qid": "Q35", "confederation": "UEFA"},
    "Ecuador": {"qid": "Q736", "confederation": "CONMEBOL"},
    "Egypt": {"qid": "Q79", "confederation": "CAF"},
    "England": {"qid": "Q21", "confederation": "UEFA"},
    "France": {"qid": "Q142", "confederation": "UEFA"},
    "Germany": {"qid": "Q183", "confederation": "UEFA"},
    "Ghana": {"qid": "Q117", "confederation": "CAF"},
    "Greece": {"qid": "Q41", "confederation": "UEFA"},
    "Honduras": {"qid": "Q783", "confederation": "CONCACAF"},
    "Hungary": {"qid": "Q28", "confederation": "UEFA"},
    "Iran": {"qid": "Q794", "confederation": "AFC"},
    "Italy": {"qid": "Q38", "confederation": "UEFA"},
    "Ivory Coast": {"qid": "Q1008", "confederation": "CAF"},
    "Côte d'Ivoire": {"qid": "Q1008", "confederation": "CAF"},
    "Jamaica": {"qid": "Q766", "confederation": "CONCACAF"},
    "Japan": {"qid": "Q17", "confederation": "AFC"},
    "Mexico": {"qid": "Q96", "confederation": "CONCACAF"},
    "Morocco": {"qid": "Q1028", "confederation": "CAF"},
    "Netherlands": {"qid": "Q55", "confederation": "UEFA"},
    "New Zealand": {"qid": "Q664", "confederation": "OFC"},
    "Nigeria": {"qid": "Q1033", "confederation": "CAF"},
    "North Korea": {"qid": "Q423", "confederation": "AFC"},
    "Panama": {"qid": "Q804", "confederation": "CONCACAF"},
    "Paraguay": {"qid": "Q733", "confederation": "CONMEBOL"},
    "Peru": {"qid": "Q419", "confederation": "CONMEBOL"},
    "Poland": {"qid": "Q36", "confederation": "UEFA"},
    "Portugal": {"qid": "Q45", "confederation": "UEFA"},
    "Republic of Ireland": {"qid": "Q27", "confederation": "UEFA"},
    "Russia": {"qid": "Q159", "confederation": "UEFA"},
    "Saudi Arabia": {"qid": "Q851", "confederation": "AFC"},
    "Senegal": {"qid": "Q1041", "confederation": "CAF"},
    "Serbia": {"qid": "Q403", "confederation": "UEFA"},
    "Slovakia": {"qid": "Q214", "confederation": "UEFA"},
    "Slovenia": {"qid": "Q215", "confederation": "UEFA"},
    "South Korea": {"qid": "Q884", "confederation": "AFC"},
    "Korea Republic": {"qid": "Q884", "confederation": "AFC"},
    "Spain": {"qid": "Q29", "confederation": "UEFA"},
    "Sweden": {"qid": "Q34", "confederation": "UEFA"},
    "Switzerland": {"qid": "Q39", "confederation": "UEFA"},
    "Togo": {"qid": "Q945", "confederation": "CAF"},
    "Trinidad and Tobago": {"qid": "Q754", "confederation": "CONCACAF"},
    "Tunisia": {"qid": "Q948", "confederation": "CAF"},
    "Ukraine": {"qid": "Q212", "confederation": "UEFA"},
    "United States": {"qid": "Q30", "confederation": "CONCACAF"},
    "USA": {"qid": "Q30", "confederation": "CONCACAF"},
    "Uruguay": {"qid": "Q77", "confederation": "CONMEBOL"},
    "Wales": {"qid": "Q25", "confederation": "UEFA"},
    # Historical / alternate names
    "West Germany": {"qid": "Q713750", "confederation": "UEFA"},
    "Soviet Union": {"qid": "Q15180", "confederation": "UEFA"},
    "Yugoslavia": {"qid": "Q83286", "confederation": "UEFA"},
    "Czechoslovakia": {"qid": "Q33946", "confederation": "UEFA"},
    "Zaire": {"qid": "Q974", "confederation": "CAF"},
    "United Arab Emirates": {"qid": "Q878", "confederation": "AFC"},
    "China PR": {"qid": "Q148", "confederation": "AFC"},
    "China": {"qid": "Q148", "confederation": "AFC"},
    "IR Iran": {"qid": "Q794", "confederation": "AFC"},
    "Northern Ireland": {"qid": "Q26", "confederation": "UEFA"},
    "Scotland": {"qid": "Q22", "confederation": "UEFA"},
    "Canada": {"qid": "Q16", "confederation": "CONCACAF"},
    "Bolivia": {"qid": "Q750", "confederation": "CONMEBOL"},
    "Venezuela": {"qid": "Q717", "confederation": "CONMEBOL"},
    "Angola": {"qid": "Q916", "confederation": "CAF"},
    "Guinea": {"qid": "Q1006", "confederation": "CAF"},
    "Qatar": {"qid": "Q846", "confederation": "AFC"},
    "Ecuador": {"qid": "Q736", "confederation": "CONMEBOL"},
    "Cameroon": {"qid": "Q1009", "confederation": "CAF"},
    "Turkiye": {"qid": "Q43", "confederation": "UEFA"},
    "Turkey": {"qid": "Q43", "confederation": "UEFA"},
    "South Africa": {"qid": "Q258", "confederation": "CAF"},
    "United States": {"qid": "Q30", "confederation": "CONCACAF"},
    "Honduras": {"qid": "Q783", "confederation": "CONCACAF"},
    "El Salvador": {"qid": "Q792", "confederation": "CONCACAF"},
    "Haiti": {"qid": "Q790", "confederation": "CONCACAF"},
    "Cuba": {"qid": "Q241", "confederation": "CONCACAF"},
    "Kuwait": {"qid": "Q817", "confederation": "AFC"},
    "Iraq": {"qid": "Q796", "confederation": "AFC"},
    "UAE": {"qid": "Q878", "confederation": "AFC"},
    "Morocco": {"qid": "Q1028", "confederation": "CAF"},
    "Zambia": {"qid": "Q953", "confederation": "CAF"},
    "DR Congo": {"qid": "Q974", "confederation": "CAF"},
    "Republic of Korea": {"qid": "Q884", "confederation": "AFC"},
}

# ── Per-tournament authoritative data ────────────────────────────────────
TOURNAMENT_META: dict[int, dict] = {
    1990: {
        "qid": "Q132529",
        "wiki_page": "1990_FIFA_World_Cup_squads",
        "winner": "West Germany",
        "golden_boot": [("Salvatore Schillaci", "Italy")],
        "golden_glove": None,
    },
    1994: {
        "qid": "Q101751",
        "wiki_page": "1994_FIFA_World_Cup_squads",
        "winner": "Brazil",
        "golden_boot": [("Hristo Stoichkov", "Bulgaria"), ("Oleg Salenko", "Russia")],
        "golden_glove": None,
    },
    1998: {
        "qid": "Q101730",
        "wiki_page": "1998_FIFA_World_Cup_squads",
        "winner": "France",
        "golden_boot": [("Davor Šuker", "Croatia")],
        "golden_glove": None,
    },
    2002: {
        "qid": "Q47735",
        "wiki_page": "2002_FIFA_World_Cup_squads",
        "winner": "Brazil",
        "golden_boot": [("Ronaldo", "Brazil")],
        "golden_glove": None,
    },
    2006: {
        "qid": "Q37285",
        "wiki_page": "2006_FIFA_World_Cup_squads",
        "winner": "Italy",
        "golden_boot": [("Miroslav Klose", "Germany")],
        "golden_glove": [("Gianluigi Buffon", "Italy")],
    },
    2010: {
        "qid": "Q176883",
        "wiki_page": "2010_FIFA_World_Cup_squads",
        "winner": "Spain",
        "golden_boot": [("Thomas Müller", "Germany"), ("David Villa", "Spain"), ("Wesley Sneijder", "Netherlands"), ("Diego Forlán", "Uruguay")],
        "golden_glove": [("Iker Casillas", "Spain")],
    },
    2014: {
        "qid": "Q79859",
        "wiki_page": "2014_FIFA_World_Cup_squads",
        "winner": "Germany",
        "golden_boot": [("James Rodríguez", "Colombia")],
        "golden_glove": [("Manuel Neuer", "Germany")],
    },
    2018: {
        "qid": "Q170645",
        "wiki_page": "2018_FIFA_World_Cup_squads",
        "winner": "France",
        "golden_boot": [("Harry Kane", "England")],
        "golden_glove": [("Thibaut Courtois", "Belgium")],
    },
    2022: {
        "qid": "Q284163",
        "wiki_page": "2022_FIFA_World_Cup_squads",
        "winner": "Argentina",
        "golden_boot": [("Kylian Mbappé", "France")],
        "golden_glove": [("Emiliano Martínez", "Argentina")],
    },
    2026: {
        "qid": "Q5020214",
        "wiki_page": "2026_FIFA_World_Cup_squads",
        "winner": None,  # in progress
        "golden_boot": [],
        "golden_glove": [],
    },
}


def _strip_accents(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


def _get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if attempt < 2:
                time.sleep(5)
            else:
                raise


def fetch_wiki_html(page: str, cache_key: str, force: bool = False) -> str:
    """Fetch Wikipedia page HTML via the parse API, cached to disk."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = RAW_DIR / f"{cache_key}.html"
    if cache_file.exists() and not force:
        return cache_file.read_text(encoding="utf-8")

    params = urllib.parse.urlencode({
        "action": "parse",
        "page": page,
        "prop": "text",
        "format": "json",
        "disableeditsection": "1",
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    data = json.loads(_get(url))
    content = data.get("parse", {}).get("text", {}).get("*", "")
    cache_file.write_text(content, encoding="utf-8")
    print(f"    Cached {cache_key}.html ({len(content)//1024} KB)")
    return content


def parse_squads_html(html_text: str, year: int) -> list[dict]:
    """
    Parse the HTML of a 'YEAR FIFA World Cup squads' Wikipedia page.
    Returns list of {"name": str, "nation": str, "position": str, "goals": int}.

    Table column layout (typical):
      No. | Pos | Player | Date of birth (age) | Caps | Goals | Club
    We read position (col 1), name (col 2), goals (col 5 if >= 7 cols).
    Goals are intentionally NOT parsed here — the caps column is too similar
    and causes false positives. Use authoritative award data for top scorers.
    """
    def strip_tags(s: str) -> str:
        s = re.sub(r'<[^>]+>', '', s)
        return html.unescape(s).strip()

    players: list[dict] = []

    # Split on h2/h3 tags to get team sections
    sections = re.split(r'<h[23][^>]*>', html_text)

    current_nation = None
    for section in sections:
        # The section starts with the (remaining) header text before the first tag
        header_raw = re.match(r'^(.*?)(?=<)', section, re.DOTALL)
        if header_raw:
            header_text = strip_tags(header_raw.group(1)).strip()
            # Try exact match, then normalised match
            if header_text in NATIONS:
                current_nation = header_text
            else:
                # Try span-based header (Wikipedia often wraps in <span>)
                span_match = re.search(r'<span[^>]*id="([^"]+)"', section[:300])
                if span_match:
                    span_id = span_match.group(1).replace('_', ' ')
                    if span_id in NATIONS:
                        current_nation = span_id

        if current_nation is None:
            continue

        # Parse all wikitables in this section
        table_matches = re.findall(
            r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
            section, re.DOTALL
        )
        for table in table_matches:
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL)
            for row in rows[1:]:  # skip header
                cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
                if len(cells) < 3:
                    continue
                cell_texts = [strip_tags(c) for c in cells]

                # Skip header rows
                if any(t in ('Pos', 'Player', 'Name', '#', 'No.', 'No') for t in cell_texts[:3]):
                    continue

                position = None
                name = None

                # Column 0 or 1: position code
                for i in range(min(3, len(cell_texts))):
                    upper = cell_texts[i].upper().strip()
                    if upper in ('GK', 'GKP', '1'):
                        position = 'GK'; break
                    elif upper in ('DF', 'DEF', 'D', '2'):
                        position = 'DF'; break
                    elif upper in ('MF', 'MID', 'M', '3'):
                        position = 'MF'; break
                    elif upper in ('FW', 'FOR', 'F', 'ST', 'ATT', '4'):
                        position = 'FW'; break

                # Column 1-4: player name
                for text in cell_texts[1:5]:
                    # Strip captain/footnote annotations: "(c)", "(Captain)", "[1]", etc.
                    cleaned = re.sub(r'\s*\([^)]{0,20}\)|\s*\[[^\]]*\]', '', text).strip()
                    # Name: 3-50 chars, letters + spaces + hyphens + apostrophes + accented
                    if (3 <= len(cleaned) <= 50
                            and re.match(r"^[\w\s'\-\.À-ÿ]+$", cleaned, re.UNICODE)
                            and not cleaned[0].isdigit()
                            and not cleaned.upper() in ('GK','DF','MF','FW')):
                        name = cleaned
                        break

                if name and current_nation:
                    players.append({
                        "name": name,
                        "nation": current_nation,
                        "position": position or "DF",
                        "goals": 0,  # not parsed from HTML (unreliable); use award data instead
                    })

    return players


def _make_sparql_style_squads(players: list[dict], year: int) -> dict:
    """Convert parsed players into the SPARQL-style JSON format expected by transform.py."""
    bindings = []
    for i, p in enumerate(players):
        nation_data = NATIONS.get(p["nation"], {})
        nation_qid = nation_data.get("qid", f"Q_UNKNOWN_{p['nation'].replace(' ', '_')}")
        # Use a Wikipedia-page-like ID for the player: prefix with 'WP_' + normalized name
        player_id = f"WP_{_strip_accents(p['name']).replace(' ', '_').replace('.', '').replace(chr(39), '')}"
        bindings.append({
            "player": {"type": "uri", "value": f"http://www.wikidata.org/entity/{player_id}"},
            "playerLabel": {"type": "literal", "value": p["name"]},
            "country": {"type": "uri", "value": f"http://www.wikidata.org/entity/{nation_qid}"},
            "countryLabel": {"type": "literal", "value": p["nation"]},
        })
    return {"results": {"bindings": bindings}}


def _make_sparql_style_positions(players: list[dict]) -> dict:
    GK_QID = "Q201330"
    bindings = []
    seen = set()
    for p in players:
        if p["position"] != "GK":
            continue
        player_id = f"WP_{_strip_accents(p['name']).replace(' ', '_').replace('.', '').replace(chr(39), '')}"
        if player_id in seen:
            continue
        seen.add(player_id)
        bindings.append({
            "player": {"type": "uri", "value": f"http://www.wikidata.org/entity/{player_id}"},
            "position": {"type": "uri", "value": f"http://www.wikidata.org/entity/{GK_QID}"},
        })
    return {"results": {"bindings": bindings}}


def _make_sparql_style_goals(players: list[dict]) -> dict:
    bindings = []
    for p in players:
        if p["goals"] <= 0:
            continue
        player_id = f"WP_{_strip_accents(p['name']).replace(' ', '_').replace('.', '').replace(chr(39), '')}"
        bindings.append({
            "player": {"type": "uri", "value": f"http://www.wikidata.org/entity/{player_id}"},
            "goals": {"type": "literal", "value": str(p["goals"])},
        })
    return {"results": {"bindings": bindings}}


def _make_award_json(award_players: list[tuple[str, str]]) -> dict:
    """award_players = list of (player_name, nation_name)"""
    bindings = []
    for name, _nation in award_players:
        player_id = f"WP_{_strip_accents(name).replace(' ', '_').replace('.', '').replace(chr(39), '')}"
        bindings.append({
            "player": {"type": "uri", "value": f"http://www.wikidata.org/entity/{player_id}"},
            "playerLabel": {"type": "literal", "value": name},
        })
    return {"results": {"bindings": bindings}}


def _make_tournament_winners_json() -> dict:
    bindings = []
    for year, meta in TOURNAMENT_META.items():
        winner = meta.get("winner")
        if not winner:
            continue
        nation_qid = NATIONS.get(winner, {}).get("qid")
        if not nation_qid:
            continue
        bindings.append({
            "tournament": {"type": "uri", "value": f"http://www.wikidata.org/entity/{meta['qid']}"},
            "winnerNation": {"type": "uri", "value": f"http://www.wikidata.org/entity/{nation_qid}"},
        })
    return {"results": {"bindings": bindings}}


def _make_confederation_json() -> dict:
    CONF_QIDS = {
        "UEFA": "Q35572", "CONMEBOL": "Q58733", "CAF": "Q168360",
        "AFC": "Q83276", "CONCACAF": "Q160549", "OFC": "Q180344",
    }
    seen = set()
    bindings = []
    for nation_name, data in NATIONS.items():
        qid = data["qid"]
        conf = data["confederation"]
        if qid in seen:
            continue
        seen.add(qid)
        bindings.append({
            "country": {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"},
            "confederation": {"type": "uri", "value": f"http://www.wikidata.org/entity/{CONF_QIDS[conf]}"},
        })
    return {"results": {"bindings": bindings}}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def fetch_year(year: int, force: bool = False) -> list[dict]:
    """Fetch and parse squads for one tournament year. Returns list of player dicts."""
    meta = TOURNAMENT_META.get(year)
    if not meta:
        raise ValueError(f"Unknown year: {year}")

    print(f"  Fetching {year} squads from Wikipedia...")
    html_text = fetch_wiki_html(meta["wiki_page"], f"wiki_squads_{year}", force=force)
    players = parse_squads_html(html_text, year)
    print(f"    Parsed {len(players)} players for {year}")

    if not players:
        print(f"    WARNING: No players parsed for {year}! Check HTML parser.")
        return []

    # Write SPARQL-compatible cache files
    _save(RAW_DIR / f"squads_{year}.json", _make_sparql_style_squads(players, year))
    _save(RAW_DIR / f"positions_{year}.json", _make_sparql_style_positions(players))
    _save(RAW_DIR / f"goals_{year}.json", _make_sparql_style_goals(players))

    return players


def fetch_awards_and_meta(years: list[int]) -> None:
    """Write tournament winners, award winners, and confederation data."""
    # Merge golden boot/glove from all requested years
    gb_players: list[tuple] = []
    gg_players: list[tuple] = []
    for year in years:
        meta = TOURNAMENT_META.get(year, {})
        gb_players.extend(meta.get("golden_boot") or [])
        gg_players.extend(meta.get("golden_glove") or [])

    _save(RAW_DIR / "award_golden_boot.json", _make_award_json(gb_players))
    _save(RAW_DIR / "award_golden_glove.json", _make_award_json(gg_players))
    _save(RAW_DIR / "tournament_winners.json", _make_tournament_winners_json())
    _save(RAW_DIR / "nation_confederations.json", _make_confederation_json())
    print(f"  Wrote award/winner/confederation files")


def fetch_all(years: list[int], force: bool = False) -> None:
    all_players = []
    for year in years:
        players = fetch_year(year, force=force)
        all_players.extend(players)
    fetch_awards_and_meta(years)
    print(f"Done. {len(all_players)} player-year entries in {RAW_DIR}/")


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    all_years = sorted(TOURNAMENT_META.keys())
    if not args:
        years = [2018]
    elif args[0] == "all":
        years = all_years
    else:
        years = [int(a) for a in args]

    print(f"Fetching years via Wikipedia: {years}")
    fetch_all(years, force=force)
