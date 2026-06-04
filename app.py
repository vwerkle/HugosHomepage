from flask import Flask, render_template, redirect, url_for
import os
import json
from blueprints.misc.routes import misc_bp
from blueprints.pools.madness.routes import madness_bp
from blueprints.pools.random_team import random_pool_bp
from blueprints.pools.moonshot import moonshot_bp, moonshot_mike_bp # Existing files
from blueprints.pools.worldcup.routes import worldcup_bp
from blueprints.reservations import reservations_bp
from blueprints.reservations import scheduler as res_scheduler
from blueprints.reservations.routes import preload_venues
from blueprints.birthdays import birthdays_bp
from blueprints.birthdays import scheduler as bday_scheduler
from blueprints.vacation.routes import vacation_bp
from blueprints.moneyline import moneyline_bp
from blueprints.moneyline import scheduler as moneyline_scheduler
from blueprints.wc_grid import wc_grid_bp
from blueprints.pools.finals.routes import finals_bp

app = Flask(__name__)
app.secret_key = 'vincent'

# Register Blueprints
app.register_blueprint(misc_bp)
app.register_blueprint(madness_bp)
app.register_blueprint(random_pool_bp)
app.register_blueprint(moonshot_bp)
app.register_blueprint(moonshot_mike_bp)
app.register_blueprint(worldcup_bp)
app.register_blueprint(reservations_bp)
app.register_blueprint(birthdays_bp)
app.register_blueprint(vacation_bp, url_prefix='/vacation')
app.register_blueprint(moneyline_bp)
app.register_blueprint(wc_grid_bp)
app.register_blueprint(finals_bp)

# Global constants (if needed across app)
DATA_DIR = 'data/madness'

def init_db():
    # Ensure data directories exist
    for path in ['data/madness', 'data/misc', 'data/random', 'data/reservations', 'data/worldcup', 'data/birthdays', 'data/vacation', 'data/moneyline', 'data/finals', 'static/vacation']:
        if not os.path.exists(path):
            os.makedirs(path)

    # Initialize JSON files
    for file in [os.path.join(DATA_DIR, 'users.json'), os.path.join(DATA_DIR, 'picks.json')]:
        if not os.path.exists(file):
            with open(file, 'w') as f:
                json.dump({}, f)

    # Initialize birthdays data and config files
    vacation_file = 'data/vacation/trips.json'
    if not os.path.exists(vacation_file):
        with open(vacation_file, 'w') as f:
            json.dump([], f)

    bday_file = 'data/birthdays/birthdays.json'
    if not os.path.exists(bday_file):
        with open(bday_file, 'w') as f:
            json.dump([], f)
    bday_cfg = 'data/birthdays/config.json'
    if not os.path.exists(bday_cfg):
        with open(bday_cfg, 'w') as f:
            json.dump({
                'gmail_address': '',
                'gmail_app_password': '',
                'to_sms_email': '',
            }, f, indent=4)

    # Initialize Finals pool data files
    for finals_file, default in [
        ('data/finals/picks.json', {}),
        ('data/finals/config.json', {
            'nhl_season': '20252026', 'nba_season': '2025-26',
            'player_ids': {'nhl': {}, 'nba': {}},
            'scoring': {'nhl_winner': 10, 'nhl_games_exact': 5, 'nhl_games_off_one': 2}
        })
    ]:
        if not os.path.exists(finals_file):
            with open(finals_file, 'w') as f:
                json.dump(default, f, indent=2)

    # Initialize World Cup data files
    for wc_file in ['data/worldcup/users.json', 'data/worldcup/picks.json', 'data/worldcup/games.json']:
        if not os.path.exists(wc_file):
            with open(wc_file, 'w') as f:
                json.dump({}, f)

    # Initialize reservation data files
    res_defaults = {
        'data/reservations/active_jobs.json': {},
        'data/reservations/history.json': [],
    }
    for path, default in res_defaults.items():
        if not os.path.exists(path):
            with open(path, 'w') as f:
                json.dump(default, f)

    # Config template (never overwrite if exists)
    cfg_path = 'data/reservations/config.json'
    if not os.path.exists(cfg_path):
        with open(cfg_path, 'w') as f:
            json.dump({
                "resy": {"api_key": "", "auth_token": "", "payment_method_id": ""},
                "opentable": {"email": "", "password": ""}
            }, f, indent=4)

@app.route('/')
def index():
    return redirect(url_for('misc.landing'))


@app.route('/pools')
def pools():
    return render_template('pools.html')

if __name__ == '__main__':
    init_db()
    res_scheduler.start_scheduler()
    bday_scheduler.start_scheduler()
    moneyline_scheduler.start_scheduler()
    preload_venues()  # kicks off background Resy + OT venue loading
    from waitress import serve
    print("Waitress is starting on port 5000...")
    serve(app, host='0.0.0.0', port=5000, threads=4)