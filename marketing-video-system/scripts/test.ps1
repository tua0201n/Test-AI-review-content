$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
uv run python -m unittest discover -s tests -v
exit $LASTEXITCODE
