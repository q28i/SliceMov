# PeakCut Studio PowerShell Launcher
$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "             PeakCut Studio Launcher               " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# 1. FFmpeg Configuration
$ffmpegCmd = Get-Command "ffmpeg" -ErrorAction SilentlyContinue
if (-not $ffmpegCmd) {
    $wingetFfmpeg = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetFfmpeg) {
        $binDir = $wingetFfmpeg.DirectoryName
        $env:PATH = "$binDir;$env:PATH"
        Write-Host "[OK] FFmpeg found at $binDir and added to session PATH." -ForegroundColor Green
    } else {
        Write-Host "[INFO] FFmpeg not found. Attempting install via winget..." -ForegroundColor Yellow
        winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
        $wingetFfmpeg = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($wingetFfmpeg) {
            $binDir = $wingetFfmpeg.DirectoryName
            $env:PATH = "$binDir;$env:PATH"
        }
    }
} else {
    Write-Host "[OK] FFmpeg detected in PATH: $($ffmpegCmd.Source)" -ForegroundColor Green
}

# 2. Virtual Environment
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[INFO] Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
    Write-Host "[INFO] Installing dependencies..." -ForegroundColor Yellow
    & ".\.venv\Scripts\pip.exe" install -r requirements.txt
    Write-Host "[OK] Dependencies installed." -ForegroundColor Green
}

# 3. Speech Model
$modelTokenFile = "data\models\sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8\tokens.txt"
if (-not (Test-Path $modelTokenFile)) {
    Write-Host "[INFO] Fetching speech model..." -ForegroundColor Yellow
    & ".\.venv\Scripts\python.exe" -m studio.fetch_model
} else {
    Write-Host "[OK] Speech model ready." -ForegroundColor Green
}

# 4. Launch Browser & Server
Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host "  Starting PeakCut at http://127.0.0.1:8765        " -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop.                           " -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
Write-Host ""

Start-Process "http://127.0.0.1:8765"
& ".\.venv\Scripts\python.exe" -m studio.server

