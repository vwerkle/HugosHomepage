from flask import Flask, render_template
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

# Global constants (if needed across app)
DATA_DIR = 'data/madness'

def init_db():
    # Ensure data directories exist
    for path in ['data/madness', 'data/misc', 'data/random', 'data/reservations', 'data/worldcup']:
        if not os.path.exists(path):
            os.makedirs(path)

    # Initialize JSON files
    for file in [os.path.join(DATA_DIR, 'users.json'), os.path.join(DATA_DIR, 'picks.json')]:
        if not os.path.exists(file):
            with open(file, 'w') as f:
                json.dump({}, f)

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
    return render_template('index.html')

@app.route('/pools')
def pools():
    return render_template('pools.html')

if __name__ == '__main__':
    init_db()
    res_scheduler.start_scheduler()
    preload_venues()  # kicks off background Resy + OT venue loading
    from waitress import serve
    print("Waitress is starting on port 5000...")
    serve(app, host='0.0.0.0', port=5000, threads=4)