"""
Read-side helpers for usage stats, shared by scripts/usage_report.py and the
monthly email.

Months are Melbourne calendar months, not UTC ones. Timestamps are stored in UTC,
so bucketing by UTC would put a run at 9am on the 1st into the previous month.
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore

from . import COLLECTION

REPORT_TZ = ZoneInfo('Australia/Melbourne')


def firestore_client():
    """Firestore client from FIREBASE_CREDENTIALS_JSON, for scripts running outside the app."""
    creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if not creds_json:
        raise RuntimeError('FIREBASE_CREDENTIALS_JSON is not set.')
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(creds_json)))
    return firestore.client()


def successful_events(db, tool=None):
    """Every successful run, optionally for one tool, as plain dicts."""
    events = (doc.to_dict() for doc in db.collection(COLLECTION).stream())
    return [e for e in events
            if e.get('outcome') == 'success' and (tool is None or e.get('tool') == tool)]


def month_key(ts):
    """'YYYY-MM' of a stored UTC timestamp, in Melbourne time."""
    return ts.astimezone(REPORT_TZ).strftime('%Y-%m')


def empty_month():
    return {'runs': 0, 'files': 0, 'seconds': 0, 'users': set()}


def by_month(events):
    """
    Returns ({'YYYY-MM': totals}, undated_count). Months with no runs are absent;
    use month_range() to fill them in.

    A server timestamp is null for the instant between the write landing and the
    server stamping it. Those events are counted as undated rather than guessed at.
    """
    months = {}
    undated = 0
    for e in events:
        ts = e.get('timestamp')
        if ts is None:
            undated += 1
            continue
        m = months.setdefault(month_key(ts), empty_month())
        m['runs'] += 1
        m['files'] += e.get('file_count', 0)
        m['seconds'] += e.get('duration_seconds', 0)
        if e.get('user_hash'):
            m['users'].add(e['user_hash'])
    return months, undated


def previous_month(today=None):
    """'YYYY-MM' of the month before `today` (default: today in Melbourne)."""
    today = today or datetime.now(REPORT_TZ).date()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f'{year:04d}-{month:02d}'


def month_range(first, last):
    """Inclusive list of 'YYYY-MM' keys from first to last."""
    year, month = map(int, first.split('-'))
    end = tuple(map(int, last.split('-')))
    keys = []
    while (year, month) <= end:
        keys.append(f'{year:04d}-{month:02d}')
        year, month = (year, month + 1) if month < 12 else (year + 1, 1)
    return keys
