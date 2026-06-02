import json
import logging
import os
from datetime import datetime

import pytz
from flask import jsonify, render_template

from blueprints.moneyline import moneyline_bp
from blueprints.moneyline.scheduler import fetch_and_cache

logger = logging.getLogger(__name__)
DATA_PATH = os.path.join('data', 'moneyline', 'daily_game.json')
EASTERN = pytz.timezone('America/New_York')


def _get_game_data():
    today = datetime.now(EASTERN).strftime('%Y-%m-%d')
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH) as f:
            data = json.load(f)
        if data.get('_fetched_date') == today:
            return data
    fetch_and_cache()
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH) as f:
            return json.load(f)
    return None


@moneyline_bp.route('/')
def game():
    return render_template('moneyline/game.html')


@moneyline_bp.route('/api/daily-game')
def daily_game():
    data = _get_game_data()
    if data is None:
        return jsonify({'error': 'Game data unavailable'}), 503
    data.pop('_fetched_date', None)
    return jsonify(data)
