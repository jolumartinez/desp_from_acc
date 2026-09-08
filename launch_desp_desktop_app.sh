#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
APP="$ROOT/desp_desktop_app/main.py"
REQUIREMENTS="$ROOT/desp_desktop_app/requirements.txt"
IS_WINDOWS=0
PYTHON_VERSION_CHECK='import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'

case "${OSTYPE:-}" in
  msys*|win32*)
    PYTHON_BIN="$VENV_DIR/Scripts/python.exe"
    IS_WINDOWS=1
    ;;
esac

if [[ ! -f "$APP" ]]; then
  echo "[DESP] No se encontró la aplicación en $APP" >&2
  exit 1
fi

if [[ ! -f "$REQUIREMENTS" ]]; then
  echo "[DESP] No se encontró el archivo de dependencias en $REQUIREMENTS" >&2
  exit 1
fi

if [[ "${OSTYPE:-}" == linux* && -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "[DESP] No hay una sesión gráfica disponible." >&2
  exit 1
fi

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.cache/desp-matplotlib}"
NUMERIC_THREADS="${DESP_NUMERIC_THREADS:-1}"
if [[ ! "$NUMERIC_THREADS" =~ ^[1-9][0-9]*$ ]]; then
  echo "[DESP] DESP_NUMERIC_THREADS debe ser un entero mayor que cero." >&2
  exit 1
fi
export OPENBLAS_NUM_THREADS="$NUMERIC_THREADS"
export OMP_NUM_THREADS="$NUMERIC_THREADS"
export MKL_NUM_THREADS="$NUMERIC_THREADS"
export NUMEXPR_NUM_THREADS="$NUMERIC_THREADS"
cd "$ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
  if [[ -e "$VENV_DIR" || -L "$VENV_DIR" ]]; then
    echo "[DESP] .venv existe, pero no contiene un Python ejecutable en $PYTHON_BIN." >&2
    echo "[DESP] Revisa o renombra ese entorno antes de volver a lanzar la aplicación." >&2
    exit 1
  fi

  BASE_PYTHON_FOUND=0
  if [[ "$IS_WINDOWS" == 1 ]] && command -v py >/dev/null 2>&1; then
    for version in -3.12 -3; do
      if py "$version" -c "$PYTHON_VERSION_CHECK" >/dev/null 2>&1; then
        BASE_PYTHON=(py "$version")
        BASE_PYTHON_FOUND=1
        break
      fi
    done
  fi
  if [[ "$BASE_PYTHON_FOUND" == 0 ]]; then
    for candidate in python3.12 python3 python; do
      if command -v "$candidate" >/dev/null 2>&1 && \
          "$candidate" -c "$PYTHON_VERSION_CHECK" >/dev/null 2>&1; then
        BASE_PYTHON=("$candidate")
        BASE_PYTHON_FOUND=1
        break
      fi
    done
  fi
  if [[ "$BASE_PYTHON_FOUND" == 0 ]]; then
    echo "[DESP] Instala Python 3.12 o posterior y asegúrate de que esté disponible en PATH." >&2
    exit 1
  fi

  echo "[DESP] Creando .venv con ${BASE_PYTHON[*]}..."
  if ! "${BASE_PYTHON[@]}" -m venv "$VENV_DIR"; then
    echo "[DESP] No se pudo crear .venv. Comprueba que Python incluya el módulo venv." >&2
    echo "[DESP] En Debian/Ubuntu puede requerirse el paquete python3-venv de la versión elegida." >&2
    exit 1
  fi
fi

if ! "$PYTHON_BIN" -c "$PYTHON_VERSION_CHECK"; then
  echo "[DESP] .venv debe usar Python 3.12 o posterior. Revisa o renombra el entorno para crearlo de nuevo." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)'; then
  echo "[DESP] El Python de .venv no corresponde a un entorno virtual válido. Revisa el entorno." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "[DESP] Preparando pip en .venv..."
  if ! "$PYTHON_BIN" -m ensurepip --upgrade; then
    echo "[DESP] No se pudo preparar pip en .venv." >&2
    exit 1
  fi
fi
echo "[DESP] Comprobando e instalando las dependencias de .venv..."
if ! "$PYTHON_BIN" -m pip install --disable-pip-version-check -r "$REQUIREMENTS"; then
  echo "[DESP] No se pudieron instalar las dependencias. Revisa el error de pip y vuelve a ejecutar el lanzador." >&2
  exit 1
fi

mkdir -p "$MPLCONFIGDIR"
echo "[DESP] Iniciando DESP Studio con $PYTHON_BIN..."
exec "$PYTHON_BIN" "$APP" "$@"
