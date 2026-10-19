param()

$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$failures = New-Object System.Collections.Generic.List[string]
$readmeName = "README_$([char]0xCC98)$([char]0xC74C)$([char]0xC2E4)$([char]0xD589).txt"
$diagnosticBundleBatName = "$([char]0xC9C4)$([char]0xB2E8)_$([char]0xD328)$([char]0xD0A4)$([char]0xC9C0)_$([char]0xC0DD)$([char]0xC131).bat"
$emergencyInstallBatName = "$([char]0xC138)$([char]0xBE48)_$([char]0xAE34)$([char]0xAE09)$([char]0xBCF5)$([char]0xAD6C)_$([char]0xC6D0)$([char]0xD074)$([char]0xB9AD)$([char]0xC124)$([char]0xCE58).bat"
$emergencyReadmeName = "README_$([char]0xC138)$([char]0xBE48)_$([char]0xAE34)$([char]0xAE09)$([char]0xBCF5)$([char]0xAD6C).txt"
$sebinUpdateCheckBatName = "$([char]0xC138)$([char]0xBE48)_$([char]0xC5C5)$([char]0xB370)$([char]0xC774)$([char]0xD2B8)_$([char]0xD655)$([char]0xC778).bat"
$sebinAutoUpdateReadmeName = "README_$([char]0xC138)$([char]0xBE48)_$([char]0xC790)$([char]0xB3D9)$([char]0xC5C5)$([char]0xB370)$([char]0xC774)$([char]0xD2B8).txt"
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP "counsel-note-pycache"

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host $Text
}

function Add-Failure {
    param([string]$Text)
    [void]$script:failures.Add($Text)
}

function Test-RequiredFiles {
    param([string]$Root)

    $requiredFiles = @(
        "app.py",
        "BUILD_INFO.json",
        "requirements.txt",
        "run_app.bat",
        "run_app.ps1",
        "install_connect_log_web_link.bat",
        "publish_sebin_update.bat",
        "make_new_pc_bootstrap_zip.bat",
        $script:sebinUpdateCheckBatName,
        $script:diagnosticBundleBatName,
        "install_first.bat",
        "install_python_first.bat",
        "install_codex_first.bat",
        $script:readmeName,
        $script:sebinAutoUpdateReadmeName,
        "counsel_modules\__init__.py",
        "counsel_modules\admin_utils.py",
        "counsel_modules\audio_batch.py",
        "counsel_modules\codex_runner.py",
        "counsel_modules\codex_runtime.py",
        "counsel_modules\google_docs_utils.py",
        "counsel_modules\log_csv_utils.py",
        "counsel_modules\log_csv_processing_history.py",
        "counsel_modules\runtime_utils.py",
        "counsel_modules\text_utils.py",
        "browser_extension\connect_log_launcher\manifest.json",
        "browser_extension\connect_log_launcher\content.js",
        "prompts\summary_ko.txt",
        "scripts\google_apps_script_doPost.js",
        "scripts\check_google_apps_script_same_date_policy.js",
        "scripts\check_connect_log_http_launcher.py",
        "scripts\check_app_health.py",
        "scripts\check_audio_batch.py",
        "scripts\check_consumed_admin_notes.py",
        "scripts\check_google_docs_parallel.py",
        "scripts\check_import_contracts.py",
        "scripts\check_log_csv_batch_state.py",
        "scripts\check_log_csv_processing_history.py",
        "scripts\check_normalize_summary.py",
        "scripts\check_quick.ps1",
        "scripts\check_release_ready.ps1",
        "scripts\check_runtime_stability.py",
        "scripts\make_new_pc_bootstrap_zip.ps1",
        "scripts\check_sebin_emergency_zip.ps1",
        "scripts\check_sebin_update_zip.ps1",
        "scripts\make_sebin_emergency_oneclick_zip.ps1",
        "scripts\publish_sebin_update.ps1",
        "scripts\sebin_check_and_apply_update.ps1",
        "scripts\make_diagnostic_bundle.ps1",
        "scripts\sebin_emergency_oneclick_install.ps1",
        "scripts\wait_for_streamlit_port.ps1",
        "scripts\connect_log_http_launcher.py",
        "scripts\install_connect_log_http_launcher.ps1",
        "scripts\install_connect_log_protocol.ps1",
        "make_sebin_emergency_oneclick_zip.bat",
        $script:emergencyInstallBatName,
        $script:emergencyReadmeName,
        "data\students\google_docs_map.csv",
        "data\students\google_apps_script_webapp_url.txt",
        "data\students\admin_api_base_url.txt",
        "data\students\admin_sid_map.csv",
        "tools\ffmpeg\bin\ffmpeg.exe"
    )

    Write-Section "[1] Required files"
    $missing = @()
    foreach ($relativePath in $requiredFiles) {
        $fullPath = Join-Path $Root $relativePath
        if (Test-Path -LiteralPath $fullPath) {
            Write-Host "OK   $relativePath"
        } else {
            Write-Host "MISS $relativePath"
            $missing += $relativePath
        }
    }

    if ($missing.Count -gt 0) {
        Add-Failure ("Missing required files: " + ($missing -join ", "))
    }
}

function Invoke-CheckCommand {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments
    )

    if ($FilePath -eq "node") {
        if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
            Write-Host "FAIL $Label"
            Add-Failure "$Label executable not found: node"
            return $null
        }
    } elseif (-not (Test-Path -LiteralPath $FilePath)) {
        Write-Host "FAIL $Label"
        Add-Failure "$Label executable not found: $FilePath"
        return $null
    }

    $output = & $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        Write-Host "OK   $Label"
    } else {
        Write-Host "FAIL $Label"
        Add-Failure "$Label failed"
        if ($output) {
            $output | ForEach-Object { Write-Host "     $_" }
        }
    }
    return $output
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

function Get-WorkingPython {
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

    foreach ($candidate in $candidates) {
        $isPath = ($candidate.FilePath -match "[\\/]")
        if ($isPath -and -not (Test-Path -LiteralPath $candidate.FilePath)) {
            Write-Host "WARN Python candidate not found: $($candidate.Name)"
            continue
        }
        if (-not $isPath -and -not (Get-Command $candidate.FilePath -ErrorAction SilentlyContinue)) {
            Write-Host "WARN Python candidate not found: $($candidate.Name)"
            continue
        }

        $result = Invoke-PythonCandidate -Candidate $candidate -Arguments @("-c", "import sys; print(sys.executable)")
        if ($result.ExitCode -eq 0) {
            $executable = ($result.Output | Select-Object -First 1)
            Write-Host "OK   Python runtime: $($candidate.Name) ($executable)"
            return $candidate
        }

        $detail = (($result.Output -join " ") + " " + $result.Error).Trim()
        Write-Host "WARN Python candidate failed: $($candidate.Name)"
        if ($detail) {
            Write-Host "     $detail"
        }
    }

    return $null
}

function Test-PyCompileCacheWriteFailure {
    param([object[]]$Output)

    $text = ($Output -join " ")
    return (
        $text -match "__pycache__" -or
        $text -match "Permission denied" -or
        $text -match "Errno 13" -or
        $text -match "Access is denied"
    )
}

function Invoke-PythonSyntaxCheck {
    param(
        [object]$Python,
        [string]$Label,
        [string]$FilePath
    )

    $compileResult = Invoke-PythonCandidate -Candidate $Python -Arguments @("-m", "py_compile", $FilePath)
    if ($compileResult.ExitCode -eq 0) {
        Write-Host "OK   $Label"
        return
    }

    if (-not (Test-PyCompileCacheWriteFailure -Output $compileResult.Output)) {
        Write-Host "FAIL $Label"
        Add-Failure "$Label failed"
        if ($compileResult.Output) {
            $compileResult.Output | ForEach-Object { Write-Host "     $_" }
        }
        if ($compileResult.Error) {
            Write-Host "     $($compileResult.Error)"
        }
        return
    }

    $astScript = "import ast, pathlib, sys; p=pathlib.Path(sys.argv[1]); ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))"
    $astResult = Invoke-PythonCandidate -Candidate $Python -Arguments @("-B", "-c", $astScript, $FilePath)
    if ($astResult.ExitCode -eq 0) {
        Write-Host "OK   $Label (AST fallback; py_compile cache write blocked)"
        return
    }

    Write-Host "FAIL $Label"
    Add-Failure "$Label failed"
    if ($astResult.Output) {
        $astResult.Output | ForEach-Object { Write-Host "     $_" }
    }
    if ($astResult.Error) {
        Write-Host "     $($astResult.Error)"
    }
}

function Invoke-PythonScriptCheck {
    param(
        [object]$Python,
        [string]$Label,
        [string]$FilePath
    )

    $result = Invoke-PythonCandidate -Candidate $Python -Arguments @("-B", $FilePath)
    if ($result.ExitCode -eq 0) {
        Write-Host "OK   $Label"
        return $result.Output
    }

    Write-Host "FAIL $Label"
    Add-Failure "$Label failed"
    if ($result.Output) {
        $result.Output | ForEach-Object { Write-Host "     $_" }
    }
    if ($result.Error) {
        Write-Host "     $($result.Error)"
    }
    return $result.Output
}

Push-Location -LiteralPath $projectRoot
try {
    Write-Host "Project root: $projectRoot"
    Write-Host "Release readiness check only. ZIP builders and publish scripts are not executed."

    Test-RequiredFiles -Root $projectRoot

    $node = "node"

    Write-Section "[2] Python runtime"
    $python = Get-WorkingPython -Root $projectRoot
    if (-not $python) {
        Write-Host "FAIL Python runtime"
        Add-Failure "No working Python executable found"
    }

    Write-Section "[3] Python syntax"
    if ($python) {
        Invoke-PythonSyntaxCheck -Python $python -Label "app.py" -FilePath (Join-Path $projectRoot "app.py")
    }

    $moduleDir = Join-Path $projectRoot "counsel_modules"
    if (Test-Path -LiteralPath $moduleDir) {
        $moduleFiles = Get-ChildItem -LiteralPath $moduleDir -Filter "*.py" | Sort-Object Name
        foreach ($moduleFile in $moduleFiles) {
            $relativeLabel = "counsel_modules\$($moduleFile.Name)"
            if ($python) {
                Invoke-PythonSyntaxCheck -Python $python -Label $relativeLabel -FilePath $moduleFile.FullName
            }
        }
    } else {
        Write-Host "FAIL counsel_modules"
        Add-Failure "counsel_modules directory not found"
    }

    Write-Section "[4] Apps Script syntax"
    Invoke-CheckCommand -Label "scripts\google_apps_script_doPost.js" -FilePath $node -Arguments @("--check", (Join-Path $projectRoot "scripts\google_apps_script_doPost.js")) | Out-Null
    Invoke-CheckCommand -Label "same-date Docs policy" -FilePath $node -Arguments @((Join-Path $projectRoot "scripts\check_google_apps_script_same_date_policy.js")) | Out-Null

    Write-Section "[5] app health check"
    if ($python) {
        $healthOutput = Invoke-PythonScriptCheck -Python $python -Label "scripts\check_app_health.py" -FilePath (Join-Path $projectRoot "scripts\check_app_health.py")
        if ($healthOutput) {
            $healthOutput | Select-Object -First 12 | ForEach-Object { Write-Host "     $_" }
        }
    }

    Write-Section "[6] import contract test"
    if ($python) {
        $importContractOutput = Invoke-PythonScriptCheck -Python $python -Label "scripts\check_import_contracts.py" -FilePath (Join-Path $projectRoot "scripts\check_import_contracts.py")
        if ($importContractOutput) {
            $importContractOutput | Select-Object -First 3 | ForEach-Object { Write-Host "     $_" }
        }
    }

    Write-Section "[7] normalize_summary test"
    if ($python) {
        $normalizeOutput = Invoke-PythonScriptCheck -Python $python -Label "scripts\check_normalize_summary.py" -FilePath (Join-Path $projectRoot "scripts\check_normalize_summary.py")
        if ($normalizeOutput) {
            $normalizeOutput | Select-Object -First 3 | ForEach-Object { Write-Host "     $_" }
        }
    }

    Write-Section "[8] consumed ADMIN registry check"
    if ($python) {
        $consumedOutput = Invoke-PythonScriptCheck -Python $python -Label "scripts\check_consumed_admin_notes.py" -FilePath (Join-Path $projectRoot "scripts\check_consumed_admin_notes.py")
        if ($consumedOutput) {
            $consumedOutput | Select-Object -First 5 | ForEach-Object { Write-Host "     $_" }
        }
    }

    Write-Section "[Final]"
    if ($failures.Count -gt 0) {
        Write-Host "FAIL release readiness check failed"
        Write-Host ""
        Write-Host "Failures:"
        foreach ($failure in $failures) {
            Write-Host "- $failure"
        }
        exit 1
    }

    Write-Host "PASS release readiness check passed"
    exit 0
}
finally {
    Pop-Location
}
