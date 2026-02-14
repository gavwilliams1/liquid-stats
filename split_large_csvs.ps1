# Split CSVs over 100MB into parts under 100MB for GitHub.
# Each part keeps the same column headings. Run the Python script.
Set-Location $PSScriptRoot
if (Get-Command python -ErrorAction SilentlyContinue) {
    python split_large_csvs.py
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py split_large_csvs.py
} else {
    Write-Host "Python not found. Install Python and run: python split_large_csvs.py"
    exit 1
}
