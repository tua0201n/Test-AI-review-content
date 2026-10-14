param([Parameter(Mandatory=$true)][string]$Url)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
$DemoConfig = Get-Content -LiteralPath (Join-Path $ProjectRoot 'configs\demo.json') -Raw | ConvertFrom-Json
uv run marketing-video prepare-demo $Url --max-pages $DemoConfig.max_pages --max-probes $DemoConfig.max_probes
exit $LASTEXITCODE
