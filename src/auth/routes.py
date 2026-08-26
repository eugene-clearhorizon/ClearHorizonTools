from firebase_admin import auth as firebase_auth
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for, jsonify

from src.auth import ALLOWED_DOMAIN

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _clean(value, limit=300):
    """Flatten client-supplied text so it can't forge extra lines in the log."""
    if not isinstance(value, str):
        return ''
    return value.replace('\r', ' ').replace('\n', ' ')[:limit]


@auth_bp.route('/login', methods=['GET'])
def login():
    if session.get('id_token'):
        return redirect(url_for('index'))
    return render_template('login.html')


@auth_bp.route('/signup', methods=['GET'])
def signup():
    if session.get('id_token'):
        return redirect(url_for('index'))
    return render_template('signup.html')


@auth_bp.route('/session', methods=['POST'])
def create_session():
    """
    Called by client JS after Firebase sign-in.
    Verifies the ID token server-side, checks email_verified and domain,
    then stores the token in the Flask session cookie.
    """
    data = request.get_json(silent=True)
    if not data or 'idToken' not in data:
        return jsonify({'error': 'Missing idToken'}), 400

    id_token = data['idToken']

    try:
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception as e:
        return jsonify({'error': f'Token verification failed: {e}'}), 401

    if not decoded.get('email_verified'):
        return jsonify({'error': 'email_not_verified', 'redirect': url_for('auth.verify_email')}), 403

    if not decoded.get('email', '').endswith(ALLOWED_DOMAIN):
        try:
            firebase_auth.delete_user(decoded['uid'])
        except Exception:
            pass
        return jsonify({'error': f'Only {ALLOWED_DOMAIN} accounts are permitted.'}), 403

    session['id_token'] = id_token
    return jsonify({'redirect': url_for('index')}), 200


@auth_bp.route('/check-verification', methods=['POST'])
def check_verification():
    """
    Called by the 'I've verified' button on the verify-email page.
    Client must call getIdToken(true) first to force-refresh the token
    so email_verified reflects the latest state.
    """
    data = request.get_json(silent=True)
    if not data or 'idToken' not in data:
        return jsonify({'error': 'Missing idToken'}), 400

    id_token = data['idToken']

    try:
        decoded = firebase_auth.verify_id_token(id_token, check_revoked=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 401

    if not decoded.get('email_verified'):
        return jsonify({'error': 'Email not yet verified. Check your inbox.'}), 403

    session['id_token'] = id_token
    return jsonify({'redirect': url_for('index')}), 200


@auth_bp.route('/report-email-failure', methods=['POST'])
def report_email_failure():
    """
    Called by the client when sendEmailVerification() throws.

    By that point the account already exists in Firebase, so a send failure is
    invisible from the server: the user shows up under Authentication but never
    receives anything. Logging it here is what makes those two cases — "Firebase
    refused to send" versus "the mail was sent and something downstream ate it" —
    tellable apart. The email is read from the verified token rather than the
    request body so this endpoint can't be used to write arbitrary log entries.
    """
    data = request.get_json(silent=True) or {}
    id_token = data.get('idToken')
    if not id_token:
        return jsonify({'error': 'Missing idToken'}), 400

    try:
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception as e:
        current_app.logger.warning('Unverifiable token on email-failure report: %s', e)
        return jsonify({'error': 'Token verification failed'}), 401

    current_app.logger.error(
        'VERIFICATION EMAIL SEND FAILED uid=%s email=%s code=%s message=%s',
        decoded.get('uid'),
        decoded.get('email'),
        _clean(data.get('code')),
        _clean(data.get('message')),
    )
    return jsonify({'status': 'logged'}), 200


@auth_bp.route('/verify-email', methods=['GET'])
def verify_email():
    return render_template('verify_email.html')


@auth_bp.route('/action', methods=['GET'])
def action():
    """
    Single landing page for every Firebase email action.

    Firebase allows one action URL per project and distinguishes the email types
    by a ?mode= parameter, so verification, password reset and email recovery all
    arrive here and are dispatched client-side. Set the action URL in Firebase
    Console -> Authentication -> Templates to point at this route.
    """
    return render_template('action.html')


def _redirect_to_action():
    """Forward a legacy per-mode URL to /auth/action, oobCode and mode intact."""
    return redirect(url_for('auth.action', **request.args.to_dict(flat=True)))


# DO NOT DELETE THESE. They are load-bearing, not legacy compatibility.
#
# The Firebase action URL still points at /auth/reset-action and could not be
# changed: the Identity Platform API rejects an update to notification.sendEmail
# .callbackUri with EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED, and the console fails with
# a generic error for the same reason. So every verification email Firebase sends
# today arrives at /auth/reset-action?mode=verifyEmail, and this redirect is the
# only thing that gets it to a handler that will honour it.
#
# Removing either route silently breaks email verification again. If the callback
# URL is ever successfully repointed at /auth/action, these can go.
@auth_bp.route('/verify-action', methods=['GET'])
def verify_action():
    return _redirect_to_action()


@auth_bp.route('/reset-action', methods=['GET'])
def reset_action():
    return _redirect_to_action()


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
