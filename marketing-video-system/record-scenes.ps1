param(
    [Parameter(Mandatory=$true)][string]$Storyboard,
    [switch]$Visible
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
$arguments = @('run','marketing-video','record-scenes',$Storyboard)
if ($Visible) { $arguments += '--visible' }
& uv @arguments
exit $LASTEXITCODE
