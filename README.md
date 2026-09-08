# DESP Studio

Aplicación de escritorio para estimar desplazamientos a partir de señales de
aceleración, con especial interés en puentes y viaductos carreteros y
ferroviarios. Permite explorar distintos métodos, revisar sus etapas de cálculo
y comparar resultados con parámetros y referencias documentados.

**Estado:** herramienta de investigación en desarrollo. La implementación y su
validación se describen por método en la [documentación técnica](docs/desp_desktop_app/README.md).

## Qué permite hacer

- Cargar señales TXT multicanal, definir unidades y seleccionar un segmento.
- Aplicar diez métodos: Trifunac–Lee, Chiu, Converse–Brady, Boore, Wang,
  Darragh, Park, Bunce, Jorge Martínez y Tokunaga.
- Inspeccionar las señales y los artefactos intermedios con gráficas interactivas.
- Comparar desplazamientos y exportar informes HTML/PDF y datos CSV/JSON.

Los cálculos se ejecutan localmente. La primera instalación de dependencias
necesita acceso al índice de paquetes o una caché local preparada.

## Inicio rápido

Necesitas **Python 3.12**, con `venv` y `pip`, y una sesión gráfica. Los
lanzadores también aceptan versiones posteriores de Python, sujetas a la
compatibilidad de las dependencias. Para clonar el proyecto necesitas Git;
también puedes descargar el ZIP de la rama correspondiente desde GitHub.

La aplicación está actualmente en `develop`, mientras se prepara la versión de
referencia en `main`:

```bash
git clone --branch develop https://github.com/jolumartinez/desp_from_acc.git
cd desp_from_acc
```

En Linux o macOS:

```bash
./launch_desp_desktop_app.sh
```

En Windows, desde PowerShell:

```powershell
.\launch_desp_desktop_app.ps1
```

El lanzador crea `.venv` si hace falta, comprueba e instala las dependencias y
abre la aplicación. Python debe estar instalado previamente. Consulta la
[guía de lanzamiento y uso](desp_desktop_app/README.md) para conocer los
requisitos, el formato de entrada y la resolución de problemas del entorno.

## Primer ejemplo

En la pestaña **Datos**, selecciona la carpeta
[`desp_desktop_app/validation_data/generated/synthetic_harmonic`](desp_desktop_app/validation_data/generated/synthetic_harmonic).
Abre `acceleration.txt`, elige `acceleration_x` y utiliza unidades `m/s²`.
Después puedes ejecutar un método, revisar sus etapas y generar un informe.

La carpeta incluye `truth_displacement.csv` como referencia conocida para
comparar resultados. También se incluye un caso con desplazamiento residual;
los [datos sintéticos](desp_desktop_app/validation_data/README.md) explican sus
hipótesis y cómo reproducirlos. Estos ejemplos generales no contienen la
geometría ni la respuesta de un tren y no sirven para validar BU o TK como
métodos ferroviarios.

## Documentación y validación

- [Guía de uso](desp_desktop_app/README.md).
- [Métodos implementados y sus límites](docs/desp_desktop_app/02_metodos_implementados.md).
- [Validación y datos de referencia](docs/desp_desktop_app/03_validacion_y_datos.md).
- [Superposición modal de Jorge Martínez](docs/desp_desktop_app/13_metodo_jorge_martinez_2024.md).
- [Tokunaga: versión implementada, hipótesis y parámetros](docs/desp_desktop_app/14_metodo_tokunaga.md).
- [Publicaciones y referencias locales](desp_desktop_app/references/README.md).

Las pruebas cubren casos sintéticos, contratos de la interfaz y exportaciones.
Su alcance no equivale a una validación experimental completa de todos los
métodos. Con las dependencias instaladas, se ejecutan desde la raíz:

```bash
.venv/bin/python -m unittest discover -s desp_desktop_app/tests -v
```

En Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s desp_desktop_app/tests -v
```

## Alcance y responsabilidad

DESP Studio se ofrece como herramienta para investigación, aprendizaje y
análisis exploratorio. Las implementaciones se basan en las referencias citadas
e incorporan las adaptaciones documentadas. Su disponibilidad no constituye una
certificación de exactitud, exhaustividad o idoneidad para una aplicación
específica, ni implica el aval de los autores de las publicaciones citadas.

Los resultados requieren revisión técnica y validación independiente,
especialmente cuando se empleen en la evaluación, el diseño o el seguimiento de
estructuras. Corresponde a quien utiliza la herramienta comprobar la calidad de
los datos, las hipótesis, los parámetros y la adecuación del método al caso
estudiado. La aplicación no sustituye el criterio profesional ni la evaluación
de seguridad estructural.

El software se proporciona sin garantías, conforme a los términos de su
licencia. En la medida permitida por la legislación aplicable, sus autores y
colaboradores no asumen responsabilidad por los daños derivados de su
utilización. Este aviso complementa las condiciones de [LICENSE](LICENSE).

## Licencia y atribuciones

Copyright © 2026 Jorge Luis Martínez Valencia y colaboradores, por sus
respectivas contribuciones.

El código original del proyecto se distribuye bajo **GNU General Public License,
versión 3** (`GPL-3.0-only`). El texto completo se conserva en [LICENSE](LICENSE).

Las dependencias y los materiales de terceros conservan sus propias condiciones;
la licencia del código no concede derechos adicionales sobre ellos. Consulta
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) para conocer las atribuciones y
los permisos de redistribución que todavía requieren confirmación.

## Participación

Las observaciones sobre los métodos, los casos de validación y las mejoras son
bienvenidas a través de [Issues](https://github.com/jolumartinez/desp_from_acc/issues)
y propuestas de cambios. Al informar un problema, indica el sistema operativo,
la versión de Python, el método y sus parámetros; incluye un ejemplo sintético
reproducible cuando sea posible. Comparte únicamente datos que tengas permiso
para publicar.

Si utilizas DESP Studio en un trabajo, agradecemos que cites este repositorio,
identifiques la versión o el commit utilizado y cites las publicaciones de los
métodos aplicados.
