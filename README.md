# Clear Horizon Tools

A small internal web app hosting utilities for Clear Horizon staff. Sign in with your
`@clearhorizon.com.au` email and pick a tool from the home page.

**Live:** https://clearhorizontools-355908014212.australia-southeast2.run.app/

Accounts are self-service — create one on the sign-up page and click the link in the
verification email. Only `@clearhorizon.com.au` addresses are accepted; anything else is
rejected at sign-up and the account is removed.

## What's in here

**Teams Transcript Cleaner** — upload one or more `.vtt` transcript files generated from
Microsoft Teams and get back a tidy Word document formatted in line with how we would
expect an interview transcript to look. It merges consecutive lines from the same speaker
into single paragraphs, adds a header with the interview length and speaker list, and
strips out isolated filler like "Mm-hmm." and "Yeah." that Teams captures as separate
cues. Upload one file and you get a `.docx` back; upload several and you get a zip.

Nothing is retained — uploads and outputs are deleted as soon as the download is sent.

There is scope for more tools to land here over time.

## Running it locally

You'll need Python 3.11+ and a `.env` file (see the next section).

First time only:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

After that, activate the venv and start the dev server:

```powershell
.\.venv\Scripts\Activate.ps1
python -u -m flask --app main run -p 8080 --debug
```

Then open http://localhost:8080. The app will refuse to start without `SECRET_KEY` set,
and will start but print a warning if the Firebase credentials are missing — sign-in
won't work in that state.

## Configuration

Copy `.env.example` to `.env` and fill in all five values. **Never commit `.env`** — it's
gitignored, and the Firebase credentials in it are as good as a password.

| Variable | Where to find it |
|---|---|
| `SECRET_KEY` | Generate one: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FIREBASE_CREDENTIALS_JSON` | Firebase Console → Project Settings → Service Accounts → Generate new private key. Paste the whole JSON file as a single line. |
| `FIREBASE_API_KEY` | Firebase Console → Project Settings → General → Web API Key |
| `FIREBASE_AUTH_DOMAIN` | Firebase Console → Project Settings → General (looks like `your-project.firebaseapp.com`) |
| `FIREBASE_PROJECT_ID` | Firebase Console → Project Settings → General |

Setting Firebase up from scratch — enabling email sign-in, authorising the domain,
generating the service account key — is a separate one-time job. See
[FIREBASE_SETUP.md](FIREBASE_SETUP.md).

## Hosting and ownership

Worth knowing before you rely on this: both the Google Cloud project and the Firebase
project sit under **Eugene Liston's personal Google Cloud account**, and deployment runs
on those credentials. It is not currently a Clear Horizon–owned asset.

Everything is running within the free tier, so there's no cost attached at present. The
practical risk is access rather than money — nobody else can deploy, change environment
variables, read the logs, or manage user accounts.

Moving it to a Clear Horizon–owned account is doable but is a migration, not a settings
change. It would mean a new Google Cloud project and a new Firebase project under a Clear
Horizon billing account, a fresh service account key and set of environment variables, and
a redeploy. Two consequences are easy to overlook:

- The live URL changes, and the new domain has to be added to Firebase's authorised
  domains before sign-in will work.
- User accounts live inside the Firebase project, so everyone would need to sign up again
  on the new one unless the existing users are explicitly exported and imported.

## Deploying

The app runs on Google Cloud Run in `australia-southeast2`. From the project root:

```powershell
.\deploy.ps1
```

The script picks up whichever project `gcloud` is currently pointed at; pass
`-ProjectId <PROJECT_ID>` to override it. It builds from the `Dockerfile`, deploys, and
prints the service URL when it's done.

If you'd rather do it by hand:

```powershell
gcloud run deploy clearhorizontools --source . --region australia-southeast2 --allow-unauthenticated
```

Cloud Run keeps its own copy of the environment variables — `.env` is not uploaded. To
change them:

```powershell
gcloud run services update clearhorizontools `
  --region australia-southeast2 `
  --set-env-vars "SECRET_KEY=...,FIREBASE_API_KEY=...,FIREBASE_AUTH_DOMAIN=...,FIREBASE_PROJECT_ID=..."
```

Set `FIREBASE_CREDENTIALS_JSON` through the Cloud Run console instead (Edit & Deploy New
Revision → Variables & Secrets) — the JSON contains characters that are awkward to escape
on the command line.

## How it fits together

Flask app, one blueprint per tool, templates sharing a common base.

```
main.py                      app setup, Firebase init, home page
src/auth/                    sign-in, sign-up, email verification, password reset
src/transcript_cleaner/      the .vtt → .docx tool
src/templates/               base.html + one template per page
src/templates/partials/      shared snippets (Firebase JS config, sign-out button)
src/static/css/style.css     all styling
```

Sign-in works like this: an unauthenticated request lands on `/auth/login`, the Firebase
JavaScript SDK does the actual sign-in in the browser, and the resulting ID token is
POSTed to `/auth/session`. The server verifies the token, checks the email is verified and
on the right domain, and stores it in the Flask session cookie. Every protected route is
wrapped in `@login_required`, which re-verifies that token on each request.

Note that Firebase ID tokens expire after an hour, so a long session will eventually
bounce you back to the sign-in page.

### Adding a tool

1. Create `src/<tool_name>/` with `__init__.py` and `routes.py`, defining a blueprint.
2. Register it in `main.py`.
3. Put `@login_required` on any route that shouldn't be public.
4. Add a template in `src/templates/` that extends `base.html`.
5. Add a card linking to it in `src/templates/index.html`.
