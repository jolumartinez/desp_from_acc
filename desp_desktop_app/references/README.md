# Referencias offline

Esta carpeta contiene publicaciones con las condiciones indicadas por sus
fuentes y el correo personal aportado por su autor como referencia del método
JM. Los algoritmos siguen necesitando validación independiente antes de un uso
metrológico.

Los [avisos de terceros](../../THIRD_PARTY_NOTICES.md) reúnen las atribuciones,
las condiciones conocidas y los permisos de redistribución pública pendientes.

| Archivo | Uso | Licencia o condición |
| --- | --- | --- |
| `bunce_bridge_displacement_2023.pdf` | Método implementado para puentes y trenes | Artículo abierto CC BY 4.0; conservar atribución |
| `prism_methodology_usgs_2017.pdf` | Referencia de procesamiento y control de calidad | Informe USGS; material público salvo elementos identificados dentro del documento |
| `vmd_baseline_2023.pdf` | Referencia experimental VMD | Artículo abierto CC BY 4.0; conservar atribución |
| [`metodoJorgeMartinezNoviembre2024.pdf`](metodoJorgeMartinezNoviembre2024.pdf) | Propuesta de superposición modal implementada como JM | Correo personal de Jorge Luis Martínez Valencia aportado por su autor como referencia local; el PDF no declara licencia abierta |
| [`tokunaga_bridge_displacement_2022.pdf`](tokunaga_bridge_displacement_2022.pdf) | Fuente principal de la formulación ferroviaria implementada como TK | © 2022 Japan Society of Civil Engineers; acceso libre en J-STAGE; copia íntegra sin modificar, sin atribuir licencia CC BY |

El correo corresponde a la propuesta de noviembre de 2024 según el nombre del
archivo y la identificación aportada por el autor. La copia conservada tiene
cinco páginas y muestra la fecha de impresión del 8 de septiembre de 2026; no
contiene una cabecera de envío con la fecha original verificable. La ecuación
se recupera del código de `easy_ama_jmpc/callbacks/app_callbacks.py`, función
`calculate_displacement_superposition_psd`, pues las imágenes de las fórmulas no
son legibles en esta copia. Véase la
[trazabilidad del método JM](../../docs/desp_desktop_app/13_metodo_jorge_martinez_2024.md).

El artículo de TK es de Munemasa Tokunaga, Manabu Ikeda y Koji Yoshida:
*Displacement response waveform restoration of simply support bridge during
train passage based on measurement acceleration integration*. Journal of Japan
Society of Civil Engineers, Ser. A1 (Structural Engineering & Earthquake
Engineering), 78(1), 47–60, 2022.
[DOI: 10.2208/jscejseee.78.1_47](https://doi.org/10.2208/jscejseee.78.1_47).
La copia procede del
[PDF publicado por J-STAGE](https://www.jstage.jst.go.jp/article/jscejseee/78/1/78_47/_pdf)
y conserva sus 14 páginas. La ficha de TK abre la página 6 del PDF, numerada 52
en el artículo, donde se presenta la identificación de escala.

Referencias editoriales no copiadas:

- Wong e Ibarra, TOA: <https://doi.org/10.1016/j.soildyn.2023.108162>
- He et al., optimización convexa: <https://doi.org/10.1016/j.soildyn.2022.107676>
- Chen y Wang, HSA: <https://doi.org/10.1016/j.soildyn.2022.107162>
- Zhou et al., VMD de tres segmentos: <https://doi.org/10.1016/j.soildyn.2026.110089>
- Tokunaga e Ikeda (2023), exposición complementaria en inglés:
  <https://doi.org/10.2219/rtriqr.64.2_115>
- Tokunaga (2024), continuación con cancelación de ruido, no reproducida en TK:
  <https://doi.org/10.1016/j.istruc.2024.106462>

TK permite consultar su fuente principal de 2022 sin conexión. Las
publicaciones complementarias de 2023 y 2024 mantienen sus enlaces editoriales.
Los cálculos no necesitan conexión. La
[guía de TK](../../docs/desp_desktop_app/14_metodo_tokunaga.md)
identifica las ecuaciones y las diferencias entre versiones.

## Integridad

```text
d665176c475eb957a2b347834756f0a9834171bc1dea22175f1e3c9425259ed9  bunce_bridge_displacement_2023.pdf
8940e2cfe470e3b7638cd8f61d6e81ac79fb5ba56e91d7c5dcd64cd746547103  prism_methodology_usgs_2017.pdf
fd04ae6cfb62644f38de507c1f2889215997b090fe68c7a8f5ef34c9b4c474e3  vmd_baseline_2023.pdf
030912a1969a3f4ed9fb64e39a30a17e2a9bae68f12f83be148f057b2ab76d22  metodoJorgeMartinezNoviembre2024.pdf
7cc62f0729bb9d52b5420541f3db1e59530815e1d76e63a6be7b068484979a9a  tokunaga_bridge_displacement_2022.pdf
```
