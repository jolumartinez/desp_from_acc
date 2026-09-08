# Preajustes y trazabilidad con la tesis

Este documento registra la auditoría de los valores iniciales de DESP Studio
contra los scripts MATLAB impresos en los apéndices B a H. El botón
`Restablecer tesis` reconstruye estos valores para el método seleccionado.

## Numeración del PDF

La numeración impresa tiene un desplazamiento de 16 páginas respecto al archivo
PDF. La aplicación conserva ambas y abre la página física del inicio de cada
apéndice.

| Método | Página impresa | Página física PDF |
| --- | ---: | ---: |
| Trifunac y Lee | 43 | 59 |
| Chiu | 58 | 74 |
| Converse y Brady | 71 | 87 |
| Boore et al. | 83 | 99 |
| Wang et al. | 96 | 112 |
| Darragh et al. | 110 | 126 |
| Park et al. | 122 | 138 |

En Linux se usa primero Evince con `--page-index` para apuntar a la página
física exacta, no a la etiqueta editorial impresa. En otros entornos se abre la
URL local con el fragmento estándar `#page=N`. La ruta del PDF está fijada por
la aplicación: el botón no solicita escoger un documento.

## Valores transcritos

| Método | Preajuste del script de la tesis |
| --- | --- |
| TL | Butterworth `filtfilt`; PB orden 1 a 25 Hz; PA orden 1 a 0.07 Hz; Simpson |
| CH | Opción 2; ajustes de grado 1; PA por `buttord`: Wp 0.25 Hz, Ws 0.017 Hz, Rp 0.5 dB, Rs 55 dB; PB orden 2 a 30 Hz; `filtfilt` |
| CB | Línea base grado 1; PB orden 2 a 25 Hz; PA por `buttord`: Wp 0.20 Hz, Ws 0.0085 Hz, Rp 0.5 dB, Rs 55 dB; pad inicial 2 s; factor de pad 1.5; `filtfilt` |
| BO | Ajuste restringido grado 2; PA orden 4 a 0.07 Hz; `caso=2`, por lo que el PA inicia desactivado; el script usa `filtfilt` si se activa |
| WA | Ruido `media(abs(a))`; factor 1.03; energía 90 %; ajuste postevento grado 2; límite `tp + 4(tf-tp)`; incrementos temporales `te/100` |
| DA | Formas lineal, cuadrática y bilineal; ajuste desde el inicio; PB orden 2 a 25 Hz; `filtfilt` |
| PA | Sustracción de la media de aceleración y de la media de velocidad; integración Simpson |

## Valores que dependen de la señal

No existe un valor universal en la tesis para las siguientes entradas:

- `T1`, tiempo de primer arribo de Boore;
- ventana utilizada por Wang para estimar el ruido preevento;
- límites de desplazamiento escalón `d_f` de Wang, cuando se usa el rango manual;
- `Z`, punto de cambio de pendiente bilineal de Darragh;
- inicio y final del recorte previo de cada registro.

La interfaz identifica estas entradas y ofrece para `d_f` tanto el rango manual
del script como el óptimo analítico sin límites. Los valores iniciales de 1 s
para Boore y 5 s para Wang son puntos operativos para poder construir el
control, no recomendaciones científicas de la tesis. Deben revisarse sobre la
gráfica de cada registro antes de aceptar resultados.

## Diferencias deliberadas

1. Los factores de calibración en voltios no se aplican porque la entrada de la
   aplicación ya debe declarar una unidad física de aceleración.
2. La integración Simpson de SciPy evita la interpolación intermedia del script;
   esto aún debe contrastarse numéricamente con los datos originales.
3. La búsqueda de Wang elimina analíticamente el bucle sobre el desplazamiento
   escalón y conserva las 100 divisiones temporales. Es una optimización del
   mismo criterio de mínimos cuadrados, no una reducción de resolución.
4. El texto de Darragh describe un Butterworth causal de cuatro polos cercano a
   50 Hz, mientras su script usa orden 2, 25 Hz y `filtfilt`. El preajuste sigue
   el script; la fase puede cambiarse desde la interfaz.

## Protección por pruebas

`tests/test_thesis_presets.py` fija las constantes, los destinos del PDF y el
orden/frecuencia crítica calculados por `buttord`. Cualquier cambio futuro en
estos valores hará fallar la suite y obligará a justificar la modificación.
