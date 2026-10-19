param(
    [string]$HostName = "localhost",
    [int]$Port = 8501,
    [int]$TimeoutSeconds = 60,
    [int]$IntervalMilliseconds = 750,
    [switch]$Quiet
)

$ErrorActionPreference = "SilentlyContinue"
$deadline = (Get-Date).AddSeconds([Math]::Max(1, $TimeoutSeconds))

while ((Get-Date) -lt $deadline) {
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if ($async.AsyncWaitHandle.WaitOne([Math]::Max(200, $IntervalMilliseconds))) {
            $client.EndConnect($async)
            if (-not $Quiet) {
                Write-Host "서버 준비 확인 완료: http://$HostName`:$Port"
            }
            exit 0
        }
    } catch {
        # Keep waiting until timeout.
    } finally {
        if ($client) {
            $client.Close()
        }
    }
    Start-Sleep -Milliseconds ([Math]::Max(200, $IntervalMilliseconds))
}

if (-not $Quiet) {
    Write-Host "서버 준비 확인 실패: http://$HostName`:$Port"
}
exit 1
