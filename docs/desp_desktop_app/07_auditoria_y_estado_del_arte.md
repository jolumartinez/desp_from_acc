# Auditoría de métodos y estado del arte

Fecha de revisión: 3 de septiembre de 2026.

## Alcance y conclusión

Se contrastaron `core/engine.py`, `core/signal_ops.py` y los preajustes del
catálogo con el texto, diagramas y scripts MATLAB de los apéndices B a H. Los
siete métodos representan sus flujos de cálculo, pero el estado técnico correcto
continúa siendo **implementados y probados**, no **validados experimentalmente**.
La validación exige los acelerogramas y desplazamientos LVDT/GNSS originales o
una referencia independiente equivalente.

```mermaid
flowchart LR
    T[Tesis: texto y scripts] --> A[Auditoría de flujo]
    A --> U[Pruebas unitarias e invariantes]
    U --> S[Casos sintéticos con verdad conocida]
    S --> R[Registros reales con referencia LVDT/GNSS]
    R --> M[Contraste MATLAB/Python]
    M --> C[Validación cuantitativa]
    C --> P[Uso profesional controlado]
```

El mismo flujo está disponible en `method_assurance.mmd`.

## Hallazgos corregidos

1. **Backend interactivo:** `reporting.py` forzaba globalmente Matplotlib a
   `Agg`. Los informes ahora crean figuras `FigureCanvasAgg` aisladas y la GUI
   conserva `FigureCanvasQTAgg`.
2. **Converse–Brady:** se retiraban los pads entre filtros. Ahora los pads se
   conservan durante pasa baja, pasa alta y doble integración, como exige el
   Apéndice D y la recomendación posterior de Boore (2005).
3. **Chiu:** la opción 2 sí integraba la velocidad corregida, pero no mostraba el
   Paso 6. La etapa “Segunda integración” ahora es explícita.
4. **Filtros cortos:** `sosfiltfilt` podía fallar y cambiar silenciosamente a un
   filtro causal. Ahora se informa que el segmento es demasiado corto.
5. **Frecuencia impuesta:** filtros e integración podían usar escalas temporales
   distintas. Cuando existe frecuencia de cabecera o manual se reconstruye un
   eje uniforme; sin ella, una irregularidad superior al 2 % se rechaza.

## Correspondencia por método

| Método | Correspondencia revisada | Diferencias deliberadas o pendientes | Estado |
| --- | --- | --- | --- |
| Trifunac–Lee | PB 25 Hz, PA 0.07 Hz, orden 1, `filtfilt`, integración, PA en velocidad y desplazamiento | SciPy SOS y Simpson acumulativa; sin corrección instrumental ni selección automática de banda | Flujo concordante |
| Chiu | Tendencia lineal en aceleración, PA por `buttord`, PB, opciones de ajuste en velocidad/desplazamiento y segunda integración | No se implementa la alternativa espectral para velocidad inicial descrita por Chiu pero ausente del script comparado | Flujo del script concordante |
| Converse–Brady | Tendencia, pad inicial, PB, extensión del pad, PA y doble integración conservando pads | Se entrega como resultado el tramo original; la señal extendida permanece visible en etapas | Corregido y concordante |
| Boore–Stephens–Joyner | Media preevento, ajuste cuadrático restringido en velocidad, derivada, PA opcional y doble integración | `arrival_s` sigue siendo decisión del analista; el grado configurable generaliza el grado 2 | Flujo concordante |
| Wang | Umbral de arribo, 90 % de energía, ajuste postevento, función continua y búsqueda `t1/t2/t3/df` | El modo predeterminado optimiza `df` analíticamente y evalúa una malla reducida; el modo de rango manual reproduce mejor el script | Aproximación funcional; prioridad alta de validación |
| Darragh/PEER | Ajustes lineal, cuadrático y bilineal, selección por error, derivación, PB y doble integración | La búsqueda automática del quiebre y el inicio configurable son extensiones; el script pide el quiebre | Flujo concordante con extensión |
| Park | Media de aceleración, integración, media de velocidad y segunda integración | Sólo cambia la implementación numérica de Simpson | Mayor fidelidad conceptual |

## Diferencias numéricas generales

- Los scripts interpolan con spline a medio paso y aplican Simpson 1/3. SciPy
  usa `cumulative_simpson` sobre las muestras originales. Es una formulación
  numérica moderna y consistente, pero no garantiza igualdad bit a bit.
- Los filtros se implementan en secciones de segundo orden, más estables que los
  coeficientes directos `b, a` de MATLAB, con la misma familia, orden y cortes.
- La aplicación recibe aceleración física. No reproduce factores de voltaje ni
  inversiones de signo específicas de cada ensayo de la tesis.
- No se implementa deconvolución de respuesta instrumental. La entrada debe
  encontrarse calibrada en `m/s²`, `cm/s²` o `g`.

## Métodos adicionales recomendados

### Prioridad de dominio: Bunce para puentes y trenes

Una vez precisado que el objetivo es medir la flecha transitoria de un puente o
viaducto durante el paso de un tren, este método es más pertinente que las
técnicas concebidas para desplazamiento cosísmico permanente. Se incorporó al
banco y su decisión técnica se documenta en `08_metodo_bunce_y_seleccion_tecnica.md`.

- Bunce et al. (2023), DOI
  <https://doi.org/10.1016/j.ymssp.2023.110554>

### Referencia de calidad: PRISM / procesamiento adaptativo USGS

PRISM añade control de calidad, detección de necesidad de corrección, selección
de esquinas, despiking y corrección adaptativa. Es la ampliación más prudente
porque existe metodología y código oficial de USGS. Conviene implementarlo como
un flujo completo y no como un filtro aislado.

- Jones, Kalkan y Stephens (2017), DOI
  <https://doi.org/10.3133/ofr20171008>
- Código oficial: <https://github.com/usgs/prism>
- Implementación Python de referencia en gmprocess:
  <https://ghsc.code-pages.usgs.gov/esi/groundmotion-processing/contents/manual/processing_steps_output.html>

### Candidato: algoritmo orientado por tipos (TOA)

Generaliza ajustes por mínimos cuadrados sobre aceleración, velocidad y
desplazamiento y sus combinaciones. Encaja con NumPy/SciPy y permitiría comparar
de manera sistemática variantes que hoy aparecen separadas entre Chiu, Darragh y
Park. Requiere conseguir el artículo completo antes de codificar sus bases y
restricciones.

- Ibarra et al. (2023), *The type-oriented algorithm for baseline correction of
  acceleration time histories*, DOI
  <https://doi.org/10.1016/j.soildyn.2023.108162>

### Candidato condicionado: optimización convexa con desplazamiento residual

Es atractiva para ensayos en mesa o estructuras donde se conoce un residual
objetivo. Automatiza localización y amplitud de cambios de línea base, pero
introduciría un solver de optimización y un dato objetivo que no siempre existe.

- He et al. (2023), DOI
  <https://doi.org/10.1016/j.soildyn.2022.107676>

### Familia cosísmica Iwan–Wu–Chao

La propia tesis reseña estos precursores de Wang. Son útiles para trazabilidad y
para comparar cuánto aporta cada automatización, aunque se solapan y no deberían
presentarse como siete soluciones independientes de igual valor.

- Iwan, Moser y Peng (1985), DOI
  <https://doi.org/10.1785/BSSA0750051225>
- Wu y Wu (2007), DOI <https://doi.org/10.1007/s10950-006-9043-x>
- Chao, Wu y Zhao (2010), DOI
  <https://doi.org/10.1007/s10950-009-9178-7>
- Boore (2005), pads y filtros, DOI
  <https://doi.org/10.1785/0120040160>

### Línea experimental: HSA/EMD y VMD

La descomposición adaptativa busca separar componentes contaminadas de baja
frecuencia sin eliminar indiscriminadamente el desplazamiento permanente. Es
prometedora, pero debe quedar marcada como experimental hasta reproducir los
casos publicados y comparar contra GNSS.

- Método HSA/EMD (2022), DOI
  <https://doi.org/10.1016/j.soildyn.2022.107162>
- Método VMD con ajuste de tres segmentos (2026), DOI
  <https://doi.org/10.1016/j.soildyn.2026.110089>

### Cuando existan sensores complementarios

La fusión multirrate de acelerómetros con GNSS, LVDT, radar o visión evita que
toda la estimación dependa de una doble integración. No es aplicable al flujo
actual de un único TXT de aceleración, pero es la dirección técnicamente más
sólida para monitoreo estructural permanente.

- Smyth y Wu (2007), DOI <https://doi.org/10.1016/j.ymssp.2006.03.005>

## Orden de trabajo recomendado

1. Conseguir los archivos experimentales y generar resultados de referencia de
   los siete scripts MATLAB.
2. Fijar tolerancias para desplazamiento pico, residual, RMSE y correlación.
3. Validar primero Park y Chiu; después TL, CB, BO y DA; finalmente Wang.
4. Validar el método Bunce con pasos de tren y desplazamiento óptico/LVDT
   sincronizado.
5. Incorporar controles de calidad inspirados en PRISM sin presentar el flujo
   como PRISM completo.
6. Evaluar TOA antes de añadir métodos EMD/VMD o aprendizaje automático.

Hasta completar los pasos 1 a 3, los informes deben entenderse como resultados
de ingeniería para revisión, no como mediciones acreditadas de desplazamiento.
