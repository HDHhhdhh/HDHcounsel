param(
    [Parameter(Mandatory = $false)]
    [string]$AppRoot
)

$ErrorActionPreference = "Stop"

if (-not $AppRoot) {
    $AppRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
$AppRoot = [System.IO.Path]::GetFullPath($AppRoot)
$launcherPath = Join-Path $AppRoot "scripts\connect_log_http_launcher.py"
$venvPythonwPath = Join-Path $AppRoot ".venv\Scripts\pythonw.exe"
$pythonwPath = if (Test-Path -LiteralPath $venvPythonwPath -PathType Leaf) {
    $venvPythonwPath
} else {
    $pythonwCommand = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($pythonwCommand) { $pythonwCommand.Source } else { "" }
}

if (-not (Test-Path -LiteralPath $launcherPath)) {
    throw "HTTP launcher was not found: $launcherPath"
}
if (-not $pythonwPath) {
    throw "pythonw.exe was not found. Install Python first."
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runValueName = "5AConnectLogLauncher"
$runCommand = '"{0}" "{1}"' -f $pythonwPath, $launcherPath

New-Item -Path $runKey -Force | Out-Null
New-ItemProperty -Path $runKey -Name $runValueName -Value $runCommand -PropertyType String -Force | Out-Null

$listenerReady = $false
$client = New-Object System.Net.Sockets.TcpClient
try {
    $client.Connect("127.0.0.1", 8765)
    $listenerReady = $true
} catch [System.Net.Sockets.SocketException] {
    $listenerReady = $false
} finally {
    $client.Dispose()
}

if (-not $listenerReady) {
    Start-Process -FilePath $pythonwPath -ArgumentList @($launcherPath) -WorkingDirectory $AppRoot -WindowStyle Hidden
}

Write-Host "Connect Log HTTP launcher registered for Windows sign-in."
Write-Host "Shortcut URL: http://127.0.0.1:8765/open"
