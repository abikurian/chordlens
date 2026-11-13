$files = @(
    "desktop.py",
    "ChordLens.spec",
    "installer\ChordLens.iss",
    "dist\ChordLens\ChordLens.exe",
    "dist\installer\ChordLens-Setup-0.2.0.exe"
)
$files += (Get-ChildItem -Path "backend\*.py" | ForEach-Object { $_.FullName })
$files += (Get-ChildItem -Path "frontend\*" | ForEach-Object { $_.FullName })

$report = foreach ($f in $files) {
    if (Test-Path $f) {
        $item = Get-Item $f
        [PSCustomObject]@{
            Path = $item.FullName.Replace("d:\Project\chordlens\", "")
            LastWriteTime = $item.LastWriteTime
            Length = $item.Length
        }
    } else {
        [PSCustomObject]@{
            Path = $f
            LastWriteTime = $null
            Length = 0
        }
    }
}

$report | Sort-Object LastWriteTime -Descending | Format-Table -AutoSize -Property Path, LastWriteTime, Length

