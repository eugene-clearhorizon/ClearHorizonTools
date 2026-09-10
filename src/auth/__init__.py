# The only email domain permitted to register or sign in.
# Injected into templates by the context processor in main.py.
ALLOWED_DOMAIN = '@clearhorizon.com.au'

# Who to chase when the verification email doesn't arrive. Delivery of Firebase's
# default sender into the Clear Horizon tenant is unreliable, so this is a routine
# request rather than an edge case — see the troubleshooting notes in
# FIREBASE_SETUP.md for how to unblock someone.
SUPPORT_CONTACT_NAME = 'Eugene'
SUPPORT_CONTACT_EMAIL = 'eugene@clearhorizon.com.au'
