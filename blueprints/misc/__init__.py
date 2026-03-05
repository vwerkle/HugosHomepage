from flask import Blueprint

misc_bp = Blueprint('misc', __name__, template_folder='../../../templates/misc')

from . import routes