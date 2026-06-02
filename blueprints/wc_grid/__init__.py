from flask import Blueprint

wc_grid_bp = Blueprint('wc_grid', __name__, url_prefix='/wc-grid')

from blueprints.wc_grid import routes  # noqa: E402, F401
