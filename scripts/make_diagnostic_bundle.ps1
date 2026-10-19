param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

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

function Get-DesktopPath {
    $oneDriveDesktop = Join-Path $env:USERPROFILE "OneDrive\Desktop"
    if (Test-Path -LiteralPath $oneDriveDesktop -PathType Container) {
        return $oneDriveDesktop
    }
    return [Environment]::GetFolderPath("Desktop")
}

function Write-TextFile {
    param(
        [string]$Path,
        [object]$Content
    )
    $text = if ($Content -is [array]) { $Content -join [Environment]::NewLine } else { [string]$Content }
    Set-Content -LiteralPath $Path -Value $text -Encoding UTF8
}

function Invoke-CaptureCommand {
    param(
        [scriptblock]$Command,
        [string]$OutputPath
    )
    try {
        $output = & $Command 2>&1
        $exitCode = if ($null -ne $global:LASTEXITCODE) { $global:LASTEXITCODE } else { 0 }
        Write-TextFile -Path $OutputPath -Content ($output | Out-String)
        return $exitCode
    } catch {
        Write-TextFile -Path $OutputPath -Content "Command failed: $($_.Exception.Message)"
        return 1
    }
}

function Invoke-PythonCandidate {
    param(
        [object]$Candidate,
        [string[]]$Arguments
    )
    $allArgs = @()
    if ($Candidate.PrefixArgs) {
        $allArgs += $Candidate.PrefixArgs
    }
    $allArgs += $Arguments
    try {
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
    }
}

function Get-PythonDiagnostics {
    param([string]$Root)
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $candidates = @(
        [PSCustomObject]@{ Name = ".venv"; FilePath = $venvPython; PrefixArgs = @() },
        [PSCustomObject]@{ Name = "py -3"; FilePath = "py"; PrefixArgs = @("-3") },
        [PSCustomObject]@{ Name = "python"; FilePath = "python"; PrefixArgs = @() },
        [PSCustomObject]@{ Name = "python3"; FilePath = "python3"; PrefixArgs = @() }
    )
    if ($codexPython -and (Test-Path -LiteralPath $codexPython)) {
        $candidates += [PSCustomObject]@{ Name = "Codex bundled Python"; FilePath = $codexPython; PrefixArgs = @() }
    }

    $diagnostics = @()
    $selected = $null
    foreach ($candidate in $candidates) {
        $isPath = ($candidate.FilePath -match "[\\/]")
        if ($isPath -and -not (Test-Path -LiteralPath $candidate.FilePath)) {
            $diagnostics += "WARN $($candidate.Name): not found"
            continue
        }
        if (-not $isPath -and -not (Get-Command $candidate.FilePath -ErrorAction SilentlyContinue)) {
            $diagnostics += "WARN $($candidate.Name): not found"
            continue
        }
        $result = Invoke-PythonCandidate -Candidate $candidate -Arguments @("-c", "import sys; print(sys.executable)")
        if ($result.ExitCode -eq 0) {
            $diagnostics += "PASS $($candidate.Name): runnable"
            if (-not $selected) {
                $selected = $candidate
            }
        } else {
            $detail = (($result.Output -join " ") + " " + $result.Error).Trim()
            $diagnostics += "WARN $($candidate.Name): failed $detail"
        }
    }
    return [PSCustomObject]@{
        Selected = $selected
        Diagnostics = $diagnostics
    }
}

function Test-StreamlitAvailability {
    param([object]$Python)
    if (-not $Python) {
        return "WARN streamlit: Python not found"
    }
    $script = "import importlib.util; print('present' if importlib.util.find_spec('streamlit') else 'missing')"
    $result = Invoke-PythonCandidate -Candidate $Python -Arguments @("-c", $script)
    if ($result.ExitCode -eq 0 -and (($result.Output | Select-Object -First 1) -eq "present")) {
        return "PASS streamlit: importable"
    }
    return "WARN streamlit: not importable"
}

function Get-CsvSummary {
    param(
        [string]$Path,
        [string[]]$RequiredColumns,
        [switch]$GoogleDocsMap
    )
    $lines = @()
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @("exists: false")
    }
    try {
        $rows = Import-Csv -LiteralPath $Path -Encoding UTF8
        $headers = @()
        if ($rows.Count -gt 0) {
            $headers = @($rows[0].PSObject.Properties.Name)
        } else {
            $firstLine = Get-Content -LiteralPath $Path -Encoding UTF8 -TotalCount 1
            if ($firstLine) {
                $headers = @($firstLine -split "," | ForEach-Object { $_.Trim('" ') })
            }
        }
        $lines += "exists: true"
        $lines += "rows: $($rows.Count)"
        foreach ($column in $RequiredColumns) {
            $lines += "column_${column}: $($headers -contains $column)"
        }
        if ($GoogleDocsMap) {
            $hasDocUrl = $headers -contains "doc_url"
            $hasDocId = $headers -contains "doc_id"
            $missingDocRef = 0
            $seen = @{}
            $duplicateCount = 0
            foreach ($row in $rows) {
                $docUrl = if ($hasDocUrl) { [string]$row.doc_url } else { "" }
                $docId = if ($hasDocId) { [string]$row.doc_id } else { "" }
                if (-not $docUrl.Trim() -and -not $docId.Trim()) {
                    $missingDocRef += 1
                }
                $name = [string]$row.student_name
                $nameKey = ($name -replace "\s+", "").ToLowerInvariant()
                if ($nameKey) {
                    if ($seen.ContainsKey($nameKey)) {
                        $duplicateCount += 1
                    } else {
                        $seen[$nameKey] = $true
                    }
                }
            }
            $lines += "column_doc_url_or_doc_id: $($hasDocUrl -or $hasDocId)"
            $lines += "rows_missing_doc_url_or_doc_id: $missingDocRef"
            $lines += "duplicate_student_name_count: $duplicateCount"
        }
    } catch {
        $lines += "read_error: $($_.Exception.Message)"
    }
    return $lines
}

function New-ConfigSummary {
    param([string]$Root)
    $studentsDir = Join-Path $Root "data\students"
    $mapPath = Join-Path $studentsDir "google_docs_map.csv"
    $appsScriptUrlPath = Join-Path $studentsDir "google_apps_script_webapp_url.txt"
    $adminBaseUrlPath = Join-Path $studentsDir "admin_api_base_url.txt"
    $adminSidMapPath = Join-Path $studentsDir "admin_sid_map.csv"
    $lines = @()
    $lines += "[google_docs_map]"
    $lines += Get-CsvSummary -Path $mapPath -RequiredColumns @("student_name") -GoogleDocsMap
    $lines += ""
    $lines += "[apps_script_url]"
    $lines += "exists: $(Test-Path -LiteralPath $appsScriptUrlPath -PathType Leaf)"
    if (Test-Path -LiteralPath $appsScriptUrlPath -PathType Leaf) {
        try {
            $value = (Get-Content -LiteralPath $appsScriptUrlPath -Encoding UTF8 -Raw).Trim()
            $looksLikeUrl = ($value -match "^https://script\.google\.com/macros/s/.+/exec$")
            $lines += "looks_like_url: $looksLikeUrl"
        } catch {
            $lines += "read_error: $($_.Exception.Message)"
        }
    }
    $lines += ""
    $lines += "[admin_settings]"
    $lines += "admin_api_base_url_exists: $(Test-Path -LiteralPath $adminBaseUrlPath -PathType Leaf)"
    $lines += "admin_sid_map_exists: $(Test-Path -LiteralPath $adminSidMapPath -PathType Leaf)"
    if (Test-Path -LiteralPath $adminSidMapPath -PathType Leaf) {
        $lines += Get-CsvSummary -Path $adminSidMapPath -RequiredColumns @("student_name", "admin_sid")
    }
    return $lines
}

function New-ConsumedRegistrySummary {
    param([string]$Root)
    $path = Join-Path $Root "data\local_consumed_admin_notes.json"
    $lines = @("exists: $(Test-Path -LiteralPath $path -PathType Leaf)")
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return $lines
    }
    try {
        $json = Get-Content -LiteralPath $path -Encoding UTF8 -Raw | ConvertFrom-Json
        $items = @($json.items)
        $lines += "json_loadable: true"
        $lines += "version_present: $($null -ne $json.version)"
        $lines += "items_is_array: true"
        $lines += "item_count: $($items.Count)"
    } catch {
        $lines += "json_loadable: false"
        $lines += "error: $($_.Exception.Message)"
    }
    return $lines
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$desktop = Get-DesktopPath
if (-not (Test-Path -LiteralPath $desktop -PathType Container)) {
    throw "Desktop path was not found."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "counsel-note-diagnostic-$timestamp"
$zipPath = Join-Path $desktop "counsel-note-diagnostic-$timestamp.zip"

if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

try {
    Write-Status "OK" "Collecting diagnostics without POST/admin writes/deploy."
    $pythonInfo = Get-PythonDiagnostics -Root $ProjectRoot
    $selectedPython = $pythonInfo.Selected
    $streamlitStatus = Test-StreamlitAvailability -Python $selectedPython
    $appVersionPath = Join-Path $ProjectRoot "APP_VERSION.txt"
    $appVersion = if (Test-Path -LiteralPath $appVersionPath -PathType Leaf) {
        (Get-Content -LiteralPath $appVersionPath -Encoding UTF8 -Raw).Trim()
    } else {
        "unknown"
    }

    $appHealthPath = Join-Path $stageRoot "app_health.txt"
    if ($selectedPython) {
        $appHealthResult = Invoke-PythonCandidate -Candidate $selectedPython -Arguments @("-B", (Join-Path $ProjectRoot "scripts\check_app_health.py"))
        Write-TextFile -Path $appHealthPath -Content (($appHealthResult.Output | Out-String).Trim())
        $appHealthExit = $appHealthResult.ExitCode
    } else {
        Write-TextFile -Path $appHealthPath -Content "WARN Python not found; app health check skipped."
        $appHealthExit = 1
    }

    $releaseCheckPath = Join-Path $stageRoot "release_check.txt"
    $releaseExit = Invoke-CaptureCommand -OutputPath $releaseCheckPath -Command {
        powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\check_release_ready.ps1")
    }

    $filePresence = @(
        "run_app.bat",
        "app.py",
        "requirements.txt",
        "prompts\summary_ko.txt",
        "scripts\check_app_health.py",
        "scripts\check_release_ready.ps1",
        "scripts\wait_for_streamlit_port.ps1",
        "tools\ffmpeg\bin\ffmpeg.exe"
    ) | ForEach-Object {
        "${_}: $(Test-Path -LiteralPath (Join-Path $ProjectRoot $_))"
    }
    Write-TextFile -Path (Join-Path $stageRoot "file_presence.txt") -Content $filePresence

    Write-TextFile -Path (Join-Path $stageRoot "config_summary.txt") -Content (New-ConfigSummary -Root $ProjectRoot)
    Write-TextFile -Path (Join-Path $stageRoot "consumed_registry_summary.txt") -Content (New-ConsumedRegistrySummary -Root $ProjectRoot)
    Write-TextFile -Path (Join-Path $stageRoot "recent_console_hint.txt") -Content @(
        "오류 화면 캡처와 함께 이 zip을 전달하세요.",
        "run_app.bat 콘솔 오류가 보이면 그 화면도 함께 캡처해서 보내주세요.",
        "이 진단 패키지는 학생명 목록, doc_url/doc_id 원문, admin URL 원문, 상담 원문 전체를 포함하지 않도록 구성되어 있습니다."
    )

    $summary = @()
    $summary += "created_at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")"
    $summary += "project_root: $ProjectRoot"
    $summary += "app_version: $appVersion"
    $summary += "os: $([System.Environment]::OSVersion.VersionString)"
    $summary += "powershell_version: $($PSVersionTable.PSVersion)"
    $summary += "ffmpeg_found: $(Test-Path -LiteralPath (Join-Path $ProjectRoot "tools\ffmpeg\bin\ffmpeg.exe") -PathType Leaf)"
    $summary += ""
    $summary += "[python_candidates]"
    $summary += $pythonInfo.Diagnostics
    $summary += "selected_python: $(if ($selectedPython) { $selectedPython.Name } else { "none" })"
    $summary += $streamlitStatus
    $summary += ""
    $summary += "[checks]"
    $summary += "check_app_health_exit_code: $appHealthExit"
    $summary += "check_release_ready_exit_code: $releaseExit"
    Write-TextFile -Path (Join-Path $stageRoot "diagnostic_summary.txt") -Content $summary

    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($stageRoot, $zipPath)

    Write-Status "PASS" "Diagnostic bundle created."
    Write-Host "Zip path: $zipPath"
    exit 0
} catch {
    Write-Status "FAIL" $_.Exception.Message
    exit 1
} finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
