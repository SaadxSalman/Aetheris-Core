# =============================================================
#  Aetheris Core — start all three tiers (Windows PowerShell)
#  Usage:  .\scripts\start-all.ps1
#  Logs:   .data/orch.*.log, .data/gw.*.log, .data/web.*.log
# =============================================================
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $root ".data"
New-Item -ItemType Directory -Force -Path $data | Out-Null

function Stop-ByPort([int]$port) {
  $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
}

# clean any previous instances on our ports
8000, 4000, 3000 | ForEach-Object { Stop-ByPort $_ }
Start-Sleep -Seconds 2

# ---- 1. Orchestrator (Python / LangGraph / FastAPI) ----
$py = Join-Path $root "orchestrator\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "[*] creating python venv + installing requirements..."
  Push-Location (Join-Path $root "orchestrator")
  python -m venv .venv
  & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
  Pop-Location
}
Start-Process -FilePath $py -ArgumentList "run.py" `
  -WorkingDirectory (Join-Path $root "orchestrator") `
  -RedirectStandardOutput (Join-Path $data "orch.out.log") `
  -RedirectStandardError (Join-Path $data "orch.err.log") `
  -WindowStyle Hidden | Out-Null
Write-Host "[1/3] orchestrator -> http://127.0.0.1:8000"

# ---- 2. Gateway (Fastify / TypeScript) ----
Push-Location (Join-Path $root "gateway")
if (-not (Test-Path "dist\index.js")) {
  Write-Host "[*] building gateway (tsc)..."
  npm install --no-fund --no-audit --loglevel=error
  npm run build --silent
}
Start-Process -FilePath "node" -ArgumentList "dist\index.js" `
  -RedirectStandardOutput (Join-Path $data "gw.out.log") `
  -RedirectStandardError (Join-Path $data "gw.err.log") `
  -WindowStyle Hidden | Out-Null
Pop-Location
Write-Host "[2/3] gateway       -> http://127.0.0.1:4000"

# ---- 3. Frontend (Next.js 15) ----
Push-Location (Join-Path $root "frontend")
if (-not (Test-Path ".next\BUILD_ID")) {
  Write-Host "[*] building frontend (next build)..."
  npm install --no-fund --no-audit --loglevel=error
  npm run build --silent
}
Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm start > ..\.data\web.out.log 2> ..\.data\web.err.log" `
  -WindowStyle Hidden | Out-Null
Pop-Location
Write-Host "[3/3] frontend      -> http://127.0.0.1:3000"

Start-Sleep -Seconds 6
Write-Host ""
Write-Host "  Aetheris Core is up.  Open  http://localhost:3000" -ForegroundColor Cyan
Write-Host "  Smoke test:  python scripts/smoke_test.py" -ForegroundColor DarkGray
