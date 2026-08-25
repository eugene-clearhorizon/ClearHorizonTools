param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Service = "clearhorizontools",

    [Parameter(Mandatory = $false)]
    [string]$Region = "australia-southeast2"
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

if (-not $ProjectId -or [string]::IsNullOrWhiteSpace($ProjectId)) {
    $activeProject = & $gcloudCommand config get-value project 2>$null
    if ($LASTEXITCODE -eq 0 -and $activeProject -and $activeProject -ne "(unset)") {
        $ProjectId = $activeProject.Trim()
    } else {
        throw "No project provided. Pass -ProjectId or run: gcloud config set project <PROJECT_ID>"
    }
}

Write-Host "Deploying service '$Service' to project '$ProjectId' in region '$Region'..."

# Pass --project per command rather than `gcloud config set project`, which would
# permanently repoint the caller's gcloud installation as a side effect of deploying.
& $gcloudCommand run deploy $Service `
    --source . `
    --project $ProjectId `
    --region $Region `
    --allow-unauthenticated

if ($LASTEXITCODE -ne 0) {
    throw "Cloud Run deployment failed."
}

$url = & $gcloudCommand run services describe $Service `
    --project $ProjectId `
    --region $Region `
    --format "value(status.url)"

if ($LASTEXITCODE -ne 0) {
    throw "Deployment succeeded, but failed to fetch service URL."
}

Write-Host ""
Write-Host "Deployment complete."
Write-Host "URL: $url"
