from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
import json
import os
import requests
import time
from datetime import datetime

finals_bp = Blueprint('finals', __name__, url_prefix='/finals')

DATA_DIR = 'data/finals'
PICKS_FILE = os.path.join(DATA_DIR, 'picks.json')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
CACHE_FILE = os.path.join(DATA_DIR, 'live_cache.json')
CACHE_TTL = 300  # 5 minutes; bypassed if a Finals game is live

DEFAULT_CONFIG = {
    "nhl_season": "20252026",
    "nba_season": "2025-26",
    "player_ids": {
        "nhl": {},
        "nba": {}
    },
    "scoring": {
        "nhl_winner": 500,
        "nhl_games_exact": 80,
        "nhl_games_off_one": 40,
        "nba_winner": 500,
        "nba_games_exact": 80,
        "nba_games_off_one": 40,
        "nhl_goal": 40,
        "nhl_assist": 20
    }
}


def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def fetch_nhl_finals_data(player_ids, season):
    """Single pass through Finals game boxscores (max 7 requests).
    Returns (series, player_stats, live_game_id) — replaces separate series,
    player-log, and live-detection calls that were hitting rate limits."""
    year = season[:4]
    id_to_name = {v: k for k, v in player_ids.items()}
    wins = {}
    teams = []
    total_games = 0
    player_stats = {name: {'goals': 0, 'assists': 0, 'points': 0} for name in player_ids}
    live_game_id = None

    for game_num in range(1, 8):
        game_id = f'{year}03041{game_num}'
        try:
            r = requests.get(
                f'https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore',
                timeout=8
            )
            if r.status_code == 404:
                break  # series not yet at this game
            if r.status_code == 429:
                time.sleep(5)
                r = requests.get(
                    f'https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore',
                    timeout=8
                )
            r.raise_for_status()
            data = r.json()
            state = data.get('gameState', '')
            home = data.get('homeTeam', {}).get('abbrev', '')
            away = data.get('awayTeam', {}).get('abbrev', '')
            if home and home not in teams: teams.append(home)
            if away and away not in teams: teams.append(away)

            is_final = state in ('FINAL', 'OFF')
            is_live  = state in ('LIVE', 'CRIT')

            if not is_final and not is_live:
                break  # game not started yet

            # Accumulate player stats from boxscore (works for both completed + live)
            for side in ('homeTeam', 'awayTeam'):
                for cat in ('forwards', 'defense'):
                    for pl in data.get('playerByGameStats', {}).get(side, {}).get(cat, []):
                        name = id_to_name.get(pl.get('playerId'))
                        if name:
                            player_stats[name]['goals']   += pl.get('goals', 0)
                            player_stats[name]['assists']  += pl.get('assists', 0)

            if is_final:
                h_score = data.get('homeTeam', {}).get('score', 0)
                a_score = data.get('awayTeam', {}).get('score', 0)
                total_games += 1
                wins[home if h_score > a_score else away] = \
                    wins.get(home if h_score > a_score else away, 0) + 1

            if is_live:
                live_game_id = game_id
                break  # don't look for more games while one is in progress

        except Exception as e:
            print(f'[Finals] NHL game {game_id} error: {e}')
            break

        time.sleep(0.2)  # be polite between requests

    for name in player_stats:
        player_stats[name]['points'] = player_stats[name]['goals'] + player_stats[name]['assists']

    series = {}
    if len(teams) >= 2:
        t1, t2 = teams[0], teams[1]
        w1, w2 = wins.get(t1, 0), wins.get(t2, 0)
        winner = t1 if w1 >= 4 else (t2 if w2 >= 4 else None)
        series = {
            'team1': t1, 'team2': t2,
            'wins1': w1, 'wins2': w2,
            'total_games': total_games,
            'winner': winner,
            'complete': winner is not None,
        }

    return series, player_stats, live_game_id


NBA_HEADERS = {
    'Accept': '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Host': 'stats.nba.com',
    'Origin': 'https://www.nba.com',
    'Referer': 'https://www.nba.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'x-nba-stats-origin': 'stats',
    'x-nba-stats-token': 'true',
}


def _nba_finals_prefix(season):
    """Game ID prefix for NBA Finals games, e.g. '00425004' for 2025-26.
    Format: 00 (NBA) + 4 (playoffs) + YY (season year) + 004 (round-4 code) + GG (game)."""
    year2 = season[2:4]  # '25' from '2025-26'
    return f'004{year2}004'


def _nba_stats_get(endpoint, params, timeout=20):
    """Single request to stats.nba.com with retry on failure."""
    for attempt in range(3):
        try:
            if attempt:
                time.sleep(attempt * 3)
            r = requests.get(
                f'https://stats.nba.com/stats/{endpoint}',
                params=params,
                headers=NBA_HEADERS,
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'[Finals] NBA {endpoint} attempt {attempt + 1} error: {e}')
    return None


def _parse_nba_gamelog(season, player_or_team='T'):
    """Fetch the full playoffs game log (one request) for teams or players."""
    return _nba_stats_get('leaguegamelog', {
        'LeagueID': '00',
        'Season': season,
        'SeasonType': 'Playoffs',
        'Direction': 'ASC',
        'PlayerOrTeam': player_or_team,
        'Sorter': 'DATE',
        'Counter': '0',
        'DateFrom': '',
        'DateTo': '',
    })


def fetch_nba_series(season):
    """Fetch NBA Finals series data via team game log, filtered to Finals game IDs."""
    prefix = _nba_finals_prefix(season)
    data = _parse_nba_gamelog(season, 'T')
    if not data:
        return {}
    try:
        rs = data.get('resultSets', [{}])[0]
        hdrs = rs.get('headers', [])
        rows = rs.get('rowSet', [])
        if not {'GAME_ID', 'TEAM_ABBREVIATION', 'WL'}.issubset(set(hdrs)):
            return {}
        gi, ti, wl_i = hdrs.index('GAME_ID'), hdrs.index('TEAM_ABBREVIATION'), hdrs.index('WL')
        team_wins, teams_seen = {}, []
        for row in rows:
            if not str(row[gi]).startswith(prefix):
                continue
            team = row[ti]
            if team not in teams_seen:
                teams_seen.append(team)
            if row[wl_i] == 'W':
                team_wins[team] = team_wins.get(team, 0) + 1
        if len(teams_seen) < 2:
            return {}
        t1, t2 = teams_seen[0], teams_seen[1]
        w1, w2 = team_wins.get(t1, 0), team_wins.get(t2, 0)
        total = w1 + w2
        winner = t1 if w1 >= 4 else (t2 if w2 >= 4 else None)
        return {'team1': t1, 'team2': t2, 'wins1': w1, 'wins2': w2,
                'total_games': total, 'winner': winner, 'complete': winner is not None}
    except Exception as e:
        print(f'[Finals] NBA series parse error: {e}')
    return {}



def fetch_nba_player_stats(player_ids, season):
    """Fetch Finals-only P+R+A per player — one leaguegamelog request, filtered by game ID and player ID."""
    prefix = _nba_finals_prefix(season)
    zeros = {'pts': 0, 'reb': 0, 'ast': 0, 'total': 0, 'games': 0}
    stats = {name: dict(zeros) for name in player_ids}
    if not player_ids:
        return stats

    id_to_name = {v: k for k, v in player_ids.items()}
    data = _parse_nba_gamelog(season, 'P')
    if not data:
        return stats

    try:
        rs = data.get('resultSets', [{}])[0]
        hdrs = rs.get('headers', [])
        rows = rs.get('rowSet', [])
        needed = {'PLAYER_ID', 'GAME_ID', 'PTS', 'REB', 'AST'}
        if not needed.issubset(set(hdrs)):
            return stats
        pid_i = hdrs.index('PLAYER_ID')
        gid_i = hdrs.index('GAME_ID')
        pts_i = hdrs.index('PTS')
        reb_i = hdrs.index('REB')
        ast_i = hdrs.index('AST')
        for row in rows:
            name = id_to_name.get(row[pid_i])
            if name and str(row[gid_i]).startswith(prefix):
                stats[name]['pts'] += row[pts_i]
                stats[name]['reb'] += row[reb_i]
                stats[name]['ast'] += row[ast_i]
                stats[name]['games'] += 1
        for name in stats:
            p, r, a = stats[name]['pts'], stats[name]['reb'], stats[name]['ast']
            stats[name]['total'] = p + r + a
    except Exception as e:
        print(f'[Finals] NBA player stats parse error: {e}')
    return stats




def fetch_nba_live_game_id(season):
    """Return the game ID if an NBA Finals game is live right now, else None.
    NBA leaguegamelog already includes live-game stats, so we only need the ID
    to know whether to bypass the cache — no separate stat merge needed."""
    prefix = _nba_finals_prefix(season)
    try:
        r = requests.get(
            'https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json',
            headers={**NBA_HEADERS, 'Host': 'cdn.nba.com'},
            timeout=8
        )
        if r.status_code != 200 or not r.text.strip():
            return None
        for game in r.json().get('scoreboard', {}).get('games', []):
            gid = str(game.get('gameId', ''))
            if gid.startswith(prefix) and game.get('gameStatus') == 2:
                return gid
    except Exception as e:
        print(f'[Finals] NBA scoreboard check error: {e}')
    return None



def get_live_data(config, force=False):
    nhl_pids = config.get('player_ids', {}).get('nhl', {})
    nba_pids = config.get('player_ids', {}).get('nba', {})
    season_nhl = config.get('nhl_season', '20252026')
    season_nba = config.get('nba_season', '2025-26')

    # Quick live-game checks (cheap — CDN for NBA, just reads local boxscore status for NHL
    # is handled inside fetch_nhl_finals_data below)
    nba_live_gid = fetch_nba_live_game_id(season_nba)

    # For NHL, peek at the cache to decide if we need to bypass it
    # (fetch_nhl_finals_data will do its own live detection)
    if not force:
        cache = load_json(CACHE_FILE, {})
        if cache.get('ts', 0) + CACHE_TTL > time.time() and not nba_live_gid:
            cached = cache.get('data', {})
            # If NHL had a live game last time, don't use the cache
            if not cached.get('nhl_live_game'):
                cached['game_live'] = bool(cached.get('nhl_live_game') or nba_live_gid)
                return cached

    # NHL: one pass through boxscores — series + player stats + live detection
    nhl_series, nhl_players, nhl_live_gid = fetch_nhl_finals_data(nhl_pids, season_nhl)

    # NBA: single leaguegamelog request (includes live game stats automatically)
    nba_players = fetch_nba_player_stats(nba_pids, season_nba)
    nba_series  = fetch_nba_series(season_nba)

    game_live = bool(nhl_live_gid or nba_live_gid)
    live = {
        'nhl_series': nhl_series,
        'nba_series': nba_series,
        'nhl_players': nhl_players,
        'nba_players': nba_players,
        'fetched_at': int(time.time()),
        'game_live': game_live,
        'nhl_live_game': nhl_live_gid,
        'nba_live_game': nba_live_gid,
    }
    if not game_live:
        save_json(CACHE_FILE, {'ts': time.time(), 'data': live})
    return live


def _series_score(p_winner_key, p_games_key, series, scoring, winner_pts_key, games_exact_key, games_off_key):
    """Compute points + labels for one sport's series picks."""
    actual_winner = series.get('winner')
    winner_ok = False
    w_pts = 0
    if actual_winner and p_winner_key == actual_winner:
        w_pts = scoring.get(winner_pts_key, 10)
        winner_ok = True

    g_pts = 0
    g_label = 'pending'
    total_g = series.get('total_games')
    if winner_ok and total_g and series.get('complete'):
        diff = abs((p_games_key or 0) - total_g)
        if diff == 0:
            g_pts = scoring.get(games_exact_key, 5)
            g_label = 'exact'
        elif diff == 1:
            g_pts = scoring.get(games_off_key, 2)
            g_label = 'close'
        else:
            g_label = 'miss'
    elif actual_winner and not winner_ok:
        g_label = 'n/a'

    return w_pts, winner_ok, actual_winner, g_pts, g_label


def calc_scores(picks, live, config):
    scoring = config.get('scoring', DEFAULT_CONFIG['scoring'])
    nhl_s = live.get('nhl_series', {})
    nba_s = live.get('nba_series', {})
    goal_pts = scoring.get('nhl_goal', 40)
    assist_pts = scoring.get('nhl_assist', 20)
    results = {}

    for name, p in picks.items():
        nhl_w_pts, nhl_winner_ok, nhl_winner_actual, nhl_g_pts, nhl_g_label = _series_score(
            p.get('nhl_winner'), p.get('nhl_games'),
            nhl_s, scoring, 'nhl_winner', 'nhl_games_exact', 'nhl_games_off_one'
        )
        nba_w_pts, nba_winner_ok, nba_winner_actual, nba_g_pts, nba_g_label = _series_score(
            p.get('nba_winner'), p.get('nba_games'),
            nba_s, scoring, 'nba_winner', 'nba_games_exact', 'nba_games_off_one'
        )

        # NHL skaters — 3 players, each (G×goal_pts) + (A×assist_pts)
        nhl_skater_details = []
        for pl in (p.get('nhl_players') or []):
            ps = live.get('nhl_players', {}).get(pl, {})
            g = ps.get('goals', 0)
            a = ps.get('assists', 0)
            nhl_skater_details.append({
                'name': pl,
                'goals': g,
                'assists': a,
                'score': g * goal_pts + a * assist_pts,
            })
        nhl_skater_total = sum(s['score'] for s in nhl_skater_details)

        # NBA player — 1 player, flat P+R+A
        nba_player_details = []
        for pl in (p.get('nba_players') or []):
            ps = live.get('nba_players', {}).get(pl, {})
            pts_v = ps.get('pts', 0)
            reb_v = ps.get('reb', 0)
            ast_v = ps.get('ast', 0)
            nba_player_details.append({
                'name': pl,
                'pts': pts_v,
                'reb': reb_v,
                'ast': ast_v,
                'score': pts_v + reb_v + ast_v,
            })
        nba_player_total = sum(s['score'] for s in nba_player_details)

        series_pts = nhl_w_pts + nba_w_pts
        games_pts = nhl_g_pts + nba_g_pts
        player_pts = nhl_skater_total + nba_player_total
        total = series_pts + games_pts + player_pts

        results[name] = {
            'nhl_winner_pts': nhl_w_pts,
            'nhl_winner_ok': nhl_winner_ok,
            'nhl_winner_actual': nhl_winner_actual,
            'nhl_games_pts': nhl_g_pts,
            'nhl_games_label': nhl_g_label,
            'nba_winner_pts': nba_w_pts,
            'nba_winner_ok': nba_winner_ok,
            'nba_winner_actual': nba_winner_actual,
            'nba_games_pts': nba_g_pts,
            'nba_games_label': nba_g_label,
            'nhl_skaters': nhl_skater_details,
            'nhl_skater_total': nhl_skater_total,
            'nba_players': nba_player_details,
            'nba_player_total': nba_player_total,
            'series_pts': series_pts,
            'games_pts': games_pts,
            'player_pts': player_pts,
            'total': total,
        }
    return results


@finals_bp.route('/')
def tracker():
    picks = load_json(PICKS_FILE)
    config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    live = get_live_data(config)
    scores = calc_scores(picks, live, config)
    ranked = sorted(scores.items(), key=lambda x: (
        x[1]['total'], x[1]['series_pts'], x[1]['games_pts'], x[1]['player_pts']
    ), reverse=True)
    fetched_at = live.get('fetched_at')
    last_updated = datetime.fromtimestamp(fetched_at).strftime('%I:%M %p').lstrip('0') if fetched_at else '—'
    nhl_sorted = sorted(live.get('nhl_players', {}).items(), key=lambda x: x[1].get('points', 0), reverse=True)
    nba_sorted = sorted(live.get('nba_players', {}).items(), key=lambda x: x[1].get('total', 0), reverse=True)
    return render_template('finals/tracker.html',
        picks=picks, config=config, live=live,
        scores=scores, ranked=ranked, last_updated=last_updated,
        nhl_sorted=nhl_sorted, nba_sorted=nba_sorted,
        game_live=live.get('game_live', False))


@finals_bp.route('/api/live')
def api_live():
    config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    live = get_live_data(config)
    picks = load_json(PICKS_FILE)
    scores = calc_scores(picks, live, config)
    ranked = sorted(scores.items(), key=lambda x: (
        x[1]['total'], x[1]['series_pts'], x[1]['games_pts'], x[1]['player_pts']
    ), reverse=True)
    return jsonify({
        'fetched_at': live.get('fetched_at'),
        'game_live': live.get('game_live', False),
        'nhl_series': live.get('nhl_series', {}),
        'nba_series': live.get('nba_series', {}),
        'ranked': [{'name': n, **sc} for n, sc in ranked],
    })


@finals_bp.route('/refresh')
def refresh():
    config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    get_live_data(config, force=True)
    return redirect(url_for('finals.tracker'))


@finals_bp.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('finals_admin') != 'hugo':
        return redirect(url_for('finals.login'))
    picks = load_json(PICKS_FILE)
    config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    msg = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'picks':
            try:
                save_json(PICKS_FILE, json.loads(request.form['data']))
                msg = ('ok', 'Picks saved.')
            except Exception as e:
                msg = ('err', str(e))
        elif action == 'config':
            try:
                save_json(CONFIG_FILE, json.loads(request.form['data']))
                if os.path.exists(CACHE_FILE):
                    os.remove(CACHE_FILE)
                msg = ('ok', 'Config saved and cache cleared.')
            except Exception as e:
                msg = ('err', str(e))
        elif action == 'refresh':
            config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
            get_live_data(config, force=True)
            msg = ('ok', 'Live data refreshed.')
        picks = load_json(PICKS_FILE)
        config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    return render_template('finals/admin.html',
        picks_json=json.dumps(picks, indent=2),
        config_json=json.dumps(config, indent=2),
        msg=msg)


@finals_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('pw') == 'hugo':
            session['finals_admin'] = 'hugo'
            return redirect(url_for('finals.admin'))
        error = 'Wrong password.'
    return render_template('finals/login.html', error=error)
