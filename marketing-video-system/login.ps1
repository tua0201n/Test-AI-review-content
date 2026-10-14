$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
uv run marketing-video login @args
exit $LASTEXITCODE
