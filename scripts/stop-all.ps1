# =============================================================
#  Aetheris Core — stop all tiers (Windows PowerShell)
#  Usage:  .\scripts\stop-all.ps1
# =============================================================
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot

# 1. kill by port (frontend / gateway / orchestrator)
foreach ($port in 3000, 4000, 8000) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

# 2. kill by command line (uvicorn reloader children, next start, node dist)
$patterns = @("*Aetheris-Core*", "*run.py*", "*next start*", "*dist\index.js*")
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe' OR Name='cmd.exe'" |
  Where-Object {
    $cl = $_.CommandLine
    $cl -and (($patterns | Where-Object { $cl -like $_ }).Count -gt 0) -and ($cl -notlike "*stop-all*")
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2
Write-Host "Aetheris Core stopped." -ForegroundColor Cyan
