param(
    [string]$Workspace = "C:\websites\mt5 2",
    [string]$StartUtc = "2026-06-23T00:00:00Z",
    [string]$EndUtc = "2026-07-31T00:00:00Z",
    [int]$SegmentHours = 12
)

$ErrorActionPreference = "Stop"
$outputDirectory = Join-Path $Workspace "artifacts\ticks\segments"
$progressPath = Join-Path $Workspace "artifacts\ticks\download-progress.log"
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$current = [DateTimeOffset]::Parse($StartUtc).ToUniversalTime()
$end = [DateTimeOffset]::Parse($EndUtc).ToUniversalTime()

"START $($current.ToString('o')) -> $($end.ToString('o'))" |
    Set-Content -LiteralPath $progressPath -Encoding utf8

while ($current -lt $end) {
    $next = $current.AddHours($SegmentHours)
    if ($next -gt $end) {
        $next = $end
    }

    $filename = "XAUUSD_{0}_{1}.csv.gz" -f `
        $current.ToString("yyyyMMdd_HHmm"), `
        $next.ToString("yyyyMMdd_HHmm")
    $outputPath = Join-Path $outputDirectory $filename
    $coveragePath = [System.IO.Path]::ChangeExtension($outputPath, ".csv.coverage.json")

    if ((Test-Path -LiteralPath $outputPath) -and (Test-Path -LiteralPath $coveragePath)) {
        "SKIP $filename" | Add-Content -LiteralPath $progressPath -Encoding utf8
        $current = $next
        continue
    }

    "BEGIN $filename" | Add-Content -LiteralPath $progressPath -Encoding utf8
    Push-Location $Workspace
    try {
        & python -m straddle_replica download-ticks `
            --terminal "C:\Program Files\MetaTrader 5\terminal64.exe" `
            --symbol XAUUSD `
            --start $current.ToString("o") `
            --end $next.ToString("o") `
            --output $outputPath `
            --chunk-days ($SegmentHours / 24.0)

        if ($LASTEXITCODE -ne 0) {
            throw "Tick export failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    "DONE $filename" | Add-Content -LiteralPath $progressPath -Encoding utf8
    $current = $next
}

"COMPLETE" | Add-Content -LiteralPath $progressPath -Encoding utf8
