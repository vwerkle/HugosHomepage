from flask import Blueprint

moneyline_bp = Blueprint('moneyline', __name__, url_prefix='/moneyline')

from blueprints.moneyline import routes  # noqa: E402, F401
