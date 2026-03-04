# Flask Web App Starter

A Flask starter template as per [these docs](https://flask.palletsprojects.com/en/3.0.x/quickstart/#a-minimal-application).

## Getting Started

Previews should run automatically when starting a workspace.

## Deploying Updates (Cloud Run)

This app is deployed to Cloud Run.

Live URL:
`https://clearhorizontools-355908014212.australia-southeast2.run.app/`

Deploy from the project root:

```powershell
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud run deploy clearhorizontools --source . --region australia-southeast2 --allow-unauthenticated
```

Or use the helper script:

```powershell
.\deploy.ps1 -ProjectId <YOUR_PROJECT_ID>
```
