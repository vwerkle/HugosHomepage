import requests
import json
import os
import logging

logger = logging.getLogger(__name__)

RESY_BASE = "https://api.resy.com"
CONFIG_PATH = os.path.join('data', 'reservations', 'config.json')

PHILLY_LAT = '39.9526'
PHILLY_LONG = '-75.1652'


def _load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)['resy']


def _headers():
    cfg = _load_config()
    return {
        'Authorization': f'ResyAPI api_key="{cfg["api_key"]}"',
        'X-Resy-Auth-Token': cfg['auth_token'],
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Origin': 'https://resy.com',
        'Referer': 'https://resy.com/',
        'Accept': 'application/json, text/plain, */*',
        'Cache-Control': 'no-cache',
    }


def is_configured():
    """Return True if Resy credentials are filled in."""
    try:
        cfg = _load_config()
        return bool(cfg.get('api_key') and cfg.get('auth_token'))
    except Exception:
        return False


def search_philly_venues(party_size=2):
    """
    Return list of Philadelphia Resy venues for dropdown.
    Uses /4/find with lat/lng — the only endpoint that reliably returns JSON.
    Paginates via the 'bookmark' cursor until exhausted.
    """
    from datetime import date, timedelta
    headers = _headers()
    # Use a near-future date so we get real results
    search_day = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')

    venues = []
    seen_ids = set()
    bookmark = None

    while True:
        params = {
            'lat': PHILLY_LAT,
            'long': PHILLY_LONG,
            'day': search_day,
            'party_size': party_size,
            'per_page': 100,
        }
        if bookmark:
            params['bookmark'] = bookmark

        resp = requests.get(
            f"{RESY_BASE}/4/find",
            headers=headers,
            params=params,
            timeout=15,
        )
        if resp.status_code != 200:
            raise Exception(f"Resy API returned HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()

        results = data.get('results', {}).get('venues', [])
        if not results:
            break

        for v in results:
            venue = v.get('venue', {})
            vid = venue.get('id', {})
            resy_id = vid.get('resy') if isinstance(vid, dict) else vid
            if not resy_id or resy_id in seen_ids:
                continue
            seen_ids.add(resy_id)

            name = venue.get('name') or venue.get('venue_name', '')
            if not name:
                # Fall back to venue_group name
                name = venue.get('venue_group', {}).get('name', '')
            loc = venue.get('location', {})
            neighborhood = loc.get('neighborhood', '') or loc.get('city', '')

            venues.append({
                'name': name,
                'venue_id': str(resy_id),
                'platform': 'resy',
                'neighborhood': neighborhood,
            })

        bookmark = data.get('bookmark')
        if not bookmark or len(results) < 100:
            break

    return venues


def get_availability(venue_id, date, party_size):
    """
    Get available time slots for a venue.
    Returns list of dicts: {time, config_token, type}
    date format: 'YYYY-MM-DD'
    """
    headers = _headers()
    params = {
        'venue_id': venue_id,
        'day': date,
        'party_size': party_size,
        'lat': PHILLY_LAT,
        'long': PHILLY_LONG,
    }
    try:
        resp = requests.get(
            f"{RESY_BASE}/4/find",
            headers=headers,
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"Resy availability check returned {resp.status_code} for venue {venue_id}: {resp.text[:100]}")
            return []
        data = resp.json()
    except Exception as e:
        logger.error(f"Resy availability error for venue {venue_id}: {e}")
        return []

    slots = []
    for result in data.get('results', {}).get('venues', []):
        for slot in result.get('slots', []):
            slot_date = slot.get('date', {})
            config = slot.get('config', {})
            slots.append({
                'time': slot_date.get('start', ''),   # "2026-04-10 19:00:00"
                'config_token': config.get('token', ''),
                'type': config.get('type', 'table'),
            })
    return slots


def _get_book_token(config_token, date, party_size):
    """Exchange config token for a book token."""
    headers = _headers()
    data = {
        'config_id': config_token,
        'day': date,
        'party_size': party_size,
    }
    try:
        resp = requests.post(
            f"{RESY_BASE}/3/details",
            headers=headers,
            data=data,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get('book_token', {}).get('value')
    except Exception as e:
        logger.error(f"Resy get_book_token error: {e}")
        return None


def book_slot(config_token, date, party_size):
    """
    Book a reservation slot.
    Returns (success: bool, detail: str)
    """
    cfg = _load_config()
    payment_method_id = cfg.get('payment_method_id', '')

    book_token = _get_book_token(config_token, date, party_size)
    if not book_token:
        return False, "Failed to obtain book token"

    headers = _headers()
    data = {
        'book_token': book_token,
        'payment_method_id': payment_method_id,
        'source_id': 'resy.com-venue-details',
    }
    try:
        resp = requests.post(
            f"{RESY_BASE}/3/book",
            headers=headers,
            data=data,
            timeout=10,
        )
        if resp.status_code == 201:
            resy_token = resp.json().get('resy_token', 'confirmed')
            return True, resy_token
        logger.warning(f"Resy booking failed {resp.status_code}: {resp.text[:200]}")
        return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        logger.error(f"Resy book_slot error: {e}")
        return False, str(e)
