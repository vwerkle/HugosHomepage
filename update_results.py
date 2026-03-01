import json
import requests
import os

# Use the same variables from your main app
API_KEY = '069fb0f664323b83b2cdd9349e662208'
PICKS_FILE = 'picks.json'

def update_all_results_logic(days_back='1'):
    url = f'https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores/?apiKey={API_KEY}&daysFrom={days_back}'
    response = requests.get(url)
    if response.status_code != 200: return 0

    scores_data = response.json()
    if not os.path.exists(PICKS_FILE): return 0
    
    with open(PICKS_FILE, 'r') as f:
        all_picks = json.load(f)
        
    updated_count = 0

    for user, dates in all_picks.items():
        for date_str, picks in dates.items(): # date_str is "2026-03-01"
            for p in picks:
                # Skip if already graded
                if p.get('result') != 'pending': continue
                
                parts = p['game_info'].rsplit(' ', 1)
                picked_team, spread = parts[0], float(parts[1])

                for game in scores_data:
                    if not game['completed']: continue
                    
                    # 1. NEW: Check if the game's start date matches the pick's date
                    # API commence_time is "2026-03-01T21:00:00Z"
                    game_date = game['commence_time'].split('T')[0]
                    
                    if game_date != date_str:
                        continue # This is a different game day, skip it!

                    # 2. Check if our team is in this specific game
                    if picked_team in [game['home_team'], game['away_team']]:
                        # Create a clean dictionary of scores: {"Duke": 80, "UNC": 75}
                        score_dict = {s['name']: int(s['score']) for s in game['scores']}
                        
                        my_s = score_dict.get(picked_team, 0)
                        # Identify the opponent's name to get their score
                        opp_name = game['away_team'] if picked_team == game['home_team'] else game['home_team']
                        opp_s = score_dict.get(opp_name, 0)

                        # Standard spread logic
                        if (my_s + spread) > opp_s:
                            p['result'] = 'win'
                        elif (my_s + spread) < opp_s:
                            p['result'] = 'loss'
                        else:
                            p['result'] = 'push'
                        
                        updated_count += 1
                        break # Found the right game for this pick, stop looking in scores_data

    with open(PICKS_FILE, 'w') as f:
        json.dump(all_picks, f, indent=4)
        
    return updated_count

if __name__ == "__main__":
    update_all_results_logic(1)