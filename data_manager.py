import requests
import json
import os
from datetime import datetime, timezone
import pytz
API_KEY = '069fb0f664323b83b2cdd9349e662208'
SPREADS_FILE = 'daily_spreads.json'

def fetch_and_save_spreads():
    # 1. Check if the key is still the placeholder
    if API_KEY == 'PASTE_YOUR_ACTUAL_API_KEY_HERE':
        print("CRITICAL: You haven't added your Odds API key yet!")
        return False

    url = f'https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/?apiKey={API_KEY}&regions=us&markets=spreads&oddsFormat=american'
    
    try:
        response = requests.get(url)
        
        # 2. Check for API-specific errors (like out of credits)
        if response.status_code != 200:
            print(f"API Error {response.status_code}: {response.text}")
            return False
            
        data = response.json()
        formatted_games = {}
        eastern = pytz.timezone('US/Eastern')

        for game in data:
            try:
            # Convert UTC string to Eastern Time object
                utc_dt = datetime.strptime(game['commence_time'], '%Y-%m-%dT%H:%M:%SZ')
                utc_dt = pytz.utc.localize(utc_dt)

                # 2. Convert to Eastern ONLY to define the dictionary key
                eastern = pytz.timezone('US/Eastern')
                est_dt = utc_dt.astimezone(eastern)

                # This will turn "Feb 27 01:00 UTC" into "Feb 26 20:00 EST"
                date_key = est_dt.strftime('%Y-%m-%d') 

                # 3. Save the entry under the CORRECT Eastern date
                if date_key not in formatted_games:
                    formatted_games[date_key] = []

                bookmaker = game['bookmakers'][0]
                market = bookmaker['markets'][0]
                home_team = game['home_team']
                away_team = game['away_team']
                
                # Safety Check: Find the spread value for the home team
                outcomes = market.get('outcomes', [])
                home_spread = next((o['point'] for o in market.get('outcomes', []) if o['name'] == home_team), 0)
                away_spread = home_spread * -1  # If home is -4.5, away is +4.5

                game_entry = {
                    "away_team": away_team,
                    "away_spread": f"+{away_spread}" if away_spread > 0 else str(away_spread),
                    "home_team": home_team,
                    "home_spread": f"+{home_spread}" if home_spread > 0 else str(home_spread),
                    "lock_time": game['commence_time']
                }
                
                if date_key not in formatted_games:
                    formatted_games[date_key] = []
                formatted_games[date_key].append(game_entry)
            except (IndexError, KeyError) as e:
                print(f"Skipping a game due to missing data: {e}")
                continue

        # 4. Save to file
        with open(SPREADS_FILE, 'w') as f:
            json.dump(formatted_games, f, indent=4)
        
        print(f"Success! Saved {len(data)} games to {SPREADS_FILE}")
        return True

    except Exception as e:
        print(f"General Error in data_manager: {e}")
        return False