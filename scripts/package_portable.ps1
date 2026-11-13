$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'

$src = "dist\ChordLens"
$dest = "dist\portable\ChordLens-v0.2.0-windows-x64.zip"

if (Test-Path $dest) {
    Remove-Item -Force $dest
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
Write-Host "Creating zip from $src to $dest..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory((Resolve-Path $src).Path, (Join-Path (Get-Location).Path $dest), [System.IO.Compression.CompressionLevel]::Optimal, $false)
Write-Host "Zip creation complete."

