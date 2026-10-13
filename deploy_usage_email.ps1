# Deploys the monthly usage email: a Cloud Run job that runs src/stats/monthly_email.py,
# and a Cloud Scheduler trigger that starts it at 8am Melbourne time on the 1st.
#
# Safe to re-run. Re-run it after changing the email code or its settings in .env -
# the Cloud Build trigger on main only redeploys the web service, not this job.
#
#     .\deploy_usage_email.ps1
#
# Plain ASCII only: Windows PowerShell 5.1 reads BOM-less files in the ANSI codepage.

param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectId = "evaluation-tools",

    [Parameter(Mandatory = $false)]
    [string]$Region = "australia-southeast2",

    [Parameter(Mandatory = $false)]
    [string]$Job = "usage-email",

    [Parameter(Mandatory = $false)]
    [string]$SchedulerLocation = "australia-southeast1",

    [Parameter(Mandatory = $false)]
    [string]$Schedule = "0 8 1 * *"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$gcloudCommand = Get-Command gcloud -ErrorAction SilentlyContinue
if (-not $gcloudCommand) {
    $fallbackGcloud = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (Test-Path $fallbackGcloud) {
        $gcloudCommand = $fallbackGcloud
    } else {
        throw "gcloud CLI is not installed or not on PATH."
    }
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "No virtualenv at $python. See README.md, Running it locally."
}

function Invoke-Gcloud {
    & $gcloudCommand @args
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud $($args -join ' ') failed."
    }
}

function Test-Gcloud {
    # Exists-checks fail by design, so don't let stderr trip ErrorActionPreference.
    $ErrorActionPreference = "Continue"
    & $gcloudCommand @args *> $null
    return ($LASTEXITCODE -eq 0)
}

$schedulerJob = "$Job-monthly"
$serviceAccountName = "$Job-scheduler"
$serviceAccount = "$serviceAccountName@$ProjectId.iam.gserviceaccount.com"

# Copy the job's settings out of .env into a temporary env-vars file. It is written
# as JSON, which gcloud reads as YAML, so the Firebase credentials need no escaping.
$envKeys = @(
    "FIREBASE_CREDENTIALS_JSON", "USAGE_EMAIL_TO", "USAGE_EMAIL_FROM",
    "MAILGUN_API_KEY", "MAILGUN_DOMAIN", "MAILGUN_API_BASE", "SENDGRID_API_KEY"
)
# Python single quotes only: PowerShell 5.1 and 7 disagree on escaping embedded
# double quotes in native arguments, and this sidesteps both.
$exportEnv = "import json, sys; from dotenv import dotenv_values; " +
    "v = {k: x for k, x in dotenv_values('.env').items() if x}; " +
    "missing = [k for k in ('FIREBASE_CREDENTIALS_JSON', 'USAGE_EMAIL_TO', 'USAGE_EMAIL_FROM') if k not in v]; " +
    "missing += [] if ('MAILGUN_API_KEY' in v or 'SENDGRID_API_KEY' in v) else ['MAILGUN_API_KEY or SENDGRID_API_KEY']; " +
    "missing and sys.exit('Missing from .env: ' + ', '.join(missing)); " +
    "json.dump({k: v[k] for k in sys.argv[2:] if k in v}, open(sys.argv[1], 'w'))"

$envFile = Join-Path $env:TEMP ("usage-email-env-" + [guid]::NewGuid() + ".yaml")

Push-Location $PSScriptRoot
try {
    & $python -c $exportEnv $envFile @envKeys
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the job's settings from .env."
    }

    Write-Host "Deploying Cloud Run job '$Job' to project '$ProjectId' in region '$Region'..."
    Invoke-Gcloud run jobs deploy $Job `
        --source . `
        --project $ProjectId `
        --region $Region `
        --command python `
        "--args=-m,src.stats.monthly_email" `
        --env-vars-file $envFile `
        --max-retries 1 `
        --task-timeout 5m
} finally {
    # The file holds the Firebase key and the mail API key.
    Remove-Item $envFile -Force -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host "Setting up Cloud Scheduler trigger '$schedulerJob'..."
Invoke-Gcloud services enable cloudscheduler.googleapis.com --project $ProjectId

if (-not (Test-Gcloud iam service-accounts describe $serviceAccount --project $ProjectId)) {
    Invoke-Gcloud iam service-accounts create $serviceAccountName `
        --display-name "Starts the monthly usage email job" `
        --project $ProjectId
    # A new service account takes a few seconds to become visible to IAM.
    Start-Sleep -Seconds 15
}

Invoke-Gcloud run jobs add-iam-policy-binding $Job `
    --member "serviceAccount:$serviceAccount" `
    --role roles/run.invoker `
    --project $ProjectId `
    --region $Region

$schedulerArgs = @(
    "--location", $SchedulerLocation,
    "--schedule", $Schedule,
    "--time-zone", "Australia/Melbourne",
    "--uri", "https://run.googleapis.com/v2/projects/$ProjectId/locations/$Region/jobs/${Job}:run",
    "--http-method", "POST",
    "--oauth-service-account-email", $serviceAccount,
    "--project", $ProjectId
)
if (Test-Gcloud scheduler jobs describe $schedulerJob --location $SchedulerLocation --project $ProjectId) {
    Invoke-Gcloud scheduler jobs update http $schedulerJob @schedulerArgs
} else {
    Invoke-Gcloud scheduler jobs create http $schedulerJob @schedulerArgs
}

Write-Host ""
Write-Host "Done. The email goes out on schedule '$Schedule' (Australia/Melbourne)."
Write-Host "To send one now, as a real email:"
Write-Host "  gcloud run jobs execute $Job --project $ProjectId --region $Region --wait"
