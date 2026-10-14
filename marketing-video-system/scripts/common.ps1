$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONUTF8 = '1'
$env:UV_CACHE_DIR = Join-Path $ProjectRoot '.runtime\uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $ProjectRoot '.runtime\python'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $ProjectRoot '.venv'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $ProjectRoot '.runtime\browsers'
$env:BROWSER_USE_CONFIG_DIR = Join-Path $ProjectRoot '.runtime\browser-use'
$env:XDG_CACHE_HOME = Join-Path $ProjectRoot '.runtime\cache'
