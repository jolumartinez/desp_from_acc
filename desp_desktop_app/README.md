# DESP Studio

Aplicación de escritorio offline para estimar desplazamientos a partir de
aceleraciones. Está escrita completamente en Python y utiliza el mismo conjunto
tecnológico de `oma_desktop_app`: PyQt5, NumPy, SciPy, Pandas, Matplotlib y
Plotly.

## Lanzamiento

Desde la raíz del repositorio, en Windows (PowerShell):

```powershell
.\launch_desp_desktop_app.ps1
```

En Linux, macOS o Git Bash/MSYS2:

```bash
./launch_desp_desktop_app.sh
```

Los lanzadores utilizan `.venv\Scripts\python.exe` en Windows y
`.venv/bin/python` en Linux/macOS, y crean una caché local de Matplotlib. No
levantan contenedores, base de datos, API ni servicio de red. La comprobación de
`DISPLAY`/`WAYLAND_DISPLAY` sólo se aplica a Linux.

El entorno debe tener instaladas las dependencias. En Windows:

```powershell
# Sólo si todavía no existe .venv:
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r desp_desktop_app\requirements.txt
```

Si aparece `ModuleNotFoundError: No module named 'pandas'`, faltan dependencias
en ese entorno; ejecuta el comando de instalación anterior.

Para ejecutar el módulo directamente en Linux/macOS:

```bash
MPLCONFIGDIR=.cache/desp-matplotlib .venv/bin/python desp_desktop_app/main.py
```

## Entrada

1. Seleccionar una carpeta. La búsqueda de archivos `.txt` es recursiva.
2. Elegir un archivo y uno de sus canales.
3. Indicar la unidad de aceleración: `m/s²`, `cm/s²` o `g`.
4. Conservar la frecuencia detectada o introducir una frecuencia conocida.
5. Opcionalmente, escribir los límites o arrastrar sobre la historia temporal y
   pulsar **Aplicar segmento**. Los métodos procesarán únicamente ese intervalo.

La lectura del TXT y el cálculo inicial del espectro se realizan en segundo
plano. Mientras están activos, la aplicación muestra una barra de progreso
indeterminada y bloquea los controles de entrada para evitar cargas duplicadas.

Formato recomendado:

```text
# SamplingRate = 200
time,acceleration_x,acceleration_y
0.000,0.0012,-0.0004
0.005,0.0014,-0.0003
```

También se admiten separadores detectables por Pandas, fechas en la primera
columna y archivos numéricos sin encabezado con al menos dos columnas.

## Flujo funcional

- **Datos:** inspección temporal y espectral, zoom/paneo y recorte no destructivo
  del canal seleccionado.
- **Métodos:** siete procedimientos de la tesis y el método Bunce para puentes y
  trenes, cada uno con configuración, diagrama, referencia, etapas gráficas y
  ejecución independiente. Las etapas se recorren con un selector y controles
  anterior/siguiente.
- **Comparar:** superposición, envolvente, correlación y métricas en una escala
  común.
- **Informe:** HTML interactivo autocontenido, PDF, CSV por método y manifiesto
  JSON.

Las gráficas Qt incorporan la barra nativa de Matplotlib para zoom, paneo,
restablecimiento y exportación. Las historias temporales también pueden
reproducirse progresivamente.

Para mantener fluidas las señales extensas, las gráficas dibujan como máximo
20 000 puntos uniformemente distribuidos. Esta reducción es exclusivamente
visual: los métodos y las exportaciones conservan todas las muestras.

El recorte no modifica el TXT ni la señal cargada. La vista conserva el registro
completo como contexto, el segmento activo se realza y los resultados e informes
registran sus límites originales.

## Validación

```bash
.venv/bin/python desp_desktop_app/tools/generate_validation_data.py
MPLCONFIGDIR=/tmp/desp-mpl .venv/bin/python -m unittest discover -s desp_desktop_app/tests -v
```

La documentación técnica completa está en
[`docs/desp_desktop_app`](../docs/desp_desktop_app/README.md).

Las publicaciones abiertas que pueden acompañar legalmente una distribución
offline están inventariadas en [`references`](references/README.md).
