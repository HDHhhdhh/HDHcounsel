param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function New-TextFromCodePoints {
    param([int[]]$CodePoints)
    return -join ($CodePoints | ForEach-Object { [char]$_ })
}

$KoreanTest = New-TextFromCodePoints @(0xD14C, 0xC2A4, 0xD2B8)
$KoreanStudent = New-TextFromCodePoints @(0xD559, 0xC0DD)
$ReadmeFirstRun = "README_" + (New-TextFromCodePoints @(0xCC98, 0xC74C, 0xC2E4, 0xD589)) + ".txt"
$IconFile = (New-TextFromCodePoints @(0xC0C1, 0xB2F4, 0xC571)) + ".ico"

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

function Test-EntryBanned {
    param([string]$EntryName)
    $normalized = $EntryName -replace "\\", "/"
    $fileName = Split-Path $normalized -Leaf

    $bannedPatterns = @(
        "(^|/)\.venv(/|$)",
        "(^|/)__pycache__(/|$)",
        "(^|/)\.git(/|$)",
        "(^|/)data/uploads(/|$)",
        "(^|/)data/transcripts(/|$)",
        "(^|/)data/tmp(/|$)",
        "(^|/)data/drafts(/|$)",
        "(^|/)data/admin_notes_backups(/|$)",
        "(^|/)_debug_audio(/|$)",
        "(^|/)_admin_api_debug(/|$)",
        "\.pyc$",
        "streamlit\.out\.log$",
        "streamlit\.err\.log$"
    )

    foreach ($pattern in $bannedPatterns) {
        if ($normalized -match $pattern) {
            return $true
        }
    }

    if ($normalized.Contains($KoreanTest)) {
        return $true
    }
    if ($normalized.Contains($KoreanTest + $KoreanStudent)) {
        return $true
    }
    if ($fileName -like "_*.txt") {
        return $true
    }
    if ($fileName -like "*check*.txt") {
        return $true
    }
    if ($fileName -like "*search*.txt") {
        return $true
    }

    return $false
}

function Copy-ReleaseFile {
    param(
        [string]$RelativePath,
        [string]$StageRoot
    )
    $source = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        return
    }
    $destination = Join-Path $StageRoot $RelativePath
    $destinationDir = Split-Path $destination -Parent
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

function Copy-ReleaseDirectory {
    param(
        [string]$RelativePath,
        [string]$StageRoot
    )
    $source = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        return
    }
    $destination = Join-Path $StageRoot $RelativePath
    Get-ChildItem -LiteralPath $source -Recurse -Force | ForEach-Object {
        $childRelative = $_.FullName.Substring($source.Length).TrimStart("\", "/")
        $entryRelative = if ($childRelative) {
            Join-Path $RelativePath $childRelative
        } else {
            $RelativePath
        }

        if (Test-EntryBanned -EntryName $entryRelative) {
            return
        }

        $target = Join-Path $StageRoot $entryRelative
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Path $target -Force | Out-Null
        } else {
            $targetDir = Split-Path $target -Parent
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$desktopCandidates = @()
$projectParent = Split-Path $ProjectRoot -Parent
if ($projectParent -and (Test-Path -LiteralPath $projectParent -PathType Container) -and ((Split-Path $projectParent -Leaf) -eq "Desktop")) {
    $desktopCandidates += $projectParent
}
$desktopCandidates += [Environment]::GetFolderPath("Desktop")
$desktopCandidates += [Environment]::GetFolderPath("DesktopDirectory")
$oneDriveDesktop = Join-Path ([Environment]::GetFolderPath("UserProfile")) "OneDrive\Desktop"
$desktopCandidates += $oneDriveDesktop
$desktopCandidates += $projectParent

$desktop = ""
foreach ($candidate in ($desktopCandidates | Where-Object { $_ } | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
        continue
    }
    $probePath = Join-Path $candidate ".counsel-note-release-write-test-$PID.tmp"
    try {
        Set-Content -LiteralPath $probePath -Value "" -NoNewline -Encoding UTF8
        Remove-Item -LiteralPath $probePath -Force
        $desktop = $candidate
        break
    } catch {
        if (Test-Path -LiteralPath $probePath) {
            Remove-Item -LiteralPath $probePath -Force -ErrorAction SilentlyContinue
        }
    }
}
if (-not $desktop) {
    throw "Writable Desktop path was not found."
}

Write-Host ""
Write-Host "Counsel Note release zip builder" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host ""

$requiredFiles = @(
    "app.py",
    "requirements.txt",
    "run_app.bat",
    "install_first.bat",
    "install_python_first.bat",
    "install_codex_first.bat",
    $ReadmeFirstRun,
    "data/glossary/academy_terms.csv",
    "data/students/google_docs_map.csv",
    "data/students/google_apps_script_webapp_url.txt",
    "data/students/admin_api_base_url.txt",
    "data/students/admin_sid_map.csv",
    "scripts/google_apps_script_doPost.js",
    "scripts/check_normalize_summary.py",
    "scripts/check_release_ready.ps1",
    "tools/ffmpeg/bin/ffmpeg.exe"
)

$requiredDirectories = @(
    "counsel_modules",
    "prompts",
    "data/glossary"
)

$requiredCounselModuleFiles = @(
    "counsel_modules/__init__.py",
    "counsel_modules/admin_utils.py",
    "counsel_modules/google_docs_utils.py",
    "counsel_modules/log_csv_utils.py",
    "counsel_modules/text_utils.py"
)

$requiredPromptFiles = @(
    "prompts/summary_ko.txt"
)

$recommendedFiles = @(
    "README.md",
    $IconFile
)

$missingRequired = @()
foreach ($relativePath in $requiredFiles) {
    $path = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Write-Status "OK" "Required file found: $relativePath"
    } else {
        Write-Status "FAIL" "Required file missing: $relativePath"
        $missingRequired += $relativePath
    }
}

foreach ($relativePath in $requiredDirectories) {
    $path = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $path -PathType Container) {
        Write-Status "OK" "Required folder found: $relativePath"
    } else {
        Write-Status "FAIL" "Required folder missing: $relativePath"
        $missingRequired += $relativePath
    }
}

foreach ($relativePath in $requiredCounselModuleFiles) {
    $path = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Write-Status "OK" "Required counsel module found: $relativePath"
    } else {
        Write-Status "FAIL" "Required counsel module missing: $relativePath"
        $missingRequired += $relativePath
    }
}

foreach ($relativePath in $requiredPromptFiles) {
    $path = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Write-Status "OK" "Required prompt found: $relativePath"
    } else {
        Write-Status "FAIL" "Required prompt missing: $relativePath"
        $missingRequired += $relativePath
    }
}

foreach ($relativePath in $recommendedFiles) {
    $path = Join-Path $ProjectRoot $relativePath
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Write-Status "OK" "Recommended file found: $relativePath"
    } else {
        Write-Status "WARN" "Recommended file missing: $relativePath"
    }
}

$ffmpegBin = Join-Path $ProjectRoot "tools/ffmpeg/bin"
if (Test-Path -LiteralPath $ffmpegBin -PathType Container) {
    Write-Status "OK" "Will include tools/ffmpeg/bin"
} else {
    Write-Status "WARN" "tools/ffmpeg/bin not found. m4a/mp3 transcription may require ffmpeg installation."
}

if ($missingRequired.Count -gt 0) {
    Write-Host ""
    Write-Status "FAIL" "Required project items are missing. Zip was not created."
    Write-Host "Original project missing list:"
    $missingRequired | Sort-Object -Unique | ForEach-Object { Write-Host "- $_" }
    Write-Host ""
    Write-Host "? ???? ??? ?? zip? ?? ???? ???."
    exit 1
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$zipPath = Join-Path $desktop "counsel-note-release-$timestamp.zip"
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "counsel-note-release-$timestamp"

if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

$filesToCopy = @($requiredFiles + $recommendedFiles) | Select-Object -Unique
foreach ($relativePath in $filesToCopy) {
    Copy-ReleaseFile -RelativePath $relativePath -StageRoot $stageRoot
}

Copy-ReleaseDirectory -RelativePath "counsel_modules" -StageRoot $stageRoot
Copy-ReleaseDirectory -RelativePath "prompts" -StageRoot $stageRoot

if (Test-Path -LiteralPath $ffmpegBin -PathType Container) {
    Copy-ReleaseDirectory -RelativePath "tools/ffmpeg/bin" -StageRoot $stageRoot
}

$stagedBanned = Get-ChildItem -LiteralPath $stageRoot -Recurse -Force | Where-Object {
    $relative = $_.FullName.Substring($stageRoot.Length).TrimStart("\", "/")
    Test-EntryBanned -EntryName $relative
}

if ($stagedBanned.Count -gt 0) {
    Write-Host ""
    Write-Status "FAIL" "Staging folder contains banned files."
    $stagedBanned | ForEach-Object {
        $relative = $_.FullName.Substring($stageRoot.Length).TrimStart("\", "/")
        Write-Host "- $relative"
    }
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
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
        if (Test-EntryBanned -EntryName $entryName) {
            return
        }
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
    $badEntries = @()
    $zipEntries = @($archive.Entries | ForEach-Object { $_.FullName -replace "\\", "/" })
    foreach ($entry in $archive.Entries) {
        if (Test-EntryBanned -EntryName $entry.FullName) {
            $badEntries += $entry.FullName
        }
    }
} finally {
    $archive.Dispose()
}

Remove-Item -LiteralPath $stageRoot -Recurse -Force

Write-Host ""
if ($badEntries.Count -gt 0) {
    Write-Status "FAIL" "Zip inspection failed. Banned entries were found."
    $badEntries | ForEach-Object { Write-Host "- $_" }
    Write-Host "Zip path: $zipPath"
    exit 1
}

$requiredZipEntries = @(
    $requiredFiles + $requiredCounselModuleFiles + $requiredPromptFiles
) | ForEach-Object { $_ -replace "\\", "/" } | Select-Object -Unique
$missingZipEntries = @()
foreach ($entryName in $requiredZipEntries) {
    if ($zipEntries -contains $entryName) {
        Write-Status "PASS" "Zip contains: $entryName"
    } else {
        Write-Status "FAIL" "Zip missing: $entryName"
        $missingZipEntries += $entryName
    }
}

$counselModuleEntries = @($zipEntries | Where-Object { $_ -like "counsel_modules/*.py" })
if ($counselModuleEntries.Count -gt 0) {
    Write-Status "PASS" "Zip contains counsel_modules Python files: $($counselModuleEntries.Count)"
    $counselModuleEntries | Sort-Object | ForEach-Object { Write-Host "- $_" }
} else {
    Write-Status "FAIL" "Zip does not contain counsel_modules Python files."
    $missingZipEntries += "counsel_modules/*.py"
}

if ($missingZipEntries.Count -gt 0) {
    Write-Host ""
    Write-Status "FAIL" "Zip internal inspection failed. Required entries are missing."
    Write-Host "Zip internal missing list:"
    $missingZipEntries | Sort-Object -Unique | ForEach-Object { Write-Host "- $_" }
    Write-Host ""
    Write-Host "? ???? ??? ?? zip? ?? ???? ???."
    Write-Host "Zip path: $zipPath"
    exit 1
}

Write-Status "PASS" "Final result: PASS - all required project and zip entries were found. Ready to share with assistants"
Write-Host "Zip path: $zipPath"
exit 0
