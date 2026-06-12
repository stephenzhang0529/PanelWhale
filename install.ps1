# install.ps1 — Install DeepSeek API Usage Monitor on Windows
#
#   Right-click → Run with PowerShell  (or)
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Requires: Python 3.8+ and pip

$ErrorActionPreference = "Stop"

$AppDir     = "$env:LOCALAPPDATA\Programs\deepseek-monitor"
$ConfigDir  = "$env:APPDATA\deepseek-monitor"
$DataDir    = "$env:LOCALAPPDATA\deepseek-monitor"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DeepSeek API Monitor — Windows Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---- 1. Check Python -------------------------------------------------------------
Write-Host "-> Checking Python installation ..."
$python = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $ver = & $cmd --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -match "(\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 8) {
                $python = $cmd
                Write-Host "   Found: $ver ($python)" -ForegroundColor Green
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Write-Host "ERROR: Python 3.8+ is required but was not found." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Red
    pause
    exit 1
}

# ---- 2. Copy application files ---------------------------------------------------
Write-Host ""
Write-Host "-> Installing application to $AppDir ..."
if (Test-Path $AppDir) {
    Remove-Item -Recurse -Force $AppDir
}
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

Copy-Item -Recurse "$ScriptRoot\main.py"           $AppDir\
Copy-Item -Recurse "$ScriptRoot\monitor"            $AppDir\
Copy-Item -Recurse "$ScriptRoot\requirements.txt"   $AppDir\
Copy-Item -Recurse "$ScriptRoot\deepseek-color.png" $AppDir\
if (Test-Path "$ScriptRoot\config.yaml") {
    Copy-Item "$ScriptRoot\config.yaml" $AppDir\
}

Write-Host "   Application files copied." -ForegroundColor Green

# ---- 3. Install Python dependencies ----------------------------------------------
Write-Host ""
Write-Host "-> Installing Python dependencies ..."
& $python -m pip install --upgrade pip -q
& $python -m pip install -r "$AppDir\requirements.txt" -q
Write-Host "   Dependencies installed." -ForegroundColor Green

# ---- 4. User config --------------------------------------------------------------
Write-Host ""
Write-Host "-> Setting up configuration ..."
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

if (-not (Test-Path "$ConfigDir\config.yaml")) {
    $configContent = @'
# PanelWhale — configuration
# Environment variable DEEPSEEK_API_KEY overrides the file.

api_key: "sk-your-api-key-here"

# How often to check balance (seconds).  Minimum: 30.
poll_interval_seconds: 300

# Balance thresholds for colour changes and desktop notifications.
#   above yellow — normal  (💎)
#   yellow .. red — warning (🟡)
#   below red      — danger  (🔴)
alert_threshold_yellow: 5.0
alert_threshold_red: 1.0
'@
    Set-Content -Path "$ConfigDir\config.yaml" -Value $configContent -Encoding UTF8
    Write-Host "   Config created at $ConfigDir\config.yaml" -ForegroundColor Green

    $apiKey = Read-Host "   Enter your API key (or press Enter to skip)"
    if ($apiKey) {
        (Get-Content "$ConfigDir\config.yaml") -replace 'sk-your-api-key-here', $apiKey | Set-Content "$ConfigDir\config.yaml" -Encoding UTF8
        Write-Host "   API key saved." -ForegroundColor Green
    }
} else {
    Write-Host "   Config already exists, skipping." -ForegroundColor Yellow
}

# ---- 5. Data directory -----------------------------------------------------------
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
Write-Host "   Data directory ready: $DataDir" -ForegroundColor Green

# ---- 6. Create startup shortcut --------------------------------------------------
Write-Host ""
Write-Host "-> Creating startup shortcut ..."
$shortcutPath = "$StartupDir\deepseek-monitor.lnk"
$targetPath   = $python
$arguments    = """$AppDir\main.py"""
$workingDir   = $AppDir

$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath       = $targetPath
$shortcut.Arguments        = $arguments
$shortcut.WorkingDirectory = $workingDir
$shortcut.Description      = "DeepSeek API Usage Monitor"
if (Test-Path "$AppDir\deepseek-color.png") {
    $shortcut.IconLocation  = "$AppDir\deepseek-color.png"
}
$shortcut.Save()
Write-Host "   Startup shortcut created." -ForegroundColor Green

# ---- 7. Start now ----------------------------------------------------------------
Write-Host ""
Write-Host "-> Starting the monitor ..."
try {
    Stop-Process -Name "python" -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
} catch {}
$proc = Start-Process -FilePath $python -ArgumentList """$AppDir\main.py""" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2

if ($proc.HasExited) {
    Write-Host "   Monitor may have failed to start." -ForegroundColor Yellow
    Write-Host "   Check logs under $DataDir\logs\" -ForegroundColor Yellow
} else {
    Write-Host "   Monitor started (PID $($proc.Id))." -ForegroundColor Green
    Write-Host "   Look for the DeepSeek icon in your system tray." -ForegroundColor Green
}

# ---- 8. Done ---------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Installation complete!" -ForegroundColor Cyan
Write-Host ""
Write-Host " Manage with:"
Write-Host "   $AppDir\main.py          (run manually)"
Write-Host "   Task Manager → Startup   (disable auto-start)"
Write-Host ""
Write-Host " Files:"
Write-Host "   App:      $AppDir"
Write-Host "   Config:   $ConfigDir\config.yaml"
Write-Host "   Data:     $DataDir\logs\"
Write-Host "   Startup:  $shortcutPath"
Write-Host "========================================" -ForegroundColor Cyan

pause
