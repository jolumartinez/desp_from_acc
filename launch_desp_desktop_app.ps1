$ErrorActionPreference = 'Stop'
# Native exit codes are checked below, including when running under PowerShell 7.
$PSNativeCommandUseErrorActionPreference = $false

$venvDir = Join-Path $PSScriptRoot '.venv'
$pythonBin = Join-Path $venvDir 'Scripts\python.exe'
$appMain = Join-Path $PSScriptRoot 'desp_desktop_app\main.py'
$requirements = Join-Path $PSScriptRoot 'desp_desktop_app\requirements.txt'

if (-not (Test-Path -LiteralPath $appMain -PathType Leaf)) {
    throw "[DESP] No se encontro la aplicacion en $appMain."
}
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "[DESP] No se encontro el archivo de dependencias en $requirements."
}

$numericThreads = if ($env:DESP_NUMERIC_THREADS) { $env:DESP_NUMERIC_THREADS } else { '1' }
if ($numericThreads -cnotmatch '^[1-9][0-9]*\z') {
    throw '[DESP] DESP_NUMERIC_THREADS debe ser un entero mayor que cero.'
}

function Test-SupportedPython {
    param(
        [string]$Executable,
        [string[]]$PythonArguments = @()
    )
    try {
        & $Executable @PythonArguments -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $pythonBin -PathType Leaf)) {
    if (Test-Path -LiteralPath $venvDir) {
        throw "[DESP] El entorno existente en $venvDir esta incompleto o pertenece a otra plataforma: falta $pythonBin. Revisalo y renombralo antes de volver a lanzar la app para crear uno nuevo."
    }

    $candidates = @(
        @{ Command = 'py'; PythonArguments = @('-3.12') },
        @{ Command = 'py'; PythonArguments = @('-3') },
        @{ Command = 'python3.12'; PythonArguments = @() },
        @{ Command = 'python3'; PythonArguments = @() },
        @{ Command = 'python'; PythonArguments = @() }
    )
    $systemPython = $null
    $systemPythonArguments = @()
    foreach ($candidate in $candidates) {
        $command = Get-Command -Name $candidate.Command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command -and (Test-SupportedPython -Executable $command.Source -PythonArguments $candidate.PythonArguments)) {
            $systemPython = $command.Source
            $systemPythonArguments = $candidate.PythonArguments
            break
        }
    }
    if ($null -eq $systemPython) {
        throw '[DESP] Se necesita Python 3.12 o superior. Instala Python 3.12 con el lanzador py o agregalo a PATH y vuelve a ejecutar este script.'
    }

    Write-Host "[DESP] Creando el entorno Python en $venvDir..."
    & $systemPython @systemPythonArguments -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        throw '[DESP] No se pudo crear .venv. Revisa el error anterior y comprueba que tu instalacion de Python incluya venv y ensurepip.'
    }
}

if (-not (Test-SupportedPython -Executable $pythonBin)) {
    throw "[DESP] El entorno en $venvDir no funciona con Python 3.12 o superior. Revisalo y renombralo antes de volver a lanzar la app para crear uno nuevo."
}
& $pythonBin -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
if ($LASTEXITCODE -ne 0) {
    throw "[DESP] El interprete en $pythonBin no pertenece a un entorno virtual valido. Revisa .venv antes de volver a lanzar la app."
}

$env:OPENBLAS_NUM_THREADS = $numericThreads
$env:OMP_NUM_THREADS = $numericThreads
$env:MKL_NUM_THREADS = $numericThreads
$env:NUMEXPR_NUM_THREADS = $numericThreads

Push-Location -LiteralPath $PSScriptRoot
try {
    $pipAvailable = $false
    try {
        & $pythonBin -m pip --version 2>$null | Out-Null
        $pipAvailable = ($LASTEXITCODE -eq 0)
    }
    catch {
        $pipAvailable = $false
    }
    if (-not $pipAvailable) {
        Write-Host '[DESP] Preparando pip en el entorno Python...'
        & $pythonBin -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) {
            throw '[DESP] No se pudo preparar pip. Revisa el error anterior; la app no se iniciara.'
        }
    }

    Write-Host '[DESP] Comprobando e instalando las dependencias de DESP...'
    & $pythonBin -m pip install --disable-pip-version-check -r $requirements
    if ($LASTEXITCODE -ne 0) {
        throw '[DESP] No se pudieron instalar las dependencias. Revisa el error anterior y la conexion a Internet; la app no se iniciara.'
    }

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
