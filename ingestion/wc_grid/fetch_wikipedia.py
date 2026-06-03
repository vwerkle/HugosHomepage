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
                # Handles formats: "GK", "1GK", "GK", "GKP", "2DF", "DF", "3MF", "4FW", etc.
                for i in range(min(3, len(cell_texts))):
                    upper = cell_texts[i].upper().strip()
                    if 'GK' in upper or 'GKP' in upper or upper == '1':
                        position = 'GK'; break
                    elif 'DF' in upper or 'DEF' in upper or upper in ('D', '2'):
                        position = 'DF'; break
                    elif 'MF' in upper or 'MID' in upper or upper in ('M', '3'):
                        position = 'MF'; break
                    elif ('FW' in upper or 'FOR' in upper or 'ST' in upper
                          or 'ATT' in upper or upper in ('F', '4')):
                        position = 'FW'; break

                # Column 1-4: player name (detect captain before stripping annotation)
                is_captain = False
                for text in cell_texts[1:5]:
                    # Detect captain marker before stripping
                    raw = text.strip()
                    if re.search(r'\(c\)', raw, re.IGNORECASE):
                        is_captain = True
                    # Strip captain/footnote annotations: "(c)", "(Captain)", "[1]", etc.
                    cleaned = re.sub(r'\s*\([^)]{0,20}\)|\s*\[[^\]]*\]', '', raw).strip()
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
                        "is_captain": is_captain,
                        "goals": 0,
                    })

    return players


def _player_id(name: str) -> str:
    """Stable player ID from name."""
    return f"WP_{_strip_accents(name).replace(' ', '_').replace('.', '').replace(chr(39), '')}"


def _make_squad_json(players: list[dict], year: int) -> dict:
    """Clean squad JSON format (v2) replacing the old SPARQL-style format."""
    records = []
    seen: set[str] = set()
    for p in players:
        pid = _player_id(p["name"])
        if pid in seen:
            continue
        seen.add(pid)
        nation_data = NATIONS.get(p["nation"], {})
        nation_qid = nation_data.get("qid", f"Q_UNKNOWN_{p['nation'].replace(' ', '_')}")
        records.append({
            "id": pid,
            "name": p["name"],
            "nation_name": p["nation"],
            "nation_id": nation_qid,
            "position": p["position"],   # GK | DF | MF | FW
            "is_captain": p.get("is_captain", False),
            "goals": p.get("goals", 0),
            "tournament_year": year,
        })
    return {"format": "squad_v2", "year": year, "players": records}


def fetch_match_data(year: int, force: bool = False) -> dict:
    """
    Fetch match-level data (goal scorers, final participants, etc.) from Wikipedia.
    Returns a dict with keys: scorers, final_players, final_scorers, semi_players.
    Falls back to empty data when Wikipedia pages don't exist yet (tournament ongoing).

    Caches to data/wc_grid/raw/match_data_{year}.json.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = RAW_DIR / f"match_data_{year}.json"
    if cache_file.exists() and not force:
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    result: dict = {
        "year": year,
        "scorers": [],          # list of {"name": str, "nation": str, "goals": int}
        "final_players": [],    # list of {"name": str, "nation": str}
        "final_scorers": [],    # list of {"name": str, "nation": str}
        "semi_players": [],     # list of {"name": str, "nation": str}
        "penalty_scorers": [],  # list of {"name": str, "nation": str}
    }

    # Try fetching the tournament statistics page for goal scorers
    stats_pages = [
        f"{year}_FIFA_World_Cup_statistics",
        f"{year}_FIFA_World_Cup_golden_boot",
    ]
    for page in stats_pages:
        try:
            html_content = fetch_wiki_html(page, f"match_stats_{year}_{page.split('_')[-1]}", force=force)
            scorers = _parse_top_scorers_html(html_content)
            if scorers:
                result["scorers"] = scorers
                print(f"    Found {len(scorers)} goal scorers from {page}")
                break
        except Exception:
            pass  # page doesn't exist yet

    # Try fetching the final page
    final_pages = [
        f"{year}_FIFA_World_Cup_final",
        f"{year}_FIFA_World_Cup_Final",
    ]
    for page in final_pages:
        try:
            html_content = fetch_wiki_html(page, f"match_final_{year}", force=force)
            final_data = _parse_match_html(html_content)
            if final_data["players"] or final_data["scorers"]:
                result["final_players"] = final_data["players"]
                result["final_scorers"] = final_data["scorers"]
                print(f"    Found final data: {len(final_data['players'])} players, {len(final_data['scorers'])} scorers")
                break
        except Exception:
            pass

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def _parse_top_scorers_html(html_text: str) -> list[dict]:
    """Extract goal scorers from a tournament statistics or top scorers page."""
    def strip_tags(s: str) -> str:
        return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()

    scorers = []
    # Look for tables with player name + goals columns
    table_matches = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
        html_text, re.DOTALL
    )
    for table in table_matches:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL)
        for row in rows[1:]:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
            texts = [strip_tags(c) for c in cells]
            if len(texts) < 2:
                continue
            # Look for a name + numeric goals pair
            name = None
            goals = 0
            nation = None
            for text in texts:
                cleaned = re.sub(r'\s*\([^)]{0,20}\)', '', text).strip()
                if 3 <= len(cleaned) <= 50 and not cleaned[0].isdigit():
                    if re.match(r"^[\w\s'\-\.À-ÿ]+$", cleaned, re.UNICODE):
                        name = cleaned
            for text in reversed(texts):
                try:
                    goals = int(text.strip())
                    break
                except ValueError:
                    pass
            if name and goals > 0:
                scorers.append({"name": name, "nation": nation or "Unknown", "goals": goals})
    return scorers


def _parse_match_html(html_text: str) -> dict:
    """Extract player names from a match page (final or semifinal)."""
    def strip_tags(s: str) -> str:
        return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()

    players = []
    scorers = []
    # Extract all player links (href=/wiki/PlayerName)
    player_links = re.findall(r'href="/wiki/([^"]+)"[^>]*>([^<]+)</a>', html_text)
    for href, display in player_links:
        display = display.strip()
        if (3 <= len(display) <= 50
                and re.match(r"^[\w\s'\-\.À-ÿ]+$", display, re.UNICODE)
                and display[0].isupper()):
            players.append({"name": display, "nation": "Unknown"})

    return {"players": players[:100], "scorers": scorers}


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

    # Write clean v2 squad JSON (includes position, captain, goals per player)
    _save(RAW_DIR / f"squads_v2_{year}.json", _make_squad_json(players, year))

    return players


def fetch_awards_and_meta(years: list[int]) -> None:
    """Write tournament winners, award winners, and confederation data."""
    # Merge golden boot/glove from all requested years (hardcoded from TOURNAMENT_META)
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
        # Always try to fetch match data (gracefully returns empty if not available)
        print(f"  Fetching match data for {year}...")
        fetch_match_data(year, force=force)
    fetch_awards_and_meta(years)
    print(f"Done. {len(all_players)} player-year entries in {RAW_DIR}/")


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    all_years = sorted(TOURNAMENT_META.keys())
    if not args:
        years = [2026]
    elif args[0] == "all":
        years = all_years
    else:
        years = [int(a) for a in args]

    print(f"Fetching years via Wikipedia: {years}")
    fetch_all(years, force=force)
