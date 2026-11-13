$installerHash = (Get-FileHash "dist\installer\ChordLens-Setup-0.2.0.exe" -Algorithm SHA256).Hash.ToLower()
$portableHash  = (Get-FileHash "dist\portable\ChordLens-v0.2.0-windows-x64.zip" -Algorithm SHA256).Hash.ToLower()

$content = @"
# ChordLens v0.2.0 Release Checksums (SHA256)
$installerHash  ChordLens-Setup-0.2.0.exe
$portableHash  ChordLens-v0.2.0-windows-x64.zip
"@

$content | Set-Content -Path "checksums.txt" -Encoding UTF8
Write-Host "Generated checksums.txt:"
Get-Content "checksums.txt"
