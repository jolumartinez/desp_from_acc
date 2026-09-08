from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from desp_desktop_app.core.engine import run_method
from desp_desktop_app.core.io import crop_signal
from desp_desktop_app.core.reporting import build_report_html, export_result_bundle, write_pdf_report, write_report
from desp_desktop_app.tests.test_engine import harmonic_record


class ReportingTests(unittest.TestCase):
    def test_offline_html_pdf_and_data_bundle(self) -> None:
        record, _ = harmonic_record()
        result = run_method("park", record)
        html = build_report_html(record, [result], title="Validación", include_steps=False)
        self.assertIn("plotly", html.lower())
        self.assertNotIn("<script src=", html.lower())
        self.assertIn("Park", html)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = write_report(root / "report.html", html)
            pdf = write_pdf_report(root / "report.pdf", record, [result], title="Validación", include_steps=False)
            manifest = export_result_bundle(root / "data", record, [result])
            self.assertGreater(report.stat().st_size, 1_000_000)
            self.assertGreater(pdf.stat().st_size, 10_000)
            self.assertTrue(manifest.is_file())
            self.assertTrue((root / "data" / "park.csv").is_file())

    def test_cropped_segment_provenance_is_exported(self) -> None:
        record, _ = harmonic_record()
        cropped = crop_signal(record, 5.0, 15.0)
        result = run_method("park", cropped)

        html = build_report_html(cropped, [result], title="Segmento", include_steps=False)
        self.assertIn("Segmento original 5-15 s", html)
        with tempfile.TemporaryDirectory() as temp:
            manifest = export_result_bundle(Path(temp), cropped, [result])
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["sample_count"], cropped.time_s.size)
            self.assertEqual(payload["signal_metadata"]["crop_start_s"], 5.0)
            self.assertEqual(payload["signal_metadata"]["crop_end_s"], 15.0)

    def test_bridge_method_is_available_to_reports_and_data_exports(self) -> None:
        record, _ = harmonic_record()
        result = run_method(
            "bunce_bridge",
            record,
            {
                "event_mode": "manual",
                "event_start_s": 2.0,
                "event_end_s": 35.0,
                "candidate_step_s": 0.2,
                "max_candidates": 400,
                "quality_mode": "shoulders",
                "max_lift_mm": 1000.0,
            },
        )
        html = build_report_html(record, [result], title="Puente", include_steps=True)
        self.assertIn("Bunce et al.", html)
        self.assertIn("candidate_windows", html)
        self.assertIn("Ventanas de aceleración evaluadas", html)
        self.assertIn("Qué muestra:", html)
        self.assertIn("<br>Por qué se hace:", html)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = write_pdf_report(
                root / "bunce.pdf",
                record,
                [result],
                title="Puente",
                include_steps=True,
            )
            manifest = export_result_bundle(root, record, [result])
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["results"][0]["summary"]["method_id"], "bunce_bridge")
            self.assertGreater(pdf.stat().st_size, 20_000)
            self.assertTrue((root / "bunce_bridge.csv").is_file())

    def test_quality_warning_is_prominent_in_html_report(self) -> None:
        record, _ = harmonic_record()
        result = run_method("park", record)
        result.diagnostics["quality_warnings"] = ["Resultado exploratorio de prueba."]

        html = build_report_html(record, [result], title="Advertencia", include_steps=False)

        self.assertIn("Advertencia de calidad", html)
        self.assertIn("Resultado exploratorio de prueba.", html)


if __name__ == "__main__":
    unittest.main()
