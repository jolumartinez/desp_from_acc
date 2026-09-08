# Documentación de DESP Studio

Esta carpeta describe la primera implementación funcional de la aplicación de
desplazamientos construida a partir de `TESIS_DAMARIS_ARIAS_final.pdf`.

## Índice

1. [Arquitectura y flujo](01_arquitectura_y_flujo.md)
2. [Métodos implementados](02_metodos_implementados.md)
3. [Validación y datos de referencia](03_validacion_y_datos.md)
4. [Lanzamiento, operación y distribución](04_lanzamiento_y_distribucion.md)
5. [Preajustes y trazabilidad con la tesis](05_preajustes_tesis.md)
6. [Interacción con gráficas, recorte y etapas](06_interaccion_y_recorte.md)
7. [Auditoría de métodos y estado del arte](07_auditoria_y_estado_del_arte.md)
8. [Método de puentes y decisión sobre candidatos](08_metodo_bunce_y_seleccion_tecnica.md)
9. [Fichas y diagramas de métodos candidatos](09_fichas_metodos_candidatos.md)
10. [Aislamiento, cancelación y recuperación](10_aislamiento_y_recuperacion.md)
11. [Guía visual del método BU 2023](11_guia_visual_bu_2023.md)
12. [Auditoría de fidelidad del método BU 2023](12_auditoria_fidelidad_bu_2023.md)

## Estado resumido

| Componente | Estado |
| --- | --- |
| Lector multicanal TXT | Funcional |
| Siete métodos de la tesis | Funcionales en Python |
| Método Bunce para puentes y trenes | Funcional; validación propia pendiente |
| Controles independientes | Funcionales |
| Gráficas por etapa | Funcionales, embebidas e interactivas |
| Ejecuciones parciales | Conservan las etapas alcanzadas; se excluyen de comparación e informe |
| Zoom, paneo, historial y exportación de gráficas | Funcionales mediante Matplotlib |
| Recorte temporal no destructivo | Funcional; conserva trazabilidad del intervalo original |
| Navegación de etapas | Selector directo y controles anterior/siguiente |
| Carga asíncrona | Funcional; lectura y FFT fuera del hilo Qt |
| Aislamiento del cálculo | Funcional; un proceso descartable por método |
| Cancelación y tiempo límite | Funcionales; conserva etapas completadas y evita procesos huérfanos |
| Auditoría contra los scripts MATLAB | Flujo revisado; equivalencia numérica pendiente de datos originales |
| Comparación de resultados | Funcional |
| HTML offline, PDF, CSV y JSON | Funcionales |
| Casos sintéticos reproducibles | Incluidos |
| Validación bit a bit contra MATLAB | Pendiente de los archivos originales |
| Datos AKTH10 | Descargador incluido; requiere cuenta NIED |
| Datos experimentales de puentes/péndulo/mesa | No publicados junto con la tesis |
| Biblioteca de referencias offline | Bunce, PRISM y VMD 2023 incluidos conforme a sus licencias |

La palabra **funcional** significa que el flujo ejecuta, produce series finitas y
está cubierto por pruebas de contrato. No significa todavía que todos los
resultados hayan sido acreditados contra los archivos experimentales originales.
