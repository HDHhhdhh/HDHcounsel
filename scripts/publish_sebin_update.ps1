param(
    [switch]$DryRun,
    [string]$UpdateShareRoot = "C:\Users\idotd\OneDrive\Desktop\sebin-updates",
    [string]$Notes = "counsel-note Sebin update"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Desktop = "C:\Users\idotd\OneDrive\Desktop"
if (-not (Test-Path -LiteralPath $Desktop -PathType Container)) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
}

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

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$ScriptBlock
    )
    Write-Status "OK" $Label
    & $ScriptBlock
}

function Get-LatestUpdateZip {
    param([string]$Folder)
    return Get-ChildItem -LiteralPath $Folder -Filter "counsel-note-sebin-update-*.zip" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Get-ZipTimestampVersion {
    param([string]$ZipName)
    if ($ZipName -match "counsel-note-sebin-update-(\d{8})-(\d{6})\.zip$") {
        $date = $Matches[1]
        $time = $Matches[2]
        return "$($date.Substring(0,4)).$($date.Substring(4,2)).$($date.Substring(6,2))-$($time.Substring(0,2))$($time.Substring(2,2))$($time.Substring(4,2))"
    }
    return (Get-Date -Format "yyyy.MM.dd-HHmmss")
}

function Test-UpdateZipSafety {
    param([string]$ZipPath)
    $checkScript = Join-Path $ProjectRoot "scripts\check_sebin_update_zip.ps1"
    if (-not (Test-Path -LiteralPath $checkScript -PathType Leaf)) {
        throw "check_sebin_update_zip.ps1 is missing"
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $checkScript -ZipPath $ZipPath
    if ($LASTEXITCODE -ne 0) {
        throw "update zip validation failed"
    }
}

function Read-BuildInfo {
    $path = Join-Path $ProjectRoot "BUILD_INFO.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Status "WARN" "BUILD_INFO.json could not be read: $($_.Exception.Message)"
        return $null
    }
}

Write-Host ""
Write-Host "Counsel Note Sebin update publisher" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Share folder: $UpdateShareRoot"
Write-Host "Dry run: $DryRun"
Write-Host ""

if ($DryRun) {
    Write-Status "OK" "Would run scripts/check_release_ready.ps1"
    Write-Status "OK" "Would create a fresh counsel-note-sebin-update ZIP"
    Write-Status "OK" "Would validate the latest update ZIP"
    Write-Status "OK" "Would create share folder if missing: $UpdateShareRoot"
    Write-Status "OK" "Would copy ZIP to share folder and write latest.json"
    Write-Status "OK" "Would publish BUILD_INFO last_updated_at as latest.json created_at when available"
    Write-Status "OK" "No files were written because -DryRun was used"
    exit 0
}

Push-Location -LiteralPath $ProjectRoot
try {
    Invoke-Step -Label "Running release readiness check" -ScriptBlock {
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\check_release_ready.ps1"
        if ($LASTEXITCODE -ne 0) {
            throw "check_release_ready.ps1 failed"
        }
    }

    Invoke-Step -Label "Creating Sebin update ZIP" -ScriptBlock {
        & powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\make_sebin_update_zip.ps1"
        if ($LASTEXITCODE -ne 0) {
            throw "make_sebin_update_zip.ps1 failed"
        }
    }

    $latestZip = Get-LatestUpdateZip -Folder $Desktop
    if (-not $latestZip) {
        throw "No counsel-note-sebin-update ZIP was created on Desktop"
    }

    Invoke-Step -Label "Validating latest update ZIP" -ScriptBlock {
        Test-UpdateZipSafety -ZipPath $latestZip.FullName
    }

    Invoke-Step -Label "Preparing share folder" -ScriptBlock {
        New-Item -ItemType Directory -Path $UpdateShareRoot -Force | Out-Null
    }

    $targetZipPath = Join-Path $UpdateShareRoot $latestZip.Name
    Invoke-Step -Label "Copying ZIP to share folder" -ScriptBlock {
        Copy-Item -LiteralPath $latestZip.FullName -Destination $targetZipPath -Force
    }

    $sha256 = (Get-FileHash -LiteralPath $targetZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $version = Get-ZipTimestampVersion -ZipName $latestZip.Name
    $buildInfo = Read-BuildInfo
    $lastUpdatedAt = ""
    if ($buildInfo -and $buildInfo.last_updated_at) {
        $lastUpdatedAt = [string]$buildInfo.last_updated_at
    } else {
        $lastUpdatedAt = (Get-Date).ToString("s")
    }
    $latest = [ordered]@{
        app = "counsel-note"
        target = "sebin"
        version = $version
        zip_name = $latestZip.Name
        sha256 = $sha256
        created_at = $lastUpdatedAt
        notes = $Notes
    }
    $latestPath = Join-Path $UpdateShareRoot "latest.json"
    Invoke-Step -Label "Writing latest.json" -ScriptBlock {
        $latest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $latestPath -Encoding UTF8
    }

    Write-Host ""
    Write-Status "PASS" "Sebin update published"
    Write-Host "Share folder: $UpdateShareRoot"
    Write-Host "ZIP: $targetZipPath"
    Write-Host "SHA256: $sha256"
    Write-Host "latest.json: $latestPath"
    Write-Host "Last updated: $lastUpdatedAt"
    exit 0
} finally {
    Pop-Location
}
