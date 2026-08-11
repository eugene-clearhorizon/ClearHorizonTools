# Firebase setup

One-time Firebase Console configuration for authentication. You only need this when
standing the project up fresh, or when something in the Firebase project has been
changed or lost.

For everyday running and deploying, see [README.md](README.md).

## Before you start

Check that the Firebase project and the Cloud Run project are the same Google Cloud
project:

1. Run `gcloud config get-value project` and note the project ID.
2. Open [Firebase Console](https://console.firebase.google.com) → your project →
   Project Settings → General.
3. Compare the **Project ID**. They should match. You can proceed if they don't, but
   make sure you're working in the Firebase project you actually mean to.

## 1. Register a web app

Firebase Console → Project Settings → General → **Your apps**.

If there's no web app (`</>`) listed, click **Add app → Web**, name it (e.g. "ClearHorizon
Tools") and click **Register app**. You can skip the SDK setup steps it offers — you only
need the three config values it shows you:

- `apiKey` → `FIREBASE_API_KEY`
- `authDomain` → `FIREBASE_AUTH_DOMAIN`
- `projectId` → `FIREBASE_PROJECT_ID`

Keep these somewhere handy; they go into `.env` and into Cloud Run.

## 2. Enable email/password sign-in

Firebase Console → Build → Authentication → Get Started (if it isn't set up yet), then the
**Sign-in method** tab → **Email/Password** → enable → Save.

## 3. Authorise the Cloud Run domain

Firebase Console → Authentication → Settings → Authorized Domains → **Add domain**:

```
clearhorizontools-355908014212.australia-southeast2.run.app
```

Without this, the Firebase JS SDK refuses to sign anyone in on the deployed site.

## 4. Generate a service account key

Firebase Console → Project Settings → Service Accounts → **Generate new private key**.
A JSON file downloads. Its entire contents become `FIREBASE_CREDENTIALS_JSON`.

Treat this file like a password. Don't commit it — `.gitignore` already excludes
`*firebase-adminsdk*.json`, but the safest thing is to move it out of the project folder
once you've copied the contents into `.env` and Cloud Run.

## 5. Deploy and set the variables

Follow the Configuration and Deploying sections of [README.md](README.md). You'll need all
five environment variables set on Cloud Run before sign-in will work.

## 6. Check it works

Visit the live site and run the whole flow:

- [ ] Sign up with a `@clearhorizon.com.au` email
- [ ] Receive and click the verification email
- [ ] Click "I've verified — continue" and land on the tools page
- [ ] Sign out and confirm you're returned to sign-in
- [ ] Try signing up with a non-`@clearhorizon.com.au` email — should be blocked

## Troubleshooting

**App won't start: "SECRET_KEY environment variable is not set"**
The variable isn't set on Cloud Run. Check the Configuration section of the README.

**Logs show "FIREBASE_CREDENTIALS_JSON not set" but the app starts**
Expected behaviour — the app runs without it, but authentication won't. Set it via the
Cloud Run console (the JSON is awkward to pass on the command line).

**Sign-in fails with "auth/configuration-not-found"**
Wrong API key or auth domain, or the web app was never registered. Re-check step 1.

**"Domain not authorized" from the Firebase JS SDK**
The Cloud Run domain isn't in Authorized Domains. Re-check step 3.

**Sign-in works but keeps redirecting to verify-email after verifying**
The browser tab is holding a stale token. Click "I've verified — continue", which forces a
refresh. If it still happens, sign out and back in.
