from flask import Flask, render_template
import os
import json
from blueprints.misc.routes import misc_bp
from blueprints.pools.madness.routes import madness_bp
from blueprints.pools.random_team import random_pool_bp
from blueprints.pools.moonshot import moonshot_bp, moonshot_mike_bp # Existing files

app = Flask(__name__)
app.secret_key = 'vincent'

# Register Blueprints
app.register_blueprint(misc_bp)
app.register_blueprint(madness_bp)
app.register_blueprint(random_pool_bp)
app.register_blueprint(moonshot_bp)
app.register_blueprint(moonshot_mike_bp)

# Global constants (if needed across app)
DATA_DIR = 'data/madness'

def init_db():
    # Ensure data directories exist
    for path in ['data/madness', 'data/misc', 'data/random']:
        if not os.path.exists(path):
            os.makedirs(path)
    
    # Initialize JSON files
    for file in [os.path.join(DATA_DIR, 'users.json'), os.path.join(DATA_DIR, 'picks.json')]:
        if not os.path.exists(file):
            with open(file, 'w') as f:
                json.dump({}, f)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pools')
def pools():
    return render_template('pools.html')

if __name__ == '__main__':
    init_db()
    from waitress import serve
    print("Waitress is starting on port 5000...")
    serve(app, host='0.0.0.0', port=5000, threads=4)