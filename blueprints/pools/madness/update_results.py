import json
import requests
import os
import pytz
from datetime import datetime
# Use the same variables from your main app
API_KEY = '069fb0f664323b83b2cdd9349e662208'
PICKS_FILE = 'data/madness/picks.json'


# Assuming these are defined globally or imported
# API_KEY = 'your_api_key'
# PICKS_FILE = 'data/madness/picks.json'

def update_all_results_logic(days_back='1'):
    url = f'https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores/?apiKey={API_KEY}&daysFrom={days_back}'
    
    try:
        response = requests.get(url)
        if response.status_code != 200:
            print(f"API Error: {response.status_code}")
            return 0
        scores_data = response.json()
    except Exception as e:
        print(f"Request failed: {e}")
        return 0

    if not os.path.exists(PICKS_FILE):
        print("Picks file not found.")
        return 0
    
    with open(PICKS_FILE, 'r') as f:
        all_picks = json.load(f)
        
    updated_count = 0
    eastern = pytz.timezone('US/Eastern')

    for user, dates in all_picks.items():
        for date_str, picks in dates.items():
            for p in picks:
                # 1. Skip if already graded
                if p.get('result') != 'pending':
                    continue
                
                # 2. Parse pick info
                try:
                    parts = p['game_info'].rsplit(' ', 1)
                    picked_team = parts[0].strip()
                    spread = float(parts[1])
                except (ValueError, IndexError):
                    continue

                for game in scores_data:
                    # 3. Skip unfinished games
                    if not game.get('completed'):
                        continue
                    
                    # 4. Convert UTC commence_time to US/Eastern
                    # API format: "2026-03-01T21:00:00Z"
                    utc_dt = datetime.strptime(game['commence_time'], '%Y-%m-%dT%H:%M:%SZ')
                    utc_dt = pytz.utc.localize(utc_dt)
                    est_dt = utc_dt.astimezone(eastern)
                    game_date_est = est_dt.strftime('%Y-%m-%d')
                    
                    # 5. Check if the dates match (using Eastern Time)
                    if game_date_est != date_str:
                        continue 

                    # 6. Check if picked team is in this game
                    home_team = game['home_team'].strip()
                    away_team = game['away_team'].strip()

                    if picked_team == home_team or picked_team == away_team:
                        # Map scores to team names
                        score_dict = {s['name'].strip(): int(s['score']) for s in game['scores']}
                        
                        my_score = score_dict.get(picked_team)
                        if my_score is None: 
                            continue

                        # Get opponent score
                        opp_name = away_team if picked_team == home_team else home_team
                        opp_score = score_dict.get(opp_name, 0)

                        # 7. Apply Spread Logic
                        # Final Result = (My Team Score + Spread) vs Opponent Score
                        if (my_score + spread) > opp_score:
                            p['result'] = 'win'
                        elif (my_score + spread) < opp_score:
                            p['result'] = 'loss'
                        else:
                            p['result'] = 'push'
                        
                        updated_count += 1
                        break 

    # 8. Save updated picks back to JSON
    with open(PICKS_FILE, 'w') as f:
        json.dump(all_picks, f, indent=4)
        
    return updated_count

if __name__ == "__main__":
    update_all_results_logic(1)