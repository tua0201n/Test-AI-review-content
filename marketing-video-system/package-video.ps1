param([Parameter(Mandatory=$true)][string]$VideoManifest)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
uv run marketing-video package-video $VideoManifest
exit $LASTEXITCODE
