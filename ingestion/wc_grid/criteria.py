"""
Criterion definitions and predicate functions for WC Immaculate Grid.

A criterion is a dict: {"type": str, "value": Any, "label": str}

Supported types:
  nation        value = nation_id (Wikidata QID)
  confederation value = "UEFA"|"CONMEBOL"|"CAF"|"AFC"|"CONCACAF"|"OFC"
  achievement   value = achievement key string (see ACHIEVEMENT_LABELS)
  position      value = "DF"|"MF"|"FW"  (outfield positions from squad data)
  is_gk         value = True
  is_captain    value = True
"""

from __future__ import annotations

MIN_VALID_PLAYERS = 2  # criterion must cover >= this many players to enter the pool
MAX_SAME_TYPE_PER_AXIS = 1  # no more than 1 of the same type in a row or column

ACHIEVEMENT_LABELS: dict[str, str] = {
    # Tournament-end awards (populated once the WC concludes)
    "won_wc":           "Won the World Cup",
    "golden_boot":      "Won the Golden Boot",
    "golden_glove":     "Won the Golden Glove",
    # Match-level (populated as tournament progresses)
    "scored_wc_goal":   "Scored a goal",
    "scored_in_final":  "Scored in the Final",
    "played_in_final":  "Played in the Final",
    "played_in_semis":  "Reached the semifinals",
    "scored_penalty":   "Scored a penalty",
    # Multi-WC (populated from historical data if included)
    "played_3plus_wcs": "Played in 3+ World Cups",
}

POSITION_LABELS: dict[str, str] = {
    "DF": "Defender",
    "MF": "Midfielder",
    "FW": "Forward",
}

CONFEDERATION_LABELS: dict[str, str] = {
    "UEFA":     "UEFA (Europe)",
    "CONMEBOL": "CONMEBOL (South America)",
    "CAF":      "CAF (Africa)",
    "AFC":      "AFC (Asia / Pacific)",
    "CONCACAF": "CONCACAF (N./C. America)",
    "OFC":      "OFC (Oceania)",
}


def make_criterion(ctype: str, value, entities: dict) -> dict:
    """Build a criterion dict with its human-readable label."""
    label = _make_label(ctype, value, entities)
    return {"type": ctype, "value": value, "label": label}


def _make_label(ctype: str, value, entities: dict) -> str:
    if ctype == "nation":
        nation = entities["nations"].get(value, {})
        name = nation.get("name", value)
        return f"Played for {name}"
    if ctype == "confederation":
        return CONFEDERATION_LABELS.get(value, value)
    if ctype == "achievement":
        return ACHIEVEMENT_LABELS.get(value, value)
    if ctype == "position":
        return POSITION_LABELS.get(value, value)
    if ctype == "is_gk":
        return "Goalkeeper"
    if ctype == "is_captain":
        return "Team captain"
    return str(value)


def get_valid_players(criterion: dict, entities: dict) -> frozenset[str]:
    """Return frozenset of player IDs satisfying this criterion."""
    ctype = criterion["type"]
    value = criterion["value"]
    players = entities["players"]
    nations = entities["nations"]
    appearances = entities["appearances"]
    achievements = entities["achievements"]

    if ctype == "nation":
        return frozenset(
            a["player_id"] for a in appearances
            if a["nation_id"] == value and a["player_id"] in players
        )

    if ctype == "tournament":
        return frozenset(
            a["player_id"] for a in appearances
            if a["tournament_year"] == value and a["player_id"] in players
        )

    if ctype == "confederation":
        valid_nations = frozenset(
            n["id"] for n in nations.values()
            if n["confederation"] == value
        )
        return frozenset(
            a["player_id"] for a in appearances
            if a["nation_id"] in valid_nations and a["player_id"] in players
        )

    if ctype == "achievement":
        return frozenset(
            ac["player_id"] for ac in achievements
            if ac["achievement"] == value and ac["player_id"] in players
        )

    if ctype == "position":
        return frozenset(pid for pid, p in players.items() if p.get("position") == value)

    if ctype == "is_gk":
        return frozenset(pid for pid, p in players.items() if p.get("is_gk"))

    if ctype == "is_captain":
        return frozenset(pid for pid, p in players.items() if p.get("is_captain"))

    raise ValueError(f"Unknown criterion type: {ctype!r}")


def get_valid_cell(criterion_row: dict, criterion_col: dict, entities: dict) -> frozenset[str]:
    """Players satisfying BOTH the row and column criterion."""
    return get_valid_players(criterion_row, entities) & get_valid_players(criterion_col, entities)


def build_criterion_pool(entities: dict) -> list[dict]:
    """
    Build the full pool of usable criteria from entity data.
    Only includes criteria whose player pool is >= MIN_VALID_PLAYERS.
    """
    pool: list[dict] = []

    nations = entities["nations"]
    players = entities["players"]
    appearances = entities["appearances"]
    achievements = entities["achievements"]

    # Nation criteria: one per nation that has enough players
    nation_player_counts: dict[str, int] = {}
    for a in appearances:
        if a["player_id"] in players:
            nation_player_counts[a["nation_id"]] = (
                nation_player_counts.get(a["nation_id"], 0) + 1
            )

    for n_id, count in nation_player_counts.items():
        if count >= MIN_VALID_PLAYERS and n_id in nations:
            pool.append(make_criterion("nation", n_id, entities))

    # Tournament criteria: one per year in the data
    years_seen = sorted({a["tournament_year"] for a in appearances})
    for year in years_seen:
        year_players = sum(
            1 for a in appearances
            if a["tournament_year"] == year and a["player_id"] in players
        )
        if year_players >= MIN_VALID_PLAYERS:
            pool.append(make_criterion("tournament", year, entities))

    # Confederation criteria
    for conf in ("UEFA", "CONMEBOL", "CAF", "AFC", "CONCACAF", "OFC"):
        valid_nations = {n["id"] for n in nations.values() if n["confederation"] == conf}
        conf_players = {
            a["player_id"] for a in appearances
            if a["nation_id"] in valid_nations and a["player_id"] in players
        }
        if len(conf_players) >= MIN_VALID_PLAYERS:
            pool.append(make_criterion("confederation", conf, entities))

    # Achievement criteria
    for ach_key in ACHIEVEMENT_LABELS:
        ach_players = {
            ac["player_id"] for ac in achievements
            if ac["achievement"] == ach_key and ac["player_id"] in players
        }
        if len(ach_players) >= MIN_VALID_PLAYERS:
            pool.append(make_criterion("achievement", ach_key, entities))

    # GK criterion
    gk_count = sum(1 for p in players.values() if p.get("is_gk"))
    if gk_count >= MIN_VALID_PLAYERS:
        pool.append(make_criterion("is_gk", True, entities))

    # Position criteria (outfield positions from squad data)
    for pos_code in ("DF", "MF", "FW"):
        pos_count = sum(1 for p in players.values() if p.get("position") == pos_code)
        if pos_count >= MIN_VALID_PLAYERS:
            pool.append(make_criterion("position", pos_code, entities))

    # Captain criterion
    captain_count = sum(1 for p in players.values() if p.get("is_captain"))
    if captain_count >= MIN_VALID_PLAYERS:
        pool.append(make_criterion("is_captain", True, entities))

    return pool


def criterion_key(c: dict) -> tuple:
    """Stable hashable identity for a criterion (for dedup and axis-type checks)."""
    return (c["type"], str(c["value"]))


def axes_are_diverse(row_criteria: list[dict], col_criteria: list[dict]) -> bool:
    """
    Return True if neither axis has redundant criteria.

    Rules:
    - Multiple "nation" criteria per axis are ALLOWED (each nation is distinct).
    - Multiple "tournament" criteria per axis are ALLOWED (each year is distinct).
    - "confederation", "achievement", "is_gk" are limited to 1 per axis
      (multiple same-confederation or same-achievement criteria are boring/redundant).
    """
    TYPES_WITH_LIMIT = ("confederation", "achievement", "is_gk", "position", "is_captain")
    for axis in (row_criteria, col_criteria):
        type_counts: dict[str, int] = {}
        for c in axis:
            if c["type"] not in TYPES_WITH_LIMIT:
                continue
            type_counts[c["type"]] = type_counts.get(c["type"], 0) + 1
            if type_counts[c["type"]] > MAX_SAME_TYPE_PER_AXIS:
                return False
    return True
