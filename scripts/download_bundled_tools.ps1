$ErrorActionPreference = "Stop"

$binDir = "d:\Project\chordlens\bin"
$tmpDir = "d:\Project\chordlens\tmp"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

# 1. Download and extract Deno
$denoZip = Join-Path $tmpDir "deno.zip"
$denoUrl = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
Write-Host "Downloading Deno from $denoUrl..."
curl.exe -fL -o $denoZip $denoUrl
Write-Host "Extracting Deno to $binDir..."
Expand-Archive -Path $denoZip -DestinationPath $binDir -Force
Remove-Item -Force $denoZip -ErrorAction SilentlyContinue

# Verify Deno
$denoExe = Join-Path $binDir "deno.exe"
if (Test-Path $denoExe) {
    $denoVer = & $denoExe --version
    Write-Host "Deno installed successfully: $denoVer"
} else {
    Write-Error "deno.exe was not extracted!"
}

# 2. Download and extract BtbN LGPL FFmpeg
$ffmpegZip = Join-Path $tmpDir "ffmpeg-lgpl.zip"
$ffmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip"
Write-Host "Downloading LGPL FFmpeg from $ffmpegUrl..."
curl.exe -fL -o $ffmpegZip $ffmpegUrl
Write-Host "Extracting FFmpeg to temp folder..."
$extractTemp = Join-Path $tmpDir "ffmpeg-extract"
Remove-Item -Recurse -Force $extractTemp -ErrorAction SilentlyContinue
Expand-Archive -Path $ffmpegZip -DestinationPath $extractTemp -Force

# Locate ffmpeg.exe and ffprobe.exe inside the extracted archive
$foundFfmpeg = Get-ChildItem -Path $extractTemp -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
$foundFfprobe = Get-ChildItem -Path $extractTemp -Recurse -Filter "ffprobe.exe" | Select-Object -First 1

if (-not $foundFfmpeg -or -not $foundFfprobe) {
    Write-Error "Could not find ffmpeg.exe or ffprobe.exe in extracted archive!"
}

Copy-Item -Path $foundFfmpeg.FullName -Destination (Join-Path $binDir "ffmpeg.exe") -Force
Copy-Item -Path $foundFfprobe.FullName -Destination (Join-Path $binDir "ffprobe.exe") -Force

Remove-Item -Recurse -Force $extractTemp -ErrorAction SilentlyContinue
Remove-Item -Force $ffmpegZip -ErrorAction SilentlyContinue

# 3. Verify LGPL license for FFmpeg
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$verOut = & $ffmpegExe -version
Write-Host "FFmpeg version output:"
$verOut | Select-Object -First 5 | ForEach-Object { Write-Host $_ }

$cfg = ($verOut | Select-String "configuration:").Line
Write-Host "FFmpeg configuration line: $cfg"

if ($cfg -match "--enable-gpl") {
    Write-Error "VERIFICATION FAILED: ffmpeg has --enable-gpl!"
}
if ($cfg -match "--enable-nonfree") {
    Write-Error "VERIFICATION FAILED: ffmpeg has --enable-nonfree!"
}

Write-Host "SUCCESS: Both Deno (MIT) and FFmpeg/FFprobe (LGPL verified) are in $binDir!"
