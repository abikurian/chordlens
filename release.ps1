# Release script for ChordLens
param(
    [string]$Bump = "" # "patch", "minor", "major", or explicit version like "0.2.0"
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ROOT

Write-Host "=== ChordLens Release Pipeline ===" -ForegroundColor Cyan

$currentVersion = (Get-Content "$ROOT\VERSION" -Raw).Trim()

if ($Bump) {
    if ($Bump -match '^\d+\.\d+\.\d+$') {
        $newVersion = $Bump
    } else {
        $parts = $currentVersion.Split('.')
        [int]$major = $parts[0]
        [int]$minor = $parts[1]
        [int]$patch = $parts[2]

        switch ($Bump.ToLower()) {
            "patch" { $patch += 1 }
            "minor" { $minor += 1; $patch = 0 }
            "major" { $major += 1; $minor = 0; $patch = 0 }
            default { throw "Unknown bump type '$Bump'. Use 'patch', 'minor', 'major', or 'X.Y.Z'." }
        }
        $newVersion = "$major.$minor.$patch"
    }

    Write-Host "Bumping version from $currentVersion -> $newVersion" -ForegroundColor Yellow
    Set-Content -Path "$ROOT\VERSION" -Value $newVersion -NoNewline
    $currentVersion = $newVersion
}

Write-Host "Releasing version $currentVersion" -ForegroundColor Green

# 1. Run build pipeline
& "$ROOT\build.ps1"

# 2. Checksum generation
$installerPath = "$ROOT\dist\installer\ChordLens-Setup-$currentVersion.exe"
$zipPath = "$ROOT\dist\portable\ChordLens-v$currentVersion-windows-x64.zip"
$checksumPath = "$ROOT\dist\checksums.txt"

if (-not (Test-Path $installerPath)) {
    throw "Installer missing: $installerPath"
}
if (-not (Test-Path $zipPath)) {
    throw "Portable zip missing: $zipPath"
}

$hashInstaller = (Get-FileHash -Path $installerPath -Algorithm SHA256).Hash.ToLower()
$hashZip = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToLower()

@(
    "$hashInstaller  ChordLens-Setup-$currentVersion.exe",
    "$hashZip  ChordLens-v$currentVersion-windows-x64.zip"
) | Set-Content -Path $checksumPath -Encoding utf8

Write-Host "`nGenerated SHA256 checksums:" -ForegroundColor Cyan
Get-Content $checksumPath

# 3. GitHub release via gh CLI if present
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if ($gh) {
    Write-Host "`nCreating draft GitHub release v$currentVersion via gh CLI..." -ForegroundColor Cyan
    & $gh release create "v$currentVersion" `
        "$installerPath" `
        "$zipPath" `
        "$checksumPath" `
        --title "ChordLens v$currentVersion" `
        --notes-file "$ROOT\CHANGELOG.md" `
        --draft
    Write-Host "Draft release created." -ForegroundColor Green
} else {
    Write-Host "`n[Notice] gh CLI is not installed or not in PATH." -ForegroundColor Yellow
    Write-Host "To create the draft release manually:" -ForegroundColor Yellow
    Write-Host "  1. Open https://github.com/abikurian/chordlens/releases/new"
    Write-Host "  2. Tag version: v$currentVersion"
    Write-Host "  3. Release title: ChordLens v$currentVersion"
    Write-Host "  4. Paste notes from CHANGELOG.md"
    Write-Host "  5. Attach files from dist\:"
    Write-Host "     - $installerPath"
    Write-Host "     - $zipPath"
    Write-Host "     - $checksumPath"
    Write-Host "  6. Check 'Save draft' (do not publish until verified)"
}

Write-Host "`n=== Release Pipeline Complete ===" -ForegroundColor Cyan
