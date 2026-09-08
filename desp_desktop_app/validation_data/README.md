# Datos de validación local

`generated/` contiene dos casos deterministas con desplazamiento de referencia:

- `synthetic_harmonic`: movimiento de 1.5 Hz, pico a pico de 12 mm y residual
  nulo. Es útil para métodos que eliminan componentes permanentes.
- `synthetic_residual`: transición suave hasta un desplazamiento permanente de
  40 mm. Es útil para estudiar métodos que intentan preservar el residual.

Cada caso incluye un `acceleration.txt` compatible con la aplicación, la verdad
de referencia en `truth_displacement.csv` y un `manifest.json`. Los archivos se
recrean de forma determinista con:

```bash
.venv/bin/python desp_desktop_app/tools/generate_validation_data.py
```

Estos casos verifican integración, unidades y estabilidad numérica, pero no
sustituyen una validación experimental o sísmica con medición independiente.
