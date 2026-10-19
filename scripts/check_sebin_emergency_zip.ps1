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

$EmergencyInstallBat = (New-TextFromCodePoints @(0xC138, 0xBE48, 0x5F, 0xAE34, 0xAE09, 0xBCF5, 0xAD6C, 0x5F, 0xC6D0, 0xD074, 0xB9AD, 0xC124, 0xCE58)) + ".bat"
$ReadmeSebinEmergency = "README_" + (New-TextFromCodePoints @(0xC138, 0xBE48, 0x5F, 0xAE34, 0xAE09, 0xBCF5, 0xAD6C)) + ".txt"
$ReadmeFirstRun = "README_" + (New-TextFromCodePoints @(0xCC98, 0xC74C, 0xC2E4, 0xD589)) + ".txt"
$DiagnosticBundleBat = (New-TextFromCodePoints @(0xC9C4, 0xB2E8, 0x5F, 0xD328, 0xD0A4, 0xC9C0, 0x5F, 0xC0DD, 0xC131)) + ".bat"
$ReadmeSebinAutoUpdate = "README_" + (New-TextFromCodePoints @(0xC138, 0xBE48, 0x5F, 0xC790, 0xB3D9, 0xC5C5, 0xB370, 0xC774, 0xD2B8)) + ".txt"
$SebinUpdateCheckBat = (New-TextFromCodePoints @(0xC138, 0xBE48, 0x5F, 0xC5C5, 0xB370, 0xC774, 0xD2B8, 0x5F, 0xD655, 0xC778)) + ".bat"

function Test-BannedZipEntry {
    param(
        [string]$EntryName,
        [string]$TopLevel
    )
    $normalized = $EntryName -replace "\\", "/"
    $relative = $normalized -replace "^$([regex]::Escape($TopLevel))/", ""
    $fileName = Split-Path $relative -Leaf
    $patterns = @(
        "(^|/)\.venv(/|$)",
        "(^|/)\.agents(/|$)",
        "(^|/)\.codex(/|$)",
        "(^|/)\.git(/|$)",
        "(^|/)__pycache__(/|$)",
        "(^|/)\.pytest_cache(/|$)",
        "(^|/)\.mypy_cache(/|$)",
        "(^|/)data/local_consumed_admin_notes\.json$",
        "(^|/)data/transcripts(/|$)",
        "(^|/)data/google_docs_append_logs(/|$)",
        "(^|/)data/uploads(/|$)",
        "(^|/)data/tmp(/|$)",
        "(^|/)data/diagnostics(/|$)",
        "(^|/)data/students/_backups(/|$)",
        "(^|/)generated(/|$)",
        "(^|/)tmp(/|$)",
        "(^|/)backups(/|$)",
        "(^|/)counsel-note_BACKUPS(/|$)",
        "(^|/)test-page-pipeline(/|$)",
        "(^|/)student\.js$",
        "\.bak($|[-_.])",
        "\.pyc$",
        "\.pyo$",
        "\.log$",
        "counsel-note-release-.*\.zip$",
        "counsel-note-sebin-update-.*\.zip$",
        "counsel-note-sebin-emergency-oneclick-.*\.zip$"
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
    param(
        [string]$ZipFilePath,
        [string]$TopLevel
    )

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("counsel-note-emergency-payload-import-" + [guid]::NewGuid().ToString("N"))
    $errors = New-Object System.Collections.Generic.List[string]
    try {
        [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipFilePath, $tempRoot)
        $payloadRoot = Join-Path $tempRoot "$TopLevel\payload"
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

$topLevels = @($entries | Where-Object { $_ -match "/" } | ForEach-Object { ($_ -split "/")[0] } | Sort-Object -Unique)
if ($topLevels.Count -ne 1) {
    [void]$failures.Add("zip must contain exactly one top-level folder; found $($topLevels.Count)")
    $topLevel = "counsel-note-sebin-emergency-oneclick"
} else {
    $topLevel = $topLevels[0]
    if ($topLevel -notmatch "^counsel-note-sebin-emergency-oneclick-\d{8}-\d{6}$") {
        [void]$failures.Add("top-level folder name is not emergency oneclick format: $topLevel")
    }
}

if (-not (Test-ZipHasPrefix -Entries $entries -Prefix "$topLevel/payload/")) {
    [void]$failures.Add("payload folder missing")
}

$requiredFiles = @(
    "$topLevel/$EmergencyInstallBat",
    "$topLevel/$ReadmeSebinEmergency",
    "$topLevel/sebin_emergency_manifest.txt",
    "$topLevel/payload/app.py",
    "$topLevel/payload/requirements.txt",
    "$topLevel/payload/run_app.bat",
    "$topLevel/payload/run_app.ps1",
    "$topLevel/payload/install_first.bat",
    "$topLevel/payload/$ReadmeFirstRun",
    "$topLevel/payload/$ReadmeSebinAutoUpdate",
    "$topLevel/payload/$DiagnosticBundleBat",
    "$topLevel/payload/$SebinUpdateCheckBat",
    "$topLevel/payload/publish_sebin_update.bat",
    "$topLevel/payload/counsel_modules/log_csv_utils.py",
    "$topLevel/payload/counsel_modules/text_utils.py",
    "$topLevel/payload/prompts/summary_ko.txt",
    "$topLevel/payload/scripts/check_app_health.py",
    "$topLevel/payload/scripts/check_google_apps_script_same_date_policy.js",
    "$topLevel/payload/scripts/check_import_contracts.py",
    "$topLevel/payload/scripts/check_log_csv_batch_state.py",
    "$topLevel/payload/scripts/check_release_ready.ps1",
    "$topLevel/payload/scripts/check_normalize_summary.py",
    "$topLevel/payload/scripts/check_quick.ps1",
    "$topLevel/payload/scripts/wait_for_streamlit_port.ps1",
    "$topLevel/payload/scripts/google_apps_script_doPost.js",
    "$topLevel/payload/scripts/make_diagnostic_bundle.ps1",
    "$topLevel/payload/scripts/publish_sebin_update.ps1",
    "$topLevel/payload/scripts/sebin_emergency_oneclick_install.ps1",
    "$topLevel/payload/scripts/sebin_check_and_apply_update.ps1",
    "$topLevel/payload/tools/ffmpeg/bin/ffmpeg.exe",
    "$topLevel/payload/data/students/google_docs_map.csv",
    "$topLevel/payload/data/students/google_apps_script_webapp_url.txt"
)

foreach ($required in $requiredFiles) {
    if ($entries -notcontains $required) {
        [void]$failures.Add("required entry missing: $required")
    }
}

$optionalSettings = @(
    "$topLevel/payload/data/students/admin_api_base_url.txt",
    "$topLevel/payload/data/students/admin_sid_map.csv"
)
foreach ($optional in $optionalSettings) {
    if ($entries -notcontains $optional) {
        Write-Host "WARN optional setting not present: $optional"
    }
}

$requiredPrefixes = @(
    "$topLevel/payload/counsel_modules/",
    "$topLevel/payload/prompts/",
    "$topLevel/payload/scripts/",
    "$topLevel/payload/data/students/"
)
foreach ($requiredPrefix in $requiredPrefixes) {
    if (-not (Test-ZipHasPrefix -Entries $entries -Prefix $requiredPrefix)) {
        [void]$failures.Add("required folder missing: $requiredPrefix")
    }
}

$bannedEntries = @($entries | Where-Object { Test-BannedZipEntry -EntryName $_ -TopLevel $topLevel } | Sort-Object)
foreach ($entry in $bannedEntries) {
    [void]$failures.Add("banned entry included: $entry")
}

if ($failures.Count -eq 0) {
    $payloadImportFailures = Test-PayloadImportContract -ZipFilePath $zipItem.FullName -TopLevel $topLevel
    foreach ($payloadImportFailure in $payloadImportFailures) {
        [void]$failures.Add($payloadImportFailure)
    }
}

if ($failures.Count -gt 0) {
    Write-Host "FAIL sebin emergency zip validation failed"
    foreach ($failure in $failures) {
        Write-Host "- $failure"
    }
    exit 1
}

Write-Host "PASS sebin emergency zip validation passed"
Write-Host "PASS data/students included"
Write-Host "PASS local_consumed_admin_notes.json excluded"
Write-Host "PASS payload import contract passed"
Write-Host "zip: $($zipItem.FullName)"
Write-Host "entries: $($entries.Count)"
Write-Host "bytes: $($zipItem.Length)"
exit 0
