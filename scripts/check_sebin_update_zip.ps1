param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function New-TextFromCodePoints {
    param([int[]]$CodePoints)
    return -join ($CodePoints | ForEach-Object { [char]$_ })
}

$UpdateRunnerBat = (New-TextFromCodePoints @(0xC5C5, 0xB370, 0xC774, 0xD2B8, 0x5F, 0xC2E4, 0xD589)) + ".bat"
$RestoreRunnerBat = (New-TextFromCodePoints @(0xBCF5, 0xAD6C, 0x5F, 0xC2E4, 0xD589)) + ".bat"
$ReadmeSebinUpdate = "README_" + (New-TextFromCodePoints @(0xC138, 0xBE48, 0xC5C5, 0xB370, 0xC774, 0xD2B8)) + ".txt"

function Test-BannedZipEntry {
    param([string]$EntryName)

    $normalized = $EntryName -replace "\\", "/"
    $relative = $normalized -replace "^counsel-note-sebin-update/", ""
    $fileName = Split-Path $relative -Leaf
    $patterns = @(
        "(^|/)\.venv(/|$)",
        "(^|/)\.agents(/|$)",
        "(^|/)\.codex(/|$)",
        "(^|/)\.git(/|$)",
        "(^|/)__pycache__(/|$)",
        "(^|/)\.pytest_cache(/|$)",
        "(^|/)\.mypy_cache(/|$)",
        "(^|/)generated(/|$)",
        "(^|/)tmp(/|$)",
        "(^|/)backups(/|$)",
        "(^|/)counsel-note_BACKUPS(/|$)",
        "(^|/)data/students/_backups(/|$)",
        "(^|/)data/google_docs_append_logs(/|$)",
        "(^|/)data/local_consumed_admin_notes\.json$",
        "(^|/)test-page-pipeline(/|$)",
        "(^|/)student\.js$",
        "\.bak($|[-_.])",
        "\.pyc$",
        "\.pyo$",
        "\.log$",
        "counsel-note-release-.*\.zip$",
        "counsel-note-sebin-update-.*\.zip$"
    )
    foreach ($pattern in $patterns) {
        if ($relative -match $pattern) {
            return $true
        }
    }
    return $fileName -eq "student.js"
}

function Test-ZipHasPrefix {
    param(
        [string[]]$Entries,
        [string]$Prefix
    )
    $normalizedPrefix = $Prefix -replace "\\", "/"
    return [bool]($Entries | Where-Object { $_.StartsWith($normalizedPrefix) } | Select-Object -First 1)
}

function Invoke-PythonCandidate {
    param(
        [object]$Candidate,
        [string[]]$Arguments,
        [string]$WorkingDirectory = ""
    )

    $allArgs = @()
    if ($Candidate.PrefixArgs) {
        $allArgs += $Candidate.PrefixArgs
    }
    $allArgs += $Arguments

    try {
        if ($WorkingDirectory) {
            Push-Location -LiteralPath $WorkingDirectory
        }
        $output = & $Candidate.FilePath @allArgs 2>&1
        return [PSCustomObject]@{
            ExitCode = $LASTEXITCODE
            Output = $output
            Error = ""
        }
    } catch {
        return [PSCustomObject]@{
            ExitCode = 1
            Output = @()
            Error = $_.Exception.Message
        }
    } finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

function Get-WorkingPython {
    param([string]$Root)

    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $candidates = @(
        [PSCustomObject]@{ Name = "payload .venv"; FilePath = $venvPython; PrefixArgs = @() },
        [PSCustomObject]@{ Name = "py -3"; FilePath = "py"; PrefixArgs = @("-3") },
        [PSCustomObject]@{ Name = "python"; FilePath = "python"; PrefixArgs = @() },
        [PSCustomObject]@{ Name = "python3"; FilePath = "python3"; PrefixArgs = @() }
    )
    if ($codexPython -and (Test-Path -LiteralPath $codexPython)) {
        $candidates += [PSCustomObject]@{ Name = "Codex bundled Python"; FilePath = $codexPython; PrefixArgs = @() }
    }

    foreach ($candidate in $candidates) {
        $isPath = ($candidate.FilePath -match "[\\/]")
        if ($isPath -and -not (Test-Path -LiteralPath $candidate.FilePath)) {
            continue
        }
        if (-not $isPath -and -not (Get-Command $candidate.FilePath -ErrorAction SilentlyContinue)) {
            continue
        }

        $result = Invoke-PythonCandidate -Candidate $candidate -Arguments @("-c", "import sys; print(sys.executable)")
        if ($result.ExitCode -eq 0) {
            return $candidate
        }
    }

    return $null
}

function Test-PayloadImportContract {
    param([string]$ZipFilePath)

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("counsel-note-payload-import-" + [guid]::NewGuid().ToString("N"))
    $errors = New-Object System.Collections.Generic.List[string]
    try {
        [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipFilePath, $tempRoot)
        $payloadRoot = Join-Path $tempRoot "counsel-note-sebin-update\payload"
        if (-not (Test-Path -LiteralPath $payloadRoot -PathType Container)) {
            [void]$errors.Add("payload folder missing after extraction")
            return $errors
        }

        $checkScript = Join-Path $payloadRoot "scripts\check_import_contracts.py"
        if (-not (Test-Path -LiteralPath $checkScript -PathType Leaf)) {
            [void]$errors.Add("payload import contract script missing")
            return $errors
        }

        $logCsvUtils = Join-Path $payloadRoot "counsel_modules\log_csv_utils.py"
        if (-not (Test-Path -LiteralPath $logCsvUtils -PathType Leaf)) {
            [void]$errors.Add("payload counsel_modules/log_csv_utils.py missing")
            return $errors
        }

        $python = Get-WorkingPython -Root $payloadRoot
        if (-not $python) {
            [void]$errors.Add("working Python not found for payload import contract")
            return $errors
        }

        $contractResult = Invoke-PythonCandidate -Candidate $python -Arguments @("-B", $checkScript) -WorkingDirectory $payloadRoot
        if ($contractResult.ExitCode -ne 0) {
            $detail = (($contractResult.Output -join " ") + " " + $contractResult.Error).Trim()
            [void]$errors.Add("payload import contract failed: $detail")
        }

        $directImport = "from counsel_modules.log_csv_utils import classify_google_docs_save_result; print('payload log_csv_utils import ok')"
        $directResult = Invoke-PythonCandidate -Candidate $python -Arguments @("-B", "-c", $directImport) -WorkingDirectory $payloadRoot
        if ($directResult.ExitCode -ne 0) {
            $detail = (($directResult.Output -join " ") + " " + $directResult.Error).Trim()
            [void]$errors.Add("payload classify_google_docs_save_result import failed: $detail")
        }

        return $errors
    } finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

$failures = New-Object System.Collections.Generic.List[string]

if (-not (Test-Path -LiteralPath $ZipPath -PathType Leaf)) {
    Write-Host "FAIL zip not found: $ZipPath"
    exit 1
}

$zipItem = Get-Item -LiteralPath $ZipPath
if ($zipItem.Length -le 0) {
    Write-Host "FAIL zip is empty: $ZipPath"
    exit 1
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$archive = [System.IO.Compression.ZipFile]::OpenRead($zipItem.FullName)
try {
    $entries = @($archive.Entries | ForEach-Object { $_.FullName -replace "\\", "/" })
} finally {
    $archive.Dispose()
}

if (-not (Test-ZipHasPrefix -Entries $entries -Prefix "counsel-note-sebin-update/")) {
    [void]$failures.Add("top-level counsel-note-sebin-update folder missing")
}
if (-not (Test-ZipHasPrefix -Entries $entries -Prefix "counsel-note-sebin-update/payload/")) {
    [void]$failures.Add("payload folder missing")
}

$requiredFiles = @(
    "counsel-note-sebin-update/$UpdateRunnerBat",
    "counsel-note-sebin-update/$RestoreRunnerBat",
    "counsel-note-sebin-update/$ReadmeSebinUpdate",
    "counsel-note-sebin-update/sebin_update_manifest.txt",
    "counsel-note-sebin-update/payload/app.py",
    "counsel-note-sebin-update/payload/run_app.bat",
    "counsel-note-sebin-update/payload/run_app.ps1",
    "counsel-note-sebin-update/payload/requirements.txt",
    "counsel-note-sebin-update/payload/scripts/check_release_ready.ps1",
    "counsel-note-sebin-update/payload/scripts/check_app_health.py",
    "counsel-note-sebin-update/payload/scripts/check_google_apps_script_same_date_policy.js",
    "counsel-note-sebin-update/payload/scripts/check_import_contracts.py",
    "counsel-note-sebin-update/payload/scripts/check_log_csv_batch_state.py",
    "counsel-note-sebin-update/payload/scripts/check_normalize_summary.py",
    "counsel-note-sebin-update/payload/scripts/check_quick.ps1",
    "counsel-note-sebin-update/payload/scripts/wait_for_streamlit_port.ps1",
    "counsel-note-sebin-update/payload/scripts/google_apps_script_doPost.js",
    "counsel-note-sebin-update/payload/counsel_modules/log_csv_utils.py",
    "counsel-note-sebin-update/payload/data/students/google_docs_map.csv",
    "counsel-note-sebin-update/payload/data/students/google_apps_script_webapp_url.txt",
    "counsel-note-sebin-update/payload/data/students/admin_api_base_url.txt",
    "counsel-note-sebin-update/payload/data/students/admin_sid_map.csv",
    "counsel-note-sebin-update/payload/tools/ffmpeg/bin/ffmpeg.exe"
)

foreach ($required in $requiredFiles) {
    if ($entries -notcontains $required) {
        [void]$failures.Add("required entry missing: $required")
    }
}

$requiredPrefixes = @(
    "counsel-note-sebin-update/payload/counsel_modules/",
    "counsel-note-sebin-update/payload/prompts/",
    "counsel-note-sebin-update/payload/data/students/"
)

foreach ($requiredPrefix in $requiredPrefixes) {
    if (-not (Test-ZipHasPrefix -Entries $entries -Prefix $requiredPrefix)) {
        [void]$failures.Add("required folder missing: $requiredPrefix")
    }
}

$bannedEntries = @($entries | Where-Object { Test-BannedZipEntry -EntryName $_ } | Sort-Object)
foreach ($entry in $bannedEntries) {
    [void]$failures.Add("banned entry included: $entry")
}

if ($failures.Count -eq 0) {
    $payloadImportFailures = Test-PayloadImportContract -ZipFilePath $zipItem.FullName
    foreach ($payloadImportFailure in $payloadImportFailures) {
        [void]$failures.Add($payloadImportFailure)
    }
}

if ($failures.Count -gt 0) {
    Write-Host "FAIL sebin update zip validation failed"
    foreach ($failure in $failures) {
        Write-Host "- $failure"
    }
    exit 1
}

Write-Host "PASS sebin update zip validation passed"
Write-Host "PASS payload import contract passed"
Write-Host "PASS data/students included"
Write-Host "zip: $($zipItem.FullName)"
Write-Host "entries: $($entries.Count)"
Write-Host "bytes: $($zipItem.Length)"
exit 0
