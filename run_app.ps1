param(
    [switch]$NoPrompt,
    [switch]$SkipBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$env:PATH = "$root\tools\ffmpeg\bin;$env:APPDATA\npm;C:\Program Files\nodejs;$env:PATH"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$streamlitPort = 8501
$streamlitUrl = "http://localhost:$streamlitPort"
$waitScript = Join-Path $root "scripts\wait_for_streamlit_port.ps1"
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
$chromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$startupMutex = New-Object System.Threading.Mutex($false, "Local\5AConnectLogStreamlitStartup8501")

function Wait-ForEnter {
    if ($NoPrompt) {
        return
    }

    Write-Host ""
    Read-Host "Press Enter to close this PowerShell window"
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Host ".venv was not found."
    Write-Host "Run install_first.bat first."
    Wait-ForEnter
    exit 1
}

& $pythonExe --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ".venv exists, but its Python is broken."
    Write-Host "Run install_first.bat to rebuild .venv."
    Wait-ForEnter
    exit 1
}

& $pythonExe -c "import streamlit" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Streamlit is not installed in .venv."
    Write-Host "Run install_first.bat first."
    Wait-ForEnter
    exit 1
}

if (-not (Test-Path -LiteralPath $waitScript)) {
    Write-Host "Wait script was not found: $waitScript"
    Wait-ForEnter
    exit 1
}

$hasStartupMutex = $false
try {
    try {
        $hasStartupMutex = $startupMutex.WaitOne([TimeSpan]::FromSeconds(70))
    } catch [System.Threading.AbandonedMutexException] {
        $hasStartupMutex = $true
    }
    if (-not $hasStartupMutex) {
        throw "Another 5A Connect Log startup is still in progress. Please try again shortly."
    }

    Write-Host "Checking app server status..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $waitScript -HostName localhost -Port $streamlitPort -TimeoutSeconds 1 -Quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "App server is already running."
    } else {
        Write-Host "Starting app server..."
        Start-Process -FilePath $pythonExe -ArgumentList @(
            "-m", "streamlit", "run", "app.py",
            "--server.address", "localhost",
            "--server.port", "$streamlitPort",
            "--server.headless", "true"
        ) -WorkingDirectory $root -WindowStyle Hidden

        Write-Host "Waiting for server to be ready..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File $waitScript -HostName localhost -Port $streamlitPort -TimeoutSeconds 60
        if ($LASTEXITCODE -ne 0) {
            throw "Server readiness check failed. The app server is not open yet."
        }
    }
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message
    Wait-ForEnter
    exit 1
} finally {
    if ($hasStartupMutex) {
        $startupMutex.ReleaseMutex()
    }
    $startupMutex.Dispose()
}

if (-not $SkipBrowser) {
    Write-Host "Opening Chrome..."
    if (Test-Path -LiteralPath $chromeExe) {
        Start-Process -FilePath $chromeExe -ArgumentList $streamlitUrl
    } else {
        Write-Host "Chrome was not found. Opening with the default browser instead."
        Start-Process $streamlitUrl
    }
}

Write-Host "App is running. You can close this PowerShell window after Chrome opens."
Wait-ForEnter
