# Validación y datos de referencia

## Qué queda incluido

El repositorio contiene dos casos sintéticos reproducibles en
`desp_desktop_app/validation_data/generated`:

| Caso | Verdad conocida | Objetivo |
| --- | --- | --- |
| Armónico | 1.5 Hz entre ventanas en reposo, desplazamiento entre 0 y 12 mm, residual cero | Integración, fase, amplitud y efectos de borde |
| Residual | Transición suave hasta 40 mm | Conservación de desplazamiento permanente |

Cada paquete contiene el TXT que lee la aplicación, el desplazamiento verdadero
y un manifiesto. Se generan sin aleatoriedad con
`tools/generate_validation_data.py`.

Las pruebas automatizadas comprueban:

- lectura multicanal y conversión de `cm/s²` y `g`;
- forma, finitud y etapas de los métodos con señales adecuadas a sus hipótesis;
- reconstrucción del armónico limpio con Park;
- conversión del formato K-NET ASCII;
- generación offline de HTML, PDF, CSV y JSON.

En la verificación de la incorporación de JM, el 8 de septiembre de 2026, la
suite completa pasó **74 pruebas**, incluidas 14 nuevas de cálculo, informes y
contratos de interfaz para el método.

Además, ocho comparaciones contra la función original de `easy_ama_jmpc`
produjeron un **error absoluto máximo de 0** entre los vectores de desplazamiento:
X, Y y Z del registro de vía 1 (21 095 muestras a 500 Hz) y del registro de vía 2
(10 841 muestras a 250 Hz), con los valores iniciales; y Z de ambos archivos con
amortiguamiento 0.035. Se mantuvieron 20 modos, Welch de 512 muestras y umbral
0.001. El código original se extrajo para este contraste sin iniciar Dash.

Estas comparaciones verifican fidelidad al código recibido, no exactitud física
frente a desplazamientos medidos. Los extremos de Z **no coinciden con las
cifras del correo**, ni con el amortiguamiento inicial 0.002 ni al cambiarlo a
0.035. No se dispone de la configuración histórica completa ni del segmento
exacto usado para generar aquellas cifras. La
[guía de JM](13_metodo_jorge_martinez_2024.md#validación-realizada)
conserva los resultados numéricos y esta limitación.

TK necesita un caso ferroviario coherente con luz, ejes, velocidad y posición
del sensor configurados. Las propuestas iniciales de entrada por energía y de
frecuencia por luz deben contrastarse con el evento y, cuando sea posible, con
vibración libre posterior al paso. La lista inicial de seis ejes es configurable
y no sustituye la geometría real. Su verificación debe separar la recuperación de una solución
analítica conocida de la validación frente a desplazamientos medidos. La
[guía de TK](14_metodo_tokunaga.md) identifica la formulación de 2022, las
salvaguardas añadidas por DESP y la diferencia con el método publicado en 2024.
Una prueba numérica no acredita por sí sola su uso en puentes continuos,
tráfico mixto o pasos con baja relación señal/ruido.

## Datos usados en la tesis

La tesis compara estimaciones con cinco familias de datos: péndulo
cuasiarmónico, puente vehicular, puente peatonal, mesa vibradora de la UNAM y el
sismo de Tohoku de 2011 en AKTH10. El PDF contiene figuras y scripts, pero no los
vectores de aceleración, LVDT, extensómetro o GPS.

El artículo derivado de la tesis fue publicado posteriormente como D. Arias-Lara
y J. De-la-Colina, *Assessment of methodologies to estimate displacements from
measured acceleration records*, Measurement 114 (2018), 261-273,
<https://doi.org/10.1016/j.measurement.2017.09.019>. La ficha editorial no ofrece
un archivo suplementario de datos.

## Procedencia caso por caso

| Caso | Procedencia indicada por la tesis | Ruta más prometedora |
| --- | --- | --- |
| Péndulo cuasiarmónico | Once ensayos de 0.5 a 5.5 Hz en el péndulo de la Facultad de Ingeniería de la UAEMex | Solicitar el paquete a los autores y la tesis de Álvarez Espinosa |
| Puente vehicular | Campaña propia en un puente de Toluca, vano de 30 m, excitado con camión de unas 35 t | Solicitar archivos de las pruebas 13 y 19 a los autores |
| Puente peatonal | Campaña propia sobre puente de celosía de 20 m, excitado por grupos de personas | Solicitar archivos de las pruebas 5 y 7 a los autores |
| Mesa vibradora | Instituto de Ingeniería de la UNAM, sismo sintético en tres intensidades | Consultar a autores y Laboratorio de Mesa Vibradora de la UNAM |
| Tohoku AKTH10 | Aceleración de CESMD; GPS de GSI mediante NGDS | CESMD/NIED para aceleración y Nottingham/GSI para GNSS |

### Péndulo y tesis relacionada

La referencia `[23]` del artículo es J. De-la-Colina y J. Valdés, *Péndulo de
prueba para el estudio dinámico de modelos estructurales*, Revista de Ingeniería
Sísmica 82 (2010), disponible en
<https://www.scielo.org.mx/scielo.php?script=sci_arttext&pid=S0185-092X2010000100002>.
Describe el equipo de la UAEMex, pero no adjunta las series usadas en 2016.

La referencia `[24]` aporta una pista todavía más directa:

> J. A. Álvarez Espinosa, *Evaluación experimental de la metodología de Chiu
> para calcular desplazamientos a partir de aceleraciones*, tesis de maestría,
> Universidad Autónoma del Estado de México, 2016.

Esa tesis no apareció indexada con un archivo descargable en la búsqueda actual.
Conviene solicitarla por título exacto al repositorio de la UAEMex y preguntar si
su depósito conserva anexos digitales.

### Puentes y mesa vibradora

El texto no atribuye los datos de ambos puentes a una base externa: describe la
instrumentación y las pruebas como trabajo experimental de los autores. Tampoco
publica el nombre o coordenadas de los puentes. Para la mesa vibradora sí señala
el Instituto de Ingeniería de la UNAM y agradece a Roberto Duran, entonces jefe
del laboratorio, por el apoyo durante los ensayos. Esto apunta a archivos de
campaña custodiados por UAEMex/UNAM, no a un portal público.

El autor de correspondencia que aparece en la tesis y en el artículo es Jaime
De-la-Colina, `jcolina@uaemex.mx`. La tesis también publica el contacto de
Damaris Arias-Lara. Es preferible iniciar por el autor de correspondencia y por
el repositorio institucional, citando el DOI y el identificador de tesis
`20.500.11799/57875`.

### AKTH10 disponible con registro

NIED publica el evento del 11 de marzo de 2011 en K-NET/KiK-net. AKTH10 es una
estación KiK-net y la componente de superficie este-oeste usa la extensión
`EW2`. La descarga requiere una cuenta NIED.

```bash
export NIED_USERNAME='usuario'
export NIED_PASSWORD='contraseña'
.venv/bin/python desp_desktop_app/tools/download_nied_akth10.py
unset NIED_PASSWORD
```

El script no almacena credenciales. Conserva el archivo original, crea el TXT en
SI y registra URL, cabecera y SHA-256 en `provenance.json`. Los datos descargados
se excluyen de Git para evitar incorporar archivos sujetos a términos externos.

Registro y formato oficial:

- <https://www.kyoshin.bosai.go.jp/en/https_download/>
- <https://www.kyoshin.bosai.go.jp/en/knetascii/>

La procedencia citada literalmente por la tesis es el Center for Engineering
Strong Motion Data. Su informe del evento conserva una fila específica para
`OODATE / AKTH10`:

<https://www.strongmotioncenter.org/cgi-bin/CESMD/iqr_dist_DM2.pl?IQRID=Japan_11Mar2011_usc0001xgp&SFlag=0>

NIED es la fuente primaria de la red KiK-net y ofrece una ruta más directa y
trazable al formato original.

### GPS de contraste

La tesis atribuye la serie GPS de 1 Hz a GSI/NGDS. La ruta histórica mencionada
ya no constituye un paquete reproducible. GSI conserva el informe técnico
`G4-No.1` con RINEX de 1 s para el terremoto de Tohoku y exige una solicitud por
correo que indique finalidad, producto, usuarios, periodo y estaciones:

<https://www.gsi.go.jp/ENGLISH/geonet_technical_report.html>

Para reproducir exactamente la comparación se debe solicitar la estación GPS
empleada por los autores, su serie procesada este-oeste y la convención de
coordenadas. Un RINEX bruto no es aún una serie de desplazamiento: requiere
procesamiento GNSS y definición de referencia.

Existe además un conjunto abierto y ya procesado, con DOI
<https://doi.org/10.17639/nott.6999>, que contiene series norte, este y vertical
de 847 estaciones GEONET a 1 Hz. El ZIP ocupa aproximadamente 323.8 MB:

<https://rdmc.nottingham.ac.uk/handle/internal/7006>

Es una muy buena fuente de contraste, pero no se puede afirmar que reproduzca
exactamente la serie de NGDS usada en la tesis hasta identificar la estación
GEONET elegida, la referencia PPP y la ventana temporal. Por su tamaño no se
descarga automáticamente al repositorio.

### Ensayos experimentales no adjuntos

No se encontró un repositorio público enlazado por la tesis para los datos de
péndulo, puentes o mesa vibradora. La vía correcta es solicitar a la autora o al
repositorio de la UAEMex:

- aceleraciones originales y factores de calibración;
- señales LVDT/extensómetro usadas como verdad;
- ventanas exactas de cada figura;
- frecuencia original y datos interpolados a 200/400 Hz;
- versiones finales de los `.m` que produjeron los resultados.

Sin esos elementos sería posible digitalizar figuras, pero no sería una
validación científica defendible y por eso no se incorporó esa práctica.

## Qué solicitar exactamente

Para evitar recibir sólo imágenes o archivos incompletos, la solicitud debería
pedir:

1. Los TXT o MAT originales de aceleración de los casos y números de prueba
   mostrados en los apéndices B-H.
2. Las series medidas correspondientes de LVDT, extensómetro y GPS.
3. Factores de calibración, polaridad, unidad y frecuencia de cada canal.
4. Ventanas de recorte y desfases aplicados antes de las comparaciones.
5. Coordenadas de sensores usadas para la interpolación geométrica del péndulo.
6. Scripts `.m` finales y cualquier función auxiliar no impresa en la tesis.
7. Permiso y forma de citar o redistribuir los datos dentro de un paquete de
   pruebas interno.

Texto sugerido para la solicitud:

```text
Solicito, para validación y reproducción interna de los algoritmos del artículo
doi:10.1016/j.measurement.2017.09.019, las series originales y de referencia de
los ensayos cuasiarmónicos, puente vehicular, puente peatonal y mesa vibradora,
incluidos metadatos de calibración, frecuencia, ventanas, sincronización y los
scripts MATLAB finales. Los archivos se conservarán con su procedencia y no se
redistribuirán sin autorización expresa.
```

## Plan de acreditación

1. Ejecutar cada caso original en MATLAB y exportar aceleración, velocidad y
   desplazamiento por etapa.
2. Ejecutar DESP Studio con parámetros equivalentes.
3. Comparar máximo absoluto, residual, RMS, correlación y error normalizado.
4. Definir tolerancias por método y por banda útil.
5. Fijar archivos, SHA-256, parámetros y versión de código en un manifiesto.
6. Convertir cada contraste aceptado en una prueba de regresión.
