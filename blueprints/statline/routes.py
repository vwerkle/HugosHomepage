import logging
from datetime import datetime

import pytz
from flask import jsonify, render_template, request, session

from blueprints.statline import statline_bp
from blueprints.statline.config import AUTOCOMPLETE_MAX, SCORING, TIMEZONE
from blueprints.statline.engine import autocomplete_players, build_puzzle, load_csvs

logger = logging.getLogger(__name__)
EASTERN = pytz.timezone(TIMEZONE)

# Load CSVs once when the blueprint is imported
load_csvs()

# Simple date-keyed cache so puzzle isn't rebuilt on every API call
_puzzle_cache = {}

# Per-date reroll salts set by admin; cleared on restart
_date_salts = {}


def _get_puzzle():
    today = datetime.now(EASTERN).strftime('%Y-%m-%d')
    salt = _date_salts.get(today, 0)
    cache_key = f"{today}-{salt}"
    if cache_key not in _puzzle_cache:
        puzzle = build_puzzle(salt=salt)
        _puzzle_cache.clear()
        _puzzle_cache[cache_key] = puzzle
    return _puzzle_cache[cache_key]


@statline_bp.route('/')
def game():
    is_admin = session.get('user') == 'hugo'
    return render_template('statline/game.html', scoring=SCORING, is_admin=is_admin)


@statline_bp.route('/api/puzzle')
def api_puzzle():
    try:
        puzzle = _get_puzzle()
        return jsonify(puzzle)
    except Exception:
        logger.exception("Statline: puzzle error")
        return jsonify({'error': 'Puzzle unavailable'}), 503


@statline_bp.route('/api/admin/reroll', methods=['POST'])
def api_admin_reroll():
    if session.get('user') != 'hugo':
        return jsonify({'error': 'Unauthorized'}), 403
    today = datetime.now(EASTERN).strftime('%Y-%m-%d')
    _date_salts[today] = _date_salts.get(today, 0) + 1
    _puzzle_cache.clear()
    puzzle = _get_puzzle()
    logger.info(f"Statline: admin reroll for {today}, salt={_date_salts[today]}")
    return jsonify({'ok': True, 'salt': _date_salts[today], 'puzzle': puzzle})


@statline_bp.route('/api/autocomplete')
def api_autocomplete():
    sport    = request.args.get('sport', '').strip()
    category = request.args.get('category', '').strip()
    q        = request.args.get('q', '').strip()
    if not sport or not category:
        return jsonify([])
    try:
        results = autocomplete_players(sport, category, q, limit=AUTOCOMPLETE_MAX)
        return jsonify(results)
    except Exception:
        logger.exception("Statline: autocomplete error")
        return jsonify([])
