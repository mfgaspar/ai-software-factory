<#
.SYNOPSIS
    Install compose on Windows.

.DESCRIPTION
    Checks git, installs uv if it is missing (after asking), installs the `compose`
    command with `uv tool install`, then runs `compose check`. Claude Code itself is
    optional: compose uses the `claude` on your PATH, or the one bundled with the Claude
    Agent SDK that this installs. Workflow shell steps run under the `sh` that comes with
    Git for Windows.

.EXAMPLE
    .\install.ps1
    .\install.ps1 -Source C:\src\compose
    .\install.ps1 -Source https://example.com/you/compose.git -Yes

    If scripts are blocked:  powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
[CmdletBinding()]
param(
    # A compose checkout or a git URL (default: the folder this script is in).
    [string]$Source = "",
    # Don't ask before installing uv.
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$PythonVersion = "3.12"

function Fail([string]$Message) {
    Write-Host "install: $Message" -ForegroundColor Red
    exit 1
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) {
    Fail "this script is for Windows; on Linux and macOS use install.sh"
}

if (-not $Source) {
    $Source = $PSScriptRoot
    if (-not (Test-Path (Join-Path $Source "pyproject.toml"))) {
        Fail "run this from a compose checkout, or pass -Source"
    }
}
if ($Source -match '^(https?|ssh)://' -or $Source -match '^git@') {
    $Target = "git+$Source"
} elseif ($Source -like 'git+*') {
    $Target = $Source
} else {
    if (-not (Test-Path (Join-Path $Source "pyproject.toml"))) {
        Fail "$Source is not a compose checkout"
    }
    $Target = (Resolve-Path $Source).Path
}

if (-not (Test-Command "git")) {
    Fail "git is required: install Git for Windows (https://git-scm.com/download/win), which also provides the sh that workflow shell steps use, then run this again"
}

if (-not (Test-Command "uv")) {
    $local = Join-Path $env:USERPROFILE ".local\bin"
    if (Test-Path (Join-Path $local "uv.exe")) { $env:Path = "$local;$env:Path" }
}
if (-not (Test-Command "uv")) {
    Write-Host "uv is not installed. It installs compose and the Python it needs."
    Write-Host "It would be installed with the official installer: https://astral.sh/uv/install.ps1"
    if (-not $Yes) {
        $answer = Read-Host "Install uv now? [y/N]"
        if ($answer -notmatch '^(y|yes)$') { Fail "uv is required: see https://docs.astral.sh/uv/" }
    }
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if ($LASTEXITCODE -ne 0) { Fail "installing uv failed" }
    $env:Path = "$(Join-Path $env:USERPROFILE '.local\bin');$env:Path"
    if (-not (Test-Command "uv")) {
        Fail "uv was installed but is not on PATH; open a new terminal and run this again"
    }
}

Write-Host "Installing compose from $Target ..."
uv tool install --force --reinstall --python $PythonVersion $Target
if ($LASTEXITCODE -ne 0) { Fail "uv tool install failed" }

$BinDir = (uv tool dir --bin).Trim()
if (-not (($env:Path -split ';') -contains $BinDir)) {
    $env:Path = "$BinDir;$env:Path"
    Write-Host ""
    Write-Host "$BinDir is not on your PATH. Add it with:  uv tool update-shell"
}

$gitSh = Join-Path (Split-Path (Split-Path (Get-Command git).Source)) "bin\sh.exe"
if (-not (Test-Command "sh") -and -not (Test-Path $gitSh)) {
    Write-Host ""
    Write-Host "No sh found: workflow shell steps will run under cmd.exe, and the built-in workflows expect sh. Git for Windows provides it." -ForegroundColor Yellow
}

Write-Host ""
# from the home folder, so only the prerequisites are checked, not the current repository
Push-Location $HOME
try { compose check } finally { Pop-Location }
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "compose is ready. In a repository: compose init --engine claude"
} else {
    Write-Host ""
    Write-Host "compose is installed, but 'compose check' found something to fix (see above)."
    if (-not (Test-Command "claude")) {
        Write-Host "To install Claude Code: https://docs.claude.com/en/docs/claude-code/setup"
    }
}
