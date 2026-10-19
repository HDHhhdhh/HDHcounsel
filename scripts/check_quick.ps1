$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP "counsel-note-pycache"

function New-PythonCandidate {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$PrefixArgs = @()
    )
    [PSCustomObject]@{
        Name = $Name
        FilePath = $FilePath
        PrefixArgs = $PrefixArgs
    }
}

function Invoke-PythonCandidate {
    param(
        [object]$Python,
        [string[]]$Arguments
    )

    $allArgs = @()
    if ($Python.PrefixArgs) {
        $allArgs += $Python.PrefixArgs
    }
    $allArgs += $Arguments
    & $Python.FilePath @allArgs
    return $LASTEXITCODE
}

function Get-QuickPython {
    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $candidates = @(
        (New-PythonCandidate -Name ".venv" -FilePath (Join-Path $root ".venv\Scripts\python.exe")),
        (New-PythonCandidate -Name "py -3" -FilePath "py" -PrefixArgs @("-3")),
        (New-PythonCandidate -Name "python" -FilePath "python"),
        (New-PythonCandidate -Name "python3" -FilePath "python3")
    )
    if ($codexPython -and (Test-Path -LiteralPath $codexPython)) {
        $candidates += New-PythonCandidate -Name "Codex bundled Python" -FilePath $codexPython
    }
    foreach ($candidate in $candidates) {
        $isPath = ($candidate.FilePath -match "[\\/]")
        if ($isPath -and -not (Test-Path -LiteralPath $candidate.FilePath)) {
            continue
        }
        if (-not $isPath -and -not (Get-Command $candidate.FilePath -ErrorAction SilentlyContinue)) {
            continue
        }
        try {
            Invoke-PythonCandidate -Python $candidate -Arguments @("--version") | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
        }
    }
    throw "No usable Python runtime found."
}

$python = Get-QuickPython
Write-Host "Quick check Python: $($python.Name) ($($python.FilePath))"

Write-Host "[1/9] app health --fast"
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_app_health.py", "--fast") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_app_health.py --fast failed"
}

Write-Host "[2/9] import contracts"
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_import_contracts.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_import_contracts.py failed"
}

Write-Host "[3/9] app syntax"
Invoke-PythonCandidate -Python $python -Arguments @("-m", "py_compile", "app.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "app.py py_compile failed"
}

Write-Host "[4/9] counsel_modules syntax"
Get-ChildItem "counsel_modules" -Filter "*.py" | ForEach-Object {
    Invoke-PythonCandidate -Python $python -Arguments @("-m", "py_compile", $_.FullName) | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "py_compile failed: $($_.FullName)"
    }
}

Write-Host "[5/9] log CSV batch state"
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_log_csv_batch_state.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_log_csv_batch_state.py failed"
}

Write-Host "[6/9] log CSV processing history"
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_csv_persistence.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_csv_persistence.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_log_csv_processing_history.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_log_csv_processing_history.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_log_csv_controls.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_log_csv_controls.py failed"
}

Write-Host "[7/9] Connect Log HTTP launcher"
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_connect_log_http_launcher.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_connect_log_http_launcher.py failed"
}

Write-Host "[8/9] audio batch"
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_audio_batch.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_audio_batch.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_batch_review_counts.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_batch_review_counts.py failed"
}

Write-Host "[9/9] runtime stability"
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_csv_worker.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_csv_worker.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_docs_reconnect.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_docs_reconnect.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_google_docs_transport.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_google_docs_transport.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_google_docs_parallel.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_google_docs_parallel.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_runtime_stability.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_runtime_stability.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_admin_save_ui.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_admin_save_ui.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_audio_upload_layout.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_audio_upload_layout.py failed"
}
Invoke-PythonCandidate -Python $python -Arguments @("scripts\check_ui_refresh.py") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "check_ui_refresh.py failed"
}

Write-Host "quick checks passed"
