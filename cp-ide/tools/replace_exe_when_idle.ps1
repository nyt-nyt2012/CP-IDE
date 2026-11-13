# Wait until CP-IDE.exe is closed, then replace it with the freshly built one.
#
# Usage (from the project root):
#   powershell -ExecutionPolicy Bypass -File cp-ide\tools\replace_exe_when_idle.ps1
#
# The script is pure ASCII on purpose: PowerShell 5.1 reads .ps1 files as GBK
# when they have no BOM, so any non-ASCII character would break it.

$ErrorActionPreference = 'Stop'

# ...\<project>\cp-ide\tools\replace_exe_when_idle.ps1  ->  ...\<project>
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent (Split-Path -Parent $scriptDir)
$src = Join-Path $root 'cp-ide\dist\CP-IDE.exe'
$dst = Join-Path $root 'CP-IDE.exe'
$logDir = Join-Path $root 'cp-ide\dist'
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}
$log = Join-Path $logDir 'replace_exe.log'

function Write-Log([string]$text) {
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -LiteralPath $log -Value ("[$stamp] $text") -Encoding UTF8
}

if (-not (Test-Path -LiteralPath $src)) {
    Write-Log "source exe not found: $src"
    exit 1
}

Write-Log "waiting for CP-IDE.exe to exit ..."
while (Get-Process -Name 'CP-IDE' -ErrorAction SilentlyContinue) {
    Start-Sleep -Seconds 2
}

try {
    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Log "replaced: $dst"
} catch {
    Write-Log ("replace failed: " + $_.Exception.Message)
    exit 1
}
exit 0
