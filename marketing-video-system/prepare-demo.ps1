$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
uv run marketing-video prepare-demo @args
exit $LASTEXITCODE
