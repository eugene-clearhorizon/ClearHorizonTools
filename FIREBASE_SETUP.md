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

## 4. Set the email action URL

Firebase Console → Authentication → **Templates** → edit any template → **Customize action
URL**:

```
https://clearhorizontools-355908014212.australia-southeast2.run.app/auth/action
```

This is a **single setting for the whole project**, even though the console shows it inside
each template's editor. Every action email — verification, password reset, email recovery —
uses it, and Firebase tells them apart by appending `?mode=...` to it.

That is why the app has one `/auth/action` route that dispatches on `mode`, rather than a
route per email type. Pointing this at a per-mode URL such as `/auth/verify-action` breaks
every other mode: the page sees a `mode` it doesn't handle and bounces the user to the
sign-in page, silently discarding the code in the link.

Check the link in a real email if you're unsure it's right. The console's template preview
shows placeholder values (`mode=action&oobCode=code`), not what actually gets sent.

## 5. Generate a service account key

Firebase Console → Project Settings → Service Accounts → **Generate new private key**.
A JSON file downloads. Its entire contents become `FIREBASE_CREDENTIALS_JSON`.

Treat this file like a password. Don't commit it — `.gitignore` already excludes
`*firebase-adminsdk*.json`, but the safest thing is to move it out of the project folder
once you've copied the contents into `.env` and Cloud Run.

## 6. Deploy and set the variables

Follow the Configuration and Deploying sections of [README.md](README.md). You'll need all
five environment variables set on Cloud Run before sign-in will work.

## 7. Check it works

Visit the live site and run the whole flow:

- [ ] Sign up with a `@clearhorizon.com.au` email
- [ ] Receive and click the verification email — it should land on `/auth/action`
      and say "Your email has been verified", not bounce to the sign-in page
- [ ] Click "I've verified — continue" and land on the tools page
- [ ] Sign out and confirm you're returned to sign-in
- [ ] Try signing up with a non-`@clearhorizon.com.au` email — should be blocked
- [ ] Use "Forgot password" on the sign-in page and click that link too — it shares
      the same action URL, so it is the other half of the same setting

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

**Clicking the verification link just lands on the sign-in page, and the account stays unverified**

The action URL is pointing at a per-mode route instead of `/auth/action`. The link carries
`mode=verifyEmail`; a page that only handles `resetPassword` redirects it away without ever
calling `applyActionCode`, so the code in the link is thrown away and `email_verified` is
never set. The user then signs in, gets sent back to the verify page, clicks the link
again, and loops forever.

Fix the action URL as described in step 4. `/auth/verify-action` and `/auth/reset-action`
still work — they now forward to `/auth/action` with the query string intact, so links
already sitting in inboxes are fine — but the console should point at `/auth/action`.

**Nobody receives the verification email, but the accounts appear under Authentication**

Two different faults look identical from the Firebase console, and the app now tells them
apart for you. Work out which one you have before changing anything:

1. *Firebase refused to send.* The signup page redirects to the verify page showing
   "we couldn't send the verification email" instead of "check your inbox", and the
   application log carries a line beginning `VERIFICATION EMAIL SEND FAILED`, with the
   Firebase error code. Find it with:

   ```powershell
   gcloud run services logs read clearhorizontools `
     --project evaluation-tools --region australia-southeast2 --limit 200 |
     Select-String "VERIFICATION EMAIL SEND FAILED"
   ```

   A `code=auth/too-many-requests` means the project hit its daily send quota. Any other
   code usually means custom SMTP is configured and broken — check Firebase Console →
   Authentication → Templates → SMTP settings.

2. *The mail was sent and something downstream ate it.* The verify page says "check your
   inbox" as normal and there is no `VERIFICATION EMAIL SEND FAILED` line in the log.
   Firebase handed the message off; the problem is delivery.

   `clearhorizon.com.au` is on Microsoft 365 (its MX is
   `clearhorizon-com-au.mail.protection.outlook.com`), and Exchange Online Protection
   routinely quarantines mail from `noreply@clear-horizon-tools.firebaseapp.com` — the
   `firebaseapp.com` domain is shared by every Firebase project, so its sender
   reputation is everyone’s combined. Because only `@clearhorizon.com.au` addresses
   can register, every verification email hits that one filter, so this fails for
   everyone at once.

   Confirm it in Exchange admin center → Mail flow → **Message trace**, searching for the
   sender. That shows whether the message reached the tenant and what EOP did with it.
   Then either allow the sender domain in Defender → Policies → Tenant Allow/Block List,
   or — better — configure custom SMTP in Firebase so verification mail comes from
   `clearhorizon.com.au` and isn't sharing anyone else's reputation.

**Sign-in works but keeps redirecting to verify-email after verifying**
The browser tab is holding a stale token. Click "I've verified — continue", which forces a
refresh. If it still happens, sign out and back in.
