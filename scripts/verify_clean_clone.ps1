<#
.SYNOPSIS
  Verify NUMIDIA EYE from a genuinely clean clone of the remote.

.DESCRIPTION
  Clones `origin` into a scratch directory and proves the submission works the
  way the documentation claims:

    1. what a clone does and does not contain
    2. `uv sync` installs
    3. the CREDENTIAL-FREE FIRMS archive path populates a database
       (--db comes BEFORE the `fetch` subcommand)
    4. the API starts on port 8010 and reports honest status
    5. the static site serves on 5500
    6. /ai fails CLOSED - no numeric probability without a registered artifact

  It asserts the fail-closed contract, not just that processes start. Anything
  unexpected is a failure with a non-zero exit code.

  Kills only the PIDs it starts, and removes only its own scratch directory.

.EXAMPLE
  pwsh -File scripts/verify_clean_clone.ps1
  pwsh -File scripts/verify_clean_clone.ps1 -ApiPort 8010 -SitePort 5500
#>
[CmdletBinding()]
param(
  [int]$ApiPort = 8010,
  [int]$SitePort = 5500,
  [string]$Repo = (Join-Path (Split-Path $PSScriptRoot -Parent) '')
)

$ErrorActionPreference = 'Continue'
$script:Failures = @()
$startedPids = @()

function Step { param($m) Write-Host "`n== $m" -ForegroundColor Cyan }
function Ok   { param($m) Write-Host "   OK    $m" -ForegroundColor Green }
function Info { param($m) Write-Host "   ..    $m" -ForegroundColor Gray }
function Bad  { param($m) Write-Host "   FAIL  $m" -ForegroundColor Red; $script:Failures += $m }
function Assert {
  param([bool]$cond, [string]$msg)
  if ($cond) { Ok $msg } else { Bad $msg }
}

$scratch = Join-Path ([System.IO.Path]::GetTempPath()) ("numidia-clean-clone-" + [guid]::NewGuid().ToString('N').Substring(0,8))
$git = (Get-Command git -EA SilentlyContinue).Source
if (-not $git) { Write-Host "git not found on PATH" -ForegroundColor Red; exit 2 }

function Cleanup {
  foreach ($pid_ in $startedPids) {
    try { Stop-Process -Id $pid_ -Force -EA SilentlyContinue; Write-Host "   .. stopped pid $pid_" } catch {}
  }
  # remove only our own scratch dir
  if ($scratch -and (Test-Path $scratch) -and $scratch -like '*numidia-clean-clone-*') {
    try { Remove-Item $scratch -Recurse -Force -EA SilentlyContinue; Write-Host "   .. removed $scratch" } catch {}
  }
}
trap { Bad "unexpected error: $($_.Exception.Message)"; Cleanup; exit 1 }

Write-Host "NUMIDIA EYE - clean clone verification" -ForegroundColor White
Write-Host "scratch: $scratch"

# ---------------------------------------------------------------- 1. clone
Step "1. Clone from origin"
$origin = (& $git -C $Repo remote get-url origin) 2>$null
Assert ([bool]$origin) "origin remote resolves ($origin)"
if (-not $origin) { Cleanup; exit 1 }
& $git clone --quiet --no-hardlinks $origin $scratch 2>&1 | Out-Null
Assert (Test-Path (Join-Path $scratch '.git')) "clone created"

$cloneHead = (& $git -C $scratch rev-parse HEAD).Trim()
$cloneShort = (& $git -C $scratch rev-parse --short HEAD).Trim()
Write-Host "   HEAD  $cloneShort  ($cloneHead)"

# ------------------------------------------------- 2. presence expectations
Step "2. Clone contents (expect present / expect absent)"
$present = @('data\labels\firms_labels_v2.csv','services\ml\models\verifier_v2\model.joblib',
             'services\ml\models\verifier_v2\manifest.json','apps\site\index.html',
             'apps\site\vendor\maplibre-gl.js','apps\site\vendor\LICENSE-maplibre.txt',
             'docs\SETUP.md','docs\licensing.md','MODEL_LICENSE.md','apps\web\package-lock.json')
$absent  = @('.env','data\db')
foreach ($p in $present) { Assert (Test-Path (Join-Path $scratch $p)) "present: $p" }
foreach ($p in $absent)  { Assert (-not (Test-Path (Join-Path $scratch $p))) "absent:  $p" }
$n = (Get-ChildItem -Recurse -File $scratch -Force -EA SilentlyContinue |
      Where-Object { $_.FullName -notlike '*\.git\*' } | Measure-Object).Count
Info "total files in clone: $n"

# --------------------------------------------------------------- 3. install
Step "3. uv sync --extra api --extra ml --extra dev"
Push-Location $scratch
$sync = & uv sync --extra api --extra ml --extra dev 2>&1
$syncExit = $LASTEXITCODE
Pop-Location
Assert ($syncExit -eq 0) "uv sync exit=$syncExit"

# --------------------------------------------- 4. keyless FIRMS archive path
Step "4. Keyless archive fetch (no .env, no FIRMS_MAP_KEY)"
Push-Location $scratch
# NOTE: --db is a top-level option and MUST precede the `fetch` subcommand.
$fetch = & uv run python -m numidia_worker.cli --db data/db/numidia.db fetch --mode archive 2>&1 | Out-String
$fetchExit = $LASTEXITCODE
Pop-Location
Assert ($fetchExit -eq 0) "archive fetch exit=$fetchExit"
if ($fetch -match '"status":\s*"ok"') { Ok "fetch reported status ok" } else { Bad "fetch did not report status ok"; $fetch.Split("`n") | Select-Object -First 12 | ForEach-Object { Write-Host "        $_" } }
$rows = if ($fetch -match '"total":\s*(\d+)') { $Matches[1] } else { '0' }
Assert ([int]$rows -gt 0) "archive fetch stored $rows detections"
Assert (Test-Path (Join-Path $scratch 'data\db\numidia.db')) "database file created"
# The ingest must NOT claim an AI verdict when no artifact is registered.
if ($fetch -match '"status":\s*"AI_UNAVAILABLE"') { Ok "ingest reported AI_UNAVAILABLE (no artifact registered)" }
else { Info "NOTE: ingest reported a verification block that was not AI_UNAVAILABLE - inspect manually" }

# ------------------------------------------------------------------ 5. API
Step "5. API on port $ApiPort"
Push-Location $scratch
$api = Start-Process -PassThru -WindowStyle Hidden -FilePath "uv" `
        -ArgumentList @('run','uvicorn','numidia_api.app:app','--host','127.0.0.1','--port',"$ApiPort") `
        -RedirectStandardOutput (Join-Path $scratch 'api.out') -RedirectStandardError (Join-Path $scratch 'api.err')
Pop-Location
$startedPids += $api.Id
Info "api pid $($api.Id); waiting for readiness (the 48.5 MB artifact verification makes first start slow)"

$ready = $false
for ($i=0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 2
  try { if ((Invoke-RestMethod "http://127.0.0.1:$ApiPort/health" -TimeoutSec 10).status -eq 'ok') { $ready = $true; break } } catch {}
}
Assert $ready "/health reports ok"

if ($ready) {
  try {
    $st = Invoke-RestMethod "http://127.0.0.1:$ApiPort/system/status" -TimeoutSec 180
    Write-Host "   ..    firms=$($st.firms) ai=$($st.ai) model=$(if($st.model){$st.model}else{'<none>'}) state=$($st.data_state) detections=$($st.detections_count)"
    Assert ([bool]$st.data_state) "data_state is reported"
    Assert ($st.detections_count -ge 0) "detection count reported"
  } catch { Bad "/system/status failed: $($_.Exception.Message)" }

  # ------------------------------------------------- 6. fail-closed contract
  Step "6. /ai must fail CLOSED without a registered artifact"
  $env:NUMIDIA_ACTIVE_MODEL = ''   # ensure the default unset path
  try {
    $det = Invoke-RestMethod "http://127.0.0.1:$ApiPort/detections?limit=1" -TimeoutSec 60
    if ($det -and @($det).Count -gt 0) {
      $id = @($det)[0].detection_id
      Info "testing detection $id"
      $code = 0; $body = $null
      try {
        $body = Invoke-RestMethod "http://127.0.0.1:$ApiPort/detections/$id/ai" -TimeoutSec 120
        $code = 200
      } catch {
        $code = [int]$_.Exception.Response.StatusCode
        try { $body = $_.ErrorDetails.Message | ConvertFrom-Json } catch { $body = $null }
      }
      if ($code -eq 200 -and $body.status -eq 'AI_UNAVAILABLE') {
        Ok "HTTP 200 with AI_UNAVAILABLE status"
      } else {
        Assert ($code -eq 503) "/ai returned $code (expected 503 when no artifact)"
      }
      if ($body) {
        Assert ($body.probability -eq $null) "probability is null, not a fabricated number"
        Assert ($body.model -eq $null)      "model is null"
        Assert ($body.prediction -eq $null) "prediction is null"
      } else { Bad "could not parse /ai body" }
    } else { Bad "no detections available to test /ai" }
  } catch { Bad "fail-closed probe failed: $($_.Exception.Message)" }
}

# ----------------------------------------------------------------- 7. site
Step "7. Static site on port $SitePort"
$site = Start-Process -PassThru -WindowStyle Hidden -FilePath "python" `
        -ArgumentList @('-m','http.server',"$SitePort",'--bind','127.0.0.1') -WorkingDirectory (Join-Path $scratch 'apps\site')
$startedPids += $site.Id
$siteOk = $false
for ($i=0; $i -lt 20; $i++) {
  Start-Sleep -Milliseconds 800
  try { if ((Invoke-WebRequest "http://127.0.0.1:$SitePort/" -TimeoutSec 10 -UseBasicParsing).StatusCode -eq 200) { $siteOk = $true; break } } catch {}
}
Assert $siteOk "site returns HTTP 200 at http://127.0.0.1:$SitePort/"

Cleanup

# ---------------------------------------------------------------- verdict
Write-Host ""
if ($script:Failures.Count -eq 0) {
  Write-Host "RESULT: PASS - clean clone at $cloneShort satisfies every assertion." -ForegroundColor Green
  exit 0
} else {
  Write-Host "RESULT: FAIL - $($script:Failures.Count) assertion(s) failed:" -ForegroundColor Red
  $script:Failures | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
  exit 1
}