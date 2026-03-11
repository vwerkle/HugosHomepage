from flask import Blueprint, render_template, request, session, redirect, url_for
import json, os, pytz
from datetime import datetime, timedelta, timezone
from .data_manager import fetch_and_save_spreads
from .update_results import update_all_results_logic

madness_bp = Blueprint('madness', __name__)

DATA_DIR = 'data/madness'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
PICKS_FILE = os.path.join(DATA_DIR, 'picks.json')
SPREADS_FILE = os.path.join(DATA_DIR, 'daily_spreads.json')
REGISTRATION_OPEN = True

@madness_bp.route('/dness')
def dness_hub():
    return render_template('madness/dness_hub.html')

@madness_bp.route('/admin/update-games', methods=['GET', 'POST'])
def update_games():
    # Only allow logged-in admins (optional: add your own admin check here)
    if request.method == 'POST':
        # 1. Update Spreads for the future
        spreads_success = fetch_and_save_spreads()
        
        # 2. Update Results for the past
        # Check if user provided a specific date to look back, else default to '3' days
        lookback = request.form.get('days_back', '1')
        results_count = update_all_results_logic(days_back=lookback)
        message = f"Spreads Updated: {spreads_success} | Picks Graded: {results_count}"
        return render_template('madness/admin.html', message=message)

    return render_template('madness/admin.html')

@madness_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if not REGISTRATION_OPEN: return "Registration is closed!"
    if request.method == 'POST':
        name, pw, champ = request.form['name'], request.form['password'], request.form['champion']
        with open(USERS_FILE, 'r+') as f:
            users = json.load(f)
            if name in users: return "User already exists!"
            users[name] = {"password": pw, "champion": champ}
            f.seek(0); json.dump(users, f); f.truncate()
        session['user'] = name 
        return redirect(url_for('madness.login'))
    return render_template('madness/signup.html')

@madness_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        name, pw = request.form.get('name'), request.form.get('password')
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
        if name in users and users[name]['password'] == pw:
            session['user'] = name
            return redirect(url_for('madness.make_picks'))
        error = "Invalid username or password."
    return render_template('madness/login.html', error=error)

@madness_bp.route('/make-picks', methods=['GET', 'POST'])
def make_picks():
    username = session.get('user')
    if not username: return redirect(url_for('madness.login'))
    
    # 1. TIME & DATE SETUP
    eastern = pytz.timezone('US/Eastern')
    now_est = datetime.now(eastern)
    today_raw = now_est.strftime('%Y-%m-%d')
    tomorrow_dt = now_est + timedelta(days=1)
    tomorrow_raw = tomorrow_dt.strftime('%Y-%m-%d')
    today_pretty = now_est.strftime('%b %d')
    tomorrow_pretty = tomorrow_dt.strftime('%b %d')
    
    selected_date = request.args.get('date', today_raw)
    current_time_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # 2. LOAD ACTIVE SPREADS & BUILD LOCK LOOKUP
    games_for_date = []
    game_lock_lookup = {}  # Map Team -> Lock Time
    expired_options = set() # Exact strings that are already locked

    if os.path.exists(SPREADS_FILE):
        with open(SPREADS_FILE, 'r') as f:
            games_for_date = json.load(f).get(selected_date, [])
            games_for_date = sorted(games_for_date, key=lambda x: x['lock_time'])
            
            for g in games_for_date:
                away_str = f"{g['away_team']} {g['away_spread']}".strip()
                home_str = f"{g['home_team']} {g['home_spread']}".strip()
                
                # Build lookup for "Smart Locking" (Team-based)
                game_lock_lookup[g['away_team'].strip()] = g['lock_time']
                game_lock_lookup[g['home_team'].strip()] = g['lock_time']

                # Identify if game has started
                if g['lock_time'][:16] <= current_time_str[:16]:
                    expired_options.add(away_str)
                    expired_options.add(home_str)

    # 3. LOAD SAVED PICKS
    saved_selections = []
    saved_picks_raw_data = []
    if os.path.exists(PICKS_FILE):
        with open(PICKS_FILE, 'r') as f:
            all_user_picks = json.load(f)
            user_data = all_user_picks.get(username, {})
            saved_picks_raw_data = user_data.get(selected_date, [])
            saved_selections = [p['game_info'] for p in saved_picks_raw_data]

    while len(saved_selections) < 5:
        saved_selections.append("")

    # 4. SMART SLOT LOCKS
    slot_locks = [False] * 5
    for i in range(5):
        pick_str = saved_selections[i].strip()
        if not pick_str: continue
        
        # Extract Team Name (handles "LSU Tigers +6.5" -> "LSU Tigers")
        team_part = pick_str.rsplit(' ', 1)[0].strip() if " " in pick_str else pick_str
        
        lock_time = game_lock_lookup.get(team_part)
        
        if lock_time:
            # Game is live: lock only if time passed
            if lock_time[:16] <= current_time_str[:16]:
                slot_locks[i] = True
        else:
            # Game is graded/missing: lock it!
            slot_locks[i] = True

    # 5. POST LOGIC
    if request.method == 'POST':
        target_date = request.form.get('date') 
        user_selections = list(filter(None, request.form.getlist('game_picks')))
        
        # BOUNCER: Security checks
        if len(user_selections) > 5:
            return render_template('madness/picks.html', error="Max 5 picks allowed!", **locals())
        if len(user_selections) != len(set(user_selections)):
            return render_template('madness/picks.html', error="Duplicate teams selected!", **locals())

        # ANTI-CHEAT: Ensure no new picks for started games
        for pick in user_selections:
            if pick in expired_options and pick not in saved_selections:
                return render_template('madness/picks.html', error=f"Too late! {pick} has started.", **locals())

        # Format and Save (Preserve existing results)
        new_picks_data = []
        for pick in user_selections:
            existing_status = next((p.get('result', 'pending') for p in saved_picks_raw_data if p['game_info'] == pick), 'pending')
            new_picks_data.append({"game_info": pick, "result": existing_status})

        with open(PICKS_FILE, 'r+') as f:
            all_picks = json.load(f)
            if username not in all_picks: all_picks[username] = {}
            all_picks[username][target_date] = new_picks_data
            f.seek(0); json.dump(all_picks, f, indent=4); f.truncate()
            
        return redirect(url_for('madness.results'))

    return render_template('madness/picks.html', 
                           games=games_for_date, 
                           selected_date=selected_date,
                           today_raw=today_raw,
                           tomorrow_raw=tomorrow_raw,
                           today_pretty=today_pretty,
                           tomorrow_pretty=tomorrow_pretty,
                           current_time_str=current_time_str,
                           slot_locks=slot_locks,
                           saved_selections=saved_selections,
                           expired_options=expired_options)

@madness_bp.route('/results')
def results():
    eastern = pytz.timezone('US/Eastern')
    now_est = datetime.now(eastern)
    today_raw = now_est.strftime('%Y-%m-%d')
    # 1. Load Picks and Spreads
    all_picks = json.load(open(PICKS_FILE)) if os.path.exists(PICKS_FILE) else {}
    all_spreads = json.load(open(SPREADS_FILE)) if os.path.exists(SPREADS_FILE) else {}
    
    # Use UTC time to match the API lock_times
    current_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    logged_in_user = session.get('user')
    
    usernames = sorted(all_picks.keys())
    all_dates = set()
    for user_data in all_picks.values():
        all_dates.update(user_data.keys())
    
    # Sorted oldest to newest to match your Excel sheet flow
    sorted_dates = sorted(list(all_dates))

    table_data = []
    
    for d in sorted_dates:
        # 2. Build a more robust lookup for this specific date
        # We strip() the strings to prevent hidden space issues
        games_on_day = all_spreads.get(d, [])
        games_lookup = {}
        for g in games_on_day:
            away_key = f"{g['away_team']} {g['away_spread']}".strip()
            home_key = f"{g['home_team']} {g['home_spread']}".strip()
            games_lookup[away_key] = g['lock_time']
            games_lookup[home_key] = g['lock_time']

        day_block = {'date': d, 'slots': []}
        
        # 3. Iterate through the 5 pick slots
        for i in range(5):
            slot_data = {}
            for user in usernames:
                user_picks = all_picks[user].get(d, [])
                if i < len(user_picks):
                    pick_obj = user_picks[i]
                    pick_str = pick_obj['game_info'].strip()
                    result_status = pick_obj.get('result', 'pending')
                    
                    # 1. Lookup the lock time from current spreads
                    game_lock_time = games_lookup.get(pick_str)
                    
                    # 2. Determine visibility
                    is_own_pick = (user == logged_in_user)
                    
                    # LOGIC: Show if result is final, OR lock time passed, OR it's a past date
                    is_started = False
                    if result_status != 'pending':
                        is_started = True
                    elif game_lock_time:
                        is_started = current_time >= game_lock_time
                    elif d < today_raw: 
                        # If date 'd' is before today, it's definitely started
                        is_started = True

                    if is_own_pick or is_started:
                        display_text = pick_str
                        is_hidden = False
                    else:
                        display_text = "🔒 HIDDEN"
                        is_hidden = True
                        
                    slot_data[user] = {
                        'info': display_text,
                        'result': result_status,
                        'is_hidden': is_hidden
                    }
                else:
                    slot_data[user] = {'info': '', 'result': 'none', 'is_hidden': False}
            
            day_block['slots'].append({'label': f"Day {d} - P{i+1}", 'users': slot_data})
        
        table_data.append(day_block)
    user_totals = {user: 0 for user in usernames}
    for row in table_data:
        for slot in row['slots']:
            for user, p in slot['users'].items():
                if p.get('result') == 'win':
                    user_totals[user] += 1
    sorted_leaderboard = sorted(user_totals.items(), key=lambda x: x[1], reverse=True)

    # Re-calculate leaders (just for the crown/styling)
    max_score = max(user_totals.values()) if user_totals else 0
    leaders = [u for u, s in user_totals.items() if s == max_score and s > 0]
    # Pass user_totals to the template
    return render_template('madness/results.html', 
                           usernames=usernames, 
                           table_data=table_data, 
                           current_time=current_time,
                           user_totals=user_totals,
                           leaders=leaders,
                           sorted_leaderboard=sorted_leaderboard)