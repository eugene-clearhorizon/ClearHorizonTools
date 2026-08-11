from firebase_admin import auth as firebase_auth
from flask import Blueprint, redirect, render_template, request, session, url_for, jsonify

from src.auth import ALLOWED_DOMAIN

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


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


@auth_bp.route('/verify-email', methods=['GET'])
def verify_email():
    return render_template('verify_email.html')


@auth_bp.route('/verify-action', methods=['GET'])
def verify_action():
    return render_template('verify_action.html')


@auth_bp.route('/reset-action', methods=['GET'])
def reset_action():
    return render_template('reset_action.html')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
