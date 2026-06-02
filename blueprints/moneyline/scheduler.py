import base64
import hashlib
import json
import logging
import os
import re
from datetime import datetime

import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

logger = logging.getLogger(__name__)

EASTERN = pytz.timezone('America/New_York')
DATA_PATH = os.path.join('data', 'moneyline', 'daily_game.json')
API_URL = 'https://timeline-production-6c18.up.railway.app/api/moneyline/daily-game'
SECRET = 'XkaKm30N51IGGlofzK6pWb9MmyXhdLCr'

_scheduler = None


def _decrypt(encrypted_b64, date_str):
    key = hashlib.sha256((SECRET + date_str).encode()).digest()
    raw = base64.b64decode(encrypted_b64)
    iv = raw[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plain = unpad(cipher.decrypt(raw[16:]), AES.block_size)
    return json.loads(plain.decode('utf-8'))


def _clean_question(text):
    return re.sub(r'  +', ' ', text).strip()


def fetch_and_cache():
    try:
        date_str = datetime.now(EASTERN).strftime('%Y-%m-%d')
        resp = requests.get(API_URL, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

        decrypted = _decrypt(raw['data'], date_str)
        rounds = decrypted.get('rounds', [])
        for r in rounds:
            r['question'] = _clean_question(r.get('question', ''))

        game = {
            'game_number': raw.get('game_number'),
            'date': date_str,
            'rounds': rounds,
            '_fetched_date': date_str,
        }
        with open(DATA_PATH, 'w') as f:
            json.dump(game, f)
        logger.info(f'[Moneyline] Cached game #{game["game_number"]} for {date_str}')
    except Exception as e:
        logger.error(f'[Moneyline] Fetch failed: {e}')


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=EASTERN)
    _scheduler.add_job(
        fetch_and_cache,
        trigger=CronTrigger(hour=5, minute=0, timezone=EASTERN),
        id='moneyline_daily_fetch',
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
