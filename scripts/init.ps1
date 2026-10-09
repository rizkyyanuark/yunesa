$ErrorActionPreference = 'Stop'
$initScript = Join-Path $PSScriptRoot 'init-env.py'
python $initScript
exit $LASTEXITCODE
