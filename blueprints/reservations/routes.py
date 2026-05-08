import json
import logging
import threading
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, jsonify, session
from blueprints.reservations import reservations_bp
from blueprints.reservations import scheduler
import pytz

logger = logging.getLogger(__name__)
EASTERN = pytz.timezone('America/New_York')

# Venue cache populated eagerly in background — never blocks the browser
_venue_cache = {'resy': [], 'opentable': [], 'loaded_at': None, 'errors': {}, 'loading': False}
_cache_lock = threading.Lock()
_CACHE_TTL_MINUTES = 60
_load_in_progress = False


def _require_hugo():
    if session.get('user') != 'hugo':
        return redirect(url_for('madness.login') + '?next=/reservations')
    return None


def _load_venues_background():
    """Run in a background thread; fills _venue_cache without blocking requests."""
    global _load_in_progress
    with _cache_lock:
        if _load_in_progress:
            return
        _load_in_progress = True
        _venue_cache['loading'] = True
    try:
        from blueprints.reservations import resy_client, opentable_client

        # Resy is fast (~1s API call) — load first
        if resy_client.is_configured():
            try:
                resy = resy_client.search_philly_venues()
                with _cache_lock:
                    _venue_cache['resy'] = resy
                    _venue_cache['errors'].pop('resy', None)
                logger.info(f"[Venues] Resy loaded: {len(resy)} venues")
            except Exception as e:
                err = str(e)
                logger.error(f"[Venues] Resy failed: {err}")
                with _cache_lock:
                    _venue_cache['errors']['resy'] = err
        else:
            with _cache_lock:
                _venue_cache['errors']['resy'] = 'Not configured (missing api_key or auth_token)'

        # OpenTable is slow (~30s Firefox launch) — load after Resy
        if opentable_client.is_configured():
            try:
                ot = opentable_client.search_philly_venues()
                with _cache_lock:
                    _venue_cache['opentable'] = ot
                    _venue_cache['loaded_at'] = datetime.now()
                    _venue_cache['errors'].pop('opentable', None)
                logger.info(f"[Venues] OpenTable loaded: {len(ot)} venues")
            except Exception as e:
                err = str(e)
                logger.error(f"[Venues] OpenTable failed: {err}")
                with _cache_lock:
                    _venue_cache['errors']['opentable'] = err
        else:
            with _cache_lock:
                _venue_cache['errors']['opentable'] = 'Not configured (missing email or password)'

        with _cache_lock:
            _venue_cache['loaded_at'] = datetime.now()
            _venue_cache['loading'] = False
    finally:
        _load_in_progress = False


def _cache_stale():
    with _cache_lock:
        loaded = _venue_cache.get('loaded_at')
    if loaded is None:
        return True
    return (datetime.now() - loaded).total_seconds() / 60 > _CACHE_TTL_MINUTES


def preload_venues():
    """Called at app startup to kick off background venue loading."""
    threading.Thread(target=_load_venues_background, daemon=True).start()


@reservations_bp.route('/reservations')
def reservations():
    guard = _require_hugo()
    if guard:
        return guard
    active_jobs = scheduler.get_all_jobs()
    history = scheduler.get_history()

    time_options = []
    for h in range(11, 24):
        for m in (0, 30):
            if h == 11 and m == 0:
                continue
            t24 = f"{h:02d}:{m:02d}"
            hour12 = h if h <= 12 else h - 12
            ampm = 'AM' if h < 12 else 'PM'
            label = f"{hour12}:{m:02d} {ampm}"
            time_options.append({'value': t24, 'label': label})

    today = datetime.now(EASTERN).strftime('%Y-%m-%d')

    return render_template(
        'reservations/reservations.html',
        active_jobs=active_jobs,
        history=history,
        time_options=time_options,
        today=today,
    )


@reservations_bp.route('/reservations/refresh-venues', methods=['POST'])
def refresh_venues():
    guard = _require_hugo()
    if guard:
        return jsonify({}), 403
    global _load_in_progress
    if not _load_in_progress:
        # Reset cache so it reloads fresh
        with _cache_lock:
            _venue_cache['resy'] = []
            _venue_cache['opentable'] = []
            _venue_cache['loaded_at'] = None
            _venue_cache['errors'] = {}
            _venue_cache['loading'] = False
        threading.Thread(target=_load_venues_background, daemon=True).start()
    return jsonify({'status': 'refreshing'})


@reservations_bp.route('/reservations/restaurants')
def get_restaurants():
    guard = _require_hugo()
    if guard:
        return jsonify([]), 403

    # Trigger a background refresh if cache is stale
    if _cache_stale() and not _load_in_progress:
        threading.Thread(target=_load_venues_background, daemon=True).start()

    # Return whatever is cached right now (Resy may be ready before OT finishes)
    with _cache_lock:
        combined = _venue_cache['resy'] + _venue_cache['opentable']
        errors = dict(_venue_cache['errors'])
        loading = _venue_cache['loading']
    combined.sort(key=lambda v: v['name'].lower())
    return jsonify({'venues': combined, 'errors': errors, 'loading': loading})


@reservations_bp.route('/reservations/add', methods=['POST'])
def add_reservation():
    guard = _require_hugo()
    if guard:
        return guard
    platform = request.form.get('platform')
    venue_id = request.form.get('venue_id')
    venue_name = request.form.get('venue_name', '')
    date_str = request.form.get('date')
    party_size = int(request.form.get('party_size', 2))
    min_time = request.form.get('min_time', '18:00')
    max_time = request.form.get('max_time', '21:00')

    if not all([platform, venue_id, date_str]):
        return redirect(url_for('reservations.reservations'))

    scheduler.add_job(
        platform=platform,
        venue_id=venue_id,
        venue_name=venue_name,
        date_str=date_str,
        party_size=party_size,
        min_time=min_time,
        max_time=max_time,
    )
    return redirect(url_for('reservations.reservations'))


@reservations_bp.route('/reservations/cancel/<job_id>', methods=['POST'])
def cancel_reservation(job_id):
    guard = _require_hugo()
    if guard:
        return guard
    scheduler.remove_job(job_id)
    return redirect(url_for('reservations.reservations'))


@reservations_bp.route('/reservations/status')
def reservation_status():
    guard = _require_hugo()
    if guard:
        return jsonify({}), 403
    """JSON endpoint for live job status refresh."""
    return jsonify(scheduler.get_all_jobs())
