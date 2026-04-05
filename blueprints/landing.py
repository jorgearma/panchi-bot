import os
from flask import Blueprint, send_from_directory

LANDING_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'templates', 'landing-page')
)

blueprint_landing = Blueprint('landing', __name__)


@blueprint_landing.route('/')
def index():
    return send_from_directory(LANDING_DIR, 'index.html')


@blueprint_landing.route('/landing/<path:filename>')
def static_files(filename):
    return send_from_directory(LANDING_DIR, filename)
