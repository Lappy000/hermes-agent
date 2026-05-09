# install.ps1 — Hermes Agent Windows installer (PowerShell)
#
# Usage: irm https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.ps1 | iex
#   or:  .\install.ps1 [-Branch main] [-NoPath] [-Upgrade]
#
# Requires: Python 3.11+, Git

[CmdletBinding()]
param(
    [string]$Branch = "main",
    [switch]$NoPath,
    [switch]$Upgrade
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Speed up Invoke-WebRequest

# Configuration
$HermesHome = "$env:USERPROFILE\.hermes"
$HermesAgent = "$HermesHome\hermes-agent"
$HermesBin = "$HermesHome\bin"
$MinPythonMajor = 3
$MinPythonMinor = 11

# Colors
function Write-Step { param([string]$msg) Write-Host "  → " -ForegroundColor Cyan -NoNewline; Write-Host $msg }
function Write-Ok { param([string]$msg) Write-Host "  ✓ " -ForegroundColor Green -NoNewline; Write-Host $msg }
function Write-Warn { param([string]$msg) Write-Host "  ⚠ " -ForegroundColor Yellow -NoNewline; Write-Host $msg }
function Write-Err { param([string]$msg) Write-Host "  ✗ " -ForegroundColor Red -NoNewline; Write-Host $msg }

# Banner
Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║       Hermes Agent — Windows Installer       ║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# ─── Check Python ───────────────────────────────────────────────────────────
Write-Step "Checking Python..."

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        try {
            $ver = & $found.Source --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge $MinPythonMajor -and $minor -ge $MinPythonMinor) {
                    $python = $found.Source
                    break
                }
            }
        } catch {}
    }
}

if (-not $python) {
    Write-Err "Python $MinPythonMajor.$MinPythonMinor+ required but not found."
    Write-Host "    Install from: https://www.python.org/downloads/" -ForegroundColor Gray
    Write-Host "    Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Gray
    exit 1
}

$pyVer = & $python --version 2>&1
Write-Ok "Found $pyVer at $python"

# ─── Check Git ──────────────────────────────────────────────────────────────
Write-Step "Checking Git..."

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Write-Err "Git is required but not found."
    Write-Host "    Install from: https://git-scm.com/download/win" -ForegroundColor Gray
    exit 1
}

$gitVer = & git --version 2>&1
Write-Ok "Found $gitVer"

# ─── Clone or Update ────────────────────────────────────────────────────────
if (Test-Path $HermesAgent) {
    if ($Upgrade) {
        Write-Step "Updating Hermes Agent..."
        Push-Location $HermesAgent
        try {
            & git fetch origin $Branch --quiet 2>&1 | Out-Null
            & git checkout $Branch --quiet 2>&1 | Out-Null
            & git pull origin $Branch --quiet 2>&1 | Out-Null
            Write-Ok "Updated to latest $Branch"
        } catch {
            Write-Warn "Git pull failed: $_. Continuing with existing code."
        }
        Pop-Location
    } else {
        Write-Ok "Hermes Agent already cloned at $HermesAgent"
        Write-Host "    Use -Upgrade to pull latest changes." -ForegroundColor Gray
    }
} else {
    Write-Step "Cloning Hermes Agent..."
    New-Item -ItemType Directory -Force -Path $HermesHome | Out-Null
    & git clone --branch $Branch --depth 1 `
        "https://github.com/NousResearch/hermes-agent.git" $HermesAgent 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to clone repository"
        exit 1
    }
    Write-Ok "Cloned hermes-agent ($Branch)"
}

# ─── Create Virtual Environment ────────────────────────────────────────────
$VenvDir = "$HermesAgent\venv"
$VenvPython = "$VenvDir\Scripts\python.exe"
$VenvPip = "$VenvDir\Scripts\pip.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Step "Creating virtual environment..."
    & $python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create virtual environment"
        exit 1
    }
    Write-Ok "Virtual environment created"
} else {
    Write-Ok "Virtual environment exists"
}

# ─── Install Dependencies ───────────────────────────────────────────────────
Write-Step "Installing Hermes Agent (this may take a minute)..."
& $VenvPip install --upgrade pip --quiet 2>&1 | Out-Null
& $VenvPip install -e "$HermesAgent[cli,pty]" --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "pip install with [cli,pty] failed, trying [cli] only..."
    & $VenvPip install -e "$HermesAgent[cli]" --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install Hermes Agent"
        exit 1
    }
}
Write-Ok "Hermes Agent installed"

# ─── Create Wrapper Scripts ─────────────────────────────────────────────────
Write-Step "Creating command wrappers..."
New-Item -ItemType Directory -Force -Path $HermesBin | Out-Null

# hermes.cmd — batch wrapper (works in cmd.exe and PowerShell)
$cmdWrapper = @"
@echo off
"$VenvDir\Scripts\python.exe" -m hermes_cli.main %*
"@
Set-Content -Path "$HermesBin\hermes.cmd" -Value $cmdWrapper -Encoding ASCII

# hermes.ps1 — PowerShell wrapper (preferred in PS sessions)
$ps1Wrapper = @"
#!/usr/bin/env pwsh
& "$VenvDir\Scripts\python.exe" -m hermes_cli.main @args
"@
Set-Content -Path "$HermesBin\hermes.ps1" -Value $ps1Wrapper -Encoding UTF8

Write-Ok "Created hermes.cmd and hermes.ps1 in $HermesBin"

# ─── Add to PATH ───────────────────────────────────────────────────────────
if (-not $NoPath) {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$HermesBin*") {
        Write-Step "Adding $HermesBin to user PATH..."
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$HermesBin", "User")
        # Also update current session
        $env:Path = "$env:Path;$HermesBin"
        Write-Ok "Added to PATH (restart terminal for full effect)"
    } else {
        Write-Ok "$HermesBin already in PATH"
    }
} else {
    Write-Warn "Skipped PATH modification (-NoPath flag)"
    Write-Host "    Add $HermesBin to your PATH manually." -ForegroundColor Gray
}

# ─── Enable Long Paths (optional) ──────────────────────────────────────────
Write-Step "Checking long path support..."
try {
    $longPaths = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -ErrorAction SilentlyContinue
    if ($longPaths.LongPathsEnabled -ne 1) {
        Write-Warn "Long paths not enabled. Some deep skill paths may fail."
        Write-Host "    Run as Admin: Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name 'LongPathsEnabled' -Value 1" -ForegroundColor Gray
    } else {
        Write-Ok "Long paths enabled"
    }
} catch {
    Write-Warn "Could not check long path status"
}

# ─── Windows Defender Exclusion Hint ────────────────────────────────────────
Write-Host ""
Write-Warn "Consider adding Windows Defender exclusion for performance:"
Write-Host "    Add-MpPreference -ExclusionPath '$HermesHome'" -ForegroundColor Gray
Write-Host ""

# ─── Done ───────────────────────────────────────────────────────────────────
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║          Installation Complete! ✓            ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "    1. Open a new terminal (PowerShell or cmd)" -ForegroundColor Gray
Write-Host "    2. Run: hermes setup" -ForegroundColor Gray
Write-Host "    3. Follow the setup wizard to configure your LLM provider" -ForegroundColor Gray
Write-Host ""
Write-Host "  Quick start:" -ForegroundColor White
Write-Host "    hermes              # Start interactive chat" -ForegroundColor Gray
Write-Host "    hermes doctor       # Check system health" -ForegroundColor Gray
Write-Host "    hermes --help       # See all options" -ForegroundColor Gray
Write-Host ""
