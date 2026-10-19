param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

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

function Get-DesktopPath {
    $defaultDesktop = Join-Path $env:USERPROFILE "Desktop"
    if (Test-Path -LiteralPath $defaultDesktop -PathType Container) {
        return $defaultDesktop
    }
    $shellDesktop = [Environment]::GetFolderPath("Desktop")
    if ($shellDesktop -and (Test-Path -LiteralPath $shellDesktop -PathType Container)) {
        return $shellDesktop
    }
    throw "Desktop folder was not found."
}

function Get-UniqueBackupPath {
    param(
        [string]$ParentPath,
        [string]$Timestamp
    )
    $base = Join-Path $ParentPath "emergency_restore_backup_$Timestamp"
    if (-not (Test-Path -LiteralPath $base)) {
        return $base
    }
    for ($i = 2; $i -lt 100; $i++) {
        $candidate = "$base`_$i"
        if (-not (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    throw "Could not find an available backup folder name."
}

function Invoke-DiagnosticBundle {
    param([string]$InstalledRoot)

    try {
        $diagnosticScript = Join-Path $InstalledRoot "scripts\make_diagnostic_bundle.ps1"
        if (-not (Test-Path -LiteralPath $diagnosticScript -PathType Leaf)) {
            Write-Status "WARN" "Diagnostic script was not found after install copy."
            return
        }

        Write-Status "WARN" "Creating diagnostic bundle on Desktop..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File $diagnosticScript
        $desktop = Get-DesktopPath
        $latest = Get-ChildItem -LiteralPath $desktop -Filter "counsel-note-diagnostic-*.zip" -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($latest) {
            Write-Status "WARN" "Diagnostic zip: $($latest.FullName)"
            Write-Host "Please send this diagnostic zip with a screenshot of the error."
        }
    } catch {
        Write-Status "WARN" "Diagnostic bundle creation failed: $($_.Exception.Message)"
    }
}

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$ScriptBlock,
        [string]$InstalledRoot = ""
    )

    Write-Status "OK" $Label
    try {
        & $ScriptBlock
    } catch {
        Write-Status "FAIL" "$Label failed: $($_.Exception.Message)"
        if ($InstalledRoot) {
            Invoke-DiagnosticBundle -InstalledRoot $InstalledRoot
        }
        exit 1
    }
}

function Invoke-External {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = ""
    )

    Write-Status "OK" $Label
    if ($WorkingDirectory) {
        Push-Location -LiteralPath $WorkingDirectory
    }
    try {
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "$Label exited with code $exitCode"
        }
    } finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$packageRoot = (Resolve-Path (Join-Path $payloadRoot "..")).Path
$targetRoot = Join-Path $env:USERPROFILE "counsel-note-app"
$backupParent = Join-Path $env:USERPROFILE "counsel-note_BACKUPS"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Get-UniqueBackupPath -ParentPath $backupParent -Timestamp $timestamp

Write-Host ""
Write-Host "counsel-note Sebin emergency oneclick restore" -ForegroundColor Cyan
Write-Host "Package: $packageRoot"
Write-Host "Payload: $payloadRoot"
Write-Host "Install target: $targetRoot"
Write-Host ""

Invoke-Step -Label "Checking payload" -ScriptBlock {
    $required = @(
        "app.py",
        "requirements.txt",
        "run_app.bat",
        "install_first.bat",
        "scripts\check_app_health.py",
        "scripts\check_import_contracts.py",
        "scripts\check_release_ready.ps1",
        "scripts\make_diagnostic_bundle.ps1",
        "data\students\google_docs_map.csv",
        "data\students\google_apps_script_webapp_url.txt"
    )
    foreach ($relativePath in $required) {
        $fullPath = Join-Path $payloadRoot $relativePath
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            throw "Required payload file missing: $relativePath"
        }
    }
}

if (Test-Path -LiteralPath $targetRoot) {
    Invoke-Step -Label "Backing up existing counsel-note folder" -ScriptBlock {
        New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
        Move-Item -LiteralPath $targetRoot -Destination $backupRoot
        Write-Status "PASS" "Existing folder moved to: $backupRoot"
    }
} else {
    Write-Status "PASS" "No existing counsel-note folder. Fresh install will be created."
}

Invoke-Step -Label "Copying payload to counsel-note-app" -ScriptBlock {
    New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
    robocopy $payloadRoot $targetRoot /E /XD ".venv" ".agents" ".codex" ".git" "__pycache__" ".pytest_cache" ".mypy_cache" "data\transcripts" "data\google_docs_append_logs" "data\uploads" "data\tmp" "data\diagnostics" "generated" "tmp" "backups" "counsel-note_BACKUPS" /XF "data\local_consumed_admin_notes.json" "*.pyc" "*.pyo" "*.log" "student.js" | Out-Host
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with code $LASTEXITCODE"
    }
    Write-Status "PASS" "Payload copied."
} -InstalledRoot $targetRoot

Invoke-Step -Label "Running install_first.bat" -ScriptBlock {
    $env:COUNSEL_NOTE_NO_PAUSE = "1"
    Push-Location -LiteralPath $targetRoot
    try {
        & cmd.exe /d /c "`"$targetRoot\install_first.bat`""
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "install_first.bat exited with code $exitCode"
        }
    } finally {
        Pop-Location
        Remove-Item Env:\COUNSEL_NOTE_NO_PAUSE -ErrorAction SilentlyContinue
    }
} -InstalledRoot $targetRoot

$python = Join-Path $targetRoot ".venv\Scripts\python.exe"
Invoke-Step -Label "Checking installed Python runtime" -ScriptBlock {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw ".venv Python was not created."
    }
    & $python -c "import sys; print(sys.executable)"
    if ($LASTEXITCODE -ne 0) {
        throw ".venv Python smoke test failed."
    }
} -InstalledRoot $targetRoot

Invoke-Step -Label "Running app health check" -ScriptBlock {
    Push-Location -LiteralPath $targetRoot
    try {
        & $python ".\scripts\check_app_health.py"
        if ($LASTEXITCODE -ne 0) {
            throw "check_app_health.py exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} -InstalledRoot $targetRoot

Invoke-Step -Label "Running import contract check" -ScriptBlock {
    Push-Location -LiteralPath $targetRoot
    try {
        & $python ".\scripts\check_import_contracts.py"
        if ($LASTEXITCODE -ne 0) {
            throw "check_import_contracts.py exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} -InstalledRoot $targetRoot

Invoke-Step -Label "Running release readiness check" -ScriptBlock {
    Push-Location -LiteralPath $targetRoot
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\check_release_ready.ps1"
        if ($LASTEXITCODE -ne 0) {
            throw "check_release_ready.ps1 exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} -InstalledRoot $targetRoot

Write-Status "PASS" "Install and validation completed. Starting app..."
Start-Process -FilePath (Join-Path $targetRoot "run_app.bat") -WorkingDirectory $targetRoot
exit 0
