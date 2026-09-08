from __future__ import annotations

import base64
import html
import io
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from .analysis import comparison_rows, pairwise_correlation
from .catalog import METHOD_BY_ID
from .models import MethodResult, ProcessStep, SignalRecord
from .signal_ops import displacement_scale


COLORS = ("#005199", "#008BAC", "#3CBFAE", "#8F489A", "#F5A114", "#CA252C", "#6588B1")


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _segment_description(record: SignalRecord) -> str:
    start = record.metadata.get("crop_start_s")
    end = record.metadata.get("crop_end_s")
    if start is None or end is None:
        return "Señal completa"
    return f"Segmento original {float(start):.6g}-{float(end):.6g} s"


def _step_png(step: ProcessStep) -> str:
    figure = Figure(figsize=(9.2, 3.2), dpi=120)
    FigureCanvasAgg(figure)
    axis = figure.add_subplot(111)
    _draw_step_series(axis, step)
    axis.set_title(step.title, loc="left", color="#00205B", fontsize=11, fontweight="bold")
    axis.set_xlabel(step.x_label)
    axis.set_ylabel(step.y_label)
    axis.grid(True, color="#DAD9D7", linewidth=0.7, alpha=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    if len(step.series) > 1:
        axis.legend(frameon=False, ncol=min(3, len(step.series)))
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _draw_step_series(axis: Any, step: ProcessStep) -> None:
    for index, (label, values) in enumerate(step.series.items()):
        style = step.series_styles.get(label, "line")
        options: dict[str, Any] = {
            "label": label,
            "color": COLORS[index % len(COLORS)],
        }
        if style == "points":
            options.update({"linestyle": "none", "marker": "o", "markersize": 4.5})
        else:
            options.update(
                {"linestyle": "--" if style == "dashed" else "-", "linewidth": 1.1}
            )
        axis.plot(step.x, values, **options)


def _comparison_html(results: list[MethodResult], unit: str) -> str:
    factor, label = displacement_scale(unit)
    figure = go.Figure()
    for index, result in enumerate(results):
        figure.add_trace(
            go.Scatter(
                x=result.time_s,
                y=result.displacement_m * factor,
                mode="lines",
                name=result.method_name,
                line={"color": COLORS[index % len(COLORS)], "width": 1.5},
            )
        )
    figure.update_layout(
        template="plotly_white",
        height=480,
        margin={"l": 58, "r": 24, "t": 48, "b": 52},
        title={"text": "Comparación de desplazamientos", "x": 0.02},
        xaxis_title="Tiempo [s]",
        yaxis_title=f"Desplazamiento [{label}]",
        hovermode="x unified",
        font={"family": "Arial, sans-serif", "color": "#323E48"},
        legend={"orientation": "h", "y": 1.12, "x": 0.0},
    )
    return pio.to_html(figure, full_html=False, include_plotlyjs=True, config={"displaylogo": False, "responsive": True})


def build_report_html(
    record: SignalRecord,
    results: Iterable[MethodResult],
    *,
    title: str,
    displacement_unit: str = "mm",
    include_steps: bool = True,
) -> str:
    items = list(results)
    if not items:
        raise ValueError("El informe requiere al menos un método ejecutado.")
    factor, unit_label = displacement_scale(displacement_unit)
    rows = comparison_rows(items)
    names, correlation = pairwise_correlation(items)
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    segment_description = _segment_description(record)

    metric_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['method']))}</td>"
        f"<td>{float(row['peak_m']) * factor:.5g}</td>"
        f"<td>{float(row['residual_m']) * factor:.5g}</td>"
        f"<td>{float(row['rms_m']) * factor:.5g}</td>"
        f"<td>{float(row['correlation_consensus']):.4f}</td>"
        f"<td>{float(row['nrmse_consensus']):.4f}</td>"
        f"<td>{float(row['elapsed_s']):.3f}</td>"
        "</tr>"
        for row in rows
    )
    correlation_header = "".join(f"<th>{html.escape(name)}</th>" for name in names)
    correlation_rows = "".join(
        f"<tr><th>{html.escape(names[i])}</th>"
        + "".join(f"<td>{correlation[i, j]:.3f}</td>" for j in range(len(names)))
        + "</tr>"
        for i in range(len(names))
    )

    method_sections: list[str] = []
    for result in items:
        spec = METHOD_BY_ID[result.method_id]
        reference_html = html.escape(spec.reference)
        if spec.reference_url:
            reference_html = f'<a href="{html.escape(spec.reference_url)}">{reference_html}</a>'
        elif spec.local_reference_file:
            reference_html += f" Documento local: <code>{html.escape(spec.local_reference_file)}</code>."
        parameter_rows = "".join(
            f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
            for key, value in result.parameters.items()
        )
        diagnostic_rows = "".join(
            f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>"
            for key, value in result.summary().items()
            if key not in {"method_id", "method"}
        )
        warnings = result.diagnostics.get("quality_warnings", [])
        if isinstance(warnings, str):
            warnings = [warnings]
        warning_html = "".join(
            f"<p class='quality-warning'><strong>Advertencia de calidad:</strong> {html.escape(str(warning))}</p>"
            for warning in warnings
        )
        flow = "".join(f"<span>{index + 1}. {html.escape(label)}</span>" for index, label in enumerate(spec.flow))
        charts = ""
        if include_steps:
            charts = "".join(
                "<figure>"
                f"<img src='data:image/png;base64,{_step_png(step)}' alt='{html.escape(step.title)}'>"
                f"<figcaption>{html.escape(step.description).replace(chr(10), '<br>')}</figcaption>"
                "</figure>"
                for step in result.steps
            )
        method_sections.append(
            f"""
            <section class="method">
              <div class="method-head"><span class="code">{spec.short_name}</span><div><h2>{html.escape(spec.name)}</h2><p>{html.escape(spec.summary)}</p></div></div>
              <div class="flow">{flow}</div>
              {warning_html}
              <p><strong>Uso recomendado:</strong> {html.escape(spec.intended_use)}</p>
              <p><strong>Limitación:</strong> {html.escape(spec.limitation)}</p>
              <p class="reference"><strong>Referencia:</strong> {reference_html} {html.escape(spec.thesis_pages)}</p>
              <div class="two-col"><div><h3>Configuración</h3><table>{parameter_rows}</table></div><div><h3>Resultado</h3><table>{diagnostic_rows}</table></div></div>
              {charts}
            </section>
            """
        )

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{margin:0;background:#F4F5F3;color:#323E48;font-family:Arial,sans-serif;line-height:1.5}}main{{max-width:1180px;margin:auto;background:white;min-height:100vh}}header{{padding:42px 54px;background:#00205B;color:white}}header h1{{margin:0 0 8px;font-size:30px}}header p{{margin:4px 0;color:#D9EEF8}}section{{padding:30px 54px;border-bottom:1px solid #DAD9D7}}h2,h3{{color:#00205B}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:8px 10px;border-bottom:1px solid #DAD9D7;text-align:right}}th:first-child,td:first-child{{text-align:left}}.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:30px}}.method-head{{display:flex;gap:16px;align-items:flex-start}}.code{{display:grid;place-items:center;min-width:52px;height:52px;background:#008BAC;color:white;font-weight:bold;font-size:18px}}.flow{{display:flex;gap:5px;flex-wrap:wrap;margin:18px 0}}.flow span{{padding:7px 10px;background:#EAF4F7;border-left:3px solid #008BAC;font-size:12px}}.quality-warning{{padding:10px 14px;color:#6B4300;background:#FFF4DC;border-left:4px solid #F5A114}}figure{{margin:24px 0}}figure img{{width:100%;height:auto}}figcaption,.reference{{font-size:12px;color:#54565B}}a{{color:#005199}}@media(max-width:760px){{header,section{{padding:24px}}.two-col{{grid-template-columns:1fr}}}}@media print{{body{{background:white}}main{{max-width:none}}.method{{break-before:page}}}}
</style></head><body><main>
<header><h1>{html.escape(title)}</h1><p>Estudio de desplazamientos derivados de aceleración</p><p>{html.escape(record.source_path.name)} · Canal {html.escape(record.channel)} · {record.sampling_rate_hz:.6g} Hz · {html.escape(segment_description)} · Generado {generated}</p></header>
<section><h2>Comparación</h2>{_comparison_html(items, displacement_unit)}
<h3>Indicadores respecto al consenso mediano</h3><table><thead><tr><th>Método</th><th>Pico [{unit_label}]</th><th>Residual [{unit_label}]</th><th>RMS [{unit_label}]</th><th>Correlación</th><th>NRMSE</th><th>Tiempo [s]</th></tr></thead><tbody>{metric_rows}</tbody></table>
<h3>Correlación entre métodos</h3><table><thead><tr><th>Método</th>{correlation_header}</tr></thead><tbody>{correlation_rows}</tbody></table></section>
{''.join(method_sections)}
<section><p class="reference">Las estimaciones dependen de la calidad de la aceleración, la banda seleccionada y las hipótesis de línea base. Deben revisarse visualmente y mediante análisis de sensibilidad antes de emplearlas para decisiones estructurales.</p></section>
</main></body></html>"""


def export_result_bundle(output_dir: Path, record: SignalRecord, results: Iterable[MethodResult]) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    items = list(results)
    for result in items:
        data = np.column_stack((result.time_s, result.acceleration_mps2, result.velocity_mps, result.displacement_m))
        np.savetxt(
            output_dir / f"{result.method_id}.csv",
            data,
            delimiter=",",
            header="time_s,acceleration_mps2,velocity_mps,displacement_m",
            comments="",
        )
    payload = {
        "source": str(record.source_path),
        "channel": record.channel,
        "sampling_rate_hz": record.sampling_rate_hz,
        "input_unit": record.input_unit,
        "sample_count": int(record.time_s.size),
        "signal_metadata": _json_ready(record.metadata),
        "results": [
            {
                "summary": _json_ready(result.summary()),
                "parameters": _json_ready(result.parameters),
                "reference": {
                    "citation": METHOD_BY_ID[result.method_id].reference,
                    "basis": METHOD_BY_ID[result.method_id].reference_basis,
                    "url": METHOD_BY_ID[result.method_id].reference_url,
                    "local_file": METHOD_BY_ID[result.method_id].local_reference_file,
                    "local_page": METHOD_BY_ID[result.method_id].local_reference_page,
                },
            }
            for result in items
        ],
    }
    manifest = output_dir / "results.json"
    manifest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def write_report(path: Path, html_text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    return path


def write_pdf_report(
    path: Path,
    record: SignalRecord,
    results: Iterable[MethodResult],
    *,
    title: str,
    displacement_unit: str = "mm",
    include_steps: bool = True,
) -> Path:
    items = list(results)
    if not items:
        raise ValueError("El informe requiere al menos un método ejecutado.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    factor, unit_label = displacement_scale(displacement_unit)
    rows = comparison_rows(items)

    with PdfPages(path) as pdf:
        cover = Figure(figsize=(8.27, 11.69))
        cover.patch.set_facecolor("white")
        cover.text(0.08, 0.92, title, color="#00205B", fontsize=24, weight="bold")
        cover.text(0.08, 0.875, "Estudio de desplazamientos derivados de aceleración", color="#008BAC", fontsize=12)
        source = (
            f"Fuente: {record.source_path.name}\nCanal: {record.channel}\n"
            f"Frecuencia de muestreo: {record.sampling_rate_hz:.6g} Hz\n"
            f"Datos: {_segment_description(record)} ({record.time_s.size:,} muestras)\n"
            f"Métodos incluidos: {len(items)}"
        )
        cover.text(0.08, 0.80, source, color="#323E48", fontsize=10, linespacing=1.6)
        cover.text(
            0.08,
            0.70,
            "El resultado depende de la calidad del acelerograma, las frecuencias de corte y las hipótesis de línea base. "
            "Debe revisarse junto con el análisis de sensibilidad y el contexto físico de la medición.",
            color="#54565B",
            fontsize=10,
            wrap=True,
        )
        cover_axis = cover.add_axes((0.08, 0.35, 0.84, 0.27))
        cover_axis.axis("off")
        cell_text = [
            [
                str(row["method"]),
                f"{float(row['peak_m']) * factor:.5g}",
                f"{float(row['residual_m']) * factor:.5g}",
                f"{float(row['correlation_consensus']):.4f}",
            ]
            for row in rows
        ]
        table = cover_axis.table(
            cellText=cell_text,
            colLabels=("Método", f"Pico [{unit_label}]", f"Residual [{unit_label}]", "Corr. consenso"),
            loc="upper left",
            cellLoc="right",
            colLoc="right",
            colWidths=(0.42, 0.19, 0.20, 0.19),
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.5)
        pdf.savefig(cover, bbox_inches="tight")

        comparison = Figure(figsize=(11.69, 8.27))
        axis = comparison.add_subplot(111)
        for index, result in enumerate(items):
            axis.plot(
                result.time_s,
                result.displacement_m * factor,
                label=result.method_name,
                color=COLORS[index % len(COLORS)],
                linewidth=1.2,
            )
        axis.set_title("Comparación de desplazamientos", loc="left", color="#00205B", fontsize=15, weight="bold")
        axis.set_xlabel("Tiempo [s]")
        axis.set_ylabel(f"Desplazamiento [{unit_label}]")
        axis.grid(True, color="#DAD9D7", alpha=0.75)
        axis.spines[["top", "right"]].set_visible(False)
        axis.legend(frameon=False, ncol=min(3, len(items)))
        comparison.tight_layout()
        pdf.savefig(comparison)

        for result in items:
            spec = METHOD_BY_ID[result.method_id]
            warnings = result.diagnostics.get("quality_warnings", [])
            if isinstance(warnings, str):
                warnings = [warnings]
            method_cover = Figure(figsize=(8.27, 11.69))
            method_cover.text(0.08, 0.92, f"{spec.short_name}  {spec.name}", color="#00205B", fontsize=20, weight="bold")
            method_cover.text(0.08, 0.87, "\n".join(textwrap.wrap(spec.summary, 92)), color="#323E48", fontsize=10)
            if warnings:
                warning_text = "Advertencia de calidad: " + " ".join(str(item) for item in warnings)
                method_cover.text(
                    0.08,
                    0.80,
                    "\n".join(textwrap.wrap(warning_text, 100)),
                    color="#6B4300",
                    fontsize=9,
                    bbox={"facecolor": "#FFF4DC", "edgecolor": "#F5A114", "pad": 7},
                )
            flow_title_y = 0.70 if warnings else 0.78
            flow_text_y = 0.66 if warnings else 0.74
            configuration_title_y = 0.55 if warnings else 0.63
            configuration_text_y = 0.51 if warnings else 0.59
            method_cover.text(0.08, flow_title_y, "Flujo", color="#008BAC", fontsize=12, weight="bold")
            flow_text = "  >  ".join(f"{index + 1}. {label}" for index, label in enumerate(spec.flow))
            method_cover.text(0.08, flow_text_y, "\n".join(textwrap.wrap(flow_text, 92)), color="#323E48", fontsize=9)
            method_cover.text(0.08, configuration_title_y, "Configuración", color="#008BAC", fontsize=12, weight="bold")
            configuration = "\n".join(f"{key}: {value}" for key, value in result.parameters.items())
            method_cover.text(0.08, configuration_text_y, configuration, color="#323E48", fontsize=8, linespacing=1.35)
            reference_location = spec.reference_url or spec.local_reference_file or ""
            reference = f"Referencia: {spec.reference}\n{reference_location}\n{spec.thesis_pages}"
            method_cover.text(0.08, 0.18, "\n".join(textwrap.wrap(reference, 100)), color="#54565B", fontsize=8)
            pdf.savefig(method_cover, bbox_inches="tight")

            selected_steps = result.steps if include_steps else result.steps[-1:]
            for step in selected_steps:
                figure = Figure(figsize=(11.69, 8.27))
                step_axis = figure.add_subplot(111)
                _draw_step_series(step_axis, step)
                step_axis.set_title(step.title, loc="left", color="#00205B", fontsize=15, weight="bold")
                step_axis.set_xlabel(step.x_label)
                step_axis.set_ylabel(step.y_label)
                step_axis.grid(True, color="#DAD9D7", alpha=0.75)
                step_axis.spines[["top", "right"]].set_visible(False)
                if len(step.series) > 1:
                    step_axis.legend(frameon=False, ncol=min(3, len(step.series)))
                explanation = "\n".join(
                    wrapped
                    for paragraph in step.description.splitlines()
                    for wrapped in (textwrap.wrap(paragraph, 135) or [""])
                )
                figure.text(0.10, 0.02, explanation, color="#54565B", fontsize=8)
                figure.tight_layout(rect=(0, 0.14, 1, 1))
                pdf.savefig(figure)
    return path
