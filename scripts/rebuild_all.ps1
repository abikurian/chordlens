$ErrorActionPreference = "Continue"
$ROOT = (Resolve-Path ".").Path
Set-Location $ROOT

Write-Host "=== Rebuilding ChordLens Desktop App & Installer ==="

# Frontend JavaScript syntax check
Write-Host "[Step 0/2] Checking frontend JavaScript syntax..."
$jsFiles = Get-ChildItem -Path "$ROOT\frontend" -Filter *.js
$syntaxFailed = $false
foreach ($js in $jsFiles) {
    & node --check $js.FullName
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Syntax check FAILED for: $($js.Name)"
        $syntaxFailed = $true
    } else {
        Write-Host "  [PASS] $($js.Name)"
    }
}
if ($syntaxFailed) {
    Write-Error "Frontend JavaScript syntax check failed. Aborting build."
    exit 1
}

Write-Host "[Step 1/2] Running PyInstaller on ChordLens.spec..."

& "$ROOT\.venv\Scripts\pyinstaller.exe" --noconfirm "$ROOT\ChordLens.spec"
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$exePath = "$ROOT\dist\ChordLens\ChordLens.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "PyInstaller failed: $exePath not found."
    exit 1
}
$distSize = (Get-ChildItem -Path "$ROOT\dist\ChordLens" -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host "[Step 1/2] PyInstaller complete! Dist folder size: $([math]::Round($distSize / 1MB, 2)) MB"

Write-Host "[Step 2/2] Running Inno Setup compiler on ChordLens.iss..."
$iscc = "$env:LOCALAPPDATA\Programs\Antigravity IDE\resources\app\node_modules\innosetup\bin\ISCC.exe"
if (-not (Test-Path $iscc)) {
    $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
}
if (-not $iscc -or -not (Test-Path $iscc)) {
    Write-Error "ISCC compiler not found."
    exit 1
}

& $iscc "$ROOT\installer\ChordLens.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$version = (Get-Content "$ROOT\VERSION" -Raw).Trim()
$installerPath = "$ROOT\dist\installer\ChordLens-Setup-$version.exe"
if (-not (Test-Path $installerPath)) {
    Write-Error "Inno Setup compilation failed: $installerPath not found."
    exit 1
}

$installerItem = Get-Item $installerPath
Write-Host "[Step 2/2] Inno Setup compiler complete!"
Write-Host "FINAL_INSTALLER_PATH: $($installerItem.FullName)"
Write-Host "FINAL_INSTALLER_SIZE_BYTES: $($installerItem.Length)"
Write-Host "FINAL_INSTALLER_SIZE_MB: $([math]::Round($installerItem.Length / 1MB, 2)) MB"
Write-Host "ALL BUILDS FINISHED SUCCESSFULLY"
