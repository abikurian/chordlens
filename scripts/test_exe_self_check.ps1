$logOut = "d:\Project\chordlens\tmp\exe_self_check.log"
$logErr = "d:\Project\chordlens\tmp\exe_self_check_err.log"
Remove-Item -Force $logOut, $logErr -ErrorAction SilentlyContinue

$exe = "d:\Project\chordlens\dist\ChordLens\ChordLens.exe"
Write-Host "Starting $exe --self-check..."
$proc = Start-Process -FilePath $exe -ArgumentList "--self-check" -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru -NoNewWindow

$exited = $proc.WaitForExit(90000)
if (-not $exited) {
    Write-Warning "Timed out after 90 seconds. Stopping process $($proc.Id)..."
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    exit 1
} else {
    Write-Host "Process finished with exit code: $($proc.ExitCode)"
    exit $proc.ExitCode
}

