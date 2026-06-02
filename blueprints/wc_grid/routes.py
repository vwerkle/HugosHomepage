import os
from flask import send_from_directory
from blueprints.wc_grid import wc_grid_bp

_STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'wc-grid')


@wc_grid_bp.route('/', defaults={'path': ''})
@wc_grid_bp.route('/<path:path>')
def index(path: str):
    # Serve the React SPA; all client-side routing is handled by React
    return send_from_directory(_STATIC_DIR, 'index.html')
