$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
uv run marketing-video plan-demo @args
exit $LASTEXITCODE
