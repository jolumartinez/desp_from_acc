# Fichas de métodos candidatos

Estas fichas describen qué haría falta para convertir cada referencia en una
implementación ejecutable. Los diagramas son reconstrucciones originales a
partir de las publicaciones citadas; no son figuras copiadas de los artículos.

## PRISM y corrección adaptativa

```mermaid
flowchart LR
    A[Aceleración física] --> O[Detectar onset]
    O --> M[Restar media preevento]
    M --> V[Integrar a velocidad]
    V --> F[Elegir ajuste lineal o cuadrático]
    F --> D[Derivar ajuste y corregir aceleración]
    D --> Q{QC de velocidad}
    Q --> TP[Taper + pads]
    TP --> BP[Filtro acausal de banda]
    BP --> A2{¿Deriva residual?}
    A2 -- Sí --> ABC[Polinomios extremos + spline + búsqueda t2]
    A2 -- No --> I[Doble integración]
    ABC --> I
    I --> QF[QC final de velocidad y desplazamiento]
```

**Insumos:** aceleración calibrada, preevento, onset, frecuencia de muestreo,
esquinas de filtro defendibles y umbrales de calidad. El flujo oficial también
usa metadatos sísmicos para seleccionar banda y generar productos COSMOS.

**Decisión:** no añadirlo como método de tren. Sus ideas de trazabilidad, pads y
QC sí son aplicables. Referencia local:
[`prism_methodology_usgs_2017.pdf`](../../desp_desktop_app/references/prism_methodology_usgs_2017.pdf).

## TOA

```mermaid
flowchart LR
    A[Aceleración] --> T[Elegir tipo: A, V, D o secuencia]
    T --> B[Definir bases y órdenes polinómicos]
    B --> LS[Construir sistema de mínimos cuadrados]
    LS --> S[Resolver coeficientes]
    S --> K[Aplicar corrección cinemáticamente compatible]
    K --> I[Reintegrar a/v/d]
    I --> Q[Comprobar condiciones iniciales y finales]
```

**Insumos:** el TXT actual es suficiente en principio. Faltan, para una réplica
defendible, el texto completo o material suplementario que define las matrices,
bases, normalización y aplicación consistente de las siete combinaciones.

**Decisión:** no etiquetar una detracción polinómica genérica como TOA. Chiu,
Darragh y Park ya permiten estudiar varias de sus ideas sin afirmar equivalencia.
Referencia: <https://doi.org/10.1016/j.soildyn.2023.108162>.

## Optimización convexa con residual objetivo

```mermaid
flowchart LR
    A[Aceleración] --> R[Residual medido o impuesto]
    R --> O[Problema convexo con penalización L1]
    O --> C[Localizar cambios de línea base]
    C --> AC[Aceleración corregida]
    AC --> I[Doble integración]
    I --> V{¿Coincide con residual y forma esperada?}
    V -- No --> L[Ajustar penalización]
    L --> O
    V -- Sí --> D[Resultado]
```

**Insumo adicional obligatorio:** desplazamiento residual objetivo obtenido con
GNSS, LVDT, cámara, radar u otra referencia. En un paso de tren puede proponerse
cero sólo si se ha comprobado respuesta elástica y retorno al reposo.

**Decisión:** reservarlo para una futura modalidad de fusión o validación. El
resumen publicado no basta para reproducir todos los detalles del solver y la
selección iterativa de la penalización. Referencia:
<https://doi.org/10.1016/j.soildyn.2022.107676>.

## HSA con EMD

```mermaid
flowchart LR
    A[Registro cercano a falla] --> E[Descomposición EMD]
    E --> H[Espectro de Hilbert por componente]
    H --> EN[Distribución de energía por banda]
    EN --> C[Identificar componentes contaminantes]
    C --> RC[Reconstruir señal corregida]
    RC --> I[Integrar]
    I --> P[PGD y desplazamiento permanente]
```

**Insumos:** puede operar con aceleración, pero necesita una implementación EMD
especializada, reglas completas de selección y casos cercanos a falla para
validación. Su objetivo es preservar desplazamiento permanente sísmico, distinto
de la flecha transitoria de un puente descargado.

**Decisión:** no incorporar al flujo operativo ferroviario. Referencia:
<https://doi.org/10.1016/j.soildyn.2022.107162>.

## VMD iterativo

```mermaid
flowchart LR
    A[Aceleración] --> V[Integrar a velocidad]
    V --> M[VMD en componentes IMF]
    M --> E[Entropía de componentes de baja frecuencia]
    E --> Z[Último cruce por cero]
    Z --> C[Conservar componentes y tramo previo]
    C --> R{¿Resto monótono o constante?}
    R -- No --> M
    R -- Sí --> S[Sumar registros corregidos]
    S --> D[Integrar a desplazamiento permanente]
```

**Insumos:** el TXT es suficiente, pero se necesita una biblioteca VMD incluida
en la distribución y fijar criterios de convergencia, número de modos, penalidad
y entropía. El artículo de 2023 remite parte del procedimiento detallado a una
referencia de congreso de 2021 y señala que los datos se solicitan a los autores.

**Decisión:** conservar como experimento sísmico, no como estimador principal de
paso de tren. Referencia local CC BY:
[`vmd_baseline_2023.pdf`](../../desp_desktop_app/references/vmd_baseline_2023.pdf).
La variante VMD de tres segmentos de 2026 permanece sólo referenciada mediante
su DOI: <https://doi.org/10.1016/j.soildyn.2026.110089>.

## Regla para promover un candidato

```mermaid
flowchart LR
    P[Paper y formulación completa] --> C[Código reproducible]
    C --> S[Pruebas sintéticas]
    S --> B[Benchmark publicado]
    B --> T[Pasos de tren con referencia óptica/LVDT]
    T --> U[Análisis de incertidumbre]
    U --> O[Método operativo]
```

Hasta completar esa cadena, un candidato puede estudiarse pero no debe mezclarse
con resultados operativos en informes sin una etiqueta experimental explícita.
