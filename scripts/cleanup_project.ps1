param(
    [switch]$DryRun,
    [switch]$RemoveVenv,
    [switch]$KeepStaticfiles,
    [switch]$SkipEnvNormalize,
    [switch]$SkipGitIndex
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$argsList = @("scripts/cleanup_project.py")
if ($DryRun) { $argsList += "--dry-run" }
if ($RemoveVenv) { $argsList += "--remove-venv" }
if ($KeepStaticfiles) { $argsList += "--keep-staticfiles" }
if ($SkipEnvNormalize) { $argsList += "--skip-env-normalize" }
if ($SkipGitIndex) { $argsList += "--skip-git-index" }

python @argsList
