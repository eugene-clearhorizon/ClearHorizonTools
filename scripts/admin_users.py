"""
Admin workarounds for accounts blocked by undelivered verification email.

Run from the project root with the virtualenv Python:

    .venv\\Scripts\\python.exe scripts/admin_users.py list
    .venv\\Scripts\\python.exe scripts/admin_users.py link  someone@clearhorizon.com.au
    .venv\\Scripts\\python.exe scripts/admin_users.py verify someone@clearhorizon.com.au

Needs FIREBASE_CREDENTIALS_JSON, the same service account the app uses. It is read
from .env, so this talks to whichever Firebase project .env points at.

There is no such thing as looking up the code from an email that was already sent.
Firebase stores a hash of the outstanding oobCode and never exposes it, so the only
options are to mint a fresh link (`link`) or to skip verification (`verify`).
"""

import argparse
import datetime
import json
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from src.auth import ALLOWED_DOMAIN


def _init():
    creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if not creds_json:
        sys.exit("FIREBASE_CREDENTIALS_JSON is not set. Check .env in the project root.")
    firebase_admin.initialize_app(credentials.Certificate(json.loads(creds_json)))


def _stamp(millis):
    if not millis:
        return '(never)'
    return datetime.datetime.fromtimestamp(millis / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')


def _require_allowed(email):
    """Same domain rule the signup page enforces, so this can't be used to bless outsiders."""
    if not email.endswith(ALLOWED_DOMAIN):
        sys.exit("Refusing: %s is not a %s address." % (email, ALLOWED_DOMAIN))


def cmd_list(args):
    rows = []
    page = firebase_auth.list_users()
    while page:
        for u in page.users:
            rows.append((u.user_metadata.creation_timestamp, u.email, u.email_verified,
                         u.user_metadata.last_sign_in_timestamp, u.uid))
        page = page.get_next_page()

    rows.sort(key=lambda r: r[0] or 0)
    print("%-17s %-36s %-9s %-17s %s" % ("CREATED (UTC)", "EMAIL", "VERIFIED", "LAST SIGN-IN", "UID"))
    for created, email, verified, last_seen, uid in rows:
        print("%-17s %-36s %-9s %-17s %s" % (
            _stamp(created), email, "yes" if verified else "NO", _stamp(last_seen), uid))

    unverified = sum(1 for r in rows if not r[2])
    print("\n%d account(s), %d unverified." % (len(rows), unverified))


def cmd_link(args):
    """
    Mint a fresh verification link without sending anything.

    Hand it over by whatever channel actually works — Teams, Slack, in person. The
    person still clicks it themselves, so the flow runs exactly as designed; only
    the delivery hop is replaced. Single use, and it expires.
    """
    _require_allowed(args.email)
    user = firebase_auth.get_user_by_email(args.email)
    if user.email_verified:
        print("%s is already verified. Nothing to do." % args.email)
        return
    print(firebase_auth.generate_email_verification_link(args.email))
    print("\nSingle use, and it expires. Send it over a channel you trust.")


def cmd_verify(args):
    """
    Mark the address verified directly, skipping the email entirely.

    This asserts the person controls the mailbox without them having proved it, so
    only use it for someone whose identity you already established another way.
    """
    _require_allowed(args.email)
    user = firebase_auth.get_user_by_email(args.email)
    if user.email_verified:
        print("%s is already verified. Nothing to do." % args.email)
        return

    print("About to mark %s (uid %s) verified without an email round-trip." % (args.email, user.uid))
    if input("Type the email again to confirm: ").strip().lower() != args.email.lower():
        sys.exit("Mismatch — nothing changed.")

    firebase_auth.update_user(user.uid, email_verified=True)
    print("Done. %s can sign in now." % args.email)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('list', help='show every account and whether it is verified')

    p_link = sub.add_parser('link', help='mint a verification link without sending email')
    p_link.add_argument('email')

    p_verify = sub.add_parser('verify', help='mark an address verified, skipping the email')
    p_verify.add_argument('email')

    args = parser.parse_args()
    _init()
    {'list': cmd_list, 'link': cmd_link, 'verify': cmd_verify}[args.command](args)


if __name__ == '__main__':
    main()
