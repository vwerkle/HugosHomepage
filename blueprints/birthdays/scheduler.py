import json
import logging
import os
import smtplib
from datetime import date
from email.mime.text import MIMEText

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

EASTERN = pytz.timezone('America/New_York')
DATA_PATH = os.path.join('data', 'birthdays', 'birthdays.json')
CONFIG_PATH = os.path.join('data', 'birthdays', 'config.json')

_scheduler = None

MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]


def _send_sms(message):
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        gmail = cfg.get('gmail_address', '')
        app_pw = cfg.get('gmail_app_password', '')
        to_sms = cfg.get('to_sms_email', '')
        if not all([gmail, app_pw, to_sms]):
            return
        msg = MIMEText(message)
        msg['From'] = gmail
        msg['To'] = to_sms
        msg['Subject'] = ''
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail, app_pw)
            server.sendmail(gmail, to_sms, msg.as_string())
    except Exception as e:
        logger.error(f'[Birthdays] SMS failed: {e}')


def _days_until_next(month, day):
    today = date.today()
    try:
        bday = date(today.year, month, day)
    except ValueError:
        bday = date(today.year, 3, 1)
    if bday < today:
        try:
            bday = date(today.year + 1, month, day)
        except ValueError:
            bday = date(today.year + 1, 3, 1)
    return (bday - today).days


def _check_birthdays():
    try:
        with open(DATA_PATH) as f:
            entries = json.load(f)
    except Exception as e:
        logger.error(f'[Birthdays] Could not load data: {e}')
        return

    for entry in entries:
        name = entry.get('name', '?')
        month = entry.get('month', 1)
        day = entry.get('day', 1)
        alert_days = entry.get('alert_days', 7)

        days_until = _days_until_next(month, day)
        month_name = MONTH_NAMES[month]

        # normalise legacy int to list
        if isinstance(alert_days, int):
            alert_days = [alert_days]

        if days_until == 0 or days_until in alert_days:
            if days_until == 0:
                _send_sms(f"Today is {name}'s birthday! \U0001f382")
            else:
                _send_sms(f"{name}'s birthday is in {days_until} days! ({month_name} {day})")


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=EASTERN)
    _scheduler.add_job(
        _check_birthdays,
        trigger=CronTrigger(hour=9, minute=0, timezone=EASTERN),
        id='birthday_daily_check',
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=82800,  # 23 hrs — fires even if app restarts late in the day
    )
    _scheduler.start()
