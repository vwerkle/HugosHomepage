from flask import Blueprint

# We define it here so routes.py can import it
madness_bp = Blueprint('madness', __name__, template_folder='../../../templates/madness')

from . import routes