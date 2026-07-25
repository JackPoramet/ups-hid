# UPS Monitor — Build Automation Script
# ========================================
# Build .exe ด้วย PyInstaller แล้วสร้าง installer ด้วย Inno Setup
#
# Usage:
#   .\build.ps1
#   .\build.ps1 -SkipInstaller   (build .exe อย่างเดียว)
#   .\build.ps1 -Clean           (ลบ build artifacts ก่อน build)

param(
    [switch]$SkipInstaller,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Paths -------------------------------------------------------------------
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir   # UPS/
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvPip     = Join-Path $ProjectRoot ".venv\Scripts\pip.exe"
$SpecFile    = Join-Path $ScriptDir "build_exe.spec"
$DistDir     = Join-Path $ScriptDir "dist"
$InstallerScript = Join-Path $ScriptDir "installer\installer.iss"
$ExeOutput   = Join-Path $DistDir "ENEREX-UPS-Monitor.exe"

# -- Helper Functions ---------------------------------------------------------
function Write-Step {
    param([string]$msg)
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
}

function Write-OK   { param([string]$msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }

# -- Check prerequisites -----------------------------------------------------
Write-Step "Checking prerequisites"

# Python venv
if (-not (Test-Path $VenvPython)) {
    Write-Fail "Python venv not found at: $VenvPython"
    Write-Warn "Run: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
    exit 1
}
Write-OK "Python venv found"

# PyInstaller
$pyinstallerCheck = & $VenvPython -c "import PyInstaller; print(PyInstaller.__version__)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "PyInstaller not found -- installing..."
    & $VenvPip install pyinstaller --quiet
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to install PyInstaller"; exit 1 }
}
Write-OK ("PyInstaller: {0}" -f $pyinstallerCheck)

# -- Clean -------------------------------------------------------------------
if ($Clean) {
    Write-Step "Cleaning build artifacts"
    foreach ($dir in @("build", "dist", "__pycache__")) {
        $path = Join-Path $ScriptDir $dir
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
            Write-OK ("Removed: {0}" -f $dir)
        }
    }
}

# -- Step 1: Build .exe ------------------------------------------------------
Write-Step "Building .exe with PyInstaller"

Push-Location $ProjectRoot
try {
    & $VenvPython -m PyInstaller `
        "$SpecFile" `
        --noconfirm `
        --distpath "$DistDir" `
        --workpath (Join-Path $ScriptDir "build")

    if ($LASTEXITCODE -ne 0) {
        Write-Fail ("PyInstaller build failed (exit code: {0})" -f $LASTEXITCODE)
        exit 1
    }
} finally {
    Pop-Location
}

if (-not (Test-Path $ExeOutput)) {
    Write-Fail ("Expected output not found: {0}" -f $ExeOutput)
    exit 1
}

$exeSize = [math]::Round((Get-Item $ExeOutput).Length / 1MB, 1)
Write-OK ("Build successful: ENEREX-UPS-Monitor.exe ({0} MB)" -f $exeSize)

# -- Step 2: Build Installer -------------------------------------------------
if (-not $SkipInstaller) {
    Write-Step "Building Installer with Inno Setup"

    # หา Inno Setup compiler (รองรับทั้ง v6, v7 และ PATH)
    $InnoCmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($InnoCmd) {
        $IsccExe = $InnoCmd.Source
    } else {
        $InnoSetupPaths = @(
            "$env:LocalAppData\Programs\Inno Setup 7\ISCC.exe",
            "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe",
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe",
            "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
            "C:\Program Files\Inno Setup 7\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe"
        )
        $IsccExe = $InnoSetupPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    }

    if (-not $IsccExe) {
        Write-Warn "Inno Setup not found -- skipping installer build"
        Write-Warn "Download from: https://jrsoftware.org/isinfo.php"
    } else {
        Write-OK ("Inno Setup found: {0}" -f $IsccExe)

        & $IsccExe "$InstallerScript"
        if ($LASTEXITCODE -ne 0) {
            Write-Fail ("Inno Setup build failed (exit code: {0})" -f $LASTEXITCODE)
            exit 1
        }

        $installerOutput = Join-Path $ScriptDir "installer\Output\ENEREX-UPS-Monitor-Setup.exe"
        if (Test-Path $installerOutput) {
            $setupSize = [math]::Round((Get-Item $installerOutput).Length / 1MB, 1)
            Write-OK ("Installer built: ENEREX-UPS-Monitor-Setup.exe ({0} MB)" -f $setupSize)
        }
    }
}

# -- Done ---------------------------------------------------------------------
Write-Step "Build Complete"
Write-OK "Output files:"
Write-Host ("    .exe:      {0}" -f $ExeOutput) -ForegroundColor White
if (-not $SkipInstaller) {
    $installerPath = Join-Path $ScriptDir 'installer\Output\ENEREX-UPS-Monitor-Setup.exe'
    Write-Host ("    Installer: {0}" -f $installerPath) -ForegroundColor White
}
Write-Host ""
