# Auditoría de fidelidad del método BU 2023

Fecha de revisión: 4 de septiembre de 2026.

## Resultado

Se contrastó `core/engine.py` con las Secciones 2, 4 y 5 y las Figuras 3,
10, 11 y 15 de Bunce et al. (2023). La forma ideal publicada contiene seis
**valles de carga** `T1-T6` y cinco **recuperaciones** `P1-P5`. En consecuencia,
observar seis excursiones de flecha no implica que deban buscarse seis `P_i`.

También hay seis **ramas ascendentes**: `T1 -> P1`, ..., `T5 -> P5` y
`T6 -> hombro posterior`. La última no termina en un máximo interior porque no
vuelve a descender; termina en el estado descargado y se controla mediante el
hombro poscarga.

```mermaid
flowchart LR
    T1[Valle T1] --> P1[Recuperación P1]
    P1 --> T2[Valle T2]
    T2 --> P2[Recuperación P2]
    P2 --> T3[Valle T3]
    T3 --> X[...]
    X --> P5[Recuperación P5]
    P5 --> T6[Valle T6]
```

## Defectos corregidos

### Detecciones que no eran máximos locales

La versión anterior elegía el mayor valor dentro de una tolerancia alrededor de
cada `P_i`. Una curva con un único valle suave llegaba a reportar tres picos en
los bordes de esas ventanas, aun sin tener ningún máximo local. Ahora se usa
`scipy.signal.find_peaks` con los criterios publicados:

- separación mínima;
- anchura mínima;
- prominencia mínima.

Cada detección se puede asociar a un solo `P_i`; una muestra ya no puede contarse
dos veces. Si faltan recuperaciones, el proceso termina y conserva sus gráficas,
pero el control ferroviario queda en advertencia.

### Promedio de los hombros

La versión anterior promediaba primero cada hombro y daba el mismo peso a ambos,
aunque tuvieran cantidades diferentes de muestras. La Sección 2 indica sumar las
velocidades absolutas y dividir entre el total de datos. El indicador corregido
es:

```text
q_shoulder = (sum(|v_pre|) + sum(|v_post|)) / (N_pre + N_post)
```

## Correspondencia verificada

- aceleración original sin filtrar;
- combinación de inicios y finales alrededor del evento;
- tendencia lineal independiente para cada ventana;
- integración acumulativa con condiciones iniciales nulas;
- rechazo de levantamiento aparente mayor que el umbral;
- calidad de hombros mediante velocidad absoluta media;
- geometría `d_i = m_i + x_sensor` y `P_i = (d_i/L)T`;
- gradiente relativo entre recuperaciones asociadas;
- clasificación y presentación de ventanas alternativas.

## Extensiones y límites pendientes

La detección automática del evento, la polaridad automática, la tolerancia de
asociación y la continuidad exploratoria son extensiones de DESP, no partes del
artículo. Además, el máximo de candidatos puede adelgazar la malla: esto protege
la aplicación frente a cálculos excesivos, pero deja de ser una búsqueda
exhaustiva si no se usa un periodo de muestra como paso y un límite suficiente.

La configuración actual permite derivar posiciones y puntos medios desde las
separaciones entre ejes; el preajuste tiene seis ejes y cinco huecos. También
conserva la entrada manual de longitud entre ejes extremos y `m_i`. No recibe
cargas individuales ni calcula la línea de influencia, por lo que no demuestra
que cada rama observada corresponda a un eje concreto. La elección de cada
hueco como candidato a recuperación es una ayuda de DESP. La geometría sólo
predice tiempos de recuperación y se aplica después de integrar.

La hipótesis de `P_i` próximos a cero fue demostrada en un vano ferroviario de
14.8 m cuya longitud era comparable con la separación entre conjuntos de ejes.
Para un vano de 100 m con separaciones mucho menores, pueden coexistir numerosos
ejes sobre el puente y no producirse descarga entre ellos. En ese caso debe usarse
el control básico por hombros o desarrollar una predicción basada en la línea de
influencia y las posiciones/cargas de todos los ejes.

La implementación sigue pendiente de validación metrológica contra aceleración
QA-750 y desplazamiento Imetrum sincronizados. Las pruebas sintéticas verifican
ahora dos invariantes: una sola parábola no inventa recuperaciones y seis valles
se distinguen correctamente de las cinco recuperaciones que los separan.

## Referencia primaria

A. Bunce et al., *A robust approach to calculating bridge displacements from
unfiltered accelerations for highway and railway bridges*, Mechanical Systems
and Signal Processing 200 (2023) 110554,
<https://doi.org/10.1016/j.ymssp.2023.110554>.
