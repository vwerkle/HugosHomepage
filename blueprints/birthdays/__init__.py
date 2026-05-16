from flask import Blueprint

birthdays_bp = Blueprint('birthdays', __name__, url_prefix='/birthdays')

from blueprints.birthdays import routes  # noqa: E402, F401
