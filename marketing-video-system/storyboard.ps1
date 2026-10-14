param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [string]$Language = 'vi',
    [int]$Duration = 40,
    [ValidateSet('16:9','9:16','1:1')][string]$AspectRatio = '16:9'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
uv run marketing-video storyboard $Manifest --language $Language --duration $Duration --aspect-ratio $AspectRatio
exit $LASTEXITCODE
