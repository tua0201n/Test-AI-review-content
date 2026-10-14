param(
    [Parameter(Mandatory=$true)][string]$Storyboard,
    [Parameter(Mandatory=$true)][string]$Recording,
    [string]$Voice = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
$arguments = @('run','marketing-video','compose-video',$Storyboard,$Recording)
if ($Voice) { $arguments += @('--voice',$Voice) }
& uv @arguments
exit $LASTEXITCODE
