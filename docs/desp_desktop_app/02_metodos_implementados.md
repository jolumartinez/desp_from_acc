# Métodos implementados

La fuente de alcance es la tesis local, especialmente los apéndices B a H. Los
scripts MATLAB están impresos dentro del PDF; no existían archivos `.m`
independientes en la carpeta recibida. La implementación traduce los flujos a
Python y convierte en controles las decisiones que los scripts solicitaban por
consola.

```mermaid
flowchart TB
    TL[TL: PB + PA en a, v y d]
    CH[CH: tendencia + PA + corrección de deriva]
    CB[CB: línea base + pads + PB/PA]
    BO[BO: media preevento + ajuste restringido]
    WA[WA: corrección continua y escalón]
    DA[DA: ajuste lineal/cuadrático/bilineal]
    PA[PA: medias de aceleración y velocidad]
    BU[BU: ventanas + detrend + QC de puente/tren]
```

El detalle equivalente se conserva en `methods_overview.mmd`.

## Matriz de implementación

| Código | Método | Implementación y controles | Uso principal | Aspecto crítico |
| --- | --- | --- | --- | --- |
| TL | Trifunac y Lee, 1990 | PB y PA Butterworth sin desfase; integración Simpson/trapecios; orden y cortes configurables | Residual esperado cercano a cero | El PA elimina desplazamiento permanente |
| CH | Chiu, 1997 | Tendencia polinómica en aceleración, PA, PB opcional y corrección en velocidad o desplazamiento | Movimiento fuerte digital | Sensible al corte PA y a la variante final |
| CB | Converse y Brady, 1992 | Línea base por recta/media/constante, pads persistentes, PB/PA bidireccional y doble integración con pads | Flujo BAP con banda conocida | No incluye corrección de respuesta instrumental |
| BO | Boore et al., 2002 | Media preevento, ajuste restringido en velocidad, derivada y PA opcional con fase configurable | Desplazamiento residual | Requiere tiempo de primer arribo defendible |
| WA | Wang et al., 2011 | Arribo por umbral configurable, ventana energética, ajuste postevento y búsqueda `t1/t2/t3` | Desplazamiento cosísmico permanente | Mayor costo y sensibilidad a ventanas |
| DA | Darragh et al., 2004 | Ajuste lineal, cuadrático o bilineal continuo en velocidad; selección manual o por MSE | Flujo PEER cercano a falla | La forma funcional exige criterio |
| PA | Park et al., 2005 | Sustracción de medias en aceleración y velocidad | Vibración de puentes y residual cero | No distingue error instrumental de señal física |
| BU | Bunce et al., 2023 | Búsqueda de ventanas, tendencia lineal, doble integración, rechazo de levantamiento y calidad por hombros/picos | Paso de vehículos y trenes sobre puentes | Exige señal de reposo antes/después y acelerómetro de muy bajo ruido |

## Correspondencia y límites

1. **Escalado:** los scripts MATLAB contienen factores en voltios específicos de
   cada ensayo. DESP Studio recibe aceleración física y hace una conversión de
   unidad explícita. No replica factores de sensores que no aplican a los TXT
   actuales.
2. **Recorte:** los scripts piden manualmente inicio y final antes del método.
   DESP Studio permite escribir esos límites o seleccionarlos sobre la gráfica;
   el segmento se rebasa a `t=0` sin modificar el TXT.
3. **Integración:** se usa `scipy.integrate.cumulative_simpson` o trapecios. Es una
   implementación numérica moderna del propósito descrito, no una reproducción
   bit a bit de la interpolación a 400 Hz usada en algunos ejemplos de la tesis.
4. **Filtros:** se utilizan secciones de segundo orden de SciPy. El preajuste
   reproduce `filtfilt` en TL, CH, CB, BO y DA porque así están escritos los
   scripts MATLAB. En BO y DA la interfaz permite elegir la variante causal
   descrita por el texto metodológico.
5. **Instrumento:** no se implementa deconvolución de respuesta instrumental. Es
   correcta la omisión sólo cuando la entrada ya está calibrada como aceleración.
6. **Wang:** el valor por defecto reproduce el umbral del script de la tesis:
   `1.03 × media(|a|)` en el preevento. También puede utilizarse desviación
   estándar para contrastar el criterio publicado. La búsqueda usa por defecto
   100 divisiones temporales, equivalentes al incremento `te/100` del script;
   el criterio, el nivel de ruido, el valor elegido y el error quedan registrados.
7. **Parámetros iniciales:** TL parte de filtros de orden 1; CH usa pasa baja de
   orden 2 a 30 Hz; y DA usa orden 2 a 25 Hz. Son los valores de partida de los
   ejemplos MATLAB de la tesis, no parámetros universales para cualquier señal.
8. **Diseño automático:** CH y CB ejecutan `scipy.signal.buttord` con `Wp`,
   `Ws`, `Rp` y `Rs`, en lugar de reemplazarlo por un orden supuesto. La interfaz
   conserva además un modo manual separado para estudios de sensibilidad.
9. **Pads de CB:** los ceros añadidos se conservan durante pasa baja, pasa alta y
   doble integración, de acuerdo con el Apéndice D y con Boore (2005). La serie
   final expuesta se recorta nuevamente al intervalo original, mientras las
   etapas permiten inspeccionar la señal extendida.
10. **Chiu:** la opción 2 muestra de manera explícita el Paso 6, integración de la
    velocidad corregida. El cálculo ya existía, pero antes quedaba absorbido por
    la gráfica titulada “Desplazamiento final”.
11. **Bunce:** no filtra la aceleración. Prueba ventanas con diferentes inicios y
    finales, ajusta una recta por ventana y clasifica el resultado según la
    estabilidad de velocidad antes y después de la carga. El modo ferroviario
    calcula los tiempos de los picos esperados con luz, posición del sensor,
    longitud entre ejes extremos, puntos medios entre conjuntos de ejes y
    duración observada o velocidad; también admite tiempos manuales.

Por estas diferencias, el estado correcto es **implementación funcional del
flujo**, todavía no **equivalencia certificada con MATLAB**.

La auditoría detallada, sus hallazgos y los métodos candidatos posteriores a la
tesis están en `07_auditoria_y_estado_del_arte.md`.

## Referencias primarias

- H.-C. Chiu, *Stable Baseline Correction of Digital Strong-Motion Data*, BSSA
  87(4), 1997: <https://doi.org/10.1785/BSSA0870040932>
- A. Converse y A. G. Brady, *BAP Basic Strong-Motion Accelerogram Processing
  Software*, USGS OFR 92-296-A: <https://doi.org/10.3133/ofr92296A>
- D. M. Boore, C. D. Stephens y W. B. Joyner, BSSA 92(4), 2002:
  <https://doi.org/10.1785/0120000926>
- R. Wang et al., BSSA 101(5), 2011:
  <https://doi.org/10.1785/0120110039>
- K.-T. Park et al., *Engineering Structures* 27, 2005:
  <https://doi.org/10.1016/j.engstruct.2004.10.013>
- A. Bunce et al., *Mechanical Systems and Signal Processing* 200, 2023:
  <https://doi.org/10.1016/j.ymssp.2023.110554>
- Tesis local y copia institucional:
  <https://ri.uaemex.mx/handle/20.500.11799/57875>
