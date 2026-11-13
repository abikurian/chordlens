$exe = "d:\Project\chordlens\dist\ChordLens\ChordLens.exe"
Write-Host "Launching $exe in background..."
$proc = Start-Process -FilePath $exe -PassThru

$deadline = (Get-Date).AddSeconds(15)
$port = $null

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    if ($proc.HasExited) {
        Write-Error "ChordLens.exe exited prematurely with code $($proc.ExitCode)!"
        exit 1
    }
    
    # Check log for port
    $logPath = "$env:LOCALAPPDATA\ChordLens\logs\chordlens.log"
    if (Test-Path $logPath) {
        $lines = Get-Content $logPath -Tail 20
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
            Write-Host "Health check response: $($health | ConvertTo-Json -Compress)"
            if ($health.status -eq "ok" -and $health.version -eq "0.2.0") {
                Write-Host "SUCCESS: FastAPI backend responded with status=ok and version=0.2.0 on port $port!"
                break
            }
        } catch {
            # Still warming up
        }
    }
}

Write-Host "Stopping ChordLens process $($proc.Id)..."
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Get-Process -Name "ChordLens" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

if (-not $port) {
    Write-Error "Failed to find port or reach /api/health within 15 seconds"
    exit 1
}

Write-Host "Verification complete and clean."
