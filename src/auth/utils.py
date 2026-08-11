from functools import wraps
from flask import session, redirect, url_for
from firebase_admin import auth as firebase_auth


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        id_token = session.get('id_token')
        if not id_token:
            return redirect(url_for('auth.login'))
        try:
            decoded = firebase_auth.verify_id_token(id_token)
        except Exception:
            # Expired, revoked or malformed — all resolve to "sign in again"
            session.clear()
            return redirect(url_for('auth.login'))
        if not decoded.get('email_verified'):
            return redirect(url_for('auth.verify_email'))
        return f(*args, **kwargs)
    return decorated_function
