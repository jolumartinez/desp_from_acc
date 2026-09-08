$ErrorActionPreference = 'Stop'

$pythonBin = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$appMain = Join-Path $PSScriptRoot 'desp_desktop_app\main.py'

if (-not (Test-Path -LiteralPath $pythonBin -PathType Leaf)) {
    throw "[DESP] No se encontro Python en $pythonBin. Crea .venv con Python 3.12 e instala desp_desktop_app\requirements.txt."
}
if (-not (Test-Path -LiteralPath $appMain -PathType Leaf)) {
    throw "[DESP] No se encontro la aplicacion en $appMain."
}

$numericThreads = if ($env:DESP_NUMERIC_THREADS) { $env:DESP_NUMERIC_THREADS } else { '1' }
if ($numericThreads -cnotmatch '^[1-9][0-9]*\z') {
    throw '[DESP] DESP_NUMERIC_THREADS debe ser un entero mayor que cero.'
}
$env:OPENBLAS_NUM_THREADS = $numericThreads
$env:OMP_NUM_THREADS = $numericThreads
$env:MKL_NUM_THREADS = $numericThreads
$env:NUMEXPR_NUM_THREADS = $numericThreads

Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not $env:MPLCONFIGDIR) {
        $env:MPLCONFIGDIR = Join-Path $PSScriptRoot '.cache\desp-matplotlib'
    }
    $cachePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($env:MPLCONFIGDIR)
    [System.IO.Directory]::CreateDirectory($cachePath) | Out-Null
    Write-Host "[DESP] Iniciando DESP Studio con $pythonBin..."
    & $pythonBin $appMain @args
    $appExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $appExitCode
