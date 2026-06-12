# uninstall.ps1 — Remove DeepSeek API Usage Monitor
#
#   Right-click → Run with PowerShell  (or)
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1

$ErrorActionPreference = "Continue"

$AppDir     = "$env:LOCALAPPDATA\Programs\deepseek-monitor"
$ConfigDir  = "$env:APPDATA\deepseek-monitor"
$DataDir    = "$env:LOCALAPPDATA\deepseek-monitor"
$StartupDir = [Environment]::GetFolderPath("Startup")
$Shortcut   = "$StartupDir\deepseek-monitor.lnk"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DeepSeek API Monitor — Uninstaller" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---- 1. Kill running processes ---------------------------------------------------
Write-Host "-> Stopping running instances ..."
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    $proc = $_
    try {
        $cmdline = (Get-WmiObject Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
        if ($cmdline -match "deepseek.*main\.py") {
            Stop-Process -Id $proc.Id -Force
            Write-Host "   Stopped PID $($proc.Id)" -ForegroundColor Green
        }
    } catch {}
}
Write-Host "   Done." -ForegroundColor Green

# ---- 2. Remove startup shortcut --------------------------------------------------
if (Test-Path $Shortcut) {
    Remove-Item -Force $Shortcut
    Write-Host "   Startup shortcut removed." -ForegroundColor Green
} else {
    Write-Host "   No startup shortcut found." -ForegroundColor Yellow
}

# ---- 3. Remove application -------------------------------------------------------
if (Test-Path $AppDir) {
    Remove-Item -Recurse -Force $AppDir
    Write-Host "   Application directory removed." -ForegroundColor Green
} else {
    Write-Host "   No application directory found." -ForegroundColor Yellow
}

# ---- 4. Remove config ------------------------------------------------------------
if (Test-Path $ConfigDir) {
    $confirm = Read-Host "   Remove config at $ConfigDir? [y/N]"
    if ($confirm -eq 'y' -or $confirm -eq 'Y') {
        Remove-Item -Recurse -Force $ConfigDir
        Write-Host "   Config removed." -ForegroundColor Green
    } else {
        Write-Host "   Config kept." -ForegroundColor Yellow
    }
}

# ---- 5. Remove data --------------------------------------------------------------
if (Test-Path $DataDir) {
    $confirm = Read-Host "   Remove balance history at $DataDir? [y/N]"
    if ($confirm -eq 'y' -or $confirm -eq 'Y') {
        Remove-Item -Recurse -Force $DataDir
        Write-Host "   Data removed." -ForegroundColor Green
    } else {
        Write-Host "   Data kept." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Uninstall complete." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

pause
