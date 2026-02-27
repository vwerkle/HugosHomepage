from flask import Flask, render_template, request,session, redirect,url_for
import sys
import json
import os
import pytz
from moonshot import moonshot_bp,moonshot_mike_bp
from data_manager import fetch_and_save_spreads
from update_results import update_all_results_logic
from datetime import datetime,timedelta,timezone
app = Flask(__name__)
app.secret_key = 'vincent'
app.register_blueprint(moonshot_bp)
app.register_blueprint(moonshot_mike_bp)
locations = {"Fairmount","Fishtown","Rittenhouse","Center City","West Philly","NoLibs","South Philly","Fitler Square"}

REGISTRATION_OPEN = True
USERS_FILE = 'users.json'
PICKS_FILE = 'picks.json'

def init_db():
    for file in [USERS_FILE, PICKS_FILE]:
        if not os.path.exists(file):
            with open(file, 'w') as f:
                json.dump({}, f)

@app.route("/")
def home():
    print("test")
    return render_template('home.html')


@app.route("/recipes")
def recipes():
    recipesList = make_json_recipes()
    print(type(recipesList))
    #print (recipesList.join())
    return render_template('recipes.html',recipes=recipesList)

@app.route("/restaurants")
def restaurants():
    restList = make_json_restaurants()
    sorted_rest = sorted(restList.values(),key=lambda x: x['rating'],reverse=True)
    tags = sorted(set(tag for rest in sorted_rest for tag in rest['tags']) - set(locations))
    return render_template('restaurants.html',restaurants=sorted_rest,tags=tags,locationfilters=locations)

@app.route('/recipe/<int:recipe_id>')
def recipe(recipe_id):
    recipe=next((r for r in recipesList if r['id']==recipe_id),None)
    if recipe:
        return render_template('recipe.html',recipe=recipe)
    else:
        return "Recipe not found", 404
    

def make_json_recipes():
    with open('Recipes.txt','r') as file:
        lines=file.readlines()
        #print(lines)
    recipesList = {}
    current_cat=""
    current_subcat=""
    current_rec={}

    for line in lines:
        line=line.strip()
        if line=="":
            continue
        elif line[0]=='-':
            current_cat=line[1:]
            recipesList[current_cat]={}
            #print(current_cat)
        elif line[0]=='+':
            current_subcat=line[1:]
            recipesList[current_cat][current_subcat]=[]
        elif not current_rec:
            current_rec['title']=line
        elif 'notes'not in current_rec:
            current_rec['notes']=line
        elif 'image' not in current_rec:
            current_rec['image']=line
        elif 'date'not in current_rec:
            current_rec['date']=line
            recipesList[current_cat][current_subcat].append(current_rec)
            current_rec={}
    
    recipes_json=json.dumps(recipesList, indent=4)

    with open('recipes.json','w') as jsonfile:
        jsonfile.write(recipes_json)

    return recipesList

def make_json_restaurants():
    with open('Restaurants.txt', 'r') as file:
        lines=file.readlines()
    restaurants = {}
    current_rest={}
    for line in lines:
        line= line.strip()
        if line=="":
            continue
        elif not current_rest:
            current_rest['name']=line
        elif 'rating'not in current_rest:
            current_rest['rating']=float(line)
        elif 'price'not in current_rest:
            current_rest['price']=int(line)
        elif 'html'not in current_rest:
            current_rest['html']=line
        elif 'tags'not in current_rest:
            current_rest['tags']=line.split(',')
            #print(current_rest['tags'])
            restaurants[current_rest['name']]=current_rest
            current_rest={}
    restaurants_json=json.dumps(restaurants, indent=4)

    with open('restaurants.json','w') as jsonfile:
        jsonfile.write(restaurants_json)

    return restaurants

@app.route('/admin/update-games', methods=['GET', 'POST'])
def update_games():
    # Only allow logged-in admins (optional: add your own admin check here)
    if request.method == 'POST':
        # 1. Update Spreads for the future
        spreads_success = fetch_and_save_spreads()
        
        # 2. Update Results for the past
        # Check if user provided a specific date to look back, else default to '3' days
        lookback = request.form.get('days_back', '3')
        results_count = update_all_results_logic(days_back=lookback)
        
        message = f"Spreads Updated: {spreads_success} | Picks Graded: {results_count}"
        return render_template('admin.html', message=message)

    return render_template('admin.html')

@app.route('/dness')
def dness_hub():
    return render_template('dness_hub.html')
@app.route('/signup')
def signup():
    if not REGISTRATION_OPEN:
        return "Registration is closed!"
    
    if request.method == 'POST':
        name = request.form['name']
        pw = request.form['password']
        champ = request.form['champion']
        
        with open(USERS_FILE, 'r+') as f:
            users = json.load(f)
            if name in users: return "User already exists!"
            users[name] = {"password": pw, "champion": champ}
            f.seek(0)
            json.dump(users, f)
            f.truncate()
        
        # --- ADD THIS LINE ---
        session['user'] = name 
        # ---------------------
        
        return "Signed up! You are now logged in. Go make your picks!"
    return render_template('signup.html')

@app.route('/make-picks', methods=['GET', 'POST'])
def make_picks():
    username = session.get('user')
    if not username:
        return redirect(url_for('login'))

    eastern = pytz.timezone('US/Eastern')
    now_est = datetime.now(eastern)
    
    today_raw = now_est.strftime('%Y-%m-%d')
    tomorrow_dt = now_est + timedelta(days=1)
    tomorrow_raw = tomorrow_dt.strftime('%Y-%m-%d')
    
    # These will now correctly match Feb 26 if it's currently evening EST
    today_pretty = now_est.strftime('%b %d')
    tomorrow_pretty = tomorrow_dt.strftime('%b %d')

    selected_date = request.args.get('date', today_raw)

    # 3. Load games for that date
    games_for_date = []
    if os.path.exists('daily_spreads.json'):
        with open('daily_spreads.json', 'r') as f:
            all_spreads = json.load(f)
            games_for_date = all_spreads.get(selected_date, [])
            games_for_date = sorted(games_for_date, key=lambda x: x['lock_time'])

    saved_selections = []
    if os.path.exists(PICKS_FILE):
        with open(PICKS_FILE, 'r') as f:
            all_user_picks = json.load(f)
            # Get this user's dictionary -> then get the list for this date
            user_data = all_user_picks.get(username, {})
            existing_picks_list = user_data.get(selected_date, [])
            
            # Convert the list of dicts into a simple list of strings for the HTML to match
            saved_selections = [p['game_info'] for p in existing_picks_list]

    # Ensure we always pass a list of 5 strings so the loop doesn't break
    while len(saved_selections) < 5:
        saved_selections.append("")
    # For string comparison in HTML, ISO format is still best:
    current_time_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    if request.method == 'POST':
        # 1. Get the target date from the hidden input field
        target_date = request.form.get('date') 
        
        # 2. Get the list of picks (removes empty dropdowns)
        user_selections = list(filter(None, request.form.getlist('game_picks')))
        if len(user_selections) != len(set(user_selections)):
        # Refetch the data needed to reload the page with an error
            games_for_date = []
            if os.path.exists('daily_spreads.json'):
                with open('daily_spreads.json', 'r') as f:
                    games_for_date = json.load(f).get(target_date, [])
            
            return render_template('picks.html', 
                                games=games_for_date,
                                selected_date=target_date,
                                error="You cannot select the same game twice!",
                                today_raw=today_raw,
                                tomorrow_raw=tomorrow_raw,
                                today_pretty=today_pretty,
                                tomorrow_pretty=tomorrow_pretty,
                                current_time=current_time_str,
                                saved_selections=saved_selections
                                )
        # 3. Format them for storage
        new_picks_data = [{"game_info": p, "result": "pending"} for p in user_selections]

        # 4. Open and update the picks file
        with open(PICKS_FILE, 'r+') as f:
            all_picks = json.load(f)
            
            # Ensure the user has a dictionary entry
            if username not in all_picks:
                all_picks[username] = {}
            
            # Save the new picks specifically for the targeted date
            # This prevents "Tomorrow" picks from overwriting "Today" picks
            all_picks[username][target_date] = new_picks_data
            
            # Move pointer to start and overwrite the file
            f.seek(0)
            json.dump(all_picks, f, indent=4)
            f.truncate()
        return redirect(url_for('results'))

    return render_template('picks.html', 
                           games=games_for_date, 
                           selected_date=selected_date,
                           today_raw=today_raw,
                           tomorrow_raw=tomorrow_raw,
                           today_pretty=today_pretty,
                           tomorrow_pretty=tomorrow_pretty,
                           current_time=current_time_str,
                           saved_selections=saved_selections)
                        

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        pw = request.form['password']
        
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
            
        if name in users and users[name]['password'] == pw:
            session['user'] = name
            return redirect(url_for('make_picks'))
        else:
            return "Invalid name or password."
            
    return '''
        <form method="post">
            Name: <input type="text" name="name"><br>
            Password: <input type="password" name="password"><br>
            <input type="submit" value="Login">
        </form>
    '''

@app.route('/results')
def results():
    eastern = pytz.timezone('US/Eastern')
    now_est = datetime.now(eastern)
    today_raw = now_est.strftime('%Y-%m-%d')
    # 1. Load Picks and Spreads
    all_picks = json.load(open(PICKS_FILE)) if os.path.exists(PICKS_FILE) else {}
    all_spreads = json.load(open('daily_spreads.json')) if os.path.exists('daily_spreads.json') else {}
    
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
                    
                    # Use the lock time from spreads if available
                    game_lock_time = games_lookup.get(pick_str)
                    
                    # Determine visibility
                    is_own_pick = (user == logged_in_user)
                    
                    # A game is "started" if:
                    # - It has a final result already
                    # - OR its lock_time has passed
                    # - OR it's a pick from a previous day (not in current spreads)
                    if result_status != 'pending':
                        is_started = True
                    elif game_lock_time:
                        is_started = current_time >= game_lock_time
                    else:
                        is_started = d < today_raw 

                    if is_own_pick or is_started:
                        display_text = pick_str
                    else:
                        display_text = "🔒 HIDDEN"
                    
                    slot_data[user] = {
                        'info': display_text,
                        'result': pick_obj.get('result', 'pending'),
                        'is_hidden': not (is_own_pick or is_started)
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
    return render_template('results.html', 
                           usernames=usernames, 
                           table_data=table_data, 
                           current_time=current_time,
                           user_totals=user_totals,
                           leaders=leaders,
                           sorted_leaderboard=sorted_leaderboard)

if __name__ == '__main__':
    print("hello")
    #print("hello",file=sys.stdout)
    #app.run(debug=True)