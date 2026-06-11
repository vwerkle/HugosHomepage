import csv
import hashlib
import logging
import os
import random
from datetime import date, datetime

import pytz

from blueprints.statline.config import (
    AUTOCOMPLETE_MAX, CSV_COLUMNS, GAME_EPOCH, SCORING, SPORTS, TIMEZONE,
)

logger = logging.getLogger(__name__)
DATA_DIR = os.path.join('data', 'statline')
EASTERN = pytz.timezone(TIMEZONE)

# In-memory player data: {sport_key: [player_dict, ...]}
_players = {}


def load_csvs():
    """Load all sport CSVs into memory. Called once at startup."""
    for sport_key in SPORTS:
        path = os.path.join(DATA_DIR, f'{sport_key}.csv')
        if not os.path.exists(path):
            logger.warning(f"Statline: CSV not found at {path} — {sport_key} disabled")
            _players[sport_key] = []
            continue
        try:
            col_map = CSV_COLUMNS[sport_key]
            players = []
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    p = {}
                    for logical, physical in col_map.items():
                        raw = (row.get(physical) or '').strip()
                        if logical in ('id', 'name', 'position'):
                            p[logical] = raw
                        else:
                            try:
                                p[logical] = float(raw) if raw != '' else None
                            except ValueError:
                                p[logical] = None
                    if p.get('id') and p.get('name'):
                        players.append(p)
            _players[sport_key] = players
            logger.info(f"Statline: loaded {len(players)} {sport_key} players from {path}")
        except Exception:
            logger.exception(f"Statline: failed to load {sport_key}.csv")
            _players[sport_key] = []


def get_players(sport_key):
    return _players.get(sport_key, [])


def _game_number(d):
    epoch = date.fromisoformat(GAME_EPOCH) if isinstance(GAME_EPOCH, str) else GAME_EPOCH
    return max(1, (d - epoch).days + 1)


def _seed(d, tag, salt=0):
    """Deterministic integer seed from (date, tag) pair."""
    key = f"{d.isoformat()}-{tag}" if salt == 0 else f"{d.isoformat()}-{tag}-{salt}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16)


def _best_achievable(players, target_id, stat_key):
    """
    Return (value, name, id) of the non-target player whose stat is closest
    to the target's. Ties: returns the first (alphabetically by name).
    Returns (None, None, None) when no non-target player has the stat.
    """
    target_val = None
    for p in players:
        if p['id'] == target_id:
            target_val = p.get(stat_key)
            break
    if target_val is None:
        return None, None, None

    best = None
    for p in players:
        if p['id'] == target_id:
            continue
        val = p.get(stat_key)
        if val is None:
            continue
        if best is None or abs(val - target_val) < abs(best['val'] - target_val) or (
            abs(val - target_val) == abs(best['val'] - target_val) and p['name'] < best['name']
        ):
            best = {'val': val, 'name': p['name'], 'id': p['id']}

    if best is None:
        return None, None, None
    return best['val'], best['name'], best['id']


def build_puzzle(for_date=None, salt=0):
    """
    Build today's puzzle deterministically from the date seed.
    Each sport uses ALL its positions; each player gets one randomly chosen stat.
    Bump salt to re-roll the puzzle for a given date without affecting other days.
    """
    if for_date is None:
        for_date = datetime.now(EASTERN).date()

    game_num = _game_number(for_date)
    puzzle = {
        'date': for_date.isoformat(),
        'game_number': game_num,
        'sports': [],
    }

    for sport_key, sport_cfg in SPORTS.items():
        players = get_players(sport_key)
        if not players:
            continue

        sport_players = []
        # Build the full positions list. Baseball gets a 3rd slot randomly chosen
        # between SP and Hitter; football uses its fixed 3 positions unchanged.
        all_positions = list(sport_cfg['positions'])
        if 'random_position' in sport_cfg:
            rp_rng = random.Random(_seed(for_date, f"{sport_key}-random-pos", salt))
            all_positions.append(rp_rng.choice(sport_cfg['random_position']))

        # Duplicate positions get a per-occurrence index in their seed so they pick
        # different targets; chosen_target_ids prevents repeating the same player.
        chosen_target_ids = set()
        position_counts = {}
        for position_key in all_positions:
            occurrence = position_counts.get(position_key, 0)
            position_counts[position_key] = occurrence + 1

            pos_cfg = sport_cfg[position_key]
            thresh_col = pos_cfg['threshold']['col']
            thresh_min = pos_cfg['threshold']['min']

            eligible = [
                p for p in players
                if p.get('position') == position_key
                and p.get(thresh_col) is not None
                and p[thresh_col] >= thresh_min
                and any(p.get(cat['key']) is not None for cat in pos_cfg['categories'])
                and p['id'] not in chosen_target_ids
            ]
            if not eligible:
                logger.warning(
                    f"Statline {for_date}: no eligible targets for {sport_key}/{position_key} (occurrence {occurrence})"
                )
                continue

            target_rng = random.Random(
                _seed(for_date, f"{sport_key}-{position_key}-target-{occurrence}", salt)
            )
            target = target_rng.choice(eligible)
            chosen_target_ids.add(target['id'])

            # Pick 1 random category from those the target has data for.
            available_cats = [c for c in pos_cfg['categories'] if target.get(c['key']) is not None]
            cat_rng = random.Random(
                _seed(for_date, f"{sport_key}-{position_key}-cat-{occurrence}", salt)
            )
            chosen_cat = cat_rng.choice(available_cats)

            stat_key = chosen_cat['key']
            target_val = target.get(stat_key)
            best_val, best_name, best_id = _best_achievable(players, target['id'], stat_key)

            logger.info(
                f"Statline puzzle {for_date} #{game_num}: "
                f"{sport_key}/{position_key} → {target['name']} ({stat_key}={target_val})"
            )

            sport_players.append({
                'position':       position_key,
                'position_label': pos_cfg['label'],
                'target_id':      target['id'],
                'target_name':    target['name'],
                'category': {
                    'key':              stat_key,
                    'label':            chosen_cat['label'],
                    'fmt':              chosen_cat['fmt'],
                    'target_value':     target_val,
                    'best_value':       best_val,
                    'best_player_name': best_name,
                    'best_player_id':   best_id,
                },
            })

        if sport_players:
            puzzle['sports'].append({
                'sport':       sport_key,
                'sport_label': sport_cfg['label'],
                'emoji':       sport_cfg['emoji'],
                'players':     sport_players,
            })

    return puzzle


def autocomplete_players(sport_key, stat_key, query, limit=AUTOCOMPLETE_MAX):
    """
    Return players from sport_key who have a non-null value for stat_key
    and whose name contains query (case-insensitive). Sorted by name.
    """
    players = get_players(sport_key)
    q = query.lower().strip()
    results = []
    for p in players:
        if p.get(stat_key) is None:
            continue
        name = p.get('name', '')
        if q and q not in name.lower():
            continue
        results.append({
            'id':       p['id'],
            'name':     name,
            'value':    p[stat_key],
            'position': p.get('position', ''),
        })
    results.sort(key=lambda x: x['name'])
    return results[:limit]
