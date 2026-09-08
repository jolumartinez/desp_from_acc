# Lanzamiento, operación y distribución

## Dependencias

DESP Studio usa las versiones ya fijadas para `oma_desktop_app`:

- Python 3.12
- PyQt5 5.15.10
- NumPy 2.4.4
- Pandas 3.0.2
- SciPy 1.17.1
- Matplotlib 3.10.8
- Plotly 6.6.0

No necesita MATLAB Runtime. `requirements.txt` sólo declara este subconjunto del
entorno existente.

## Linux

```bash
cd /ruta/al/repositorio/desp_from_acc
./launch_desp_desktop_app.sh
```

El lanzador comprueba `.venv`, el archivo principal y la sesión gráfica. La
caché de Matplotlib queda en `.cache/desp-matplotlib`. También fija a uno los
hilos de OpenBLAS, OpenMP, MKL y NumExpr. Es la configuración recomendada para
esta carga 1D y puede modificarse explícitamente antes de lanzar la aplicación.

```bash
DESP_NUMERIC_THREADS=2 ./launch_desp_desktop_app.sh
```

Cada método se ejecuta en un proceso local descartable. No es un servicio, no
abre puertos y no requiere conexión. El proceso se cierra al terminar, cancelar
o superar el límite de 15 minutos.

## Windows durante desarrollo

Desde la raíz del repositorio en PowerShell:

```powershell
.\launch_desp_desktop_app.ps1
```

Este lanzador usa `.venv\Scripts\python.exe`, configura la caché local de
Matplotlib y limita los hilos numéricos igual que el lanzador de Linux. Windows
no necesita las variables `DISPLAY` ni `WAYLAND_DISPLAY`. El lanzador `.sh`
también detecta el entorno Windows cuando se ejecuta desde Git Bash/MSYS2.

Para preparar el entorno por primera vez:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r desp_desktop_app\requirements.txt
```

Si `.venv` ya existe, ejecuta sólo la instalación de dependencias. Un error
como `ModuleNotFoundError: No module named 'pandas'` indica que la instalación
está incompleta. Los entornos virtuales de Windows y Linux/WSL no son
intercambiables; se deben crear con Python del sistema donde se ejecutará la app.

También se puede lanzar directamente:

```powershell
.\.venv\Scripts\python.exe desp_desktop_app\main.py
```

La aplicación guarda informes por defecto bajo el directorio local de datos del
usuario. Se puede forzar una ubicación portable con `DESP_APP_DATA_DIR`.

## Salidas

Cada generación crea una carpeta fechada con:

```text
Informe_YYYYMMDD_HHMMSS/
├── informe.html
├── informe.pdf
└── datos/
    ├── results.json
    └── <metodo>.csv
```

El HTML lleva Plotly dentro del propio archivo. El PDF y los CSV no requieren
software adicional para su conservación. El manifiesto registra fuente, canal,
frecuencia, unidades, parámetros y métricas.

## Ejecutable futuro

La arquitectura es compatible con el mismo PyInstaller usado por OMA. El
ejecutable debe compilarse de forma nativa en cada sistema operativo; no se
genera un `.exe` de Windows desde Linux. Deben incluirse como datos:

- `desp_desktop_app/assets`;
- `TESIS_DAMARIS_ARIAS_final.pdf` si se desea la consulta offline;
- metadatos de Plotly requeridos por PyInstaller.

Antes de distribuir conviene añadir una especificación PyInstaller propia,
probar rutas con espacios, firmar binarios y ejecutar los casos de validación en
Windows y Linux. Ningún secreto es necesario para operar DESP Studio. Las
credenciales NIED sólo pertenecen a la utilidad opcional de descarga y nunca se
incorporan al ejecutable.

## Aspectos pendientes de producto

- equivalencia cuantitativa con los datos originales de la tesis;
- guardado y reapertura de sesiones de análisis;
- análisis sistemático de sensibilidad de cortes y tiempos;
- firma y proceso reproducible de ejecutables para Linux y Windows;
- manual de aceptación metrológica y trazabilidad de calibración.
