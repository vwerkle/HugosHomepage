import json
import os
import uuid
from datetime import date, datetime
from flask import render_template, request, redirect, url_for, session
from blueprints.birthdays import birthdays_bp

DATA_PATH = os.path.join('data', 'birthdays', 'birthdays.json')

MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]


def _require_hugo():
    if session.get('user') != 'hugo':
        return redirect(url_for('madness.login') + '?next=/birthdays')
    return None


def _load():
    with open(DATA_PATH) as f:
        return json.load(f)


def _save(entries):
    with open(DATA_PATH, 'w') as f:
        json.dump(entries, f, indent=2)


def _days_until_next(month, day):
    today = date.today()
    try:
        bday = date(today.year, month, day)
    except ValueError:
        # Feb 29 on non-leap year — use Mar 1
        bday = date(today.year, 3, 1)
    if bday < today:
        try:
            bday = date(today.year + 1, month, day)
        except ValueError:
            bday = date(today.year + 1, 3, 1)
    return (bday - today).days


def _parse_alert_days(raw):
    result = []
    for part in str(raw).split(','):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return sorted(set(result)) or [7]


def _annotated_sorted(entries):
    result = []
    for e in entries:
        e = dict(e)
        e['days_until'] = _days_until_next(e['month'], e['day'])
        e['month_name'] = MONTH_NAMES[e['month']]
        # normalise legacy int to list
        if isinstance(e['alert_days'], int):
            e['alert_days'] = [e['alert_days']]
        e['alert_days_str'] = ', '.join(str(d) for d in e['alert_days'])
        result.append(e)
    result.sort(key=lambda x: x['days_until'])
    return result


@birthdays_bp.route('/', methods=['GET'])
def index():
    redir = _require_hugo()
    if redir:
        return redir
    entries = _annotated_sorted(_load())
    return render_template('birthdays/index.html', entries=entries, month_names=MONTH_NAMES[1:])


@birthdays_bp.route('/add', methods=['POST'])
def add():
    redir = _require_hugo()
    if redir:
        return redir
    name = request.form.get('name', '').strip()
    try:
        month = int(request.form.get('month', 1))
        day = int(request.form.get('day', 1))
        alert_days = int(request.form.get('alert_days', 7))
    except (ValueError, TypeError):
        return redirect(url_for('birthdays.index'))
    if not name or not (1 <= month <= 12) or not (1 <= day <= 31):
        return redirect(url_for('birthdays.index'))
    entry = {
        'id': str(uuid.uuid4())[:8],
        'name': name,
        'month': month,
        'day': day,
        'alert_days': _parse_alert_days(request.form.get('alert_days', '7')),
    }
    entries = _load()
    entries.append(entry)
    _save(entries)
    return redirect(url_for('birthdays.index'))


@birthdays_bp.route('/edit/<entry_id>', methods=['POST'])
def edit(entry_id):
    redir = _require_hugo()
    if redir:
        return redir
    alert_days = _parse_alert_days(request.form.get('alert_days', '7'))
    entries = _load()
    for e in entries:
        if e['id'] == entry_id:
            e['alert_days'] = alert_days
            break
    _save(entries)
    return redirect(url_for('birthdays.index'))


@birthdays_bp.route('/delete/<entry_id>', methods=['POST'])
def delete(entry_id):
    redir = _require_hugo()
    if redir:
        return redir
    entries = [e for e in _load() if e['id'] != entry_id]
    _save(entries)
    return redirect(url_for('birthdays.index'))
