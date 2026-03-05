from flask import Blueprint, render_template, request, json
import os, random, requests

random_pool_bp = Blueprint('random_pool', __name__)
DATA_PATH = 'data/random'
API_KEY = '069fb0f664323b83b2cdd9349e662208'

@random_pool_bp.route('/random-pool')
def random_pool_viewer():
    pool_file = os.path.join(DATA_PATH, 'random_pool.json')
    try:
        with open(pool_file, 'r') as f:
            pool_data = json.load(f)
        return render_template('random/random_pool.html', pool_data=pool_data)
    except FileNotFoundError:
        return "Pool not initialized! Go to Admin."

@random_pool_bp.route('/admin/random-pool')
def admin_random_pool():
    return render_template('random/admin_random_pool.html')

@random_pool_bp.route('/admin/init-pool', methods=['POST'])
def init_pool():
    TEAMS_FILE = os.path.join(DATA_PATH, '64_teams.txt')
    PLAYERS_FILE = os.path.join(DATA_PATH, 'players.txt')
    with open(TEAMS_FILE, 'r') as f:
        teams = [line.strip() for line in f.readlines() if line.strip()]
    with open(PLAYERS_FILE, 'r') as f:
        players = [line.strip() for line in f.readlines() if line.strip()]
    
    random.shuffle(teams)
    
    # Assign teams to players (looping through players if teams > players)
    new_pool = {}
    for i, team in enumerate(teams):
        new_pool[team] = {
            "owner": players[i % len(players)],
            "status": "active",
            "last_result": "pending"
        }
    
    with open('data/random/random_pool.json', 'w') as f:
        json.dump(new_pool, f, indent=4)
    return "Pool Initialized!"
    return "Pool Initialized!"

@random_pool_bp.route('/admin/process-steals', methods=['POST'])
def process_steals():
    with open('data/random/random_pool.json', 'r') as f:
        pool_data = json.load(f)

    # Get scores (reusing your scores API)
    url = f'https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores/?apiKey={API_KEY}&daysFrom=1'
    scores_data = requests.get(url).json()

    for game in scores_data:
        if not game['completed']: continue
        
        score_map = {s['name']: int(s['score']) for s in game['scores']}
        home_team, away_team = game['home_team'], game['away_team']
        
        # Identify Winner/Loser
        winner = home_team if score_map[home_team] > score_map[away_team] else away_team
        loser = away_team if winner == home_team else home_team

        if loser in pool_data and winner in pool_data:
            loser_spread = pool_data[loser].get('locked_spread', 0)
            
            # Check the "Cover"
            if (score_map[loser] + loser_spread) > score_map[winner]:
                # THE STEAL
                thief = pool_data[loser]['owner']
                original_winner_owner = pool_data[winner]['owner']
                
                # Update history log
                log_entry = f"{thief} (Stolen from {original_winner_owner})"
                pool_data[winner]['history'].append(log_entry)
                
                # Transfer ownership
                pool_data[winner]['owner'] = thief
                pool_data[winner]['last_result'] = 'stolen'
                pool_data[loser]['status'] = 'eliminated'
            else:
                # Normal Exit
                pool_data[winner]['last_result'] = 'held'
                pool_data[loser]['status'] = 'eliminated'

    with open('data/random/random_pool.json', 'w') as f:
        json.dump(pool_data, f, indent=4)
    return "Steals and History Log Updated!"

@random_pool_bp.route('/admin/lock-spreads', methods=['POST'])
def lock_spreads():
    # Fetch current odds from The Odds API
    url = f'https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/?apiKey={API_KEY}&regions=us&markets=spreads'
    response = requests.get(url)
    if response.status_code != 200: return "API Error", 500
    
    odds_data = response.json()
    
    with open('data/random/random_pool.json', 'r') as f:
        pool_data = json.load(f)

    # Map teams to their current spread
    for game in odds_data:
        # We look for the 'h2h' or 'spreads' market
        bookmaker = game['bookmakers'][0] # Use the first available bookie
        market = bookmaker['markets'][0]
        
        for outcome in market['outcomes']:
            team_name = outcome['name']
            spread_val = outcome['point']
            
            if team_name in pool_data:
                pool_data[team_name]['locked_spread'] = float(spread_val)

    with open('data/random/random_pool.json', 'w') as f:
        json.dump(pool_data, f, indent=4)
        
    return "Spreads Locked for Today's Games!"