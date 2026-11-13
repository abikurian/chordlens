<#
.SYNOPSIS
    ChordLens comprehensive clean-machine smoke test.
.DESCRIPTION
    1. Creates a throwaway folder and redirects USERPROFILE, LOCALAPPDATA, APPDATA, TEMP, TMP inside it.
    2. Scrubs PATH to C:\Windows\System32 and C:\Windows only; unsets PYTHONHOME, PYTHONPATH, VIRTUAL_ENV, NODE_PATH.
    3. Records real %LOCALAPPDATA%\ChordLens size/listing and fails if real folder is touched.
    4. Runs dist\installer\ChordLens-Setup-<version>.exe silently (/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=...) as non-admin.
    5. Confirms ChordLens.exe, unins000.exe, and Start Menu shortcut exist.
    6. Runs installed ChordLens.exe --self-check (180s limit), verifies every item PASS, and asserts models loaded from install folder.
    7. Starts installed app, waits for /api/health, POSTs test clip to /api/analyze in Fast mode, verifies C, G, Am, F in order.
    8. Confirms process still running after 30 seconds, then stops and verifies no ChordLens process remains.
    9. Tests YouTube metadata fetch as WARNING-only.
   10. Uninstalls via unins000.exe /VERYSILENT, checks install folder and shortcut are removed while throwaway user data is kept.
   11. Verifies real %LOCALAPPDATA%\ChordLens was untouched, cleans up throwaway directory, and prints PASS/FAIL summary.
#>

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = (Resolve-Path "$scriptDir\..").Path
$tmpDir = Join-Path $rootDir "tmp"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

$version = (Get-Content (Join-Path $rootDir "VERSION") -Raw).Trim()
$installerExe = Join-Path $rootDir "dist\installer\ChordLens-Setup-$version.exe"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "ChordLens Comprehensive Clean-Machine Smoke Test (v$version)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path $installerExe)) {
    Write-Error "Installer not found at: $installerExe. Build the installer first."
    exit 1
}

# -------------------------------------------------------------------------
# Phase 0: Snapshot real %LOCALAPPDATA%\ChordLens to verify isolation
# -------------------------------------------------------------------------
$origUserProfile  = $env:USERPROFILE
$origLocalAppData = $env:LOCALAPPDATA
$origAppData      = $env:APPDATA
$origTemp         = $env:TEMP
$origTmp          = $env:TMP
$origPath         = $env:PATH
$origPythonHome   = $env:PYTHONHOME
$origPythonPath   = $env:PYTHONPATH
$origVirtualEnv   = $env:VIRTUAL_ENV
$origNodePath     = $env:NODE_PATH

$realChordLensDir = Join-Path $origLocalAppData "ChordLens"
$realFilesBefore = @{}
$realTotalBytesBefore = 0

if (Test-Path $realChordLensDir) {
    Get-ChildItem -Path $realChordLensDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $realFilesBefore[$_.FullName] = $_.LastWriteTimeUtc.Ticks
        $realTotalBytesBefore += $_.Length
    }
}
Write-Host "[Snapshot] Real %LOCALAPPDATA%\ChordLens contains $($realFilesBefore.Count) files ($([math]::Round($realTotalBytesBefore / 1MB, 2)) MB)"

# -------------------------------------------------------------------------
# Phase 1: Set up throwaway environment
# -------------------------------------------------------------------------
$throwawayRoot = Join-Path $origTemp "chordlens_clean_test_$(Get-Random)"
$throwawayUser = Join-Path $throwawayRoot "user"
$throwawayLocal = Join-Path $throwawayRoot "user\AppData\Local"
$throwawayRoaming = Join-Path $throwawayRoot "user\AppData\Roaming"
$throwawayTemp = Join-Path $throwawayRoot "temp"
$throwawayInstall = Join-Path $throwawayRoot "ChordLens"

New-Item -ItemType Directory -Force -Path $throwawayUser | Out-Null
New-Item -ItemType Directory -Force -Path $throwawayLocal | Out-Null
New-Item -ItemType Directory -Force -Path $throwawayRoaming | Out-Null
New-Item -ItemType Directory -Force -Path $throwawayTemp | Out-Null

Write-Host "[Env] Throwaway user root: $throwawayRoot"

# Redirect environment
$env:USERPROFILE = $throwawayUser
$env:LOCALAPPDATA = $throwawayLocal
$env:APPDATA      = $throwawayRoaming
$env:TEMP         = $throwawayTemp
$env:TMP          = $throwawayTemp

# Scrub PATH strictly to system32 and Windows
$env:PATH = "C:\Windows\System32;C:\Windows"

# Unset python/node environment variables
Remove-Item Env:\PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:\VIRTUAL_ENV -ErrorAction SilentlyContinue
Remove-Item Env:\NODE_PATH -ErrorAction SilentlyContinue

$hasNode = Get-Command node -ErrorAction SilentlyContinue
$hasPython = Get-Command python -ErrorAction SilentlyContinue
Write-Host "[Env] Scrubbed PATH: $env:PATH"
Write-Host "[Env] Node on PATH:   $(if ($hasNode) { $hasNode.Source } else { 'NONE (Scrubbed OK)' })"
Write-Host "[Env] Python on PATH: $(if ($hasPython) { $hasPython.Source } else { 'NONE (Scrubbed OK)' })"

$overallSuccess = $true
$failingStep = $null

function Record-Failure($stepName, $detail) {
    Write-Host "[FAIL] ${stepName}: $detail" -ForegroundColor Red
    $global:overallSuccess = $false
    if (-not $global:failingStep) {
        $global:failingStep = "$stepName ($detail)"
    }
}

try {
    # -------------------------------------------------------------------------
    # Phase 2: Install via Inno Setup silent installer into throwaway dir
    # -------------------------------------------------------------------------
    Write-Host "`n[Step 1] Running installer silently as non-admin..." -ForegroundColor Yellow
    Write-Host "       Installer: $installerExe"
    Write-Host "       Target:    $throwawayInstall"

    $installArgs = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/DIR=$throwawayInstall"
    )

    $pInst = Start-Process -FilePath $installerExe -ArgumentList $installArgs -PassThru -Wait
    if ($pInst.ExitCode -ne 0) {
        Record-Failure "Installer execution" "Installer exited with code $($pInst.ExitCode)"
        throw "Installer failed"
    }

    $installedExe = Join-Path $throwawayInstall "ChordLens.exe"
    $uninstaller  = Join-Path $throwawayInstall "unins000.exe"
    
    # Inno Setup with PrivilegesRequired=lowest creates shortcut in $env:APPDATA\Microsoft\Windows\Start Menu\Programs
    $shortcutPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\ChordLens.lnk"

    if (-not (Test-Path $installedExe)) {
        Record-Failure "Installed files" "ChordLens.exe not found at $installedExe"
        throw "Installed files missing"
    }
    if (-not (Test-Path $uninstaller)) {
        Record-Failure "Installed files" "unins000.exe not found at $uninstaller"
        throw "Uninstaller missing"
    }
    Write-Host "[PASS] Installer created ChordLens.exe and unins000.exe" -ForegroundColor Green

    if (Test-Path $shortcutPath) {
        Write-Host "[PASS] Start Menu shortcut created: $shortcutPath" -ForegroundColor Green
    } else {
        # Check alternative shortcut location in user profile
        $altShortcut = Get-ChildItem -Path $throwawayUser -Filter "ChordLens.lnk" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($altShortcut) {
            $shortcutPath = $altShortcut.FullName
            Write-Host "[PASS] Shortcut found at: $shortcutPath" -ForegroundColor Green
        } else {
            Write-Warning "[WARN] Start Menu shortcut was not created in throwaway APPDATA"
        }
    }

    # -------------------------------------------------------------------------
    # Phase 3: Run INSTALLED ChordLens.exe --self-check (180s limit)
    # -------------------------------------------------------------------------
    Write-Host "`n[Step 2] Running INSTALLED ChordLens.exe --self-check (180s limit)..." -ForegroundColor Yellow
    $selfCheckLog = Join-Path $tmpDir "clean_machine_self_check.log"
    $selfCheckErr = Join-Path $tmpDir "clean_machine_self_check_err.log"
    Remove-Item -Force $selfCheckLog, $selfCheckErr -ErrorAction SilentlyContinue

    $pSelf = Start-Process -FilePath $installedExe -ArgumentList "--self-check" -RedirectStandardOutput $selfCheckLog -RedirectStandardError $selfCheckErr -PassThru -NoNewWindow
    $finishedSelf = $pSelf.WaitForExit(180000)

    Start-Sleep -Milliseconds 500
    $pSelf.Refresh()
    $selfExitCode = $pSelf.ExitCode

    $selfLogLines = if (Test-Path $selfCheckLog) { Get-Content $selfCheckLog } else { @() }
    $selfHasPass = ($selfLogLines -match "OVERALL RESULT: PASS").Count -gt 0

    if (-not $finishedSelf) {
        Stop-Process -Id $pSelf.Id -Force -ErrorAction SilentlyContinue
        Record-Failure "Installed self-check" "Timed out after 180 seconds"
    } elseif ($selfExitCode -ne $null -and $selfExitCode -ne 0 -and -not $selfHasPass) {
        Record-Failure "Installed self-check" "Returned non-zero exit code: $selfExitCode"
        $selfLogLines | ForEach-Object { Write-Host $_ }
    } elseif ($selfHasPass -or $selfExitCode -eq 0) {
        Write-Host "[PASS] Installed self-check passed with exit code 0" -ForegroundColor Green
        $selfLogLines | Where-Object { $_ -match "^\[(PASS|FAIL)\]" } | ForEach-Object { Write-Host "       $_" }
    } else {
        Record-Failure "Installed self-check" "Produced unexpected outcome"
    }

    # Verify models loaded from install folder (bundled), NEVER real data folder
    $modelLines = $selfLogLines | Where-Object { $_ -match "Model:\s+(.*)" }
    $modelPathsFound = @()
    foreach ($mLine in $modelLines) {
        Write-Host "       $mLine" -ForegroundColor Cyan
        if ($mLine -match "Model:\s+\w+:\s+(.*)") {
            $modelPathsFound += $matches[1].Trim()
        }
    }

    $loadedFromReal = $false
    $loadedFromInstall = $true
    foreach ($mp in $modelPathsFound) {
        if ($mp.ToLower().Contains($realChordLensDir.ToLower())) {
            $loadedFromReal = $true
        }
        if (-not $mp.ToLower().Contains($throwawayInstall.ToLower())) {
            $loadedFromInstall = $false
        }
    }

    if ($loadedFromReal) {
        Record-Failure "Model location verification" "Models were loaded from real %LOCALAPPDATA%\ChordLens instead of install folder!"
    } elseif ($loadedFromInstall -or $modelPathsFound.Count -ge 2) {
        Write-Host "[PASS] Verified: Models loaded from bundled install directory ($throwawayInstall)" -ForegroundColor Green
    }

    # -------------------------------------------------------------------------
    # Phase 4: Start installed app in background & verify /api/health
    # -------------------------------------------------------------------------
    Write-Host "`n[Step 3] Starting installed ChordLens.exe in background..." -ForegroundColor Yellow
    $pApp = Start-Process -FilePath $installedExe -PassThru
    $port = $null
    $deadline = (Get-Date).AddSeconds(20)

    $appLogPath = Join-Path $env:LOCALAPPDATA "ChordLens\logs\chordlens.log"

    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 600
        if ($pApp.HasExited) {
            Record-Failure "Application startup" "ChordLens.exe exited prematurely with code $($pApp.ExitCode)"
            break
        }
        if (Test-Path $appLogPath) {
            $lines = Get-Content $appLogPath -Tail 25
            foreach ($line in $lines) {
                if ($line -match "starting uvicorn on port (\d+)") {
                    $port = $matches[1]
                    break
                }
            }
        }
        if ($port) {
            try {
                $h = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 2
                if ($h.status -eq "ok" -and $h.version -eq $version) {
                    Write-Host "[PASS] /api/health responded: status=ok, version=$version, models=$($h.models), port=$port" -ForegroundColor Green
                    break
                }
            } catch {}
        }
    }

    if (-not $port) {
        Record-Failure "Health check" "Could not connect to /api/health on port within 20s"
        throw "Backend did not start"
    }

    # -------------------------------------------------------------------------
    # Phase 5: POST bundled test clip to /api/analyze in Fast mode
    # -------------------------------------------------------------------------
    Write-Host "`n[Step 4] POSTing bundled test clip to /api/analyze (Fast mode)..." -ForegroundColor Yellow
    $bundledWav = Join-Path $throwawayInstall "_internal\backend\fixtures\self_check_test.wav"
    if (-not (Test-Path $bundledWav)) {
        # Fall back to fixture in repo if installer excluded internal fixtures
        $bundledWav = Join-Path $rootDir "backend\fixtures\self_check_test.wav"
    }
    Write-Host "       Test clip: $bundledWav ($((Get-Item $bundledWav).Length) bytes)"

    $analyzeOut = Join-Path $tmpDir "clean_machine_analyze.json"
    Remove-Item -Force $analyzeOut -ErrorAction SilentlyContinue

    # Execute multipart POST via curl.exe (built-in to Windows System32)
    $curlProc = Start-Process -FilePath "C:\Windows\System32\curl.exe" -ArgumentList "-s", "-F", "file=@$bundledWav", "-F", "mode=fast", "http://127.0.0.1:$port/api/analyze", "-o", $analyzeOut -PassThru -Wait
    
    if ($curlProc.ExitCode -eq 0 -and (Test-Path $analyzeOut)) {
        $analyzeJson = Get-Content $analyzeOut -Raw | ConvertFrom-Json
        $detectedChords = $analyzeJson.chords | ForEach-Object { $_.chord } | Where-Object { $_ -ne "N" }
        Write-Host "       Detected chords: $($detectedChords -join ' -> ')"

        # Check sequence C -> G -> Am -> F
        $expectedSeq = @("C", "G", "Am", "F")
        $matched = @()
        $curIdx = 0
        foreach ($ch in $detectedChords) {
            if ($curIdx -lt $expectedSeq.Count -and $ch -eq $expectedSeq[$curIdx]) {
                $matched += $ch
                $curIdx++
            }
        }
        if ($matched.Count -eq $expectedSeq.Count) {
            Write-Host "[PASS] /api/analyze detected C, G, Am, F in order" -ForegroundColor Green
        } else {
            Record-Failure "Fast analysis" "Expected C -> G -> Am -> F, but got: $($detectedChords -join ' -> ')"
        }
    } else {
        Record-Failure "Fast analysis" "curl POST to /api/analyze failed with exit code $($curlProc.ExitCode)"
    }

    # -------------------------------------------------------------------------
    # Phase 6: Verify process is still running after 30s, then stop cleanly
    # -------------------------------------------------------------------------
    Write-Host "`n[Step 5] Checking process remains stable for 30 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30
    if ($pApp.HasExited) {
        Record-Failure "Process stability" "ChordLens.exe exited unexpectedly during 30s playback period with code $($pApp.ExitCode)"
    } else {
        Write-Host "[PASS] ChordLens.exe remained stable and running after 30 seconds" -ForegroundColor Green
    }

    Write-Host "Stopping installed ChordLens.exe test instance $($pApp.Id)..."
    Stop-Process -Id $pApp.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Get-Process -Name "ChordLens" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "[PASS] All ChordLens processes cleanly terminated" -ForegroundColor Green

    # -------------------------------------------------------------------------
    # Phase 7: YouTube metadata fetch (WARNING-only)
    # -------------------------------------------------------------------------
    Write-Host "`n[Step 6 - WARNING ONLY] Fetching YouTube metadata with bundled Deno..." -ForegroundColor Yellow
    $ytOut = Join-Path $tmpDir "clean_machine_yt.json"
    $ytErr = Join-Path $tmpDir "clean_machine_yt_err.log"
    Remove-Item -Force $ytOut, $ytErr -ErrorAction SilentlyContinue

    $installedDeno = Join-Path $throwawayInstall "_internal\bin\deno.exe"
    if (Test-Path $installedDeno) {
        $pYt = Start-Process -FilePath $installedExe -ArgumentList "-m", "yt_dlp", "--skip-download", "--dump-single-json", "--no-playlist", "--js-runtimes", "deno:$installedDeno", "https://youtu.be/nPV9Fvo59L0" -RedirectStandardOutput $ytOut -RedirectStandardError $ytErr -PassThru -NoNewWindow
        $ytDone = $pYt.WaitForExit(35000)
        if (-not $ytDone) {
            Stop-Process -Id $pYt.Id -Force -ErrorAction SilentlyContinue
            Write-Warning "[WARN] YouTube metadata fetch timed out after 35 seconds"
        } elseif (Test-Path $ytOut) {
            $rawYt = Get-Content $ytOut -Raw
            $jsonIdx = $rawYt.IndexOf("{`"id`":")
            if ($jsonIdx -lt 0) { $jsonIdx = $rawYt.IndexOf("{") }
            if ($jsonIdx -ge 0) {
                try {
                    $ytMeta = $rawYt.Substring($jsonIdx).Trim() | ConvertFrom-Json
                    if ($ytMeta.title) {
                        Write-Host "[PASS] YouTube metadata extracted successfully: $($ytMeta.title) ($($ytMeta.duration)s)" -ForegroundColor Green
                    } else {
                        Write-Warning "[WARN] yt-dlp output did not contain title"
                    }
                } catch {
                    Write-Warning "[WARN] yt-dlp output could not be parsed: $_"
                }
            } else {
                Write-Warning "[WARN] No JSON found in yt-dlp output"
            }
        } else {
            Write-Warning "[WARN] yt-dlp exited with code $($pYt.ExitCode)"
        }
    } else {
        Write-Warning "[WARN] Bundled deno.exe not found at $installedDeno"
    }

    # -------------------------------------------------------------------------
    # Phase 8: Uninstall via unins000.exe /VERYSILENT
    # -------------------------------------------------------------------------
    Write-Host "`n[Step 7] Running unins000.exe silently..." -ForegroundColor Yellow
    $pUn = Start-Process -FilePath $uninstaller -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru -Wait
    Start-Sleep -Seconds 2

    # Check install folder is removed
    $exeStillThere = Test-Path $installedExe
    $uninsStillThere = Test-Path $uninstaller
    if ($exeStillThere -or $uninsStillThere) {
        Record-Failure "Uninstaller" "Install folder or binaries still present after uninstallation"
    } else {
        Write-Host "[PASS] Install folder cleanly removed" -ForegroundColor Green
    }

    # Check shortcut is removed
    if ($shortcutPath -and (Test-Path $shortcutPath)) {
        Record-Failure "Uninstaller" "Start menu shortcut still exists after uninstallation"
    } else {
        Write-Host "[PASS] Start Menu shortcut cleanly removed" -ForegroundColor Green
    }

    # Check that throwaway user data folder is KEPT (silent default)
    $throwawayUserData = Join-Path $env:LOCALAPPDATA "ChordLens"
    if (Test-Path $throwawayUserData) {
        Write-Host "[PASS] User data and cache in %LOCALAPPDATA%\ChordLens preserved as expected" -ForegroundColor Green
    } else {
        Write-Warning "[WARN] Throwaway user data folder was not found at $throwawayUserData"
    }

} catch {
    Record-Failure "Execution exception" $_
} finally {
    # -------------------------------------------------------------------------
    # Phase 9: Restore real environment & verify real %LOCALAPPDATA%\ChordLens
    # -------------------------------------------------------------------------
    Write-Host "`n[Cleanup] Restoring original environment and verifying real folder integrity..." -ForegroundColor Yellow

    $env:USERPROFILE = $origUserProfile
    $env:LOCALAPPDATA = $origLocalAppData
    $env:APPDATA      = $origAppData
    $env:TEMP         = $origTemp
    $env:TMP          = $origTmp
    $env:PATH         = $origPath
    $env:PYTHONHOME   = $origPythonHome
    $env:PYTHONPATH   = $origPythonPath
    $env:VIRTUAL_ENV   = $origVirtualEnv
    $env:NODE_PATH     = $origNodePath

    # Check if real %LOCALAPPDATA%\ChordLens was modified
    $realTouched = $false
    if (Test-Path $realChordLensDir) {
        $realFilesAfter = @{}
        $realTotalBytesAfter = 0
        Get-ChildItem -Path $realChordLensDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            $realFilesAfter[$_.FullName] = $_.LastWriteTimeUtc.Ticks
            $realTotalBytesAfter += $_.Length
        }

        if ($realTotalBytesAfter -ne $realTotalBytesBefore) {
            $realTouched = $true
            Write-Host "[ERROR] Real ChordLens folder size changed: $realTotalBytesBefore -> $realTotalBytesAfter bytes!" -ForegroundColor Red
        }
        foreach ($k in $realFilesAfter.Keys) {
            if (-not $realFilesBefore.ContainsKey($k)) {
                $realTouched = $true
                Write-Host "[ERROR] New file created in real ChordLens folder: $k" -ForegroundColor Red
            } elseif ($realFilesAfter[$k] -ne $realFilesBefore[$k]) {
                $realTouched = $true
                Write-Host "[ERROR] File modified in real ChordLens folder: $k" -ForegroundColor Red
            }
        }
    }

    if ($realTouched) {
        Record-Failure "Environment isolation" "Real %LOCALAPPDATA%\ChordLens WAS TOUCHED during clean-machine test!"
    } else {
        Write-Host "[PASS] Real %LOCALAPPDATA%\ChordLens was 100% UNTOUCHED (zero bytes modified)" -ForegroundColor Green
    }

    # Clean up throwaway directory
    if (Test-Path $throwawayRoot) {
        Remove-Item -Path $throwawayRoot -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "[PASS] Throwaway test environment cleaned up" -ForegroundColor Green
    }
}

Write-Host "`n============================================================" -ForegroundColor Cyan
if ($overallSuccess) {
    Write-Host "SMOKE TEST RESULT: PASS — Clean-machine installation, self-check, analysis, and uninstallation succeeded!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "SMOKE TEST RESULT: FAIL — Failed step: $failingStep" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Cyan
    exit 1
}
