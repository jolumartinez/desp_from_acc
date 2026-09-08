from __future__ import annotations

import html
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

from desp_desktop_app.core.catalog import METHOD_BY_ID
from desp_desktop_app.core.engine import default_parameters, run_method, run_method_traced
from desp_desktop_app.core.models import PartialMethodResult, SignalRecord
from desp_desktop_app.core.reporting import build_report_html, export_result_bundle, write_pdf_report


METHOD_ID = "martinez_2024"


def modal_record(
    components: tuple[tuple[float, float, float], ...] = ((0.01, 4.0, 0.3),),
    *,
    sample_count: int = 4096,
    sampling_rate: float = 128.0,
    offset: float = 0.0,
) -> SignalRecord:
    time_s = np.arange(sample_count, dtype=float) / sampling_rate
    acceleration = np.full(sample_count, offset)
    for amplitude, frequency, phase in components:
        acceleration += amplitude * np.cos(2.0 * np.pi * frequency * time_s + phase)
    return SignalRecord(Path("modal_signal.txt"), "az", time_s, acceleration, sampling_rate, "m/s²")


def analytical_response(
    time_s: np.ndarray,
    components: tuple[tuple[float, float, float], ...],
    selected_frequencies: tuple[float, ...],
    damping: float,
    *,
    offset: float = 0.0,
) -> np.ndarray:
    """Closed-form steady harmonic response, independent of FFT/Welch implementation."""
    response = np.full(time_s.size, offset * sum(1.0 / (2.0 * np.pi * f) ** 2 for f in selected_frequencies))
    for amplitude, frequency, phase in components:
        omega = 2.0 * np.pi * frequency
        transfer = sum(
            1.0 / complex((2.0 * np.pi * f) ** 2 - omega**2, 2.0 * damping * (2.0 * np.pi * f) * omega)
            for f in selected_frequencies
        )
        response += amplitude * np.real(transfer * np.exp(1j * (omega * time_s + phase)))
    return response


class MartinezMethodTests(unittest.TestCase):
    def test_defaults_preserve_the_original_graph_settings_and_local_reference(self) -> None:
        self.assertEqual(
            default_parameters(METHOD_ID),
            {"num_modes": 20, "damping_ratio": 0.002, "welch_nperseg": 512, "peak_threshold_ratio": 0.001},
        )
        spec = METHOD_BY_ID[METHOD_ID]
        self.assertEqual(spec.short_name, "JM")
        self.assertEqual(spec.local_reference_file, "references/metodoJorgeMartinezNoviembre2024.pdf")
        self.assertEqual(spec.local_reference_page, 1)
        self.assertTrue((Path(__file__).resolve().parents[1] / spec.local_reference_file).is_file())

    def test_resonant_tone_has_the_analytical_modal_gain_and_phase(self) -> None:
        components = ((0.01, 4.0, 0.3),)
        record = modal_record(components)
        for damping in (0.002, 0.035):
            with self.subTest(damping=damping):
                result = run_method(METHOD_ID, record, {"damping_ratio": damping})
                expected = analytical_response(record.time_s, components, (4.0,), damping)
                np.testing.assert_allclose(result.displacement_m, expected, rtol=1.0e-10, atol=1.0e-13)
                np.testing.assert_array_equal(result.acceleration_mps2, record.acceleration_mps2)
                np.testing.assert_allclose(
                    result.velocity_mps,
                    np.gradient(expected, record.time_s, edge_order=2),
                    rtol=1.0e-9,
                    atol=1.0e-11,
                )

    def test_selected_modes_act_on_the_entire_input_spectrum(self) -> None:
        components = ((0.02, 4.0, 0.2), (0.01, 9.0, -0.4), (0.0002, 14.0, 0.7))
        record = modal_record(components)
        result = run_method(METHOD_ID, record, {"num_modes": 2})
        self.assertEqual(result.diagnostics["selected_frequencies_hz"], [4.0, 9.0])
        expected = analytical_response(record.time_s, components, (4.0, 9.0), 0.002)
        np.testing.assert_allclose(result.displacement_m, expected, rtol=1.0e-10, atol=1.0e-13)

        # The weak 14 Hz component is not selected as a mode, but it is not masked
        # out of the input to the two selected transfer functions.
        without_weak_component = analytical_response(record.time_s, components[:2], (4.0, 9.0), 0.002)
        self.assertGreater(float(np.max(np.abs(result.displacement_m - without_weak_component))), 1.0e-8)

    def test_mode_limit_and_relative_psd_threshold_control_selection(self) -> None:
        components = ((0.02, 4.0, 0.2), (0.01, 9.0, -0.4))
        record = modal_record(components)
        for overrides in ({"num_modes": 1}, {"peak_threshold_ratio": 0.4}, {"peak_threshold_ratio": 1.0}):
            with self.subTest(parameters=overrides):
                result = run_method(METHOD_ID, record, overrides)
                self.assertEqual(result.diagnostics["selected_frequencies_hz"], [4.0])
                expected = analytical_response(record.time_s, components, (4.0,), 0.002)
                np.testing.assert_allclose(result.displacement_m, expected, rtol=1.0e-10, atol=1.0e-13)

    def test_constant_acceleration_bias_is_preserved_in_the_displacement_mean(self) -> None:
        record = modal_record(offset=0.05)
        result = run_method(METHOD_ID, record)
        self.assertAlmostEqual(float(np.mean(result.displacement_m)), 0.05 / (2.0 * np.pi * 4.0) ** 2, places=14)
        self.assertEqual(result.diagnostics["dc_policy"], "preserved")

    def test_short_and_odd_records_keep_their_length_and_harmonic_response(self) -> None:
        for count, sampling_rate, frequency in ((4, 128.0, 32.0), (127, 127.0, 7.0), (511, 511.0, 7.0)):
            with self.subTest(sample_count=count):
                components = ((0.01, frequency, 0.0),)
                record = modal_record(components, sample_count=count, sampling_rate=sampling_rate)
                result = run_method(METHOD_ID, record)
                expected = analytical_response(record.time_s, components, (frequency,), 0.002)
                self.assertEqual(result.displacement_m.shape, (count,))
                self.assertEqual(result.diagnostics["welch_nperseg_effective"], count)
                np.testing.assert_allclose(result.displacement_m, expected, rtol=1.0e-9, atol=1.0e-13)

    def test_invalid_parameters_are_rejected(self) -> None:
        record = modal_record()
        invalid = (
            ("num_modes", 0), ("num_modes", 201), ("num_modes", 1.5),
            ("damping_ratio", 0.0), ("damping_ratio", 1.1), ("damping_ratio", float("nan")),
            ("welch_nperseg", 3), ("welch_nperseg", 65537), ("welch_nperseg", 4.5),
            ("peak_threshold_ratio", -0.01), ("peak_threshold_ratio", 1.01),
            ("peak_threshold_ratio", float("nan")),
        )
        for name, value in invalid:
            with self.subTest(parameter=name, value=value):
                with self.assertRaises(ValueError):
                    run_method(METHOD_ID, record, {name: value})

    def test_nonuniform_time_and_inconsistent_sampling_rate_are_rejected(self) -> None:
        irregular = modal_record()
        irregular.time_s[100] += 0.001
        wrong_rate = modal_record()
        wrong_rate.sampling_rate_hz = 100.0
        for record in (irregular, wrong_rate):
            with self.subTest(source=record.sampling_rate_hz):
                with self.assertRaises(ValueError):
                    run_method(METHOD_ID, record)

    def test_no_peaks_preserves_the_psd_for_review_without_a_false_completed_result(self) -> None:
        record = modal_record(components=())
        result = run_method_traced(METHOD_ID, record)
        self.assertIsInstance(result, PartialMethodResult)
        keys = {step.key for step in result.steps}
        self.assertIn("welch_psd", keys)
        self.assertIn("modal_selection", keys)
        self.assertNotIn("final_displacement", keys)
        self.assertTrue(result.failure_message)

    def test_every_selected_mode_has_a_trace_and_the_contributions_sum_to_the_result(self) -> None:
        record = modal_record(((0.02, 4.0, 0.2), (0.01, 9.0, -0.4)))
        received = []
        result = run_method_traced(METHOD_ID, record, step_callback=received.append)
        self.assertNotIsInstance(result, PartialMethodResult)
        self.assertEqual([step.key for step in received], [step.key for step in result.steps])
        contributions = [step for step in result.steps if step.key.startswith("modal_contribution_")]
        self.assertEqual(len(contributions), result.diagnostics["selected_mode_count"])
        values = []
        for step in contributions:
            self.assertEqual(len(step.series), 1)
            np.testing.assert_array_equal(step.x, record.time_s)
            values.append(next(iter(step.series.values())))
        np.testing.assert_allclose(np.sum(values, axis=0), result.displacement_m, rtol=1.0e-11, atol=1.0e-14)
        steps = {step.key: step for step in result.steps}
        for key in ("modal_transfer_amplitude", "modal_transfer_phase", "modal_displacement_spectrum", "derived_velocity"):
            self.assertIn(key, steps)
        self.assertEqual(result.steps[-1].key, "final_displacement")
        self.assertTrue(any(style == "points" for style in steps["modal_selection"].series_styles.values()))
        for step in result.steps:
            for heading in ("Qué muestra:", "Por qué se hace:", "Cómo interpretarla:", "Referencia:"):
                self.assertIn(heading, step.description)


class MartinezReportingTests(unittest.TestCase):
    def test_csv_json_and_html_preserve_results_parameters_and_the_local_citation(self) -> None:
        record = modal_record(sample_count=512)
        result = run_method(METHOD_ID, record)
        spec = METHOD_BY_ID[METHOD_ID]
        document = build_report_html(record, [result], title="Validación modal", include_steps=True)
        self.assertIn(html.escape(spec.reference), document)
        self.assertIn(Path(spec.local_reference_file).name, document)
        self.assertNotIn('href=""', document)
        self.assertNotIn("<script src=", document.lower())
        for step in result.steps:
            self.assertIn(html.escape(step.title), document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = export_result_bundle(root, record, [result])
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            exported = payload["results"][0]
            self.assertEqual(exported["parameters"], result.parameters)
            self.assertEqual(exported["reference"]["citation"], spec.reference)
            self.assertEqual(exported["reference"]["local_file"], spec.local_reference_file)
            self.assertEqual(exported["reference"]["local_page"], 1)
            self.assertEqual(exported["reference"]["url"], "")
            self.assertEqual(exported["summary"]["selected_frequencies_hz"], [4.0])
            self.assertEqual(exported["summary"]["dc_policy"], "preserved")
            table = np.loadtxt(root / f"{METHOD_ID}.csv", delimiter=",", skiprows=1)
            expected = np.column_stack((result.time_s, result.acceleration_mps2, result.velocity_mps, result.displacement_m))
            np.testing.assert_array_equal(table, expected)

    @unittest.skipUnless(shutil.which("pdftotext"), "PDF text inspection requires pdftotext")
    def test_pdf_contains_the_local_citation_and_all_modal_steps(self) -> None:
        record = modal_record(sample_count=512)
        result = run_method(METHOD_ID, record)
        with tempfile.TemporaryDirectory() as directory:
            output = write_pdf_report(Path(directory) / "modal.pdf", record, [result], title="Validación modal", include_steps=True)
            extracted = subprocess.run(["pdftotext", str(output), "-"], check=True, capture_output=True, text=True).stdout
        self.assertIn(Path(METHOD_BY_ID[METHOD_ID].local_reference_file).name, extracted)
        self.assertIn("2024", extracted)
        normalized = " ".join(extracted.split())
        for step in result.steps:
            self.assertIn(" ".join(step.title.split()), normalized)


if __name__ == "__main__":
    unittest.main()
