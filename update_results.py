import json
import requests
import os

# Use the same variables from your main app
API_KEY = '069fb0f664323b83b2cdd9349e662208'
PICKS_FILE = 'picks.json'

def update_all_results_logic(days_back='3'):
    url = f'https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores/?apiKey={API_KEY}&daysFrom={days_back}'
    response = requests.get(url)
    if response.status_code != 200: return 0

    scores_data = response.json()
    all_picks = json.load(open(PICKS_FILE)) if os.path.exists(PICKS_FILE) else {}
    updated_count = 0

    for user, dates in all_picks.items():
        for date_str, picks in dates.items():
            for p in picks:
                if p.get('result') != 'pending': continue
                
                parts = p['game_info'].rsplit(' ', 1)
                picked_team, spread = parts[0], float(parts[1])

                for game in scores_data:
                    if not game['completed']: continue
                    if picked_team in [game['home_team'], game['away_team']]:
                        score_dict = {s['name']: int(s['score']) for s in game['scores']}
                        my_s = score_dict.get(picked_team, 0)
                        opp_s = score_dict.get(game['away_team'] if picked_team == game['home_team'] else game['home_team'], 0)

                        p['result'] = 'win' if (my_s + spread) > opp_s else 'loss' if (my_s + spread) < opp_s else 'push'
                        updated_count += 1

    with open(PICKS_FILE, 'w') as f:
        json.dump(all_picks, f, indent=4)
    return updated_count

if __name__ == "__main__":
    update_all_results_logic(1)