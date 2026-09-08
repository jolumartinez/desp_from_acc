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

Instala Python 3.12 con soporte para `venv` y `pip` antes del primer lanzamiento.
Los lanzadores buscan primero Python 3.12 y aceptan versiones posteriores si
no está disponible. En Windows se busca mediante `py` y después en `PATH`;
en Linux/macOS, mediante `python3.12`, `python3` o `python` en `PATH`.

Con un solo comando, el lanzador:

1. Crea `.venv` en la raíz del repositorio si todavía no existe.
2. Comprueba las dependencias con `pip install -r desp_desktop_app/requirements.txt`,
   instalando las que falten o tengan una versión distinta de la indicada.
3. Abre DESP Studio con el Python de ese entorno.

La primera instalación necesita acceso al índice de paquetes configurado o una
caché local que contenga las dependencias. En los siguientes arranques, `pip`
reutiliza los paquetes que ya cumplen los requisitos; no se fuerza su
actualización ni reinstalación. Si falta una dependencia o cambia
`requirements.txt`, se comprueba e instala de nuevo lo necesario antes de abrir
la aplicación. Si la instalación falla, el lanzador se detiene y muestra el
error; puedes volver a ejecutarlo después de resolver la causa.

Los lanzadores utilizan `.venv\Scripts\python.exe` en Windows y
`.venv/bin/python` en Linux/macOS, y crean una caché local de Matplotlib. No
levantan contenedores, base de datos, API ni servicio de red. La comprobación de
`DISPLAY`/`WAYLAND_DISPLAY` sólo se aplica a Linux: ejecútalo desde una sesión
gráfica. Las rutas se resuelven respecto al lanzador, por lo que también puedes
invocarlo desde otra carpeta.

Si `.venv` ya existe pero está incompleto, no es un entorno virtual o usa Python
anterior a 3.12, el lanzador pide revisarlo o renombrarlo, sin borrarlo ni
reemplazarlo automáticamente. En Debian/Ubuntu, un error de creación relacionado
con `venv` o `ensurepip` puede requerir instalar el paquete `python3-venv`
correspondiente al intérprete elegido. El lanzador no instala Python ni paquetes
del sistema. `.venv` se prepara en cada equipo y no se guarda en Git.

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

Las pruebas del lanzador Bash simulan Python, la instalación y la aplicación;
se pueden ejecutar sin preparar `.venv`, descargar paquetes ni abrir la GUI:

```bash
python3 -m unittest desp_desktop_app.tests.test_launchers -v
```

Para validar los métodos de análisis con las dependencias instaladas:

```bash
.venv/bin/python desp_desktop_app/tools/generate_validation_data.py
MPLCONFIGDIR=/tmp/desp-mpl .venv/bin/python -m unittest discover -s desp_desktop_app/tests -v
```

La documentación técnica completa está en
[`docs/desp_desktop_app`](../docs/desp_desktop_app/README.md).

Las publicaciones abiertas que pueden acompañar legalmente una distribución
offline están inventariadas en [`references`](references/README.md).
