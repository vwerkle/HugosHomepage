from flask import Blueprint, render_template, request, session, redirect, url_for
import json, os, requests as http_requests
from datetime import datetime, timezone
from collections import defaultdict
import pytz

EASTERN = pytz.timezone('America/New_York')

worldcup_bp = Blueprint('worldcup', __name__, url_prefix='/worldcup')

DATA_DIR = 'data/worldcup'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
PICKS_FILE = os.path.join(DATA_DIR, 'picks.json')
GAMES_FILE = os.path.join(DATA_DIR, 'games.json')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
CHAMPIONS_FILE = os.path.join(DATA_DIR, 'champions.json')

KNOCKOUT_STAGES = {'round_of_32', 'round_of_16', 'quarterfinal', 'semifinal', 'third_place', 'final'}

STAGE_LABELS = {
    'group': 'Group Stage',
    'round_of_32': 'Round of 32',
    'round_of_16': 'Round of 16',
    'quarterfinal': 'Quarterfinal',
    'semifinal': 'Semifinal',
    'third_place': 'Third Place',
    'final': 'Final',
}

# football-data.org stage codes → our internal stage keys
STAGE_MAP = {
    'GROUP_STAGE': 'group',
    'LAST_32': 'round_of_32',
    'LAST_16': 'round_of_16',
    'QUARTER_FINALS': 'quarterfinal',
    'SEMI_FINALS': 'semifinal',
    'THIRD_PLACE': 'third_place',
    'FINAL': 'final',
}

RESULT_MAP = {
    'HOME_TEAM': 'home_win',
    'AWAY_TEAM': 'away_win',
    'DRAW': 'draw',
}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)


def now_utc_str():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def is_locked(kickoff_time_str, current_time_str):
    return kickoff_time_str[:16] <= current_time_str[:16]


def kickoff_et_date(kickoff_utc_str):
    """Return the local ET date (YYYY-MM-DD) for a UTC kickoff string."""
    dt = datetime.strptime(kickoff_utc_str, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    return dt.astimezone(EASTERN).strftime('%Y-%m-%d')


def first_kickoff(games):
    times = [g['kickoff_time'] for g in games.values() if not is_tbd(g)]
    return min(times) if times else None


def is_champion_locked(games, current_time):
    first = first_kickoff(games)
    return bool(first and is_locked(first, current_time))


def get_all_teams(games):
    teams = set()
    for g in games.values():
        if not is_tbd(g):
            if g.get('home_team'):
                teams.add(g['home_team'])
            if g.get('away_team'):
                teams.add(g['away_team'])
    return sorted(teams)


def game_points(stage):
    return 2 if stage in KNOCKOUT_STAGES else 1


def pick_label(pick, home_team=None, away_team=None):
    if pick == 'home_win':
        return f"{home_team} Win" if home_team else 'Home Win'
    if pick == 'away_win':
        return f"{away_team} Win" if away_team else 'Away Win'
    if pick == 'draw':
        return 'Draw'
    return pick or ''


def team_name(team_obj):
    """Return the best available name from a football-data.org team object."""
    return team_obj.get('name') or team_obj.get('shortName') or team_obj.get('tla') or 'TBD'


def sync_from_api(api_key):
    """Pull all WC 2026 fixtures + results from football-data.org.
    Returns (added, results_updated, total) or raises on HTTP error."""
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    resp = http_requests.get(url, headers={"X-Auth-Token": api_key}, timeout=15)
    resp.raise_for_status()

    matches = resp.json().get('matches', [])
    games = load_json(GAMES_FILE, {})

    added = 0
    results_updated = 0

    for match in matches:
        ext_id = f"fd_{match['id']}"
        stage = STAGE_MAP.get(match.get('stage', ''), 'group')
        kickoff = match['utcDate']  # already "2026-06-11T18:00:00Z"
        home = team_name(match['homeTeam'])
        away = team_name(match['awayTeam'])
        group = match.get('group') or ''

        result = 'pending'
        if match.get('status') == 'FINISHED':
            winner = (match.get('score') or {}).get('winner')
            result = RESULT_MAP.get(winner, 'pending')

        if ext_id not in games:
            games[ext_id] = {
                'home_team': home,
                'away_team': away,
                'kickoff_time': kickoff,
                'stage': stage,
                'group': group,
                'result': result,
            }
            added += 1
        else:
            old_result = games[ext_id].get('result', 'pending')
            # Never overwrite a manually-set result — only update if currently pending
            new_result = result if old_result == 'pending' else old_result
            games[ext_id].update({
                'home_team': home,
                'away_team': away,
                'kickoff_time': kickoff,
                'stage': stage,
                'group': group,
                'result': new_result,
            })
            if old_result == 'pending' and new_result != 'pending':
                results_updated += 1

    save_json(GAMES_FILE, games)
    return added, results_updated, len(matches)


@worldcup_bp.route('/', methods=['GET', 'POST'])
def hub():
    username = session.get('wc_user')
    admin_data = None
    message = None
    message_type = 'success'

    if username == 'hugo':
        config = load_json(CONFIG_FILE, {})
        games = load_json(GAMES_FILE, {})

        if request.method == 'POST':
            action = request.form.get('action')

            if action == 'save_api_key':
                config['api_key'] = request.form.get('api_key', '').strip()
                save_json(CONFIG_FILE, config)
                message = "API key saved."

            elif action == 'sync':
                api_key = config.get('api_key', '')
                if not api_key:
                    message = "No API key set. Add one below first."
                    message_type = 'error'
                else:
                    try:
                        added, results_updated, total = sync_from_api(api_key)
                        message = f"Sync complete: {total} matches found, {added} new, {results_updated} results updated."
                    except http_requests.HTTPError as e:
                        message = f"API error: {e.response.status_code} — {e.response.text[:200]}"
                        message_type = 'error'
                    except Exception as e:
                        message = f"Sync failed: {e}"
                        message_type = 'error'

            elif action == 'update_result':
                game_id = request.form.get('game_id')
                result = request.form.get('result')
                if game_id in games and result in ('home_win', 'away_win', 'draw', 'pending'):
                    games[game_id]['result'] = result
                    save_json(GAMES_FILE, games)
                    message = "Result updated."

            elif action == 'delete_game':
                game_id = request.form.get('game_id')
                if game_id in games:
                    label = f"{games[game_id]['away_team']} vs {games[game_id]['home_team']}"
                    del games[game_id]
                    save_json(GAMES_FILE, games)
                    message = f"Deleted: {label}"

            games = load_json(GAMES_FILE, {})
            config = load_json(CONFIG_FILE, {})

        admin_data = {
            'games': sorted(games.items(), key=lambda x: x[1]['kickoff_time']),
            'api_key': config.get('api_key', ''),
            'message': message,
            'message_type': message_type,
        }

    return render_template('worldcup/hub.html', username=username,
                           admin=admin_data, stage_labels=STAGE_LABELS)


@worldcup_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        name, pw = request.form.get('name'), request.form.get('password')
        users = load_json(USERS_FILE, {})
        if name in users and users[name]['password'] == pw:
            session['wc_user'] = name
            next_url = request.args.get('next', '')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            if name == 'hugo':
                return redirect(url_for('worldcup.hub'))
            return redirect(url_for('worldcup.picks'))
        error = "Invalid username or password."
    return render_template('worldcup/login.html', error=error)


@worldcup_bp.route('/logout')
def logout():
    session.pop('wc_user', None)
    return redirect(url_for('worldcup.hub'))


@worldcup_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    if request.method == 'POST':
        name, pw = request.form.get('name', '').strip(), request.form.get('password', '')
        if not name or not pw:
            error = "Name and password are required."
        else:
            users = load_json(USERS_FILE, {})
            if name in users:
                error = "Username already taken."
            else:
                users[name] = {"password": pw}
                save_json(USERS_FILE, users)
                session['wc_user'] = name
                return redirect(url_for('worldcup.picks'))
    return render_template('worldcup/signup.html', error=error)


def is_tbd(game):
    tbd = {'tbd', 'tba', '', 'none'}
    return (game.get('home_team', '').strip().lower() in tbd or
            game.get('away_team', '').strip().lower() in tbd)


@worldcup_bp.route('/picks', methods=['GET', 'POST'])
def picks():
    username = session.get('wc_user')
    if not username:
        return redirect(url_for('worldcup.login', next=request.path))

    current_time = now_utc_str()
    today = current_time[:10]
    games = load_json(GAMES_FILE, {})
    all_picks = load_json(PICKS_FILE, {})
    user_picks = all_picks.get(username, {})

    champion_locked = is_champion_locked(games, current_time)
    all_teams = get_all_teams(games)
    champions = load_json(CHAMPIONS_FILE, {})
    my_champion = champions.get(username)

    # Build sorted list of dates that have at least one non-TBD game
    all_dates = sorted({
        g['kickoff_time'][:10]
        for g in games.values()
        if not is_tbd(g)
    })

    # Build per-date game index for the JS picks tray
    dates_games = {}
    for game_id, game in games.items():
        if is_tbd(game):
            continue
        d = game['kickoff_time'][:10]
        if d not in dates_games:
            dates_games[d] = []
        dates_games[d].append({
            'id': game_id,
            'home': game['home_team'],
            'away': game['away_team'],
            'stage': game['stage'],
            'locked': is_locked(game['kickoff_time'], current_time),
            'kickoff': game['kickoff_time'],
        })
    for d in dates_games:
        dates_games[d].sort(key=lambda x: x['kickoff'])

    if not all_dates:
        return render_template('worldcup/picks.html',
                               username=username,
                               games_today=[],
                               selected_date=today,
                               all_dates=[],
                               prev_date=None,
                               next_date=None,
                               user_picks=user_picks,
                               current_time=current_time,
                               dates_games={},
                               champion_locked=champion_locked,
                               all_teams=all_teams,
                               my_champion=my_champion)

    # Default to the first date with at least one unpicked non-locked game
    default_date = None
    for d in all_dates:
        for game_id, game in games.items():
            if is_tbd(game) or game['kickoff_time'][:10] != d:
                continue
            if not is_locked(game['kickoff_time'], current_time) and game_id not in user_picks:
                default_date = d
                break
        if default_date:
            break
    if not default_date:
        default_date = today if today in all_dates else next((d for d in all_dates if d >= today), all_dates[0])
    selected_date = request.args.get('date', default_date)
    if selected_date not in all_dates:
        selected_date = default_date

    idx = all_dates.index(selected_date)
    prev_date = all_dates[idx - 1] if idx > 0 else None
    next_date = all_dates[idx + 1] if idx < len(all_dates) - 1 else None

    if request.method == 'POST':
        if username not in all_picks:
            all_picks[username] = {}

        for game_id, game in games.items():
            if game['kickoff_time'][:10] != selected_date:
                continue
            if is_locked(game['kickoff_time'], current_time):
                continue
            pick_val = request.form.get(f'pick_{game_id}', '')
            if pick_val in ('home_win', 'away_win', 'draw'):
                all_picks[username][game_id] = pick_val
            elif pick_val == '' and game_id in all_picks[username]:
                del all_picks[username][game_id]

        save_json(PICKS_FILE, all_picks)
        return redirect(url_for('worldcup.picks', date=selected_date))

    # Games for the selected date only, excluding TBD
    games_today = sorted([
        {
            **game,
            'id': game_id,
            'locked': is_locked(game['kickoff_time'], current_time),
            'pts': game_points(game['stage']),
            'stage_label': STAGE_LABELS.get(game['stage'], game['stage']),
        }
        for game_id, game in games.items()
        if game['kickoff_time'][:10] == selected_date and not is_tbd(game)
    ], key=lambda x: x['kickoff_time'])

    return render_template('worldcup/picks.html',
                           username=username,
                           games_today=games_today,
                           selected_date=selected_date,
                           all_dates=all_dates,
                           prev_date=prev_date,
                           next_date=next_date,
                           user_picks=user_picks,
                           current_time=current_time,
                           dates_games=dates_games,
                           champion_locked=champion_locked,
                           all_teams=all_teams,
                           my_champion=my_champion)


@worldcup_bp.route('/champion/pick', methods=['POST'])
def champion_pick():
    username = session.get('wc_user')
    if not username:
        return {'error': 'Not logged in'}, 401

    data = request.get_json() or {}
    team = data.get('team', '').strip()

    games = load_json(GAMES_FILE, {})
    current_time = now_utc_str()

    if is_champion_locked(games, current_time):
        return {'error': 'Champion pick is locked'}, 403

    champions = load_json(CHAMPIONS_FILE, {})
    if team:
        champions[username] = team
    elif username in champions:
        del champions[username]
    save_json(CHAMPIONS_FILE, champions)
    return {'ok': True, 'team': team}


@worldcup_bp.route('/picks/submit', methods=['POST'])
def submit_picks():
    username = session.get('wc_user')
    if not username:
        return {'error': 'Not logged in'}, 401

    data = request.get_json() or {}
    picks_data = data.get('picks', {})

    current_time = now_utc_str()
    games = load_json(GAMES_FILE, {})
    all_picks = load_json(PICKS_FILE, {})

    if username not in all_picks:
        all_picks[username] = {}

    saved_count = 0
    for game_id, pick_val in picks_data.items():
        game = games.get(game_id)
        if not game or is_tbd(game):
            continue
        if is_locked(game['kickoff_time'], current_time):
            continue
        if pick_val in ('home_win', 'away_win', 'draw'):
            all_picks[username][game_id] = pick_val
            saved_count += 1

    save_json(PICKS_FILE, all_picks)
    return {'ok': True, 'saved': saved_count}


CHALK_USER = 'CHALK'


@worldcup_bp.route('/results')
def results():
    current_time = now_utc_str()
    games = load_json(GAMES_FILE, {})
    all_picks = load_json(PICKS_FILE, {})
    logged_in_user = session.get('wc_user')
    champion_locked = is_champion_locked(games, current_time)
    champions = load_json(CHAMPIONS_FILE, {})

    # CHALK always sorted last in all lists
    real_users = sorted(u for u in all_picks if u != CHALK_USER)
    usernames = real_users + ([CHALK_USER] if CHALK_USER in all_picks else [])

    user_totals = {u: 0 for u in usernames}
    for game_id, game in games.items():
        if game['result'] == 'pending':
            continue
        pts = game_points(game['stage'])
        for user in usernames:
            if all_picks.get(user, {}).get(game_id) == game['result']:
                user_totals[user] += pts

    real_lb = sorted(((u, s) for u, s in user_totals.items() if u != CHALK_USER), key=lambda x: x[1], reverse=True)
    chalk_lb = [(CHALK_USER, user_totals[CHALK_USER])] if CHALK_USER in user_totals else []
    sorted_leaderboard = real_lb + chalk_lb

    max_score = max((s for u, s in real_lb), default=0)
    leaders = [u for u, s in real_lb if s == max_score and s > 0]

    # % of completed games each real user picked same as CHALK
    chalk_picks = all_picks.get(CHALK_USER, {})
    completed_chalk_games = [
        gid for gid, g in games.items()
        if g['result'] != 'pending' and not is_tbd(g) and gid in chalk_picks
    ]
    chalk_agreement = {}
    for user in real_users:
        total = len(completed_chalk_games)
        if total == 0:
            chalk_agreement[user] = None
            continue
        user_p = all_picks.get(user, {})
        matches = sum(1 for gid in completed_chalk_games if user_p.get(gid) == chalk_picks[gid])
        chalk_agreement[user] = round(100 * matches / total)

    today_str = datetime.now(EASTERN).strftime('%Y-%m-%d')
    all_game_items = list(games.items())
    today_games    = sorted([(gid, g) for gid, g in all_game_items
                              if kickoff_et_date(g['kickoff_time']) == today_str],
                            key=lambda x: x[1]['kickoff_time'])
    completed_past = sorted([(gid, g) for gid, g in all_game_items
                              if kickoff_et_date(g['kickoff_time']) != today_str and g['result'] != 'pending'],
                            key=lambda x: x[1]['kickoff_time'], reverse=True)
    upcoming       = sorted([(gid, g) for gid, g in all_game_items
                              if kickoff_et_date(g['kickoff_time']) != today_str and g['result'] == 'pending'],
                            key=lambda x: x[1]['kickoff_time'])
    sorted_games = today_games + completed_past + upcoming
    table_rows = []
    for game_id, game in sorted_games:
        locked = is_locked(game['kickoff_time'], current_time)
        pts = game_points(game['stage'])
        user_cells = {}
        for user in usernames:
            pick = all_picks.get(user, {}).get(game_id)
            is_own = (user == logged_in_user)
            correct = (pick == game['result'] and game['result'] != 'pending')
            wrong = (pick is not None and game['result'] != 'pending' and pick != game['result'])
            if locked or is_own:
                user_cells[user] = {
                    'pick': pick_label(pick, game['home_team'], game['away_team']),
                    'hidden': False,
                    'correct': correct,
                    'wrong': wrong,
                    'result': game['result'],
                }
            else:
                user_cells[user] = {'pick': None, 'hidden': True, 'has_pick': pick is not None, 'correct': False, 'wrong': False, 'result': game['result']}
        table_rows.append({
            'game': game,
            'game_id': game_id,
            'pts': pts,
            'locked': locked,
            'users': user_cells,
            'stage_label': STAGE_LABELS.get(game['stage'], game['stage']),
        })

    return render_template('worldcup/results.html',
                           usernames=usernames,
                           table_rows=table_rows,
                           user_totals=user_totals,
                           leaders=leaders,
                           sorted_leaderboard=sorted_leaderboard,
                           logged_in_user=logged_in_user,
                           champions=champions,
                           champion_locked=champion_locked,
                           chalk_agreement=chalk_agreement,
                           chalk_user=CHALK_USER)


@worldcup_bp.route('/admin')
def admin():
    return redirect(url_for('worldcup.hub'))
