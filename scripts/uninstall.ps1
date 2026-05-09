# uninstall.ps1 — Hermes Agent Windows uninstaller (PowerShell)
#
# Usage: .\uninstall.ps1 [-KeepConfig] [-Force]

[CmdletBinding()]
param(
    [switch]$KeepConfig,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Configuration
$HermesHome = "$env:USERPROFILE\.hermes"
$HermesAgent = "$HermesHome\hermes-agent"
$HermesBin = "$HermesHome\bin"

# Colors
function Write-Step { param([string]$msg) Write-Host "  → " -ForegroundColor Cyan -NoNewline; Write-Host $msg }
function Write-Ok { param([string]$msg) Write-Host "  ✓ " -ForegroundColor Green -NoNewline; Write-Host $msg }
function Write-Warn { param([string]$msg) Write-Host "  ⚠ " -ForegroundColor Yellow -NoNewline; Write-Host $msg }

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Red
Write-Host "║       Hermes Agent — Windows Uninstaller     ║" -ForegroundColor Red
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Red
Write-Host ""

if (-not $Force) {
    $confirm = Read-Host "This will remove Hermes Agent. Continue? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "  Cancelled." -ForegroundColor Gray
        exit 0
    }
}

# ─── Stop Gateway Service ───────────────────────────────────────────────────
Write-Step "Stopping gateway service (if running)..."
$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if ($nssm) {
    & nssm stop HermesGateway 2>$null | Out-Null
    & nssm remove HermesGateway confirm 2>$null | Out-Null
    Write-Ok "Gateway service removed"
} else {
    # Try Task Scheduler
    schtasks /Delete /TN "HermesGateway" /F 2>$null | Out-Null
    Write-Ok "No service/task found (or removed)"
}

# ─── Remove from PATH ───────────────────────────────────────────────────────
Write-Step "Removing from PATH..."
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -like "*$HermesBin*") {
    $newPath = ($currentPath -split ";" | Where-Object { $_ -ne $HermesBin }) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Ok "Removed $HermesBin from PATH"
} else {
    Write-Ok "Not in PATH"
}

# ─── Remove Files ───────────────────────────────────────────────────────────
if ($KeepConfig) {
    Write-Step "Removing agent code (keeping config)..."
    if (Test-Path $HermesAgent) {
        Remove-Item -Recurse -Force $HermesAgent
    }
    if (Test-Path $HermesBin) {
        Remove-Item -Recurse -Force $HermesBin
    }
    Write-Ok "Agent code removed. Config preserved at $HermesHome"
} else {
    Write-Step "Removing all Hermes files..."
    if (Test-Path $HermesHome) {
        Remove-Item -Recurse -Force $HermesHome
    }
    Write-Ok "All Hermes files removed"
}

# ─── Done ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Hermes Agent has been uninstalled." -ForegroundColor Green
if ($KeepConfig) {
    Write-Host "  Config preserved at: $HermesHome" -ForegroundColor Gray
    Write-Host "  To fully remove: Remove-Item -Recurse $HermesHome" -ForegroundColor Gray
}
Write-Host ""
