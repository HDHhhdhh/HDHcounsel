param(
    [string]$ZipPath = "",
    [string]$OutputDir = "",
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$PackageFileNamePrefix = "5A-Connect-Log-새컴퓨터-실사용설치"
$PackageRootName = $PackageFileNamePrefix
$InstallerResourceName = "payload.zip"

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

function Get-DesktopPath {
    $preferred = "C:\Users\idotd\OneDrive\Desktop"
    if (Test-Path -LiteralPath $preferred -PathType Container) {
        return $preferred
    }
    return [Environment]::GetFolderPath("Desktop")
}

function Resolve-RealUseZip {
    param([string]$Path)

    if ($Path) {
        $resolved = (Resolve-Path -LiteralPath $Path).Path
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "ZIP was not found: $Path"
        }
        return Get-Item -LiteralPath $resolved
    }

    $desktop = Get-DesktopPath
    $latest = Get-ChildItem -LiteralPath $desktop -File -Filter "$PackageFileNamePrefix-*.zip" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) {
        throw "No $PackageFileNamePrefix-*.zip found on Desktop."
    }
    return $latest
}

function Get-ZipTimestamp {
    param([string]$Name)

    $pattern = "^$([regex]::Escape($PackageFileNamePrefix))-(\d{8}-\d{6})\.zip$"
    if ($Name -notmatch $pattern) {
        throw "Unexpected ZIP name: $Name"
    }
    return $Matches[1]
}

function Get-CSharpCompiler {
    $candidates = @(
        (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    throw "C# compiler was not found. Cannot build installer EXE on this PC."
}

function New-InstallerSource {
    param([string]$DestinationPath)

    $source = @'
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Text;

internal static class InstallerProgram
{
    private const string PayloadResourceName = "payload.zip";
    private const string PackageRootName = "5A-Connect-Log-\uC0C8\uCEF4\uD4E8\uD130-\uC2E4\uC0AC\uC6A9\uC124\uCE58";
    private const string InstallPs1Name = "\uC0C8PC_\uCC98\uC74C\uC124\uCE58.ps1";

    private static int Main(string[] args)
    {
        try
        {
            Console.OutputEncoding = Encoding.UTF8;
            if (args.Length >= 1 && args[0] == "--help")
            {
                Console.WriteLine("5A Connect Log new computer real-use installer");
                Console.WriteLine("Run without arguments to install.");
                Console.WriteLine("Use --extract-only <folder> for smoke testing without installing.");
                Console.WriteLine("If this EXE is blocked, use the ZIP installer instead.");
                return 0;
            }

            if (args.Length >= 2 && args[0] == "--extract-only")
            {
                ExtractPayload(args[1]);
                Console.WriteLine("Extracted installer payload to: " + args[1]);
                return 0;
            }

            Console.WriteLine("5A Connect Log new computer real-use installer");
            Console.WriteLine("If this EXE is blocked, use the ZIP installer instead.");

            string workRoot = Path.Combine(
                Path.GetTempPath(),
                "5A-Connect-Log-real-use-install-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8)
            );
            Directory.CreateDirectory(workRoot);
            ExtractPayload(workRoot);

            string packageRoot = FindPackageRoot(workRoot);
            string installPs1 = Path.Combine(packageRoot, InstallPs1Name);
            if (!File.Exists(installPs1))
            {
                throw new FileNotFoundException("Installer script was not found.", installPs1);
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = "powershell.exe";
            psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(installPs1);
            psi.WorkingDirectory = packageRoot;
            psi.UseShellExecute = false;

            Process process = Process.Start(psi);
            process.WaitForExit();
            if (process.ExitCode == 0)
            {
                TryDeleteDirectory(workRoot);
            }
            else
            {
                Console.WriteLine("Installer temporary files were left for troubleshooting: " + workRoot);
            }
            return process.ExitCode;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Installer EXE failed: " + ex.Message);
            Console.Error.WriteLine("If this EXE is blocked or fails, use the ZIP installer instead.");
            return 1;
        }
    }

    private static void ExtractPayload(string destination)
    {
        Directory.CreateDirectory(destination);
        string tempZip = Path.Combine(destination, PayloadResourceName);
        Assembly assembly = Assembly.GetExecutingAssembly();
        using (Stream input = assembly.GetManifestResourceStream(PayloadResourceName))
        {
            if (input == null)
            {
                string names = string.Join(", ", assembly.GetManifestResourceNames());
                throw new InvalidOperationException("Embedded payload was not found. Resources: " + names);
            }
            using (FileStream output = File.Create(tempZip))
            {
                input.CopyTo(output);
            }
        }
        ZipFile.ExtractToDirectory(tempZip, destination);
        TryDeleteFile(tempZip);
    }

    private static string FindPackageRoot(string workRoot)
    {
        string exact = Path.Combine(workRoot, PackageRootName);
        if (Directory.Exists(exact))
        {
            return exact;
        }
        string[] matches = Directory.GetDirectories(workRoot, PackageRootName + "*");
        if (matches.Length > 0)
        {
            return matches[0];
        }
        string[] directories = Directory.GetDirectories(workRoot);
        if (directories.Length == 1)
        {
            return directories[0];
        }
        return workRoot;
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static void TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch { }
    }

    private static void TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                Directory.Delete(path, true);
            }
        }
        catch { }
    }
}
'@

    $encoding = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($DestinationPath, $source, $encoding)
}

function Test-InstallerExeSmoke {
    param(
        [string]$ExePath,
        [string]$ExpectedZipTimestamp
    )

    $smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) "counsel-note-installer-exe-smoke-$ExpectedZipTimestamp"
    $resolvedSmokeRoot = [System.IO.Path]::GetFullPath($smokeRoot)
    $tempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd("\") + "\"
    if (-not $resolvedSmokeRoot.StartsWith($tempBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe smoke-test path: $resolvedSmokeRoot"
    }
    if (Test-Path -LiteralPath $resolvedSmokeRoot) {
        Remove-Item -LiteralPath $resolvedSmokeRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $resolvedSmokeRoot -Force | Out-Null

    try {
        & $ExePath "--extract-only" $resolvedSmokeRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Installer EXE extract-only smoke test failed with exit code $LASTEXITCODE."
        }

        $packageRoot = Join-Path $resolvedSmokeRoot $PackageRootName
        $required = @(
            "README_새PC_처음설치.txt",
            "새PC_처음설치.bat",
            "새PC_처음설치.ps1",
            "run_app.bat",
            "payload\app.py",
            "payload\requirements.txt",
            "payload\prompts\summary_ko.txt",
            "payload\data\students\google_docs_map.csv",
            "payload\data\students\google_apps_script_webapp_url.txt",
            "payload\data\students\admin_api_base_url.txt",
            "payload\data\students\admin_sid_map.csv",
            "payload\tools\ffmpeg\bin\ffmpeg.exe"
        )
        $missing = @()
        foreach ($relativePath in $required) {
            if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $relativePath))) {
                $missing += $relativePath
            }
        }
        if ($missing.Count -gt 0) {
            throw "Installer EXE payload is missing required entries: $($missing -join ', ')"
        }

        $entries = Get-ChildItem -LiteralPath $packageRoot -Recurse -Force
        $forbidden = @($entries | Where-Object {
            $relative = $_.FullName.Substring($packageRoot.Length).TrimStart("\", "/") -replace "\\", "/"
            $relative -match '(^|/)\.(venv|git|agents|codex|codex_drive_download)(/|$)' -or
            $relative -match '(^|/)data/local_consumed_admin_notes\.json$' -or
            $relative -match '(^|/)data/(recordings|transcripts|uploads|results|diagnostics|tmp)(/|$)' -or
            $relative -match '\.zip$|\.log$|\.pyc$|\.pyo$|\.(wav|mp3|m4a|webm|mp4|flac|aac|srt|vtt)$'
        })
        if ($forbidden.Count -gt 0) {
            throw "Installer EXE payload contains forbidden entries."
        }

        $blockedTerms = @(
            ("외부" + " 공유" + " 금지"),
            ("do not " + "share" + " externally"),
            ("share" + " externally"),
            ("민감" + "정보")
        )
        $badTextFiles = @()
        Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force |
            Where-Object { @(".txt", ".ps1", ".bat", ".json", ".md") -contains $_.Extension.ToLowerInvariant() } |
            ForEach-Object {
                $text = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8
                foreach ($term in $blockedTerms) {
                    if ($text.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                        $badTextFiles += $_.FullName.Substring($packageRoot.Length).TrimStart("\", "/")
                        break
                    }
                }
            }
        if ($badTextFiles.Count -gt 0) {
            throw "Installer EXE payload contains blocked wording: $($badTextFiles -join ', ')"
        }

        Write-Status "PASS" "Installer EXE extract-only smoke test passed."
    } finally {
        if (Test-Path -LiteralPath $resolvedSmokeRoot) {
            Remove-Item -LiteralPath $resolvedSmokeRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

$zipItem = Resolve-RealUseZip -Path $ZipPath
$timestamp = Get-ZipTimestamp -Name $zipItem.Name
if (-not $OutputDir) {
    $OutputDir = $zipItem.DirectoryName
}
if (-not (Test-Path -LiteralPath $OutputDir -PathType Container)) {
    throw "Output directory was not found: $OutputDir"
}
$exePath = Join-Path $OutputDir "$PackageFileNamePrefix-$timestamp.exe"

Write-Host ""
Write-Host "5A Connect Log installer EXE builder" -ForegroundColor Cyan
Write-Host "Basis ZIP: $($zipItem.FullName)"
Write-Host "Output EXE: $exePath"
Write-Host "Mode: .NET wrapper EXE with embedded ZIP payload"
Write-Host "Note: ZIP remains the primary distribution. EXE is a convenience wrapper."
Write-Host ""

$csc = Get-CSharpCompiler
$workRoot = Join-Path ([System.IO.Path]::GetTempPath()) "counsel-note-installer-exe-build-$timestamp"
if (Test-Path -LiteralPath $workRoot) {
    Remove-Item -LiteralPath $workRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null

try {
    $sourcePath = Join-Path $workRoot "InstallerWrapper.cs"
    New-InstallerSource -DestinationPath $sourcePath

    if (Test-Path -LiteralPath $exePath) {
        Remove-Item -LiteralPath $exePath -Force
    }

    $compilerArgs = @(
        "/nologo",
        "/target:exe",
        "/platform:anycpu",
        "/out:$exePath",
        "/resource:$($zipItem.FullName),$InstallerResourceName",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll",
        $sourcePath
    )
    & $csc @compilerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "C# compiler failed with exit code $LASTEXITCODE."
    }

    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw "EXE was not created: $exePath"
    }

    $exeItem = Get-Item -LiteralPath $exePath
    if ($exeItem.Length -le $zipItem.Length) {
        throw "EXE is unexpectedly smaller than or equal to the basis ZIP."
    }

    Write-Status "PASS" "Installer EXE created: $exePath"
    Write-Host "EXE size: $($exeItem.Length) bytes"

    if (-not $SkipSmokeTest) {
        Test-InstallerExeSmoke -ExePath $exePath -ExpectedZipTimestamp $timestamp
    }

    Write-Status "PASS" "Basis ZIP remains available: $($zipItem.FullName)"
    Write-Status "OK" "If Windows blocks the EXE, install with the ZIP instead."
    exit 0
} finally {
    if (Test-Path -LiteralPath $workRoot) {
        Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
