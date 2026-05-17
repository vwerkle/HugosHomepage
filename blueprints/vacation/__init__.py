from flask import Blueprint

vacation_bp = Blueprint('vacation', __name__, template_folder='../../templates/vacation')
from . import routes
