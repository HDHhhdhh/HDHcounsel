param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function New-TextFromCodePoints {
    param([int[]]$CodePoints)
    return -join ($CodePoints | ForEach-Object { [char]$_ })
}

$UpdateRunnerBat = (New-TextFromCodePoints @(0xC5C5, 0xB370, 0xC774, 0xD2B8, 0x5F, 0xC2E4, 0xD589)) + ".bat"
$RestoreRunnerBat = (New-TextFromCodePoints @(0xBCF5, 0xAD6C, 0x5F, 0xC2E4, 0xD589)) + ".bat"
$DiagnosticBundleBat = (New-TextFromCodePoints @(0xC9C4, 0xB2E8, 0x5F, 0xD328, 0xD0A4, 0xC9C0, 0x5F, 0xC0DD, 0xC131)) + ".bat"
$ReadmeSebinUpdate = "README_" + (New-TextFromCodePoints @(0xC138, 0xBE48, 0xC5C5, 0xB370, 0xC774, 0xD2B8)) + ".txt"
$ReadmeFirstRun = "README_" + (New-TextFromCodePoints @(0xCC98, 0xC74C, 0xC2E4, 0xD589)) + ".txt"
$SebinUpdateCheckBat = (New-TextFromCodePoints @(0xC138, 0xBE48, 0x5F, 0xC5C5, 0xB370, 0xC774, 0xD2B8, 0x5F, 0xD655, 0xC778)) + ".bat"
$ReadmeSebinAutoUpdate = "README_" + (New-TextFromCodePoints @(0xC138, 0xBE48, 0x5F, 0xC790, 0xB3D9, 0xC5C5, 0xB370, 0xC774, 0xD2B8)) + ".txt"
$EmergencyInstallBat = (New-TextFromCodePoints @(0xC138, 0xBE48, 0x5F, 0xAE34, 0xAE09, 0xBCF5, 0xAD6C, 0x5F, 0xC6D0, 0xD074, 0xB9AD, 0xC124, 0xCE58)) + ".bat"
$ReadmeSebinEmergency = "README_" + (New-TextFromCodePoints @(0xC138, 0xBE48, 0x5F, 0xAE34, 0xAE09, 0xBCF5, 0xAD6C)) + ".txt"

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

function Copy-UpdateFile {
    param(
        [string]$RelativePath,
        [string]$PayloadRoot,
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

    $destination = Join-Path $PayloadRoot $RelativePath
    $destinationDir = Split-Path $destination -Parent
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
    Write-Status "OK" "Included file: $RelativePath"
}

function Copy-UpdateDirectory {
    param(
        [string]$RelativePath,
        [string]$PayloadRoot,
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

    $destination = Join-Path $PayloadRoot $RelativePath
    Get-ChildItem -LiteralPath $source -Recurse -Force | ForEach-Object {
        $childRelative = $_.FullName.Substring($source.Length).TrimStart("\", "/")
        $entryRelative = if ($childRelative) {
            Join-Path $RelativePath $childRelative
        } else {
            $RelativePath
        }

        if (Test-UpdateBannedEntry -EntryName $entryRelative) {
            return
        }

        $target = Join-Path $PayloadRoot $entryRelative
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

function Test-UpdateBannedEntry {
    param([string]$EntryName)

    $normalized = $EntryName -replace "\\", "/"
    $fileName = Split-Path $normalized -Leaf

    $bannedPatterns = @(
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

    foreach ($pattern in $bannedPatterns) {
        if ($normalized -match $pattern) {
            return $true
        }
    }

    if ($fileName -eq "student.js") {
        return $true
    }

    return $false
}

function New-UpdateRunnerBat {
    param([string]$DestinationPath)

    $content = @'
@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PAYLOAD=%SCRIPT_DIR%payload"

echo Please close the counsel-note app/browser before updating.
echo.

if not exist "%PAYLOAD%\app.py" (
  echo Payload folder was not found. Please unzip the update package again.
  pause
  exit /b 1
)

set "TARGET=%USERPROFILE%\counsel-note-app"
if not exist "%TARGET%\app.py" set "TARGET="

set "LEGACY_COUNT=0"
set "LEGACY_TARGET="
if exist "%USERPROFILE%\Desktop\counsel-note\app.py" (
  set /a LEGACY_COUNT+=1
  set "LEGACY_TARGET=%USERPROFILE%\Desktop\counsel-note"
)
if exist "%USERPROFILE%\OneDrive\Desktop\counsel-note\app.py" (
  set /a LEGACY_COUNT+=1
  set "LEGACY_TARGET=%USERPROFILE%\OneDrive\Desktop\counsel-note"
)

if not defined TARGET if %LEGACY_COUNT% GTR 1 (
  echo Multiple legacy counsel-note folders were found.
  echo Move the active app to %%USERPROFILE%%\counsel-note-app before updating.
  pause
  exit /b 1
)
if not defined TARGET if %LEGACY_COUNT% EQU 1 set "TARGET=%LEGACY_TARGET%"

if not defined TARGET (
  echo Existing counsel-note folder was not found.
  echo Please install counsel-note with the first-install release zip first.
  pause
  exit /b 1
)

set "BACKUP_ROOT=%USERPROFILE%\counsel-note_BACKUPS"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
set "BACKUP_DIR=%BACKUP_ROOT%\sebin_update_backup_%TS%"

echo Existing app folder: %TARGET%
echo Backup folder: %BACKUP_DIR%
echo.

mkdir "%BACKUP_DIR%" >nul 2>nul
if errorlevel 1 (
  echo Could not create the backup folder. Update stopped.
  pause
  exit /b 1
)

call :BackupFile "app.py"
call :BackupFile "APP_VERSION.txt"
call :BackupFile "BUILD_INFO.json"
call :BackupFile "requirements.txt"
call :BackupFile "run_app.bat"
call :BackupFile "run_app.ps1"
if exist "%TARGET%\README_*.txt" copy /Y "%TARGET%\README_*.txt" "%BACKUP_DIR%\" >nul
call :BackupDir "counsel_modules"
call :BackupDir "prompts"
call :BackupDir "scripts"
call :BackupDir "data\students"

echo.
echo Copying payload to the existing counsel-note folder.
robocopy "%PAYLOAD%" "%TARGET%" /E /XD "%PAYLOAD%\.venv" "%PAYLOAD%\.agents" "%PAYLOAD%\.codex" /XF "student.js" >nul
if errorlevel 8 (
  echo File copy failed.
  pause
  exit /b 1
)

echo.
echo data\students settings were included and applied.
if not exist "%TARGET%\data\students" (
  echo Warning: data\students folder was not found after update.
)

if exist "%TARGET%\.venv\Scripts\python.exe" (
  echo.
  echo Running basic validation.
  "%TARGET%\.venv\Scripts\python.exe" -m py_compile "%TARGET%\app.py"
  if errorlevel 1 echo Warning: app.py validation failed. File copy is already complete.
  "%TARGET%\.venv\Scripts\python.exe" "%TARGET%\scripts\check_normalize_summary.py"
  if errorlevel 1 echo Warning: summary validation failed. File copy is already complete.
) else (
  echo.
  echo .venv Python was not found. Automatic validation was skipped.
)

echo.
echo Update complete.
echo If something goes wrong, double-click the restore batch file in this folder.
echo Press any key to run the app.
pause >nul
cd /d "%TARGET%"
start "" "%TARGET%\run_app.bat"
exit /b 0

:BackupFile
if exist "%TARGET%\%~1" (
  if not exist "%BACKUP_DIR%\%~dp1" mkdir "%BACKUP_DIR%\%~dp1" >nul 2>nul
  copy /Y "%TARGET%\%~1" "%BACKUP_DIR%\%~1" >nul
)
exit /b 0

:BackupDir
if exist "%TARGET%\%~1" (
  robocopy "%TARGET%\%~1" "%BACKUP_DIR%\%~1" /E >nul
  if errorlevel 8 (
    echo Backup failed: %~1
    exit /b 1
  )
)
exit /b 0
'@

    Set-Content -LiteralPath $DestinationPath -Value $content -Encoding UTF8
}

function New-RestoreRunnerBat {
    param([string]$DestinationPath)

    $content = @'
@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "TARGET=%USERPROFILE%\counsel-note-app"
if not exist "%TARGET%\app.py" set "TARGET="

set "LEGACY_COUNT=0"
set "LEGACY_TARGET="
if exist "%USERPROFILE%\Desktop\counsel-note\app.py" (
  set /a LEGACY_COUNT+=1
  set "LEGACY_TARGET=%USERPROFILE%\Desktop\counsel-note"
)
if exist "%USERPROFILE%\OneDrive\Desktop\counsel-note\app.py" (
  set /a LEGACY_COUNT+=1
  set "LEGACY_TARGET=%USERPROFILE%\OneDrive\Desktop\counsel-note"
)

if not defined TARGET if %LEGACY_COUNT% GTR 1 (
  echo Multiple legacy counsel-note folders were found.
  echo Move the active app to %%USERPROFILE%%\counsel-note-app before restoring.
  pause
  exit /b 1
)
if not defined TARGET if %LEGACY_COUNT% EQU 1 set "TARGET=%LEGACY_TARGET%"

if not defined TARGET (
  echo Existing counsel-note folder was not found. Restore stopped.
  pause
  exit /b 1
)

set "BACKUP_ROOT=%USERPROFILE%\counsel-note_BACKUPS"
if not exist "%BACKUP_ROOT%\sebin_update_backup_*" set "BACKUP_ROOT="

if not defined BACKUP_ROOT (
  echo No sebin update backup was found. Restore stopped.
  pause
  exit /b 1
)

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$root=$env:BACKUP_ROOT; Get-ChildItem -LiteralPath $root -Directory -Filter 'sebin_update_backup_*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do set "RESTORE_SOURCE=%%i"

if not defined RESTORE_SOURCE (
  echo No restore source was found. Restore stopped.
  pause
  exit /b 1
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
set "BEFORE_RESTORE_DIR=%BACKUP_ROOT%\before_restore_%TS%"

echo Existing app folder: %TARGET%
echo Restore source: %RESTORE_SOURCE%
echo Current state backup: %BEFORE_RESTORE_DIR%
echo.

mkdir "%BEFORE_RESTORE_DIR%" >nul 2>nul
if errorlevel 1 (
  echo Could not create backup folder before restore. Restore stopped.
  pause
  exit /b 1
)

call :BackupFile "app.py"
call :BackupFile "APP_VERSION.txt"
call :BackupFile "BUILD_INFO.json"
call :BackupFile "requirements.txt"
call :BackupFile "run_app.bat"
call :BackupFile "run_app.ps1"
if exist "%TARGET%\README_*.txt" copy /Y "%TARGET%\README_*.txt" "%BEFORE_RESTORE_DIR%\" >nul
call :BackupDir "counsel_modules"
call :BackupDir "prompts"
call :BackupDir "scripts"

echo.
echo Restoring app files from the latest sebin update backup.
call :RestoreFile "app.py"
call :RestoreFile "APP_VERSION.txt"
call :RestoreFile "BUILD_INFO.json"
call :RestoreFile "requirements.txt"
call :RestoreFile "run_app.bat"
call :RestoreFile "run_app.ps1"
if exist "%RESTORE_SOURCE%\README_*.txt" copy /Y "%RESTORE_SOURCE%\README_*.txt" "%TARGET%\" >nul
call :RestoreDir "counsel_modules"
call :RestoreDir "prompts"
call :RestoreDir "scripts"
call :RestoreDir "data\students"

echo.
echo data\students settings were restored from backup when available.
echo Existing .venv folder was not changed.

if exist "%TARGET%\.venv\Scripts\python.exe" (
  echo.
  echo Running basic validation.
  "%TARGET%\.venv\Scripts\python.exe" -m py_compile "%TARGET%\app.py"
  if errorlevel 1 echo Warning: app.py validation failed. Restore is already complete.
  "%TARGET%\.venv\Scripts\python.exe" "%TARGET%\scripts\check_normalize_summary.py"
  if errorlevel 1 echo Warning: summary validation failed. Restore is already complete.
) else (
  echo.
  echo .venv Python was not found. Automatic validation was skipped.
)

echo.
echo Restore complete.
echo Press any key to run the app.
pause >nul
cd /d "%TARGET%"
start "" "%TARGET%\run_app.bat"
exit /b 0

:BackupFile
if exist "%TARGET%\%~1" (
  if not exist "%BEFORE_RESTORE_DIR%\%~dp1" mkdir "%BEFORE_RESTORE_DIR%\%~dp1" >nul 2>nul
  copy /Y "%TARGET%\%~1" "%BEFORE_RESTORE_DIR%\%~1" >nul
)
exit /b 0

:BackupDir
if exist "%TARGET%\%~1" (
  robocopy "%TARGET%\%~1" "%BEFORE_RESTORE_DIR%\%~1" /E >nul
  if errorlevel 8 (
    echo Backup failed: %~1
    exit /b 1
  )
)
exit /b 0

:RestoreFile
if exist "%RESTORE_SOURCE%\%~1" (
  copy /Y "%RESTORE_SOURCE%\%~1" "%TARGET%\%~1" >nul
)
exit /b 0

:RestoreDir
if exist "%RESTORE_SOURCE%\%~1" (
  robocopy "%RESTORE_SOURCE%\%~1" "%TARGET%\%~1" /E >nul
  if errorlevel 8 (
    echo Restore failed: %~1
    exit /b 1
  )
)
exit /b 0
'@

    Set-Content -LiteralPath $DestinationPath -Value $content -Encoding UTF8
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
if ($OutputDir.Trim()) {
    $desktop = [System.IO.Path]::GetFullPath($OutputDir)
    if (-not (Test-Path -LiteralPath $desktop -PathType Container)) {
        throw "Output directory was not found: $desktop"
    }
} else {
    $desktop = "C:\Users\idotd\OneDrive\Desktop"
    if (-not (Test-Path -LiteralPath $desktop -PathType Container)) {
        $desktop = [Environment]::GetFolderPath("Desktop")
    }
    if (-not (Test-Path -LiteralPath $desktop -PathType Container)) {
        throw "Desktop path was not found."
    }
}

Write-Host ""
Write-Host "Counsel Note Sebin update zip builder" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Output folder: $desktop"
Write-Host ""

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$buildUpdatedAt = Get-Date -Format "s"
$buildVersion = "sebin-update-$timestamp"
$zipPath = Join-Path $desktop "counsel-note-sebin-update-$timestamp.zip"
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "counsel-note-sebin-update-$timestamp"
$packageRoot = Join-Path $stageRoot "counsel-note-sebin-update"
$payloadRoot = Join-Path $packageRoot "payload"

if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

try {
    Set-Content -LiteralPath (Join-Path $ProjectRoot "APP_VERSION.txt") -Value $buildVersion -Encoding UTF8
    $buildInfo = [ordered]@{
        last_updated_at = $buildUpdatedAt
        channel = "sebin-update"
    }
    $buildInfo | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $ProjectRoot "BUILD_INFO.json") -Encoding UTF8
    New-UpdateRunnerBat -DestinationPath (Join-Path $packageRoot $UpdateRunnerBat)
    New-RestoreRunnerBat -DestinationPath (Join-Path $packageRoot $RestoreRunnerBat)
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $ReadmeSebinUpdate) -Destination (Join-Path $packageRoot $ReadmeSebinUpdate) -Force

    $requiredPayloadFiles = @(
        "APP_VERSION.txt",
        "BUILD_INFO.json",
        "app.py",
        "requirements.txt",
        "run_app.bat",
        "run_app.ps1",
        "publish_sebin_update.bat",
        "make_sebin_emergency_oneclick_zip.bat",
        $SebinUpdateCheckBat,
        $ReadmeSebinAutoUpdate,
        $EmergencyInstallBat,
        $ReadmeSebinEmergency,
        $DiagnosticBundleBat,
        "install_first.bat",
        "install_python_first.bat",
        $ReadmeFirstRun,
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
        "scripts/make_sebin_emergency_oneclick_zip.ps1",
        "scripts/make_diagnostic_bundle.ps1",
        "scripts/publish_sebin_update.ps1",
        "scripts/sebin_check_and_apply_update.ps1",
        "scripts/sebin_emergency_oneclick_install.ps1",
        "scripts/wait_for_streamlit_port.ps1",
        "scripts/google_apps_script_doPost.js",
        "tools/ffmpeg/bin/ffmpeg.exe"
    )

    foreach ($relativePath in $requiredPayloadFiles) {
        Copy-UpdateFile -RelativePath $relativePath -PayloadRoot $payloadRoot -Required
    }

    Copy-UpdateDirectory -RelativePath "counsel_modules" -PayloadRoot $payloadRoot -Required
    Copy-UpdateDirectory -RelativePath "prompts" -PayloadRoot $payloadRoot -Required
    Copy-UpdateDirectory -RelativePath "data/glossary" -PayloadRoot $payloadRoot -Required
    Copy-UpdateDirectory -RelativePath "data/students" -PayloadRoot $payloadRoot -Required

    $payloadFileCount = (Get-ChildItem -LiteralPath $payloadRoot -Recurse -File -Force | Measure-Object).Count
    $manifestPath = Join-Path $packageRoot "sebin_update_manifest.txt"
    $manifest = @"
Sebin counsel-note update manifest

created_at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")
last_updated_at: $buildUpdatedAt
app_version: $buildVersion
build_channel: sebin-update
payload_file_count: $payloadFileCount

included_policy:
- data/students is included as required real-use student settings data

excluded_policy:
- data/local_consumed_admin_notes.json is not included
- .venv, .agents, .codex, .git, cache, log, backup, and generated folders are not included

validation:
- scripts/check_app_health.py is included in payload
- BUILD_INFO.json is included in payload
- payload import contract is checked after zip creation
- counsel_modules/log_csv_utils.py must export classify_google_docs_save_result
- diagnostic bundle creation tool is included in payload
- automatic update check helper is included in payload
- required entry check is run after zip creation
- banned entry check is run after zip creation
- data/students inclusion is checked
- local consumed registry, .venv, .agents, and .codex exclusion is checked

safety:
- no Google Docs POST is executed by this builder
- no admin POST/PATCH/DELETE is executed by this builder
- no Apps Script deployment is executed by this builder
"@
    Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding UTF8

    $stagedBanned = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object {
        $relative = $_.FullName.Substring($packageRoot.Length).TrimStart("\", "/")
        Test-UpdateBannedEntry -EntryName $relative
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

    $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $zipEntries = @($archive.Entries | ForEach-Object { $_.FullName -replace "\\", "/" })
        $badEntries = @()
        foreach ($entry in $zipEntries) {
            $relativeToPackage = $entry -replace "^counsel-note-sebin-update/", ""
            if (Test-UpdateBannedEntry -EntryName $relativeToPackage) {
                $badEntries += $entry
            }
        }
    } finally {
        $archive.Dispose()
    }

    $requiredZipEntries = @(
        "counsel-note-sebin-update/$UpdateRunnerBat",
        "counsel-note-sebin-update/$RestoreRunnerBat",
        "counsel-note-sebin-update/$ReadmeSebinUpdate",
        "counsel-note-sebin-update/sebin_update_manifest.txt",
        "counsel-note-sebin-update/payload/app.py",
        "counsel-note-sebin-update/payload/APP_VERSION.txt",
        "counsel-note-sebin-update/payload/BUILD_INFO.json",
        "counsel-note-sebin-update/payload/requirements.txt",
        "counsel-note-sebin-update/payload/run_app.bat",
        "counsel-note-sebin-update/payload/run_app.ps1",
        "counsel-note-sebin-update/payload/publish_sebin_update.bat",
        "counsel-note-sebin-update/payload/make_sebin_emergency_oneclick_zip.bat",
        "counsel-note-sebin-update/payload/$SebinUpdateCheckBat",
        "counsel-note-sebin-update/payload/$ReadmeSebinAutoUpdate",
        "counsel-note-sebin-update/payload/$EmergencyInstallBat",
        "counsel-note-sebin-update/payload/$ReadmeSebinEmergency",
        "counsel-note-sebin-update/payload/$DiagnosticBundleBat",
        "counsel-note-sebin-update/payload/install_first.bat",
        "counsel-note-sebin-update/payload/install_python_first.bat",
        "counsel-note-sebin-update/payload/$ReadmeFirstRun",
        "counsel-note-sebin-update/payload/counsel_modules/__init__.py",
        "counsel-note-sebin-update/payload/counsel_modules/admin_utils.py",
        "counsel-note-sebin-update/payload/counsel_modules/audio_batch.py",
        "counsel-note-sebin-update/payload/counsel_modules/codex_runner.py",
        "counsel-note-sebin-update/payload/counsel_modules/codex_runtime.py",
        "counsel-note-sebin-update/payload/counsel_modules/google_docs_utils.py",
        "counsel-note-sebin-update/payload/counsel_modules/log_csv_utils.py",
        "counsel-note-sebin-update/payload/counsel_modules/runtime_utils.py",
        "counsel-note-sebin-update/payload/counsel_modules/text_utils.py",
        "counsel-note-sebin-update/payload/prompts/summary_ko.txt",
        "counsel-note-sebin-update/payload/data/students/google_docs_map.csv",
        "counsel-note-sebin-update/payload/data/students/google_apps_script_webapp_url.txt",
        "counsel-note-sebin-update/payload/data/students/admin_api_base_url.txt",
        "counsel-note-sebin-update/payload/data/students/admin_sid_map.csv",
        "counsel-note-sebin-update/payload/scripts/check_app_health.py",
        "counsel-note-sebin-update/payload/scripts/check_audio_batch.py",
        "counsel-note-sebin-update/payload/scripts/check_batch_review_counts.py",
        "counsel-note-sebin-update/payload/scripts/check_consumed_admin_notes.py",
        "counsel-note-sebin-update/payload/scripts/check_google_apps_script_same_date_policy.js",
        "counsel-note-sebin-update/payload/scripts/check_google_docs_parallel.py",
        "counsel-note-sebin-update/payload/scripts/check_docs_reconnect.py",
        "counsel-note-sebin-update/payload/scripts/check_google_docs_transport.py",
        "counsel-note-sebin-update/payload/scripts/check_import_contracts.py",
        "counsel-note-sebin-update/payload/scripts/check_log_csv_batch_state.py",
        "counsel-note-sebin-update/payload/scripts/check_normalize_summary.py",
        "counsel-note-sebin-update/payload/scripts/check_quick.ps1",
        "counsel-note-sebin-update/payload/scripts/check_release_ready.ps1",
        "counsel-note-sebin-update/payload/scripts/check_runtime_stability.py",
        "counsel-note-sebin-update/payload/scripts/check_sebin_emergency_zip.ps1",
        "counsel-note-sebin-update/payload/scripts/check_sebin_update_zip.ps1",
        "counsel-note-sebin-update/payload/scripts/make_sebin_emergency_oneclick_zip.ps1",
        "counsel-note-sebin-update/payload/scripts/make_diagnostic_bundle.ps1",
        "counsel-note-sebin-update/payload/scripts/publish_sebin_update.ps1",
        "counsel-note-sebin-update/payload/scripts/sebin_check_and_apply_update.ps1",
        "counsel-note-sebin-update/payload/scripts/sebin_emergency_oneclick_install.ps1",
        "counsel-note-sebin-update/payload/scripts/wait_for_streamlit_port.ps1",
        "counsel-note-sebin-update/payload/scripts/google_apps_script_doPost.js",
        "counsel-note-sebin-update/payload/data/glossary/academy_terms.csv",
        "counsel-note-sebin-update/payload/tools/ffmpeg/bin/ffmpeg.exe"
    )

    $missingZipEntries = @()
    foreach ($entry in $requiredZipEntries) {
        if ($zipEntries -contains $entry) {
            Write-Status "PASS" "Zip contains: $entry"
        } else {
            Write-Status "FAIL" "Zip missing: $entry"
            $missingZipEntries += $entry
        }
    }

    if ($badEntries.Count -gt 0) {
        Write-Status "FAIL" "Zip contains banned entries."
        $badEntries | Sort-Object | ForEach-Object { Write-Host "- $_" }
        exit 1
    }

    if ($missingZipEntries.Count -gt 0) {
        Write-Status "FAIL" "Zip inspection failed. Required entries are missing."
        $missingZipEntries | Sort-Object | ForEach-Object { Write-Host "- $_" }
        exit 1
    }

    $zipCheckScript = Join-Path $ProjectRoot "scripts\check_sebin_update_zip.ps1"
    if (-not (Test-Path -LiteralPath $zipCheckScript -PathType Leaf)) {
        Write-Status "FAIL" "Zip validation script is missing: scripts\check_sebin_update_zip.ps1"
        exit 1
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $zipCheckScript -ZipPath $zipPath
    if ($LASTEXITCODE -ne 0) {
        Write-Status "FAIL" "External zip validation failed."
        exit 1
    }

    Write-Host ""
    Write-Status "PASS" "Sebin update zip created."
    Write-Host "Zip path: $zipPath"
    exit 0
} finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
