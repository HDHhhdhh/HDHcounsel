param(
    [switch]$DryRun,
    [string]$UpdateSource = "",
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$DefaultUpdateSource = "C:\Users\idotd\OneDrive\Desktop\sebin-updates"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CurrentRoot = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
$DefaultInstallRoot = Join-Path $env:USERPROFILE "counsel-note-app"

function Write-Status {
    param([string]$Level, [string]$Message)
    $color = switch ($Level) {
        "PASS" { "Green" }
        "OK" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        default { "White" }
    }
    Write-Host "[$Level] $Message" -ForegroundColor $color
}

function Get-InstallRoot {
    if ($InstallRoot) {
        return $InstallRoot
    }
    if (Test-Path -LiteralPath (Join-Path $DefaultInstallRoot "app.py") -PathType Leaf) {
        return $DefaultInstallRoot
    }
    if (Test-Path -LiteralPath (Join-Path $CurrentRoot "app.py") -PathType Leaf) {
        return $CurrentRoot
    }
    return $DefaultInstallRoot
}

function Get-UpdateSourceRoot {
    param([string]$Root)
    if ($UpdateSource) {
        return $UpdateSource
    }
    $localSourceFile = Join-Path $Root "data\local_update_source.txt"
    if (Test-Path -LiteralPath $localSourceFile -PathType Leaf) {
        $value = (Get-Content -LiteralPath $localSourceFile -Raw -Encoding UTF8).Trim()
        if ($value) {
            return $value
        }
    }
    return $DefaultUpdateSource
}

function Get-DesktopPath {
    $default = Join-Path $env:USERPROFILE "Desktop"
    if (Test-Path -LiteralPath $default -PathType Container) {
        return $default
    }
    $shell = [Environment]::GetFolderPath("Desktop")
    if ($shell -and (Test-Path -LiteralPath $shell -PathType Container)) {
        return $shell
    }
    return (Split-Path -Parent $Root)
}

function Read-LatestManifest {
    param([string]$SourceRoot)
    $latestPath = Join-Path $SourceRoot "latest.json"
    if (-not (Test-Path -LiteralPath $latestPath -PathType Leaf)) {
        throw "latest.json not found in update source: $SourceRoot"
    }
    try {
        return Get-Content -LiteralPath $latestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "latest.json could not be read: $($_.Exception.Message)"
    }
}

function Get-WorkingPython {
    param([string]$Root)
    $candidates = @(
        [PSCustomObject]@{ Name = ".venv"; FilePath = (Join-Path $Root ".venv\Scripts\python.exe"); PrefixArgs = @() },
        [PSCustomObject]@{ Name = "py -3"; FilePath = "py"; PrefixArgs = @("-3") },
        [PSCustomObject]@{ Name = "python"; FilePath = "python"; PrefixArgs = @() },
        [PSCustomObject]@{ Name = "python3"; FilePath = "python3"; PrefixArgs = @() }
    )
    foreach ($candidate in $candidates) {
        $isPath = ($candidate.FilePath -match "[\\/]")
        if ($isPath -and -not (Test-Path -LiteralPath $candidate.FilePath)) {
            continue
        }
        if (-not $isPath -and -not (Get-Command $candidate.FilePath -ErrorAction SilentlyContinue)) {
            continue
        }
        $args = @()
        if ($candidate.PrefixArgs) {
            $args += $candidate.PrefixArgs
        }
        $args += @("-c", "import sys; print(sys.executable)")
        & $candidate.FilePath @args >$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }
    return $null
}

function Invoke-Python {
    param(
        [object]$Python,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    $args = @()
    if ($Python.PrefixArgs) {
        $args += $Python.PrefixArgs
    }
    $args += $Arguments
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $Python.FilePath @args
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

function Invoke-DiagnosticBundle {
    param([string]$Root)
    try {
        $script = Join-Path $Root "scripts\make_diagnostic_bundle.ps1"
        if (Test-Path -LiteralPath $script -PathType Leaf) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $script
        }
    } catch {
        Write-Status "WARN" "Diagnostic bundle creation failed: $($_.Exception.Message)"
    }
}

function Read-InstalledBuildInfo {
    param([string]$Root)
    $path = Join-Path $Root "BUILD_INFO.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Restore-FromBackup {
    param(
        [string]$BackupRoot,
        [string]$TargetRoot
    )
    if (-not (Test-Path -LiteralPath $BackupRoot -PathType Container)) {
        Write-Status "WARN" "Backup folder missing; restore skipped."
        return
    }
    Write-Status "WARN" "Restoring app files from backup without deleting user data..."
    robocopy $BackupRoot $TargetRoot /E /XD ".venv" ".agents" ".codex" ".git" "__pycache__" "data\transcripts" "data\google_docs_append_logs" "data\uploads" "data\tmp" /XF "*.pyc" "*.pyo" "*.log" | Out-Host
    if ($LASTEXITCODE -ge 8) {
        Write-Status "WARN" "Restore robocopy returned code $LASTEXITCODE"
    }
}

function Test-InstalledApp {
    param([string]$Root)
    $python = Get-WorkingPython -Root $Root
    if (-not $python) {
        throw "No working Python was found for validation."
    }
    $contractExit = Invoke-Python -Python $python -Arguments @("-B", ".\scripts\check_import_contracts.py") -WorkingDirectory $Root
    if ($contractExit -ne 0) {
        throw "import contract failed"
    }
    $healthExit = Invoke-Python -Python $python -Arguments @("-B", ".\scripts\check_app_health.py") -WorkingDirectory $Root
    if ($healthExit -ne 0) {
        throw "health check failed"
    }
}

$Root = Get-InstallRoot
$SourceRoot = Get-UpdateSourceRoot -Root $Root

Write-Host ""
Write-Host "Counsel Note Sebin update checker" -ForegroundColor Cyan
Write-Host "Install root: $Root"
Write-Host "Update source: $SourceRoot"
Write-Host "Dry run: $DryRun"
Write-Host ""
Write-Status "WARN" "Close the counsel-note app and browser before applying updates."

if ($DryRun) {
    Write-Status "OK" "Would read latest.json from update source."
    if (Test-Path -LiteralPath (Join-Path $SourceRoot "latest.json") -PathType Leaf) {
        $latest = Read-LatestManifest -SourceRoot $SourceRoot
        Write-Status "OK" "Latest version available: $($latest.version)"
        if ($latest.created_at) {
            Write-Status "OK" "Latest last_updated_at: $($latest.created_at)"
        }
        Write-Status "OK" "Would copy ZIP locally, verify sha256, backup current folder, apply payload, then run health checks."
    } else {
        Write-Status "WARN" "latest.json not found. Set data/local_update_source.txt if the share folder path is different."
    }
    Write-Status "OK" "No files were copied or changed because -DryRun was used."
    exit 0
}

try {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "Install root does not exist: $Root"
    }
    if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
        throw "Update source folder does not exist: $SourceRoot"
    }

    $latest = Read-LatestManifest -SourceRoot $SourceRoot
    if ($latest.app -ne "counsel-note" -or $latest.target -ne "sebin") {
        throw "latest.json target does not match counsel-note/sebin"
    }
    $zipName = [string]$latest.zip_name
    if (-not $zipName -or $zipName -notmatch "^counsel-note-sebin-update-\d{8}-\d{6}\.zip$") {
        throw "latest.json zip_name is invalid"
    }
    $sourceZip = Join-Path $SourceRoot $zipName
    if (-not (Test-Path -LiteralPath $sourceZip -PathType Leaf)) {
        throw "Update ZIP not found: $zipName"
    }

    $localVersionFile = Join-Path $Root "data\local_app_version.txt"
    $appVersionFile = Join-Path $Root "APP_VERSION.txt"
    $currentVersion = ""
    if (Test-Path -LiteralPath $localVersionFile -PathType Leaf) {
        $currentVersion = (Get-Content -LiteralPath $localVersionFile -Raw -Encoding UTF8).Trim()
    } elseif (Test-Path -LiteralPath $appVersionFile -PathType Leaf) {
        $currentVersion = (Get-Content -LiteralPath $appVersionFile -Raw -Encoding UTF8).Trim()
    }
    if ($currentVersion -and $currentVersion -eq [string]$latest.version) {
        Write-Status "PASS" "Already up to date: $currentVersion"
        exit 0
    }

    Write-Host "Current version: $currentVersion"
    Write-Host "Latest version: $($latest.version)"
    $answer = Read-Host "Apply this update now? Type Y to continue"
    if ($answer -notmatch "^(Y|y|YES|yes|예)$") {
        Write-Status "WARN" "Update canceled by user."
        exit 0
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "counsel-note-sebin-update-$timestamp"
    $localZip = Join-Path $tempRoot $zipName
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

    Copy-Item -LiteralPath $sourceZip -Destination $localZip -Force
    $actualHash = (Get-FileHash -LiteralPath $localZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne ([string]$latest.sha256).ToLowerInvariant()) {
        throw "sha256 mismatch"
    }
    Write-Status "PASS" "ZIP sha256 verified."

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($localZip, $tempRoot)
    $payloadRoot = Join-Path $tempRoot "counsel-note-sebin-update\payload"
    if (-not (Test-Path -LiteralPath (Join-Path $payloadRoot "app.py") -PathType Leaf)) {
        throw "payload app.py missing after extraction"
    }

    $backupRoot = Join-Path (Split-Path -Parent $Root) "counsel-note_BACKUP_$timestamp"
    Write-Status "OK" "Creating backup: $backupRoot"
    robocopy $Root $backupRoot /E /XD ".venv" ".agents" ".codex" ".git" "__pycache__" "data\transcripts" "data\google_docs_append_logs" "data\uploads" "data\tmp" /XF "*.pyc" "*.pyo" "*.log" | Out-Host
    if ($LASTEXITCODE -ge 8) {
        throw "backup robocopy failed with code $LASTEXITCODE"
    }

    try {
        Write-Status "OK" "Applying payload including data/students. Local consumed registry stays excluded."
        robocopy $payloadRoot $Root /E /XD ".venv" ".agents" ".codex" ".git" "__pycache__" /XF "data\local_consumed_admin_notes.json" "*.pyc" "*.pyo" "*.log" "student.js" | Out-Host
        if ($LASTEXITCODE -ge 8) {
            throw "payload robocopy failed with code $LASTEXITCODE"
        }

        if (-not (Test-Path -LiteralPath (Join-Path $Root "data\students") -PathType Container)) {
            throw "data/students is missing after update"
        }

        Test-InstalledApp -Root $Root
        New-Item -ItemType Directory -Path (Join-Path $Root "data") -Force | Out-Null
        Set-Content -LiteralPath $localVersionFile -Value ([string]$latest.version) -Encoding UTF8
        Write-Status "PASS" "Update applied successfully."
        $buildInfo = Read-InstalledBuildInfo -Root $Root
        if ($buildInfo -and $buildInfo.last_updated_at) {
            Write-Host "Last updated: $($buildInfo.last_updated_at)"
        }
        Write-Host "Backup folder: $backupRoot"
        exit 0
    } catch {
        Write-Status "FAIL" "Update failed: $($_.Exception.Message)"
        Restore-FromBackup -BackupRoot $backupRoot -TargetRoot $Root
        Invoke-DiagnosticBundle -Root $Root
        exit 1
    }
} catch {
    Write-Status "FAIL" $_.Exception.Message
    if (Test-Path -LiteralPath $Root -PathType Container) {
        Invoke-DiagnosticBundle -Root $Root
    }
    exit 1
}
