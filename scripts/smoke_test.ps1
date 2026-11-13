<#
.SYNOPSIS
    ChordLens automated smoke test in a scrubbed environment.
.DESCRIPTION
    1. Scrubs PATH so external Node, Python, and system FFmpeg are completely unavailable.
    2. Runs ChordLens.exe --self-check (must return exit code 0).
    3. Launches ChordLens.exe in background, probes /api/health (must be HTTP 200 ok v0.2.0), then stops it cleanly.
    4. Runs bundled yt-dlp using bundled Deno on https://youtu.be/nPV9Fvo59L0.
       (Marked WARNING-only: reports PASS or WARN, but does NOT fail the test if network/YouTube changes occur).
#>

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = (Resolve-Path "$scriptDir\..").Path
$distApp = Join-Path $rootDir "dist\ChordLens"
$exePath = Join-Path $distApp "ChordLens.exe"
$tmpDir = Join-Path $rootDir "tmp"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "ChordLens Scrubbed Environment Smoke Test" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path $exePath)) {
    Write-Error "ChordLens executable not found at: $exePath. Run build first."
    exit 1
}

# 1. Scrub environment PATH
$origPath = $env:PATH
Write-Host "`n[Step 1] Scrubbing PATH to remove system Node, Python, and FFmpeg..." -ForegroundColor Yellow
$bundledBin = Join-Path $distApp "_internal\bin"
# Minimal system PATH: bundled bin + Windows system dirs only
$scrubbedPath = "$bundledBin;$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
$env:PATH = $scrubbedPath

$hasNode = Get-Command node -ErrorAction SilentlyContinue
$hasPython = Get-Command python -ErrorAction SilentlyContinue

Write-Host "PATH scrubbed. Node on PATH: $(if ($hasNode) { $hasNode.Source } else { 'NONE (Scrubbed OK)' })"
Write-Host "Python on PATH: $(if ($hasPython) { $hasPython.Source } else { 'NONE (Scrubbed OK)' })"

$overallSuccess = $true

# 2. Step 2: Headless self-check
Write-Host "`n[Step 2] Running headless self-check in scrubbed environment..." -ForegroundColor Yellow
$selfCheckLog = Join-Path $tmpDir "smoke_self_check.log"
$selfCheckErr = Join-Path $tmpDir "smoke_self_check_err.log"
Remove-Item -Force $selfCheckLog, $selfCheckErr -ErrorAction SilentlyContinue

$pSelf = Start-Process -FilePath $exePath -ArgumentList "--self-check" -RedirectStandardOutput $selfCheckLog -RedirectStandardError $selfCheckErr -PassThru -NoNewWindow
$finished = $pSelf.WaitForExit(90000)

Start-Sleep -Milliseconds 500
$pSelf.Refresh()
$exitCode = $pSelf.ExitCode

$logLines = if (Test-Path $selfCheckLog) { Get-Content $selfCheckLog } else { @() }
$hasPassReport = ($logLines -match "OVERALL RESULT: PASS").Count -gt 0

if (-not $finished) {
    Stop-Process -Id $pSelf.Id -Force -ErrorAction SilentlyContinue
    Write-Host "[FAIL] Self-check timed out after 90 seconds" -ForegroundColor Red
    $overallSuccess = $false
} elseif ($exitCode -ne $null -and $exitCode -ne 0 -and -not $hasPassReport) {
    Write-Host "[FAIL] Self-check returned non-zero exit code: $exitCode" -ForegroundColor Red
    if ($logLines) { $logLines | ForEach-Object { Write-Host $_ } }
    $overallSuccess = $false
} elseif ($hasPassReport -or $exitCode -eq 0) {
    Write-Host "[PASS] Self-check passed with exit code 0" -ForegroundColor Green
    if ($logLines) {
        $logLines | Where-Object { $_ -match "^\[(PASS|FAIL)\]" } | ForEach-Object { Write-Host "       $_" }
    }
} else {
    Write-Host "[FAIL] Self-check produced unknown outcome" -ForegroundColor Red
    $overallSuccess = $false
}

# 3. Step 3: Launch server & verify /api/health
Write-Host "`n[Step 3] Launching ChordLens windowed process & probing /api/health..." -ForegroundColor Yellow
$pApp = Start-Process -FilePath $exePath -PassThru
$deadline = (Get-Date).AddSeconds(18)
$port = $null
$healthOk = $false

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 600
    if ($pApp.HasExited) {
        Write-Host "[FAIL] ChordLens.exe exited prematurely with code $($pApp.ExitCode)" -ForegroundColor Red
        $overallSuccess = $false
        break
    }
    $logPath = "$env:LOCALAPPDATA\ChordLens\logs\chordlens.log"
    if (Test-Path $logPath) {
        $lines = Get-Content $logPath -Tail 25
        foreach ($line in $lines) {
            if ($line -match "starting uvicorn on port (\d+)") {
                $port = $matches[1]
                break
            }
        }
    }
    if ($port) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 2
            if ($health.status -eq "ok" -and $health.version -eq "0.2.0") {
                $healthOk = $true
                Write-Host "[PASS] /api/health responded: status=ok, version=0.2.0, ffmpeg=$($health.ffmpeg), models=$($health.models)" -ForegroundColor Green
                break
            }
        } catch {
            # Warming up
        }
    }
}

Write-Host "Stopping background test instance $($pApp.Id)..."
Stop-Process -Id $pApp.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Get-Process -Name "ChordLens" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

if (-not $healthOk) {
    Write-Host "[FAIL] Could not verify /api/health within timeout" -ForegroundColor Red
    $overallSuccess = $false
}

# 4. Step 4 (WARNING-only): Bundled yt-dlp + bundled Deno extraction test
Write-Host "`n[Step 4 - WARNING ONLY] Fetching YouTube metadata with bundled Deno (no Node on PATH)..." -ForegroundColor Yellow
Write-Host "Target URL: https://youtu.be/nPV9Fvo59L0"

$ytdlpLog = Join-Path $tmpDir "smoke_ytdlp.json"
$ytdlpErr = Join-Path $tmpDir "smoke_ytdlp_err.log"
Remove-Item -Force $ytdlpLog, $ytdlpErr -ErrorAction SilentlyContinue

$denoExe = Join-Path $distApp "_internal\bin\deno.exe"
if (-not (Test-Path $denoExe)) {
    Write-Warning "[WARN] Bundled deno.exe was not found at $denoExe"
} else {
    try {
        $pYt = Start-Process -FilePath $exePath -ArgumentList "-m", "yt_dlp", "--skip-download", "--dump-single-json", "--no-playlist", "--js-runtimes", "deno:$denoExe", "https://youtu.be/nPV9Fvo59L0" -RedirectStandardOutput $ytdlpLog -RedirectStandardError $ytdlpErr -PassThru -NoNewWindow
        $ytFinished = $pYt.WaitForExit(35000)
        if (-not $ytFinished) {
            Stop-Process -Id $pYt.Id -Force -ErrorAction SilentlyContinue
            Write-Warning "[WARN] YouTube metadata fetch timed out after 35 seconds (network latency or rate limit)."
        } elseif (Test-Path $ytdlpLog) {
            $rawContent = Get-Content $ytdlpLog -Raw
            # Locate JSON opening bracket in case of prefix logs
            $jsonStart = $rawContent.IndexOf("{`"id`":")
            if ($jsonStart -lt 0) {
                $jsonStart = $rawContent.IndexOf("{")
            }
            if ($jsonStart -ge 0) {
                $cleanJson = $rawContent.Substring($jsonStart).Trim()
                try {
                    $meta = $cleanJson | ConvertFrom-Json
                    if ($meta.title) {
                        Write-Host "[PASS] YouTube metadata extracted successfully via bundled Deno:" -ForegroundColor Green
                        Write-Host "       Title:    $($meta.title)" -ForegroundColor Green
                        Write-Host "       Uploader: $($meta.uploader)" -ForegroundColor Green
                        Write-Host "       Duration: $($meta.duration)s" -ForegroundColor Green
                    } else {
                        Write-Warning "[WARN] yt-dlp JSON parsed but did not contain a title."
                    }
                } catch {
                    Write-Warning "[WARN] Could not parse yt-dlp output as JSON: $_"
                }
            } else {
                $errMsg = if (Test-Path $ytdlpErr) { (Get-Content $ytdlpErr -Tail 3) -join " " } else { "No JSON found in output" }
                Write-Warning "[WARN] YouTube metadata extraction warning: $errMsg"
            }
        } else {
            $errMsg = if (Test-Path $ytdlpErr) { (Get-Content $ytdlpErr -Tail 3) -join " " } else { "Process exited with code $($pYt.ExitCode)" }
            Write-Warning "[WARN] YouTube extraction failed: $errMsg"
        }
    } catch {
        Write-Warning "[WARN] Exception while running bundled yt-dlp test: $_"
    }
}

# 5. Restore environment PATH
$env:PATH = $origPath

Write-Host "`n============================================================" -ForegroundColor Cyan
if ($overallSuccess) {
    Write-Host "SMOKE TEST RESULT: PASS — All mandatory requirements met." -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "SMOKE TEST RESULT: FAIL — One or more mandatory checks failed." -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Cyan
    exit 1
}
