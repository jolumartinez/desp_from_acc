# Avisos de terceros

Revisión: 8 de septiembre de 2026.

El código original de DESP Studio se ofrece bajo **GPL-3.0-only**, según
[LICENSE](LICENSE). Los documentos, datos, fuentes tipográficas y dependencias
de terceros conservan sus condiciones propias. Su presencia en el repositorio
no los convierte en material GPL ni concede permisos adicionales.

## Dependencias de la aplicación de escritorio

Resumen de las versiones de [requirements.txt](desp_desktop_app/requirements.txt),
contrastado con los metadatos y avisos de los paquetes instalados. No sustituye
sus textos de licencia ni constituye un inventario de dependencias transitivas.

| Paquete | Versión | Condición declarada |
| --- | --- | --- |
| PyQt5 | 5.15.10 | GPL v3 en la distribución utilizada |
| PyQt5-Qt5 | 5.15.2 | LGPL v3 en el paquete de bibliotecas Qt |
| PyQt5-sip | 12.15.0 | Licencia SIP; el archivo incluido contiene una licencia BSD de dos cláusulas |
| NumPy | 2.4.4 | BSD-3-Clause y licencias de componentes incluidos: 0BSD, MIT, Zlib y CC0-1.0 |
| pandas | 3.0.2 | BSD de tres cláusulas |
| SciPy | 1.17.1 | BSD de tres cláusulas; conserva avisos de componentes incluidos |
| Matplotlib | 3.10.8 | Licencia propia de Matplotlib, de tipo PSF |
| Plotly | 6.6.0 | MIT |

[Riverbank](https://www.riverbankcomputing.com/software/pyqt/intro) distingue la
licencia GPL v3 de PyQt de la LGPL de las bibliotecas Qt incluidas en sus wheels;
también ofrece PyQt mediante licencia comercial. Este proyecto utiliza la opción
GPL. Deben conservarse los avisos que acompañan a cada dependencia.

## Tipografía

`desp_desktop_app/assets/fonts/NotoSans-Regular.ttf` y `NotoSans-Bold.ttf`:
Noto Sans, © Google, bajo **SIL Open Font License 1.1**. Los avisos de autoría y
la licencia completa se conservan en
[fonts/LICENSE.txt](desp_desktop_app/assets/fonts/LICENSE.txt). La OFL exige
conservar esos avisos con las fuentes redistribuidas.

## Publicaciones y documento de referencia

- **Bunce, 2023.** Andrew Bunce, David Hester, Su Taylor, James Brownjohn,
  Farhad Huseynov y Yan Xu. *A robust approach to calculating bridge displacements
  from unfiltered accelerations for highway and railway bridges*.
  Mechanical Systems and Signal Processing, 200, 110554.
  [DOI](https://doi.org/10.1016/j.ymssp.2023.110554) ·
  [PDF local](desp_desktop_app/references/bunce_bridge_displacement_2023.pdf).
  © 2023 los autores; **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**,
  declarada en el PDF. Se conservan las atribuciones internas de terceros.

- **VMD, 2023.** Xiaoquan Xu, Yinfeng Dong, Dezhi Fang y Dong Li.
  *Permanent displacement estimation method based on variational mode
  decomposition*. Vibroengineering Procedia, 52, 48–53.
  [DOI](https://doi.org/10.21595/vp.2023.23663) ·
  [PDF local](desp_desktop_app/references/vmd_baseline_2023.pdf).
  © 2023 los autores; **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**,
  confirmada en la [publicación editorial](https://www.extrica.com/article/23663).

- **PRISM, 2017.** J. Jones, E. Kalkan y C. Stephens. *Processing and review
  interface for strong motion data (PRISM) software, version 1.0.0—Methodology
  and automated processing*. USGS Open-File Report 2017–1008, 81 páginas.
  [DOI](https://doi.org/10.3133/ofr20171008) ·
  [PDF local](desp_desktop_app/references/prism_methodology_usgs_2017.pdf).
  El aviso del informe declara que la mayor parte es de dominio público y
  exceptúa los materiales identificados como sujetos a derechos de terceros.

- **Tokunaga, 2022.** Munemasa Tokunaga, Manabu Ikeda y Koji Yoshida.
  *Displacement response waveform restoration of simply support bridge during
  train passage based on measurement acceleration integration*.
  JSCE, Ser. A1, 78(1), 47–60. © 2022 Japan Society of Civil Engineers.
  [DOI](https://doi.org/10.2208/jscejseee.78.1_47) ·
  [PDF local](desp_desktop_app/references/tokunaga_bridge_displacement_2022.pdf).
  Copia íntegra del [PDF de J-STAGE](https://www.jstage.jst.go.jp/article/jscejseee/78/1/78_47/_pdf).
  Su acceso es libre; no se ha documentado aquí una licencia abierta ni un
  permiso de redistribución pública. No se le atribuye licencia CC BY.

- **Tesis, 2016.** Damaris Sarahí Arias Lara. *Análisis de métodos para estimar
  desplazamientos a partir de aceleraciones medidas, en estructuras sometidas
  a diferentes tipos de excitación*. Universidad Autónoma del Estado de México,
  agosto de 2016. [PDF local](desp_desktop_app/TESIS_DAMARIS_ARIAS_final.pdf) ·
  [Registro institucional](https://ri.uaemex.mx/handle/20.500.11799/57875).
  No se ha verificado una licencia abierta para la copia incluida.

- **Propuesta JM, noviembre de 2024.** Jorge Luis Martínez Valencia.
  [Correo en PDF](desp_desktop_app/references/metodoJorgeMartinezNoviembre2024.pdf),
  aportado por su autor para incluirlo como referencia local de la aplicación.
  Ese permiso de inclusión no se presenta como una licencia pública general;
  el documento no declara una licencia abierta.

Los hashes y la procedencia de los PDF están en el
[registro de referencias](desp_desktop_app/references/README.md). Se conserva
la atribución de los autores; la inclusión no implica su aval de la aplicación.

## Datos de validación

Los [casos sintéticos](desp_desktop_app/validation_data/README.md) incluidos se
generan con las herramientas del proyecto y contienen desplazamientos de
referencia para comprobar los cálculos.

Queda pendiente aclarar la redistribución pública de la tesis, el artículo de
Tokunaga y el correo JM. Este inventario registra esa situación;
no afirma que todos los archivos del repositorio dispongan ya de permiso público.
