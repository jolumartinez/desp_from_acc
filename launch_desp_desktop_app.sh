#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT/.venv/bin/python"
APP="$ROOT/desp_desktop_app/main.py"

case "${OSTYPE:-}" in
  msys*|win32*) PYTHON_BIN="$ROOT/.venv/Scripts/python.exe" ;;
esac

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[DESP] No se encontró el entorno Python en $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$APP" ]]; then
  echo "[DESP] No se encontró la aplicación en $APP" >&2
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
mkdir -p "$MPLCONFIGDIR"
cd "$ROOT"
echo "[DESP] Iniciando DESP Studio con $PYTHON_BIN..."
exec "$PYTHON_BIN" "$APP" "$@"
