# Build script for ChordLens Windows Desktop App and Installer
param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ROOT

Write-Host "=== ChordLens Build Pipeline ===" -ForegroundColor Cyan

# 1. Version and Windows version info
$version = (Get-Content "$ROOT\VERSION" -Raw).Trim()
Write-Host "Building ChordLens version $version" -ForegroundColor Green

# 1b. Frontend JavaScript syntax check
Write-Host "`n--- Checking frontend JavaScript syntax ---" -ForegroundColor Cyan
$jsFiles = Get-ChildItem -Path "$ROOT\frontend" -Filter *.js
$syntaxFailed = $false
foreach ($js in $jsFiles) {
    & node --check $js.FullName
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Syntax check FAILED for: $($js.Name)"
        $syntaxFailed = $true
    } else {
        Write-Host "  [PASS] $($js.Name)" -ForegroundColor Green
    }
}
if ($syntaxFailed) {
    throw "Frontend JavaScript syntax check failed. Aborting build."
}

& "$ROOT\.venv\Scripts\python.exe" "$ROOT\scripts\make_version_info.py"

# 2. PyInstaller --onedir build
Write-Host "`n--- Running PyInstaller ---" -ForegroundColor Cyan
& "$ROOT\.venv\Scripts\pyinstaller.exe" --noconfirm "$ROOT\ChordLens.spec"

$distAppDir = "$ROOT\dist\ChordLens"
if (-not (Test-Path "$distAppDir\ChordLens.exe")) {
    throw "PyInstaller build failed: $distAppDir\ChordLens.exe not found."
}

# Measure dist size
$distSize = (Get-ChildItem -Path $distAppDir -Recurse | Measure-Object -Property Length -Sum).Sum
$distSizeMB = [math]::Round($distSize / 1MB, 2)
Write-Host "Portable folder built: $distAppDir ($distSizeMB MB)" -ForegroundColor Green

# 3. Create portable ZIP
Write-Host "`n--- Creating Portable ZIP ---" -ForegroundColor Cyan
$zipDir = "$ROOT\dist\portable"
New-Item -ItemType Directory -Force -Path $zipDir | Out-Null
$zipPath = "$zipDir\ChordLens-v$version-windows-x64.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path "$distAppDir\*" -DestinationPath $zipPath -CompressionLevel Optimal
$zipSizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "Portable zip created: $zipPath ($zipSizeMB MB)" -ForegroundColor Green

# 4. Inno Setup Compiler
if (-not $SkipInstaller) {
    Write-Host "`n--- Compiling Inno Setup Installer ---" -ForegroundColor Cyan
    $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $candidatePaths = @(
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Antigravity IDE\resources\app\node_modules\innosetup\bin\ISCC.exe",
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe"
        )
        foreach ($cand in $candidatePaths) {
            if (Test-Path $cand) {
                $iscc = $cand
                break
            }
        }
    }

    if (-not $iscc) {
        Write-Warning "Inno Setup (ISCC.exe) not found. To build installer, run:"
        Write-Warning "  winget install JRSoftware.InnoSetup"
    } else {
        Write-Host "Using Inno Setup compiler: $iscc" -ForegroundColor DarkCyan
        $issPath = "$ROOT\installer\ChordLens.iss"
        & $iscc $issPath
        $installerPath = "$ROOT\dist\installer\ChordLens-Setup-$version.exe"
        if (Test-Path $installerPath) {
            $installerSizeMB = [math]::Round((Get-Item $installerPath).Length / 1MB, 2)
            Write-Host "Installer created: $installerPath ($installerSizeMB MB)" -ForegroundColor Green
        }
    }
}

Write-Host "`n=== Build Complete ===" -ForegroundColor Cyan

