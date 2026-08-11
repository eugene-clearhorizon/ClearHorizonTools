import json
import os

import firebase_admin
from firebase_admin import credentials
from flask import Flask, render_template
from dotenv import load_dotenv

load_dotenv()

from src.auth import ALLOWED_DOMAIN
from src.auth.routes import auth_bp
from src.auth.utils import login_required
from src.transcript_cleaner.routes import transcript_cleaner_bp

# Firebase Admin SDK — initialised once per process (each Gunicorn worker is a separate process)
_creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
if _creds_json:
    _cred = credentials.Certificate(json.loads(_creds_json))
    firebase_admin.initialize_app(_cred)
else:
    print("WARNING: FIREBASE_CREDENTIALS_JSON not set. Authentication will not work.")

app = Flask(__name__, template_folder='src/templates', static_folder='src/static')

_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    raise RuntimeError("SECRET_KEY environment variable is not set.")
app.secret_key = _secret_key

app.register_blueprint(auth_bp)
app.register_blueprint(transcript_cleaner_bp)


@app.context_processor
def inject_firebase_config():
    return {
        'firebase_api_key': os.environ.get('FIREBASE_API_KEY', ''),
        'firebase_auth_domain': os.environ.get('FIREBASE_AUTH_DOMAIN', ''),
        'firebase_project_id': os.environ.get('FIREBASE_PROJECT_ID', ''),
        'allowed_domain': ALLOWED_DOMAIN,
    }


@app.route('/')
@login_required
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
