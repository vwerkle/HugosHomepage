from flask import Blueprint

reservations_bp = Blueprint('reservations', __name__, template_folder='../../../templates/reservations')

from . import routes
