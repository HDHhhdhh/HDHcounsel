param(
    [Parameter(Mandatory = $false)]
    [string]$AppRoot
)

$ErrorActionPreference = "Stop"

if (-not $AppRoot) {
    $AppRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
$AppRoot = [System.IO.Path]::GetFullPath($AppRoot)
$runAppPath = Join-Path $AppRoot "run_app.ps1"

if (-not (Test-Path -LiteralPath $runAppPath)) {
    throw "run_app.ps1 was not found: $runAppPath"
}

$powershellPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$protocolRoot = "HKCU:\Software\Classes\connectlog"
$commandKey = Join-Path $protocolRoot "shell\open\command"
$command = '"{0}" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}" -NoPrompt' -f $powershellPath, $runAppPath

New-Item -Path $commandKey -Force | Out-Null
Set-Item -Path $protocolRoot -Value "URL:5A Connect Log"
New-ItemProperty -Path $protocolRoot -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
Set-Item -Path $commandKey -Value $command

$registeredCommand = (Get-Item -LiteralPath $commandKey).GetValue("")
if ($registeredCommand -ne $command) {
    throw "The connectlog protocol command could not be verified."
}

Write-Host "Connect Log desktop protocol registered."
Write-Host "Target: $runAppPath"
