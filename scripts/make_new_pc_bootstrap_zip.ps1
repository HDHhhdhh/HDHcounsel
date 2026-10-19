param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputDir = "",
    [switch]$DisableRecordingAutoCleanup
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$PackageDisplayName = "5A Connect Log 새 컴퓨터 실사용 설치"
$PackageFileNamePrefix = "5A-Connect-Log-새컴퓨터-실사용설치"
$PackageRootName = $PackageFileNamePrefix
$PackageType = "new-computer-real-use-install"
$ManifestFileName = "new_pc_real_use_install_manifest.txt"
$NewPcInstallBase = "새PC_처음설치"
$NewPcInstallBat = "$NewPcInstallBase.bat"
$NewPcInstallPs1 = "$NewPcInstallBase.ps1"
$ReadmeNewPc = "README_$NewPcInstallBase.txt"
$CodexInstallGuide = "CODEX_$NewPcInstallBase.md"
$DiagnosticBundleBat = "진단_패키지_생성.bat"
$SebinUpdateCheckBat = "세빈_업데이트_확인.bat"
$EmergencyInstallBat = "세빈_긴급복구_원클릭설치.bat"
$ReadmeFirstRun = "README_처음실행.txt"
$ReadmeSebinUpdate = "README_세빈업데이트.txt"
$ReadmeSebinAutoUpdate = "README_세빈_자동업데이트.txt"
$ReadmeSebinEmergency = "README_세빈_긴급복구.txt"
$RecordingAutoCleanupSettingRelativePath = "data\students\recording_auto_cleanup_enabled.txt"

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

function Test-BootstrapBannedEntry {
    param([string]$EntryName)

    $normalized = $EntryName -replace "\\", "/"
    $fileName = Split-Path $normalized -Leaf
    $patterns = @(
        "(^|/)\.venv(/|$)",
        "(^|/)\.agents(/|$)",
        "(^|/)\.codex(/|$)",
        "(^|/)\.codex_drive_download(/|$)",
        "(^|/)\.git(/|$)",
        "(^|/)__pycache__(/|$)",
        "(^|/)\.pytest_cache(/|$)",
        "(^|/)\.mypy_cache(/|$)",
        "(^|/)generated(/|$)",
        "(^|/)tmp(/|$)",
        "(^|/)backups(/|$)",
        "(^|/)counsel-note_BACKUPS(/|$)",
        "(^|/)_admin_api_debug(/|$)",
        "(^|/)_debug_audio(/|$)",
        "(^|/)test-page-pipeline(/|$)",
        "(^|/)data/admin_notes_backups(/|$)",
        "(^|/)data/archive(/|$)",
        "(^|/)data/diagnostics(/|$)",
        "(^|/)data/drafts(/|$)",
        "(^|/)data/google_docs_append_logs(/|$)",
        "(^|/)data/local_consumed_admin_notes\.json$",
        "(^|/)data/local_log_csv_processing_history\.json$",
        "(^|/)data/results(/|$)",
        "(^|/)data/tmp(/|$)",
        "(^|/)data/transcripts(/|$)",
        "(^|/)data/uploads(/|$)",
        "(^|/)data/recordings(/|$)",
        "(^|/)data/students/_backups(/|$)",
        "(^|/)student\.js$",
        "\.bak($|[-_.])",
        "\.pyc$",
        "\.pyo$",
        "\.log$",
        "\.zip$",
        "\.(wav|mp3|m4a|webm|mp4|flac|aac|srt|vtt)$",
        "(^|/).*transcript.*\.(txt|json|csv)$",
        "(^|/).*result.*\.csv$",
        "(^|/).*results.*\.csv$",
        "(^|/).*log.*\.csv$"
    )

    foreach ($pattern in $patterns) {
        if ($normalized -match $pattern) {
            return $true
        }
    }
    return $fileName -eq "student.js"
}

function Copy-BootstrapFile {
    param(
        [string]$RelativePath,
        [string]$DestinationRoot,
        [switch]$Required
    )

    if (Test-BootstrapBannedEntry -EntryName $RelativePath) {
        if ($Required) {
            throw "Required file is blocked by banned rule: $RelativePath"
        }
        Write-Status "WARN" "Skipped banned optional file: $RelativePath"
        return
    }

    $source = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        if ($Required) {
            throw "Required file missing: $RelativePath"
        }
        Write-Status "WARN" "Optional file missing: $RelativePath"
        return
    }

    $destination = Join-Path $DestinationRoot $RelativePath
    $destinationDir = Split-Path $destination -Parent
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
    Write-Status "OK" "Included file: $RelativePath"
}

function Copy-BootstrapDirectory {
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

    $copiedFiles = 0
    Get-ChildItem -LiteralPath $source -Recurse -Force | ForEach-Object {
        $childRelative = $_.FullName.Substring($source.Length).TrimStart("\", "/")
        $entryRelative = if ($childRelative) {
            Join-Path $RelativePath $childRelative
        } else {
            $RelativePath
        }

        if (Test-BootstrapBannedEntry -EntryName $entryRelative) {
            return
        }

        $target = Join-Path $DestinationRoot $entryRelative
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Path $target -Force | Out-Null
        } else {
            $targetDir = Split-Path $target -Parent
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
            $copiedFiles += 1
        }
    }
    Write-Status "OK" "Included folder: $RelativePath ($copiedFiles file(s))"
}

function New-Readme {
    param([string]$DestinationPath)

    $content = @'
5A Connect Log 새 컴퓨터 실사용 설치

이 파일은 5A Connect Log를 새 컴퓨터에 처음 설치해 실사용하기 위한 패키지입니다.

1. ZIP 압축을 풉니다.
2. 새PC_처음설치.bat을 실행합니다.
   Python을 찾을 수 없다고 나오면 사용자 폴더의 counsel-note-app\install_python_first.bat을 실행한 뒤, 압축을 푼 폴더의 새PC_처음설치.bat을 다시 실행합니다.
3. 설치가 끝나면 사용자 폴더의 counsel-note-app 폴더로 이동합니다.
4. run_app.bat을 실행합니다.
5. 앱이 켜지면 학생 목록, 녹음 업로드, 정리본 생성, Docs 저장 준비 상태를 확인합니다.
6. 오류가 나면 설치된 counsel-note-app 폴더의 진단_패키지_생성.bat을 실행한 뒤, 생성된 diagnostic ZIP과 화면 캡처를 전달하세요.

전제: Codex CLI 연결은 이미 되어 있다고 가정합니다.
실사용에 필요한 학생 설정 데이터(data\students)가 포함됩니다.
'@
    Set-Content -LiteralPath $DestinationPath -Value $content -Encoding UTF8
}

function New-CodexInstallGuide {
    param(
        [string]$DestinationPath,
        [bool]$RecordingAutoCleanupDisabled
    )

    $content = @'
# 5A Connect Log 새 PC 설치 안내

이 ZIP은 프로젝트 파일이 전혀 없는 Windows 컴퓨터에 5A Connect Log를 설치하기 위한 전체 패키지입니다. Codex가 설치와 로컬 검증을 맡고, 사용자는 필요한 Windows 설치 확인창만 승인하면 됩니다.

## 설치 절차

1. ZIP을 일반 폴더에 완전히 압축 해제합니다. ZIP 안에서 파일을 직접 실행하지 않습니다.
2. 압축 해제한 최상위 폴더에서 `새PC_처음설치.bat`을 실행합니다.
3. Python을 찾지 못하면 `%USERPROFILE%\counsel-note-app\install_python_first.bat`을 실행합니다. 설치가 끝나면 새 PowerShell을 열고 최상위 폴더의 `새PC_처음설치.bat`을 다시 실행합니다.
4. Codex CLI 검사에서 실패하면 `%USERPROFILE%\counsel-note-app\install_codex_first.bat`을 실행하고 `codex login`을 완료한 뒤 설치 검사를 다시 실행합니다.
5. 설치가 끝나면 `%USERPROFILE%\counsel-note-app\run_app.bat`을 실행합니다.

## 설치 후 로컬 검증

설치 폴더에서 다음 명령을 실행하고 모두 성공하는지 확인합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_quick.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_release_ready.ps1
```

로컬 실행기 상태 주소는 `http://127.0.0.1:8765/health`, 앱 실행 주소는 `http://127.0.0.1:8765/open`입니다.

## 안전 범위

- 실사용 학생/Docs/ADMIN 설정은 패키지에 포함되어 있습니다.
- 기존 consumed 기록, CSV 처리 이력, 로그, CSV 결과, 녹음, 전사, 백업, 가상환경은 포함되지 않습니다.
- 검증 중 실제 Google Docs POST, ADMIN POST/PATCH/DELETE, Apps Script 배포를 실행하지 않습니다.
'@
    if ($RecordingAutoCleanupDisabled) {
        $content += [Environment]::NewLine + "- 이 패키지는 녹음 파일 자동삭제가 비활성화되어 있습니다. 설치 후 이 설정을 변경하지 마세요."
    }
    Set-Content -LiteralPath $DestinationPath -Value $content -Encoding UTF8
}

function New-PackageManifest {
    param(
        [string]$DestinationPath,
        [string]$BuildVersion,
        [int]$PayloadFileCount,
        [int]$StudentFileCount,
        [bool]$RecordingAutoCleanupDisabled
    )

    $manifestLines = @(
        "$PackageDisplayName manifest",
        "",
        "created_at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")",
        "package_name: $PackageFileNamePrefix",
        "package_display_name: $PackageDisplayName",
        "app_version: $BuildVersion",
        "build_channel: $PackageType",
        "package_type: $PackageType",
        "payload_file_count: $PayloadFileCount",
        "data_students_file_count: $StudentFileCount",
        "",
        "included_policy:",
        "- 이 파일은 5A Connect Log를 새 컴퓨터에 처음 설치해 실사용하기 위한 패키지입니다.",
        "- 상담 녹음/음성 업로드, 전사/정리본 생성, 학생별 Google Docs 저장 준비에 필요한 앱 파일을 포함합니다.",
        "- 실사용에 필요한 학생 설정 데이터(data/students)가 포함됩니다.",
        "- app.py, counsel_modules, prompts, run/install scripts, checks, diagnostics, and ffmpeg are included",
        "- Codex CLI connection is assumed to already exist on the new PC",
        "",
        "excluded_policy:",
        "- data/local_consumed_admin_notes.json is not included",
        "- data/local_log_csv_processing_history.json is not included",
        "- logs, CSV results, recordings, transcripts, diagnostics, generated files, caches, backups, and temporary files are not included",
        "- .venv, .agents, .codex, .codex_drive_download, .git, pyc, pyo, log files, and ZIP files are not included",
        "",
        "notes:",
        "- data/students is required real-use configuration data",
        "- no Google Docs POST is executed by this builder",
        "- no admin POST/PATCH/DELETE is executed by this builder",
        "- no Apps Script deployment or Sebin publish is executed by this builder"
    )
    if ($RecordingAutoCleanupDisabled) {
        $manifestLines += "- recording auto cleanup is disabled for this package"
    }
    Set-Content -LiteralPath $DestinationPath -Value ($manifestLines -join [Environment]::NewLine) -Encoding UTF8
}

function Test-RequirementsForRealUse {
    param([string]$PayloadRoot)

    $requirementsPath = Join-Path $PayloadRoot "requirements.txt"
    if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
        throw "requirements.txt missing from payload."
    }

    $requirementsText = Get-Content -LiteralPath $requirementsPath -Raw -Encoding UTF8
    $requiredPackages = @("streamlit", "faster-whisper", "requests")
    foreach ($packageName in $requiredPackages) {
        if ($requirementsText -notmatch "(?im)^\s*$([regex]::Escape($packageName))\s*($|[<>=#])") {
            throw "requirements.txt missing required package: $packageName"
        }
    }
    Write-Status "PASS" "requirements.txt includes Streamlit, audio transcription, and HTTP packages."
}

function Get-ForbiddenPolicyTerms {
    return @(
        ("외부" + " 공유" + " 금지"),
        ("공유" + " 금지"),
        ("민감" + "정보"),
        ("학생 정보" + "라서 " + "위험"),
        ("do not " + "share" + " externally"),
        ("share" + " externally"),
        ("sensi" + "tive")
    )
}

function Test-TextPolicy {
    param([string]$Root)

    $forbiddenTerms = Get-ForbiddenPolicyTerms
    $textExtensions = @(".txt", ".ps1", ".bat", ".json", ".md")
    $badTextFiles = @()

    Get-ChildItem -LiteralPath $Root -Recurse -File -Force | ForEach-Object {
        if ($textExtensions -notcontains $_.Extension.ToLowerInvariant()) {
            return
        }
        $text = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8
        foreach ($term in $forbiddenTerms) {
            if ($text.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $relative = $_.FullName.Substring($Root.Length).TrimStart("\", "/")
                $badTextFiles += $relative
                break
            }
        }
    }

    if ($badTextFiles.Count -gt 0) {
        Write-Status "FAIL" "Package text contains blocked policy wording."
        $badTextFiles | Sort-Object -Unique | ForEach-Object { Write-Host "- $_" }
        throw "Blocked policy wording found in package text."
    }
    Write-Status "PASS" "Package text has no blocked policy wording."
}

function New-TopLevelInstallBat {
    param([string]$DestinationPath)

    $content = @"
@echo off
chcp 65001 > nul
setlocal EnableExtensions

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0$NewPcInstallPs1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo 새 PC 처음 설치가 실패했습니다. 위 오류를 확인하세요.
  pause
  exit /b %RESULT%
)

echo 새 PC 처음 설치가 완료되었습니다.
echo 이제 run_app.bat을 실행하세요.
pause
endlocal
exit /b 0
"@
    Set-Content -LiteralPath $DestinationPath -Value $content -Encoding UTF8
}

function New-TopLevelInstallPs1 {
    param([string]$DestinationPath)

    $content = @'
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$payload = Join-Path $PSScriptRoot "payload"
$target = Join-Path $env:USERPROFILE "counsel-note-app"
$backupRoot = Join-Path $env:USERPROFILE "counsel-note_BACKUPS"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $backupRoot "new_pc_install_backup_$timestamp"

Write-Host "counsel-note / 5A Connect Log 새 PC 설치"
Write-Host "Payload: $payload"
Write-Host "Target : $target"

if (-not (Test-Path -LiteralPath $payload -PathType Container)) {
    throw "payload 폴더를 찾을 수 없습니다. ZIP을 다시 압축 해제하세요."
}

if (Test-Path -LiteralPath $target) {
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Write-Host "기존 counsel-note 폴더를 백업합니다: $backup"
    Move-Item -LiteralPath $target -Destination $backup
}

New-Item -ItemType Directory -Path $target -Force | Out-Null
Get-ChildItem -LiteralPath $payload -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
}

Set-Location -LiteralPath $target
$env:COUNSEL_NOTE_NO_PAUSE = "1"

$runtimeDirs = @(
    "tmp",
    "generated",
    "data\diagnostics",
    "data\transcripts",
    "data\uploads",
    "data\tmp",
    "data\tmp\audio_for_whisper",
    "data\google_docs_append_logs",
    "data\admin_notes_backups",
    "_debug_audio\extract_errors",
    "_admin_api_debug"
)
foreach ($relativeDir in $runtimeDirs) {
    New-Item -ItemType Directory -Path (Join-Path $target $relativeDir) -Force | Out-Null
}

$requiredPaths = @(
    @{ Label = "ffmpeg.exe"; Path = "tools\ffmpeg\bin\ffmpeg.exe"; Type = "Leaf" },
    @{ Label = "학생 설정 데이터"; Path = "data\students"; Type = "Container" },
    @{ Label = "Google Docs 매핑"; Path = "data\students\google_docs_map.csv"; Type = "Leaf" },
    @{ Label = "Google Apps Script URL"; Path = "data\students\google_apps_script_webapp_url.txt"; Type = "Leaf" },
    @{ Label = "admin SID 매핑"; Path = "data\students\admin_sid_map.csv"; Type = "Leaf" },
    @{ Label = "admin API URL"; Path = "data\students\admin_api_base_url.txt"; Type = "Leaf" },
    @{ Label = "정리본 프롬프트"; Path = "prompts\summary_ko.txt"; Type = "Leaf" },
    @{ Label = "Docs 저장 모듈"; Path = "counsel_modules\google_docs_utils.py"; Type = "Leaf" },
    @{ Label = "CSV/Docs 결과 분류 모듈"; Path = "counsel_modules\log_csv_utils.py"; Type = "Leaf" },
    @{ Label = "전사/정리본 텍스트 모듈"; Path = "counsel_modules\text_utils.py"; Type = "Leaf" }
)
foreach ($item in $requiredPaths) {
    $fullPath = Join-Path $target $item.Path
    if (-not (Test-Path -LiteralPath $fullPath -PathType $item.Type)) {
        throw "$($item.Label)을 찾을 수 없습니다: $($item.Path)"
    }
}

if (-not (Test-Path -LiteralPath ".\install_first.bat" -PathType Leaf)) {
    throw "install_first.bat이 설치 대상에 없습니다."
}

Write-Host ""
Write-Host "Python 가상환경과 requirements 설치를 시작합니다."
& ".\install_first.bat"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "install_first.bat 실패. Python이 없으면 install_python_first.bat을 먼저 실행하세요."
    Write-Host "계속 실패하면 진단_패키지_생성.bat 실행 후 ZIP과 화면 캡처를 전달하세요."
    exit $LASTEXITCODE
}

$python = Join-Path $target ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw ".venv Python을 찾을 수 없습니다. install_first.bat 로그를 확인하세요."
}

Write-Host ""
Write-Host "실사용 모듈 import 검사를 실행합니다."
& $python -c "import streamlit, requests, faster_whisper; import counsel_modules.text_utils, counsel_modules.google_docs_utils, counsel_modules.log_csv_utils, counsel_modules.admin_utils"
if ($LASTEXITCODE -ne 0) {
    Write-Host "실사용 모듈 import 실패. install_first.bat 로그와 requirements 설치 상태를 확인하세요."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "설치 후 health/import 검사를 실행합니다."
& $python ".\scripts\check_app_health.py" "--fast"
if ($LASTEXITCODE -ne 0) {
    Write-Host "health check 실패. 진단_패키지_생성.bat 실행 후 ZIP과 화면 캡처를 전달하세요."
    exit $LASTEXITCODE
}

& $python ".\scripts\check_import_contracts.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "import contract 검사 실패. 진단_패키지_생성.bat 실행 후 ZIP과 화면 캡처를 전달하세요."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "로컬 Connect Log 실행기를 등록합니다."
$launcherInstaller = Join-Path $target "scripts\install_connect_log_http_launcher.ps1"
if (-not (Test-Path -LiteralPath $launcherInstaller -PathType Leaf)) {
    throw "로컬 실행기 설치 스크립트를 찾을 수 없습니다."
}
& powershell -NoProfile -ExecutionPolicy Bypass -File $launcherInstaller -AppRoot $target
if ($LASTEXITCODE -ne 0) {
    throw "로컬 Connect Log 실행기 등록에 실패했습니다."
}

Write-Host ""
Write-Host "설치 완료. 다음 단계: $target\run_app.bat 실행"
exit 0
'@
    Set-Content -LiteralPath $DestinationPath -Value $content -Encoding UTF8
}

function New-TopLevelRunAppBat {
    param([string]$DestinationPath)

    $content = @"
@echo off
chcp 65001 > nul
setlocal EnableExtensions

set "TARGET=%USERPROFILE%\counsel-note-app"
if not exist "%TARGET%\run_app.bat" (
  echo 설치된 counsel-note를 찾을 수 없습니다.
  echo 먼저 새PC_처음설치.bat을 실행하세요.
  pause
  exit /b 1
)

call "%TARGET%\run_app.bat"
endlocal
"@
    Set-Content -LiteralPath $DestinationPath -Value $content -Encoding UTF8
}

function New-PayloadBuildInfo {
    param(
        [string]$PayloadRoot,
        [string]$BuildUpdatedAt,
        [string]$BuildVersion
    )

    Set-Content -LiteralPath (Join-Path $PayloadRoot "APP_VERSION.txt") -Value $BuildVersion -Encoding UTF8
    $buildInfo = [ordered]@{
        last_updated_at = $BuildUpdatedAt
        channel = $PackageType
        package_type = $PackageType
    }
    $buildInfo | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $PayloadRoot "BUILD_INFO.json") -Encoding UTF8
}

function Invoke-PayloadImportContractCheck {
    param([string]$PayloadRoot)

    $python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Write-Status "WARN" "Skipping payload import contract check because .venv Python was not found."
        return
    }
    $previousDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
    try {
        $env:PYTHONDONTWRITEBYTECODE = "1"
        & $python -B (Join-Path $PayloadRoot "scripts\check_import_contracts.py")
    } finally {
        if ($null -eq $previousDontWriteBytecode) {
            Remove-Item Env:\PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
        } else {
            $env:PYTHONDONTWRITEBYTECODE = $previousDontWriteBytecode
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Payload import contract check failed."
    }
    Get-ChildItem -LiteralPath $PayloadRoot -Recurse -Directory -Filter "__pycache__" -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Status "PASS" "Payload import contract check passed."
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
if (-not $OutputDir) {
    $OutputDir = "C:\Users\idotd\OneDrive\Desktop"
    if (-not (Test-Path -LiteralPath $OutputDir -PathType Container)) {
        $OutputDir = [Environment]::GetFolderPath("Desktop")
    }
}
if (-not (Test-Path -LiteralPath $OutputDir -PathType Container)) {
    throw "Output directory was not found: $OutputDir"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$buildUpdatedAt = Get-Date -Format "s"
$buildVersion = "$PackageType-$timestamp"
$zipPath = Join-Path $OutputDir "$PackageFileNamePrefix-$timestamp.zip"
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "$PackageType-$timestamp"
$packageRoot = Join-Path $stageRoot $PackageRootName
$payloadRoot = Join-Path $packageRoot "payload"

$expectedZipNamePattern = "^$([regex]::Escape($PackageFileNamePrefix))-\d{8}-\d{6}\.zip$"
if ((Split-Path -Leaf $zipPath) -notmatch $expectedZipNamePattern) {
    throw "Unexpected ZIP name: $zipPath"
}

Write-Host ""
Write-Host "$PackageDisplayName ZIP builder" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Output zip: $zipPath"
Write-Host ""

if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

try {
    New-Readme -DestinationPath (Join-Path $packageRoot $ReadmeNewPc)
    New-CodexInstallGuide `
        -DestinationPath (Join-Path $packageRoot $CodexInstallGuide) `
        -RecordingAutoCleanupDisabled ([bool]$DisableRecordingAutoCleanup)
    New-TopLevelInstallBat -DestinationPath (Join-Path $packageRoot $NewPcInstallBat)
    New-TopLevelInstallPs1 -DestinationPath (Join-Path $packageRoot $NewPcInstallPs1)
    New-TopLevelRunAppBat -DestinationPath (Join-Path $packageRoot "run_app.bat")

    $requiredPayloadFiles = @(
        "app.py",
        "requirements.txt",
        "run_app.bat",
        "run_app.ps1",
        "install_connect_log_web_link.bat",
        "install_first.bat",
        "install_python_first.bat",
        "install_codex_first.bat",
        "publish_sebin_update.bat",
        "make_sebin_emergency_oneclick_zip.bat",
        "make_new_pc_bootstrap_zip.bat",
        $DiagnosticBundleBat,
        $SebinUpdateCheckBat,
        $EmergencyInstallBat,
        $ReadmeFirstRun,
        $ReadmeSebinUpdate,
        $ReadmeSebinAutoUpdate,
        $ReadmeSebinEmergency,
        "scripts/check_admin_save_ui.py",
        "scripts/check_app_health.py",
        "scripts/check_audio_batch.py",
        "scripts/check_batch_review_counts.py",
        "scripts/check_audio_upload_layout.py",
        "scripts/check_consumed_admin_notes.py",
        "scripts/check_google_apps_script_same_date_policy.js",
        "scripts/check_connect_log_http_launcher.py",
        "scripts/check_csv_persistence.py",
        "scripts/check_csv_worker.py",
        "scripts/check_docs_reconnect.py",
        "scripts/check_google_docs_parallel.py",
        "scripts/check_google_docs_transport.py",
        "scripts/check_import_contracts.py",
        "scripts/check_log_csv_batch_state.py",
        "scripts/check_log_csv_controls.py",
        "scripts/check_log_csv_processing_history.py",
        "scripts/check_normalize_summary.py",
        "scripts/check_quick.ps1",
        "scripts/check_release_ready.ps1",
        "scripts/check_runtime_stability.py",
        "scripts/check_sebin_emergency_zip.ps1",
        "scripts/check_sebin_update_zip.ps1",
        "scripts/check_ui_refresh.py",
        "scripts/codex_map.py",
        "scripts/google_apps_script_doPost.js",
        "scripts/connect_log_http_launcher.py",
        "scripts/install_connect_log_http_launcher.ps1",
        "scripts/install_connect_log_protocol.ps1",
        "scripts/make_diagnostic_bundle.ps1",
        "scripts/make_new_pc_bootstrap_zip.ps1",
        "scripts/make_sebin_emergency_oneclick_zip.ps1",
        "scripts/make_sebin_update_zip.ps1",
        "scripts/publish_sebin_update.ps1",
        "scripts/sebin_check_and_apply_update.ps1",
        "scripts/sebin_emergency_oneclick_install.ps1",
        "scripts/ui_contract_fixture.py",
        "scripts/wait_for_streamlit_port.ps1",
        "tools/ffmpeg/bin/ffmpeg.exe"
    )

    foreach ($relativePath in $requiredPayloadFiles) {
        Copy-BootstrapFile -RelativePath $relativePath -DestinationRoot $payloadRoot -Required
    }

    Copy-BootstrapDirectory -RelativePath "counsel_modules" -DestinationRoot $payloadRoot -Required
    Copy-BootstrapDirectory -RelativePath "prompts" -DestinationRoot $payloadRoot -Required
    Copy-BootstrapDirectory -RelativePath "browser_extension" -DestinationRoot $payloadRoot -Required
    Copy-BootstrapDirectory -RelativePath "data/glossary" -DestinationRoot $payloadRoot
    Copy-BootstrapDirectory -RelativePath "data/students" -DestinationRoot $payloadRoot -Required

    if ($DisableRecordingAutoCleanup) {
        $recordingCleanupSettingPath = Join-Path $payloadRoot $RecordingAutoCleanupSettingRelativePath
        $recordingCleanupSettingDir = Split-Path $recordingCleanupSettingPath -Parent
        New-Item -ItemType Directory -Path $recordingCleanupSettingDir -Force | Out-Null
        Set-Content -LiteralPath $recordingCleanupSettingPath -Value "false" -Encoding UTF8
        Write-Status "OK" "Recording auto cleanup disabled in payload."
    }

    New-PayloadBuildInfo -PayloadRoot $payloadRoot -BuildUpdatedAt $buildUpdatedAt -BuildVersion $buildVersion

    $payloadFileCount = (Get-ChildItem -LiteralPath $payloadRoot -Recurse -File -Force | Measure-Object).Count
    $studentFileCount = (Get-ChildItem -LiteralPath (Join-Path $payloadRoot "data\students") -Recurse -File -Force | Measure-Object).Count
    $manifestPath = Join-Path $packageRoot $ManifestFileName
    New-PackageManifest `
        -DestinationPath $manifestPath `
        -BuildVersion $buildVersion `
        -PayloadFileCount $payloadFileCount `
        -StudentFileCount $studentFileCount `
        -RecordingAutoCleanupDisabled ([bool]$DisableRecordingAutoCleanup)
    Test-RequirementsForRealUse -PayloadRoot $payloadRoot
    Test-TextPolicy -Root $packageRoot

    $stagedBanned = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force | Where-Object {
        $relative = $_.FullName.Substring($packageRoot.Length).TrimStart("\", "/")
        Test-BootstrapBannedEntry -EntryName $relative
    }
    if ($stagedBanned.Count -gt 0) {
        Write-Status "FAIL" "Staging folder contains banned entries."
        $stagedBanned | ForEach-Object {
            $relative = $_.FullName.Substring($packageRoot.Length).TrimStart("\", "/")
            Write-Host "- $relative"
        }
        exit 1
    }

    Invoke-PayloadImportContractCheck -PayloadRoot $payloadRoot

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
    } finally {
        $archive.Dispose()
    }

    $badEntries = @()
    foreach ($entry in $zipEntries) {
        $relativeToPackage = $entry -replace "^$PackageRootName/", ""
        if (Test-BootstrapBannedEntry -EntryName $relativeToPackage) {
            $badEntries += $entry
        }
    }
    if ($badEntries.Count -gt 0) {
        Write-Status "FAIL" "Zip contains banned entries."
        $badEntries | ForEach-Object { Write-Host "- $_" }
        exit 1
    }

    $requiredZipEntries = @(
        "$PackageRootName/$ReadmeNewPc",
        "$PackageRootName/$CodexInstallGuide",
        "$PackageRootName/$NewPcInstallBat",
        "$PackageRootName/$NewPcInstallPs1",
        "$PackageRootName/run_app.bat",
        "$PackageRootName/$ManifestFileName",
        "$PackageRootName/payload/app.py",
        "$PackageRootName/payload/APP_VERSION.txt",
        "$PackageRootName/payload/BUILD_INFO.json",
        "$PackageRootName/payload/requirements.txt",
        "$PackageRootName/payload/run_app.bat",
        "$PackageRootName/payload/run_app.ps1",
        "$PackageRootName/payload/install_connect_log_web_link.bat",
        "$PackageRootName/payload/install_first.bat",
        "$PackageRootName/payload/install_python_first.bat",
        "$PackageRootName/payload/scripts/check_quick.ps1",
        "$PackageRootName/payload/scripts/check_release_ready.ps1",
        "$PackageRootName/payload/scripts/check_admin_save_ui.py",
        "$PackageRootName/payload/scripts/check_app_health.py",
        "$PackageRootName/payload/scripts/check_audio_batch.py",
        "$PackageRootName/payload/scripts/check_batch_review_counts.py",
        "$PackageRootName/payload/scripts/check_audio_upload_layout.py",
        "$PackageRootName/payload/scripts/check_csv_persistence.py",
        "$PackageRootName/payload/scripts/check_csv_worker.py",
        "$PackageRootName/payload/scripts/check_docs_reconnect.py",
        "$PackageRootName/payload/scripts/check_google_docs_parallel.py",
        "$PackageRootName/payload/scripts/check_google_docs_transport.py",
        "$PackageRootName/payload/scripts/check_google_apps_script_same_date_policy.js",
        "$PackageRootName/payload/scripts/check_connect_log_http_launcher.py",
        "$PackageRootName/payload/scripts/check_import_contracts.py",
        "$PackageRootName/payload/scripts/check_log_csv_batch_state.py",
        "$PackageRootName/payload/scripts/check_log_csv_controls.py",
        "$PackageRootName/payload/scripts/check_log_csv_processing_history.py",
        "$PackageRootName/payload/scripts/check_normalize_summary.py",
        "$PackageRootName/payload/scripts/check_runtime_stability.py",
        "$PackageRootName/payload/scripts/check_ui_refresh.py",
        "$PackageRootName/payload/scripts/google_apps_script_doPost.js",
        "$PackageRootName/payload/scripts/connect_log_http_launcher.py",
        "$PackageRootName/payload/scripts/install_connect_log_http_launcher.ps1",
        "$PackageRootName/payload/scripts/install_connect_log_protocol.ps1",
        "$PackageRootName/payload/scripts/ui_contract_fixture.py",
        "$PackageRootName/payload/browser_extension/connect_log_launcher/manifest.json",
        "$PackageRootName/payload/browser_extension/connect_log_launcher/content.js",
        "$PackageRootName/payload/counsel_modules/__init__.py",
        "$PackageRootName/payload/counsel_modules/admin_utils.py",
        "$PackageRootName/payload/counsel_modules/audio_batch.py",
        "$PackageRootName/payload/counsel_modules/codex_runner.py",
        "$PackageRootName/payload/counsel_modules/codex_runtime.py",
        "$PackageRootName/payload/counsel_modules/google_docs_utils.py",
        "$PackageRootName/payload/counsel_modules/local_consumed_admin_notes.py",
        "$PackageRootName/payload/counsel_modules/log_csv_utils.py",
        "$PackageRootName/payload/counsel_modules/log_csv_processing_history.py",
        "$PackageRootName/payload/counsel_modules/runtime_utils.py",
        "$PackageRootName/payload/counsel_modules/test_api_utils.py",
        "$PackageRootName/payload/counsel_modules/text_utils.py",
        "$PackageRootName/payload/prompts/summary_ko.txt",
        "$PackageRootName/payload/data/students/google_docs_map.csv",
        "$PackageRootName/payload/data/students/google_apps_script_webapp_url.txt",
        "$PackageRootName/payload/data/students/admin_api_base_url.txt",
        "$PackageRootName/payload/data/students/admin_sid_map.csv",
        "$PackageRootName/payload/tools/ffmpeg/bin/ffmpeg.exe"
    )
    if ($DisableRecordingAutoCleanup) {
        $requiredZipEntries += "$PackageRootName/payload/data/students/recording_auto_cleanup_enabled.txt"
    }

    $missingZipEntries = @()
    foreach ($entry in $requiredZipEntries) {
        if ($zipEntries -contains $entry) {
            Write-Status "PASS" "Zip contains: $entry"
        } else {
            Write-Status "FAIL" "Zip missing: $entry"
            $missingZipEntries += $entry
        }
    }

    $excludedRuntimeEntries = @(
        "$PackageRootName/payload/data/local_consumed_admin_notes.json",
        "$PackageRootName/payload/data/local_log_csv_processing_history.json"
    )
    foreach ($excludedEntry in $excludedRuntimeEntries) {
        if ($zipEntries -contains $excludedEntry) {
            Write-Status "FAIL" "Zip must not contain: $excludedEntry"
            $missingZipEntries += "runtime state exclusion failed: $excludedEntry"
        } else {
            Write-Status "PASS" "Zip excludes: $excludedEntry"
        }
    }

    $studentEntries = @($zipEntries | Where-Object { $_ -like "$PackageRootName/payload/data/students/*" })
    if ($studentEntries.Count -gt 0) {
        Write-Status "PASS" "Zip includes required real-use settings data: data/students ($($studentEntries.Count) file(s))"
    } else {
        Write-Status "FAIL" "Zip does not include data/students"
        $missingZipEntries += "data/students inclusion failed"
    }

    if ($missingZipEntries.Count -gt 0) {
        exit 1
    }

    $zipItem = Get-Item -LiteralPath $zipPath
    Write-Host ""
    Write-Status "PASS" "$PackageDisplayName ZIP created."
    Write-Host "Zip path: $zipPath"
    Write-Host "Zip size: $($zipItem.Length) bytes"
    exit 0
} finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
