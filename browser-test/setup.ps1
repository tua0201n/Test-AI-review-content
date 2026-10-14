$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.uv-python'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $PSScriptRoot '.venv-test'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PSScriptRoot '.browsers'
uv sync --locked
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run python auto_review.py --check
exit $LASTEXITCODE
