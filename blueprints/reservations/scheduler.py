import json
import os
import uuid
import logging
import threading
import time as time_module
from datetime import datetime, date, timedelta
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

EASTERN = pytz.timezone('America/New_York')
JOBS_PATH = os.path.join('data', 'reservations', 'active_jobs.json')
HISTORY_PATH = os.path.join('data', 'reservations', 'history.json')

_scheduler = None
_file_lock = threading.Lock()


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _read_jobs():
    with _file_lock:
        with open(JOBS_PATH) as f:
            return json.load(f)


def _write_jobs(jobs):
    with _file_lock:
        with open(JOBS_PATH, 'w') as f:
            json.dump(jobs, f, indent=2)


def _send_sms(message):
    """Send an SMS via Twilio. Silently skips if credentials not configured."""
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f).get('twilio', {})
        if not all([cfg.get('account_sid'), cfg.get('auth_token'), cfg.get('from_number'), cfg.get('to_number')]):
            return
        from twilio.rest import Client
        client = Client(cfg['account_sid'], cfg['auth_token'])
        client.messages.create(body=message, from_=cfg['from_number'], to=cfg['to_number'])
        logger.info(f"[Reservations] SMS sent: {message[:60]}")
    except Exception as e:
        logger.error(f"[Reservations] SMS failed: {e}")


CONFIG_PATH = os.path.join('data', 'reservations', 'config.json')


def _append_history(entry):
    with _file_lock:
        with open(HISTORY_PATH) as f:
            history = json.load(f)
        history.append(entry)
        with open(HISTORY_PATH, 'w') as f:
            json.dump(history, f, indent=2)


# ---------------------------------------------------------------------------
# Core polling logic
# ---------------------------------------------------------------------------

def _slots_in_window(slots, min_time, max_time):
    """Filter slots to those within the user's acceptable time window."""
    result = []
    for slot in slots:
        # slot['time'] is "YYYY-MM-DD HH:MM:SS" (Resy) or "HH:MM" (OpenTable)
        raw = slot.get('time', '')
        try:
            if ' ' in raw:
                t = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S').strftime('%H:%M')
            elif 'T' in raw:
                t = datetime.fromisoformat(raw).strftime('%H:%M')
            else:
                t = raw[:5]  # already HH:MM
            if min_time <= t <= max_time:
                result.append(slot)
        except Exception:
            pass
    return result


def _attempt_booking(job_id, job):
    """Try to find and book a slot for a job. Updates job status on success."""
    platform = job['platform']
    date_str = job['date']
    party_size = job['party_size']
    min_time = job['min_time']
    max_time = job['max_time']
    venue_id = job['venue_id']
    venue_name = job['venue_name']

    try:
        if platform == 'resy':
            from blueprints.reservations import resy_client
            slots = resy_client.get_availability(venue_id, date_str, party_size)
            matching = _slots_in_window(slots, min_time, max_time)
            if not matching:
                return False
            slot = matching[0]
            success, detail = resy_client.book_slot(slot['config_token'], date_str, party_size)

        elif platform == 'opentable':
            from blueprints.reservations import opentable_client
            # If venue_id is a free-text name (name: prefix), resolve it to a slug first
            if venue_id.startswith('name:'):
                raw_name = venue_id[5:]
                resolved = opentable_client.find_restaurant_slug(raw_name)
                venue_id = resolved
                # Persist the resolved slug so we don't look it up again
                jobs = _read_jobs()
                if job_id in jobs:
                    jobs[job_id]['venue_id'] = resolved
                    _write_jobs(jobs)
            slots = opentable_client.get_availability(venue_id, date_str, party_size, min_time, max_time)
            if not slots:
                return False
            slot = slots[0]
            success, detail = opentable_client.book_slot(venue_id, date_str, slot['time'], party_size)

        else:
            return False

        if success:
            now = datetime.now(EASTERN).isoformat()
            booked_time = slot.get('time', slot.get('display_time', ''))

            jobs = _read_jobs()
            if job_id in jobs:
                jobs[job_id]['status'] = 'booked'
                jobs[job_id]['booked_at'] = now
                jobs[job_id]['booked_time'] = booked_time
                _write_jobs(jobs)

            _append_history({
                'job_id': job_id,
                'venue_name': venue_name,
                'platform': platform,
                'date': date_str,
                'booked_time': booked_time,
                'party_size': party_size,
                'booked_at': now,
                'detail': detail,
            })

            # Cancel the recurring poll jobs for this reservation
            _cancel_apscheduler_jobs(job_id)
            logger.info(f"[Reservations] BOOKED {venue_name} at {booked_time} on {date_str}")

            _send_sms(
                f"Reservation booked! {venue_name} on {date_str} at {booked_time} "
                f"for {party_size} via {platform.title()}"
            )
            return True

        return False

    except Exception as e:
        logger.error(f"[Reservations] Error attempting booking for job {job_id}: {e}")
        return False


def _poll_job(job_id):
    """Regular 60-second poll. Skips if already booked."""
    jobs = _read_jobs()
    job = jobs.get(job_id)
    if not job or job.get('status') != 'watching':
        return

    # Check if the target date has already passed
    try:
        target = datetime.strptime(job['date'], '%Y-%m-%d').date()
        if target < date.today():
            jobs = _read_jobs()
            if job_id in jobs:
                jobs[job_id]['status'] = 'expired'
                _write_jobs(jobs)
            _cancel_apscheduler_jobs(job_id)
            return
    except Exception:
        pass

    logger.debug(f"[Reservations] Polling {job['venue_name']} ({job['platform']}) for {job['date']}")
    _attempt_booking(job_id, job)


def _midnight_snipe(job_id):
    """
    High-frequency snipe: called at 23:59:45 Eastern each night a job is active.
    Polls every 0.5s for 30 seconds to catch midnight reservation releases.
    """
    jobs = _read_jobs()
    job = jobs.get(job_id)
    if not job or job.get('status') != 'watching':
        return

    logger.info(f"[Reservations] Midnight snipe starting for {job['venue_name']} ({job['date']})")
    deadline = time_module.time() + 30  # run for 30 seconds
    while time_module.time() < deadline:
        jobs = _read_jobs()
        job = jobs.get(job_id)
        if not job or job.get('status') != 'watching':
            break
        if _attempt_booking(job_id, job):
            logger.info(f"[Reservations] Midnight snipe SUCCESS for {job['venue_name']}")
            break
        time_module.sleep(0.5)


# ---------------------------------------------------------------------------
# APScheduler helpers
# ---------------------------------------------------------------------------

def _release_snipe_dates(target_date_str, platform):
    """
    Calculate the likely dates when a restaurant releases reservations for target_date.
    Returns a list of date objects on which we should run an aggressive midnight snipe.

    Common release patterns:
    - Resy: 28 days in advance at midnight Eastern (most common)
    - Resy: some do 30 or 60 days in advance
    - OpenTable: 30 days in advance OR the 1st of the month prior
    - Both: some release on the 1st of the month 1-2 months before
    """
    try:
        target = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except Exception:
        return []

    candidates = set()

    if platform in ('resy', 'all'):
        # Resy most common: 28 and 30 days out
        candidates.add(target - timedelta(days=28))
        candidates.add(target - timedelta(days=30))
        candidates.add(target - timedelta(days=60))

    if platform in ('opentable', 'all'):
        # OpenTable: 30 days out + 1st of the month before
        candidates.add(target - timedelta(days=30))
        # 1st of the month in which target falls
        candidates.add(target.replace(day=1))
        # 1st of the prior month
        first_prior = (target.replace(day=1) - timedelta(days=1)).replace(day=1)
        candidates.add(first_prior)

    today = date.today()
    # Only return future dates (or today) that are before the target
    return sorted(d for d in candidates if today <= d < target)


def _cancel_apscheduler_jobs(job_id):
    global _scheduler
    if _scheduler is None:
        return
    for suffix in ['_poll', '_snipe', '_release_snipe']:
        try:
            _scheduler.remove_job(job_id + suffix)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone=EASTERN)
    _scheduler.start()

    # Re-register poll jobs for any jobs that were active before restart
    try:
        jobs = _read_jobs()
        for job_id, job in jobs.items():
            if job.get('status') == 'watching':
                _register_apscheduler_jobs(job_id)
    except Exception as e:
        logger.error(f"[Reservations] Failed to restore jobs on startup: {e}")

    logger.info("[Reservations] Scheduler started")


def _register_apscheduler_jobs(job_id):
    global _scheduler

    jobs = _read_jobs()
    job = jobs.get(job_id, {})
    platform = job.get('platform', 'resy')
    target_date = job.get('date', '')

    # 60-second regular poll
    _scheduler.add_job(
        _poll_job,
        trigger=IntervalTrigger(seconds=60, timezone=EASTERN),
        id=job_id + '_poll',
        args=[job_id],
        replace_existing=True,
        max_instances=1,
    )

    # Midnight snipe every night at 23:59:45 Eastern as a general catch-all
    _scheduler.add_job(
        _midnight_snipe,
        trigger=CronTrigger(hour=23, minute=59, second=45, timezone=EASTERN),
        id=job_id + '_snipe',
        args=[job_id],
        replace_existing=True,
        max_instances=1,
    )

    # Extra-targeted snipes on calculated release dates
    # (e.g. exactly 28 days before for Resy, 1st of month for OT)
    release_dates = _release_snipe_dates(target_date, platform)
    today = date.today()
    now_et = datetime.now(EASTERN)

    for i, rel_date in enumerate(release_dates):
        if rel_date == today and now_et.hour >= 0:
            # Release date is today and it's already past midnight — fire immediately in bg
            threading.Thread(target=_midnight_snipe, args=[job_id], daemon=True).start()
        elif rel_date > today:
            _scheduler.add_job(
                _midnight_snipe,
                trigger=CronTrigger(
                    year=rel_date.year,
                    month=rel_date.month,
                    day=rel_date.day,
                    hour=23, minute=59, second=45,
                    timezone=EASTERN,
                ),
                id=f"{job_id}_release_snipe_{i}",
                args=[job_id],
                replace_existing=True,
                max_instances=1,
            )
            logger.info(
                f"[Reservations] Scheduled release snipe for {job.get('venue_name')} "
                f"on {rel_date} (target: {target_date})"
            )


def add_job(platform, venue_id, venue_name, date_str, party_size, min_time, max_time):
    """
    Add a new reservation watch job.
    Returns the job_id.
    """
    job_id = str(uuid.uuid4())[:8]
    now = datetime.now(EASTERN).isoformat()

    job = {
        'platform': platform,
        'venue_id': venue_id,
        'venue_name': venue_name,
        'date': date_str,
        'party_size': party_size,
        'min_time': min_time,
        'max_time': max_time,
        'status': 'watching',
        'created_at': now,
        'booked_at': None,
        'booked_time': None,
    }

    jobs = _read_jobs()
    jobs[job_id] = job
    _write_jobs(jobs)

    if _scheduler:
        _register_apscheduler_jobs(job_id)

    # Do an immediate first poll so the user gets instant feedback
    threading.Thread(target=_poll_job, args=[job_id], daemon=True).start()

    logger.info(f"[Reservations] Added job {job_id} for {venue_name} on {date_str}")
    return job_id


def remove_job(job_id):
    """Cancel and remove a watch job."""
    jobs = _read_jobs()
    if job_id in jobs:
        del jobs[job_id]
        _write_jobs(jobs)

    _cancel_apscheduler_jobs(job_id)
    logger.info(f"[Reservations] Removed job {job_id}")


def get_all_jobs():
    return _read_jobs()


def get_history():
    with _file_lock:
        with open(HISTORY_PATH) as f:
            return json.load(f)
