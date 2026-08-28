"""
Anonymous usage statistics.

Writes one Firestore document per successful tool run, recording how much work
the tool did — never who did it. The only user-linked field is a one-way HMAC of
the Firebase UID, so "how many distinct people used this in June" is answerable
while "what did this particular person do" is not: the hash cannot be reversed,
and nothing else in the document points back at an account.

Nothing derived from filenames or transcript content is stored. The app tells
users their uploads are not retained, and filenames of interview transcripts are
themselves meaningful data.

Every failure in this module is swallowed and logged. A stats write must never be
the reason a user loses the download they were waiting for.
"""

import hashlib
import hmac
import os

from firebase_admin import firestore
from flask import current_app

COLLECTION = 'usage_events'


def _salt():
    """
    Key for the anonymising HMAC.

    Falls back to SECRET_KEY so there is nothing extra to configure. Rotating the
    salt re-anonymises everyone: volume and duration totals are unaffected, but
    distinct-user counts won't join across the rotation, so a user active on both
    sides of it is counted twice. Set STATS_SALT to a dedicated value if you
    expect to rotate SECRET_KEY and care about that continuity.
    """
    salt = os.environ.get('STATS_SALT') or os.environ.get('SECRET_KEY')
    return salt.encode() if salt else None


def anonymous_user_id(uid):
    """
    Stable-per-user, irreversible identifier. Returns None if it can't be salted,
    in which case the run is still recorded — just without the user dimension.

    128 bits of the digest is far past collision range for a userbase this size.
    """
    salt = _salt()
    if not salt or not uid:
        return None
    return hmac.new(salt, uid.encode(), hashlib.sha256).hexdigest()[:32]


def _client():
    """Firestore client, or None if it isn't available. firebase_admin caches it."""
    try:
        return firestore.client()
    except Exception as e:
        current_app.logger.warning('Usage stats disabled — no Firestore client: %s', e)
        return None


def record_run(event_id, tool, uid, file_count, duration_seconds, outcome='success'):
    """
    Record one completed run.

    `event_id` is the caller's per-request UUID, used as the document ID so a
    retried write can't double-count.

    Call this synchronously, before returning the response. Cloud Run throttles
    CPU once a response is sent, so a background thread may never get to run.
    """
    db = _client()
    if db is None:
        return

    try:
        db.collection(COLLECTION).document(event_id).set({
            'tool': tool,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'user_hash': anonymous_user_id(uid),
            'file_count': file_count,
            'duration_seconds': round(duration_seconds),
            'outcome': outcome,
        })
    except Exception as e:
        current_app.logger.warning('Usage stats write failed for %s: %s', event_id, e)
