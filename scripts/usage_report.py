r"""
Print usage stats from Firestore.

Run it locally, from the repo root, with the same .env the app uses:

    .\.venv\Scripts\python.exe scripts\usage_report.py

Reads every event in one pass and aggregates in Python. That's deliberate: the
volumes here are small, and it means no composite indexes and no separate query
per month. If this ever gets slow, that's a good problem and the fix is a
per-month aggregation query.
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import firebase_admin
from firebase_admin import credentials, firestore

from src.stats import COLLECTION


def _hours(seconds):
    return seconds / 3600.0


def main():
    creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if not creds_json:
        sys.exit('FIREBASE_CREDENTIALS_JSON is not set. Copy .env.example to .env and fill it in.')

    firebase_admin.initialize_app(credentials.Certificate(json.loads(creds_json)))
    db = firestore.client()

    events = [doc.to_dict() for doc in db.collection(COLLECTION).stream()]
    events = [e for e in events if e.get('outcome') == 'success']

    if not events:
        print('No usage events recorded yet.')
        return

    by_month = defaultdict(lambda: {'runs': 0, 'files': 0, 'seconds': 0, 'users': set()})
    by_tool = defaultdict(lambda: {'runs': 0, 'files': 0, 'seconds': 0})
    all_users = set()
    undated = 0

    for e in events:
        ts = e.get('timestamp')
        files = e.get('file_count', 0)
        seconds = e.get('duration_seconds', 0)
        user = e.get('user_hash')

        tool = by_tool[e.get('tool', 'unknown')]
        tool['runs'] += 1
        tool['files'] += files
        tool['seconds'] += seconds

        if user:
            all_users.add(user)

        if ts is None:
            # A server timestamp is null for the instant between the write landing
            # and the server stamping it. Count it in the totals, not the months.
            undated += 1
            continue

        month = by_month[ts.strftime('%Y-%m')]
        month['runs'] += 1
        month['files'] += files
        month['seconds'] += seconds
        if user:
            month['users'].add(user)

    total_files = sum(t['files'] for t in by_tool.values())
    total_seconds = sum(t['seconds'] for t in by_tool.values())

    print()
    print('Usage report')
    print('=' * 52)
    print()
    print('TOTALS (successful runs)')
    print(f'  Runs:              {len(events):>8,}')
    print(f'  Transcripts:       {total_files:>8,}')
    print(f'  Hours cleaned:     {_hours(total_seconds):>8,.1f}')
    print(f'  Distinct users:    {len(all_users):>8,}')
    print()

    print('BY MONTH')
    print(f'  {"Month":<9} {"Runs":>6} {"Transcripts":>12} {"Hours":>8} {"Users":>6}')
    for month in sorted(by_month):
        m = by_month[month]
        print(f'  {month:<9} {m["runs"]:>6,} {m["files"]:>12,} '
              f'{_hours(m["seconds"]):>8,.1f} {len(m["users"]):>6,}')
    print()

    print('BY TOOL')
    print(f'  {"Tool":<24} {"Runs":>6} {"Transcripts":>12} {"Hours":>8}')
    for name in sorted(by_tool):
        t = by_tool[name]
        print(f'  {name:<24} {t["runs"]:>6,} {t["files"]:>12,} {_hours(t["seconds"]):>8,.1f}')
    print()

    print('Note: "Users" counts distinct anonymous hashes, so it answers "how many')
    print('people" but never "which people". Monthly figures are not additive —')
    print('someone active in two months is counted in both.')
    if undated:
        print(f'Note: {undated} event(s) had no server timestamp yet and are in the')
        print('totals but not the monthly breakdown.')
    print()


if __name__ == '__main__':
    main()
