$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
uv sync --locked --python 3.12
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run marketing-video check --browser
exit $LASTEXITCODE
