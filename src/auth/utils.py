from functools import wraps
from flask import g, session, redirect, url_for
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
        # The claims are already decoded and verified here, so stash them for the
        # view rather than making it verify the token a second time.
        g.user = decoded
        return f(*args, **kwargs)
    return decorated_function
