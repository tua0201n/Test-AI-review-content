$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
uv run marketing-video validate-demo @args
exit $LASTEXITCODE
