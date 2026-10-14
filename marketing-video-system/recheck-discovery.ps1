$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
uv run marketing-video recheck-discovery @args
exit $LASTEXITCODE
