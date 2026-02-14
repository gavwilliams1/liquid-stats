# Split CSVs over 100MB into parts so each is under 100MB. Run: .\split_large_csvs.ps1
$ErrorActionPreference = "Stop"
$DataDir = $PSScriptRoot
$MaxBytes = 100MB

foreach ($item in Get-ChildItem -Path $DataDir -Filter "*.csv" | Sort-Object Name) {
    if ($item.Name -match "_part\d+\.csv$") { continue }
    if ($item.Length -le $MaxBytes) {
        Write-Host "Skip $($item.Name) ($([math]::Round($item.Length/1MB, 1)) MB)"
        continue
    }
    $base = [System.IO.Path]::GetFileNameWithoutExtension($item.FullName)
    $numParts = [math]::Max(2, [math]::Ceiling($item.Length / $MaxBytes))
    Write-Host "Splitting $($item.Name) ($([math]::Round($item.Length/1MB, 1)) MB) into $numParts parts..."

    $reader = [System.IO.StreamReader]::new($item.FullName, [System.Text.Encoding]::UTF8)
    try {
        $header = $reader.ReadLine()
        $lineCount = 0
        while ($null -ne $reader.ReadLine()) { $lineCount++ }
    } finally { $reader.Close() }

    $linesPerPart = [math]::Floor($lineCount / $numParts)
    $writers = @()
    $paths = @()
    for ($k = 1; $k -le $numParts; $k++) {
        $paths += Join-Path $DataDir "${base}_part${k}.csv"
        $writers += [System.IO.StreamWriter]::new($paths[$k-1], $false, [System.Text.Encoding]::UTF8)
    }
    try {
        $reader = [System.IO.StreamReader]::new($item.FullName, [System.Text.Encoding]::UTF8)
        $h = $reader.ReadLine()
        foreach ($w in $writers) { $w.WriteLine($h) }
        $idx = 0
        $part = 0
        $limit = $linesPerPart
        while ($null -ne ($line = $reader.ReadLine())) {
            if ($idx -ge $limit -and $part -lt $numParts - 1) {
                $part++
                $limit += $linesPerPart
            }
            $writers[$part].WriteLine($line)
            $idx++
        }
        $reader.Close()
    } finally {
        foreach ($w in $writers) { $w.Close() }
    }
    $partNames = 1..$numParts | ForEach-Object { "${base}_part$_.csv" }
    Write-Host "  -> $($partNames -join ', ')"
}
