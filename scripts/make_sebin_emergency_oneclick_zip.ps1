param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
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

function Write-Status {
    param(
        [string]$Level,
        [string]$Message
    )
    $color = switch ($Level) {
        "PASS" { "Green" }
        "OK" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        default { "White" }
    }
    Write-Host "[$Level] $Message" -ForegroundColor $color
}

function Test-EmergencyBannedEntry {
    param([string]$EntryName)

    $normalized = $EntryName -replace "\\", "/"
    $fileName = Split-Path $normalized -Leaf
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
        if ($normalized -match $pattern) {
            return $true
        }
    }
    return $fileName -eq "student.js"
}

function Copy-EmergencyFile {
    param(
        [string]$RelativePath,
        [string]$DestinationRoot,
        [switch]$Required
    )

    $source = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        if ($Required) {
            throw "Required file missing: $RelativePath"
        }
        Write-Status "WARN" "Optional file missing: $RelativePath"
        return
    }

    if (Test-EmergencyBannedEntry -EntryName $RelativePath) {
        if ($Required) {
            throw "Required file is blocked by banned rule: $RelativePath"
        }
        return
    }

    $destination = Join-Path $DestinationRoot $RelativePath
    $destinationDir = Split-Path $destination -Parent
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
    Write-Status "OK" "Included file: $RelativePath"
}

function Copy-EmergencyDirectory {
    param(
        [string]$RelativePath,
        [string]$DestinationRoot,
        [switch]$Required
    )

    $source = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        if ($Required) {
            throw "Required folder missing: $RelativePath"
        }
        Write-Status "WARN" "Optional folder missing: $RelativePath"
        return
    }

    Get-ChildItem -LiteralPath $source -Recurse -Force | ForEach-Object {
        $childRelative = $_.FullName.Substring($source.Length).TrimStart("\", "/")
        $entryRelative = if ($childRelative) {
            Join-Path $RelativePath $childRelative
        } else {
            $RelativePath
        }

        if (Test-EmergencyBannedEntry -EntryName $entryRelative) {
            return
        }

        $target = Join-Path $DestinationRoot $entryRelative
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Path $target -Force | Out-Null
        } else {
            $targetDir = Split-Path $target -Parent
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
    Write-Status "OK" "Included folder: $RelativePath"
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$desktop = "C:\Users\idotd\OneDrive\Desktop"
if (-not (Test-Path -LiteralPath $desktop -PathType Container)) {
    $desktop = [Environment]::GetFolderPath("Desktop")
}
if (-not (Test-Path -LiteralPath $desktop -PathType Container)) {
    throw "Desktop path was not found."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$packageName = "counsel-note-sebin-emergency-oneclick-$timestamp"
$zipPath = Join-Path $desktop "$packageName.zip"
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) $packageName
$packageRoot = Join-Path $stageRoot $packageName
$payloadRoot = Join-Path $packageRoot "payload"

Write-Host ""
Write-Host "Counsel Note Sebin emergency oneclick zip builder" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Output zip: $zipPath"
Write-Host ""

if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

try {
    Copy-EmergencyFile -RelativePath $EmergencyInstallBat -DestinationRoot $packageRoot -Required
    Copy-EmergencyFile -RelativePath $ReadmeSebinEmergency -DestinationRoot $packageRoot -Required

    $requiredPayloadFiles = @(
        "app.py",
        "requirements.txt",
        "run_app.bat",
        "run_app.ps1",
        "install_first.bat",
        "install_python_first.bat",
        $ReadmeFirstRun,
        $ReadmeSebinAutoUpdate,
        $DiagnosticBundleBat,
        $SebinUpdateCheckBat,
        "publish_sebin_update.bat",
        "scripts/check_app_health.py",
        "scripts/check_audio_batch.py",
        "scripts/check_batch_review_counts.py",
        "scripts/check_consumed_admin_notes.py",
        "scripts/check_google_apps_script_same_date_policy.js",
        "scripts/check_google_docs_parallel.py",
        "scripts/check_docs_reconnect.py",
        "scripts/check_google_docs_transport.py",
        "scripts/check_import_contracts.py",
        "scripts/check_log_csv_batch_state.py",
        "scripts/check_normalize_summary.py",
        "scripts/check_quick.ps1",
        "scripts/check_release_ready.ps1",
        "scripts/check_runtime_stability.py",
        "scripts/check_sebin_emergency_zip.ps1",
        "scripts/check_sebin_update_zip.ps1",
        "scripts/google_apps_script_doPost.js",
        "scripts/make_diagnostic_bundle.ps1",
        "scripts/publish_sebin_update.ps1",
        "scripts/sebin_emergency_oneclick_install.ps1",
        "scripts/sebin_check_and_apply_update.ps1",
        "scripts/wait_for_streamlit_port.ps1",
        "tools/ffmpeg/bin/ffmpeg.exe",
        "data/students/google_docs_map.csv",
        "data/students/google_apps_script_webapp_url.txt"
    )

    foreach ($relativePath in $requiredPayloadFiles) {
        Copy-EmergencyFile -RelativePath $relativePath -DestinationRoot $payloadRoot -Required
    }

    $optionalPayloadFiles = @(
        "APP_VERSION.txt",
        "install_codex_first.bat",
        "data/students/admin_api_base_url.txt",
        "data/students/admin_sid_map.csv"
    )
    foreach ($relativePath in $optionalPayloadFiles) {
        Copy-EmergencyFile -RelativePath $relativePath -DestinationRoot $payloadRoot
    }

    Copy-EmergencyDirectory -RelativePath "counsel_modules" -DestinationRoot $payloadRoot -Required
    Copy-EmergencyDirectory -RelativePath "prompts" -DestinationRoot $payloadRoot -Required
    Copy-EmergencyDirectory -RelativePath "data/students" -DestinationRoot $payloadRoot -Required
    Copy-EmergencyDirectory -RelativePath "data/glossary" -DestinationRoot $payloadRoot

    $payloadFileCount = (Get-ChildItem -LiteralPath $payloadRoot -Recurse -File -Force | Measure-Object).Count
    $studentFileCount = (Get-ChildItem -LiteralPath (Join-Path $payloadRoot "data\students") -Recurse -File -Force | Measure-Object).Count
    $manifestPath = Join-Path $packageRoot "sebin_emergency_manifest.txt"
    $manifest = @"
Sebin counsel-note emergency oneclick manifest

created_at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")
package_name: $packageName
payload_file_count: $payloadFileCount
data_students_file_count: $studentFileCount

included_policy:
- data/students is included for Sebin emergency restore
- app.py, counsel_modules, prompts, scripts, run_app.bat/run_app.ps1, install_first.bat, diagnostics, and ffmpeg are included

excluded_policy:
- data/local_consumed_admin_notes.json is not included
- data/transcripts, uploads, diagnostics, Google Docs append logs, old logs, CSV results, and recordings are not included
- .venv, .agents, .codex, .git, Codex auth/cache, generated, tmp, backup folders, pyc, pyo, and log files are not included

validation:
- required emergency installer files are checked
- required payload files are checked
- data/students inclusion is checked
- health check warns if Codex CLI is missing or codex --version fails
- banned entry check is run after zip creation
- payload import contract is checked after zip creation
- counsel_modules/log_csv_utils.py must export classify_google_docs_save_result

notes:
- data/students contains operational student settings needed for real use
- no Google Docs POST is executed by this builder
- no admin POST/PATCH/DELETE is executed by this builder
- no Apps Script deployment is executed by this builder
"@
    Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding UTF8

    $stagedBanned = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object {
        $relative = $_.FullName.Substring($packageRoot.Length).TrimStart("\", "/")
        Test-EmergencyBannedEntry -EntryName $relative
    }
    if ($stagedBanned.Count -gt 0) {
        Write-Status "FAIL" "Staging folder contains banned entries."
        $stagedBanned | ForEach-Object {
            $relative = $_.FullName.Substring($packageRoot.Length).TrimStart("\", "/")
            Write-Host "- $relative"
        }
        exit 1
    }

    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipArchive = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        Get-ChildItem -LiteralPath $stageRoot -Recurse -File -Force | ForEach-Object {
            $entryName = $_.FullName.Substring($stageRoot.Length).TrimStart("\", "/") -replace "\\", "/"
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zipArchive,
                $_.FullName,
                $entryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    } finally {
        $zipArchive.Dispose()
    }

    $zipCheckScript = Join-Path $ProjectRoot "scripts\check_sebin_emergency_zip.ps1"
    if (-not (Test-Path -LiteralPath $zipCheckScript -PathType Leaf)) {
        Write-Status "FAIL" "Zip validation script is missing: scripts\check_sebin_emergency_zip.ps1"
        exit 1
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $zipCheckScript -ZipPath $zipPath
    if ($LASTEXITCODE -ne 0) {
        Write-Status "FAIL" "Emergency zip validation failed."
        exit 1
    }

    $zipItem = Get-Item -LiteralPath $zipPath
    Write-Host ""
    Write-Status "PASS" "Sebin emergency oneclick zip created."
    Write-Host "Zip path: $zipPath"
    Write-Host "Zip size: $($zipItem.Length) bytes"
    exit 0
} finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
