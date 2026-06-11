from flask import Blueprint

statline_bp = Blueprint('statline', __name__, url_prefix='/statline')

from blueprints.statline import routes  # noqa: E402, F401
