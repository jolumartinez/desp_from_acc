from __future__ import annotations

from functools import lru_cache
import html
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.integrate import quad, solve_ivp

from desp_desktop_app.core.catalog import METHOD_BY_ID
from desp_desktop_app.core.engine import default_parameters, run_method, run_method_traced
from desp_desktop_app.core.execution import run_method_isolated
from desp_desktop_app.core.models import MethodResult, PartialMethodResult, SignalRecord
from desp_desktop_app.core.reporting import build_report_html, export_result_bundle
from desp_desktop_app.core.tokunaga import half_sine_spectrum, train_spectrum


METHOD_ID = "tokunaga_bridge"
STATIC_DISPLACEMENT_M = -0.001


def bridge_parameters() -> dict[str, float | int | str]:
    return {
        "bridge_span_m": 20.0,
        "train_speed_kmh": 72.0,
        "vehicle_count": 2,
        "vehicle_length_m": 20.0,
        "axle_spacing_m": 2.0,
        "bogie_spacing_m": 14.0,
        "natural_frequency_hz": 5.0,
        "entry_time_s": 2.0,
        "damping_ratio": 0.02,
        "deflection_direction": "negative",
        "band_mode": "publication",
        "spectral_floor_ratio": 0.01,
        "padding_factor": 2,
    }


@lru_cache(maxsize=2)
def _moving_load_solution(sampling_rate: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Independent time-domain oracle: solve the forced SDOF initial-value problem.

    Each axle applies a half-sine modal force while on the span. Acceleration
    comes from the differential equation, without FFTs or numerical derivatives.
    The explicit axle entry times deliberately do not use the production geometry
    or spectral helpers. The long quiet tail makes finite-record effects small.
    """
    time = np.arange(round(32.0 * sampling_rate), dtype=float) / sampling_rate
    axle_entries = np.array([2.0, 2.1, 2.7, 2.8, 3.0, 3.1, 3.7, 3.8])
    omega_b = 2.0 * np.pi * 5.0
    damping = 0.02

    def load(at: float | np.ndarray) -> np.ndarray:
        age = np.asarray(at)[..., None] - axle_entries
        return np.sum(np.where((age >= 0.0) & (age <= 1.0), np.sin(np.pi * age), 0.0), axis=-1)

    def equation(at: float, state: np.ndarray) -> tuple[float, float]:
        displacement, velocity = state
        acceleration = omega_b**2 * (STATIC_DISPLACEMENT_M * float(load(at)) - displacement)
        acceleration -= 2.0 * damping * omega_b * velocity
        return velocity, acceleration

    solution = solve_ivp(
        equation, (0.0, float(time[-1])), (0.0, 0.0), t_eval=time,
        method="DOP853", rtol=2.0e-11, atol=1.0e-13, max_step=0.01,
    )
    if not solution.success:
        raise AssertionError(solution.message)
    displacement, velocity = solution.y
    acceleration = omega_b**2 * (STATIC_DISPLACEMENT_M * load(time) - displacement)
    acceleration -= 2.0 * damping * omega_b * velocity
    return time, acceleration, displacement, velocity


def moving_train_record(sampling_rate: float = 128.0) -> tuple[SignalRecord, np.ndarray, np.ndarray]:
    time, acceleration, displacement, velocity = _moving_load_solution(sampling_rate)
    return (
        SignalRecord(Path("moving_train.txt"), "az", time.copy(), acceleration.copy(), sampling_rate, "m/s²"),
        displacement.copy(),
        velocity.copy(),
    )


@lru_cache(maxsize=1)
def six_axle_solution() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Independent SDOF solution for the user's six axles at 72 km/h.

    Arrival times are explicit, independent of the spacing parser, FFT model,
    and regular-vehicle factorization. Returns midspan acceleration and motion.
    """
    time = np.arange(4096, dtype=float) / 128.0
    arrivals = np.array([2.0, 2.87, 3.7575, 4.645, 5.5325, 6.4025])
    omega = 2.0 * np.pi * 5.0

    def forcing(at: float | np.ndarray) -> np.ndarray:
        age = np.asarray(at)[..., None] - arrivals
        return np.sum(np.where((age >= 0.0) & (age <= 1.0), np.sin(np.pi * age), 0.0), axis=-1)

    def equation(at: float, state: np.ndarray) -> tuple[float, float]:
        displacement, velocity = state
        return velocity, omega**2 * (-0.001 * float(forcing(at)) - displacement) - 0.04 * omega * velocity

    solution = solve_ivp(equation, (0.0, time[-1]), (0.0, 0.0), t_eval=time,
                         method="DOP853", rtol=2e-11, atol=1e-13, max_step=0.01)
    if not solution.success:
        raise AssertionError(solution.message)
    displacement, velocity = solution.y
    acceleration = omega**2 * (-0.001 * forcing(time) - displacement) - 0.04 * omega * velocity
    return time, acceleration, displacement


def integrated_half_sine(omega: float, duration: float, entry: float = 0.0) -> complex:
    """Quadrature of the defining Fourier integral, including its phase origin."""
    real = quad(lambda age: np.sin(np.pi * age / duration) * np.cos(omega * (age + entry)), 0.0, duration,
                epsabs=1.0e-12, epsrel=1.0e-12)[0]
    imag = quad(lambda age: -np.sin(np.pi * age / duration) * np.sin(omega * (age + entry)), 0.0, duration,
                epsabs=1.0e-12, epsrel=1.0e-12)[0]
    return complex(real, imag)


class TokunagaSpectrumTests(unittest.TestCase):
    def test_half_sine_transform_matches_quadrature_at_dc_and_removable_poles(self) -> None:
        duration = 0.73
        omega = np.array([0.0, 1.0e-10, np.pi / duration, -np.pi / duration,
                          np.pi / duration * (1.0 + 1.0e-12), 7.3 / duration, 10.0 * np.pi / duration])
        expected = np.array([integrated_half_sine(value, duration) for value in omega])
        actual = half_sine_spectrum(omega, duration)
        self.assertTrue(np.all(np.isfinite(actual)))
        np.testing.assert_allclose(actual, expected, rtol=2.0e-10, atol=2.0e-13)
        self.assertAlmostEqual(float(actual[0].real), 2.0 * duration / np.pi, places=13)

    def test_train_transform_preserves_each_axle_area_and_entry_phase(self) -> None:
        positions = np.array([0.0, 2.0, 14.0, 16.0, 20.0, 22.0, 34.0, 36.0])
        omega = 2.0 * np.pi * np.array([0.0, 0.17, 0.5, 1.0, 2.0, 3.73])
        expected = np.array([
            sum(integrated_half_sine(value, 1.0, 2.0 + position / 20.0) for position in positions)
            for value in omega
        ])
        actual = train_spectrum(omega, 20.0, 20.0, positions, 2.0)
        np.testing.assert_allclose(actual, expected, rtol=2.0e-10, atol=2.0e-13)
        self.assertAlmostEqual(float(actual[0].real), 8.0 * 2.0 / np.pi, places=12)
        self.assertLess(abs(actual[2]), 1.0e-12)  # The two vehicles cancel at 0.5 Hz.


class TokunagaMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record, cls.truth, cls.velocity_truth = moving_train_record()
        cls.parameters = bridge_parameters()

    def test_defaults_preload_six_axles_but_require_span_speed_and_sensor(self) -> None:
        defaults = default_parameters(METHOD_ID)
        for key in ("bridge_span_m", "train_speed_kmh", "sensor_position_m", "vehicle_count", "vehicle_length_m",
                    "axle_spacing_m", "bogie_spacing_m", "natural_frequency_hz"):
            self.assertEqual(defaults[key], 0, key)
        self.assertEqual(defaults["train_geometry_mode"], "axle_spacings")
        self.assertEqual(defaults["axle_spacings_m"], "17.4, 17.75, 17.75, 17.75, 17.4")
        self.assertEqual(defaults["entry_mode"], "automatic")
        self.assertEqual(defaults["frequency_mode"], "span_estimate")
        self.assertEqual(defaults["damping_ratio"], 0.02)
        self.assertEqual(defaults["band_mode"], "publication")
        self.assertEqual(defaults["padding_factor"], 2)
        spec = METHOD_BY_ID[METHOD_ID]
        self.assertEqual(spec.short_name, "TK")
        self.assertEqual(spec.year, 2022)
        self.assertEqual(spec.reference_basis, "publicación")
        self.assertIn("Tokunaga", spec.reference)
        self.assertTrue(spec.reference_url.startswith("https://"))

    def test_noiseless_acceleration_recovers_the_independent_moving_load_solution(self) -> None:
        result = run_method(METHOD_ID, self.record, self.parameters)
        peak = float(np.max(np.abs(self.truth)))
        self.assertLess(float(np.max(np.abs(result.displacement_m - self.truth))) / peak, 0.005)
        self.assertLess(float(np.max(np.abs(result.velocity_mps - self.velocity_truth))) /
                        float(np.max(np.abs(self.velocity_truth))), 0.01)
        self.assertAlmostEqual(abs(result.diagnostics["unit_static_displacement_m"]), abs(STATIC_DISPLACEMENT_M),
                               delta=abs(STATIC_DISPLACEMENT_M) * 0.005)
        self.assertLess(result.diagnostics["fit_relative_error"], 0.01)
        self.assertEqual(result.diagnostics["fit_min_hz_used"], 0.5)
        self.assertEqual(result.diagnostics["fit_max_hz_used"], 3.0)
        self.assertEqual(result.diagnostics["replacement_hz_used"], 3.0)
        self.assertEqual(result.steps[-1].key, "final_displacement")
        raw = next(step for step in result.steps if step.key == "raw_acceleration")
        self.assertTrue(any(np.array_equal(values, self.record.acceleration_mps2) for values in raw.series.values()))

    def test_six_default_axles_recover_displacement_at_midspan_and_quarter_span(self) -> None:
        time, acceleration, truth = six_axle_solution()
        for sensor_position, sensor_factor in ((10.0, 1.0), (5.0, np.sqrt(0.5))):
            with self.subTest(sensor_position=sensor_position):
                record = SignalRecord(Path("six_axles.txt"), "az", time, acceleration * sensor_factor, 128.0, "m/s²")
                result = run_method(METHOD_ID, record, {
                    "bridge_span_m": 20.0, "train_speed_kmh": 72.0, "sensor_position_m": sensor_position,
                    "entry_time_s": 2.0, "natural_frequency_hz": 5.0,
                })
                self.assertLess(float(np.max(np.abs(result.displacement_m - truth * sensor_factor))) /
                                float(np.max(np.abs(truth * sensor_factor))), 0.005)
                self.assertAlmostEqual(result.diagnostics["unit_static_displacement_m"], 0.001, delta=5e-6)
                np.testing.assert_allclose(result.diagnostics["axle_positions_m"], [0, 17.4, 35.15, 52.9, 70.65, 88.05])
                self.assertEqual(result.diagnostics["axle_count"], 6)
                self.assertAlmostEqual(result.diagnostics["train_exit_time_s"], 7.4025)
                self.assertAlmostEqual(result.diagnostics["sensor_mode_factor"], sensor_factor)
                self.assertEqual(result.parameters["train_geometry_mode"], "axle_spacings")
                step = next(step for step in result.steps if step.key == "free_vibration_spectrum")
                peak_frequency = step.x[np.argmax(step.series["PSD posterior al paso"])]
                self.assertAlmostEqual(peak_frequency, 5.0, delta=0.1)

    def test_sensor_position_does_not_convert_local_measurement_to_midspan_motion(self) -> None:
        time, acceleration, _ = six_axle_solution()
        record = SignalRecord(Path("six_axles.txt"), "az", time, acceleration, 128.0, "m/s²")
        parameters = {"bridge_span_m": 20.0, "train_speed_kmh": 72.0,
                      "entry_time_s": 2.0, "natural_frequency_hz": 5.0}
        central = run_method(METHOD_ID, record, {**parameters, "sensor_position_m": 10.0})
        quarter = run_method(METHOD_ID, record, {**parameters, "sensor_position_m": 5.0})
        np.testing.assert_allclose(quarter.displacement_m, central.displacement_m, atol=1e-14, rtol=1e-12)
        self.assertAlmostEqual(quarter.diagnostics["unit_static_displacement_m"] * np.sqrt(0.5),
                               central.diagnostics["unit_static_displacement_m"], places=12)

    def test_estimated_defaults_are_visible_exported_and_can_be_reproduced_manually(self) -> None:
        time, acceleration, _ = six_axle_solution()
        record = SignalRecord(Path("six_axles.txt"), "az", time, acceleration, 128.0, "m/s²")
        # These are the only three inputs the user needs to supply for TK.
        parameters = {"bridge_span_m": 20.0, "train_speed_kmh": 72.0, "sensor_position_m": 10.0}
        result = run_method(METHOD_ID, record, parameters)
        diagnostics = result.diagnostics
        self.assertEqual(diagnostics["entry_mode"], "automatic")
        self.assertEqual(diagnostics["frequency_mode"], "span_estimate")
        self.assertAlmostEqual(diagnostics["natural_frequency_hz_used"], 50.0 * 20.0**-0.8)
        self.assertGreater(diagnostics["entry_time_s_used"], 1.8)
        self.assertLess(diagnostics["entry_time_s_used"], 2.5)
        self.assertAlmostEqual(diagnostics["train_exit_time_s"] - diagnostics["entry_time_s_used"], 5.4025)
        self.assertTrue(any("t₀=" in warning for warning in diagnostics["quality_warnings"]))
        self.assertTrue(any("aproximación por luz" in warning for warning in diagnostics["quality_warnings"]))
        self.assertTrue({"entry_detection", "load_interval", "sensor_mode_shape", "free_vibration_spectrum"}
                        <= {step.key for step in result.steps})
        manual = run_method(METHOD_ID, record, {
            **parameters, "entry_time_s": diagnostics["entry_time_s_used"],
            "natural_frequency_hz": diagnostics["natural_frequency_hz_used"],
        })
        np.testing.assert_allclose(manual.displacement_m, result.displacement_m, atol=1e-14, rtol=1e-12)
        with tempfile.TemporaryDirectory() as temporary:
            manifest = export_result_bundle(Path(temporary), record, [result])
            payload = json.loads(manifest.read_text(encoding="utf-8"))["results"][0]
            self.assertEqual(payload["parameters"]["frequency_mode"], "span_estimate")
            self.assertEqual(payload["summary"]["axle_count"], 6)
            self.assertEqual(payload["summary"]["entry_time_s_used"], diagnostics["entry_time_s_used"])
            self.assertEqual(payload["summary"]["natural_frequency_hz_used"], diagnostics["natural_frequency_hz_used"])

    def test_explicit_geometry_rejects_invalid_spacings_sensor_and_modes(self) -> None:
        parameters = {"bridge_span_m": 20.0, "train_speed_kmh": 72.0, "sensor_position_m": 10.0,
                      "entry_time_s": 2.0, "natural_frequency_hz": 5.0}
        for invalid in ({"axle_spacings_m": "17.4, nan"}, {"axle_spacings_m": "17.4, 0"},
                        {"sensor_position_m": 0.0}, {"sensor_position_m": 20.0}, {"sensor_position_m": 21.0},
                        {"sensor_position_m": float("nan")}, {"train_geometry_mode": "unknown"},
                        {"entry_mode": "unknown"}, {"frequency_mode": "unknown"}):
            with self.subTest(invalid=invalid):
                result = run_method_traced(METHOD_ID, self.record, {**parameters, **invalid})
                self.assertIsInstance(result, PartialMethodResult)
                self.assertIn("raw_acceleration", [step.key for step in result.steps])
                self.assertNotIn("final_displacement", [step.key for step in result.steps])

    def test_sampling_rate_and_padding_do_not_change_the_physical_displacement_scale(self) -> None:
        for sampling_rate, padding in ((128.0, 1), (128.0, 4), (256.0, 2)):
            with self.subTest(sampling_rate=sampling_rate, padding=padding):
                record, truth, _ = moving_train_record(sampling_rate)
                result = run_method(METHOD_ID, record, {**self.parameters, "padding_factor": padding})
                self.assertAlmostEqual(abs(result.diagnostics["unit_static_displacement_m"]), 0.001, delta=5.0e-6)
                self.assertLess(float(np.max(np.abs(result.displacement_m - truth))) /
                                float(np.max(np.abs(truth))), 0.005)

    def test_output_derivatives_and_nonzero_displacement_dc_are_consistent(self) -> None:
        # No padding: the returned record spans the complete transform, allowing
        # a direct check of physical differentiation and the Nyquist convention.
        result = run_method(METHOD_ID, self.record, {**self.parameters, "padding_factor": 1})
        omega = 2.0 * np.pi * np.fft.rfftfreq(self.record.time_s.size, 1.0 / self.record.sampling_rate_hz)
        displacement_fft = np.fft.rfft(result.displacement_m)
        expected_velocity_fft = 1j * omega * displacement_fft
        expected_velocity_fft[-1] = 0.0
        np.testing.assert_allclose(np.fft.rfft(result.velocity_mps), expected_velocity_fft, rtol=2.0e-8, atol=1.0e-11)
        np.testing.assert_allclose(np.fft.rfft(result.acceleration_mps2), -omega**2 * displacement_fft,
                                   rtol=2.0e-7, atol=2.0e-10)
        # Integral of q''+2*zeta*w*q'+w²*q = w²*delta*load with quiet endpoints.
        expected_mean = STATIC_DISPLACEMENT_M * 8.0 * 2.0 / np.pi / 32.0
        self.assertAlmostEqual(float(np.mean(result.displacement_m)), expected_mean, delta=1.0e-6)
        self.assertAlmostEqual(float(np.mean(result.acceleration_mps2)), 0.0, places=12)

    def test_amplitude_scaling_polarity_and_time_origin_have_physical_meaning(self) -> None:
        baseline = run_method(METHOD_ID, self.record, self.parameters)
        scaled = SignalRecord(self.record.source_path, "az", self.record.time_s, -2.5 * self.record.acceleration_mps2,
                              self.record.sampling_rate_hz, "m/s²")
        reversed_result = run_method(METHOD_ID, scaled, {**self.parameters, "deflection_direction": "positive"})
        np.testing.assert_allclose(reversed_result.displacement_m, -2.5 * baseline.displacement_m, rtol=1.0e-9, atol=1.0e-11)
        shifted = SignalRecord(self.record.source_path, "az", self.record.time_s + 137.25,
                               self.record.acceleration_mps2, self.record.sampling_rate_hz, "m/s²")
        shifted_result = run_method(METHOD_ID, shifted, {**self.parameters, "entry_time_s": 139.25})
        np.testing.assert_allclose(shifted_result.displacement_m, baseline.displacement_m, rtol=1.0e-9, atol=1.0e-11)
        np.testing.assert_array_equal(shifted_result.time_s, shifted.time_s)

    def test_small_noise_and_acceleration_bias_do_not_become_large_displacement_drift(self) -> None:
        rng = np.random.default_rng(2037)
        time = self.record.time_s
        contaminated = self.record.acceleration_mps2 + 0.001 + 0.00003 * (time - np.mean(time))
        contaminated += rng.normal(0.0, 0.0002, size=time.size)
        record = SignalRecord(self.record.source_path, "az", time, contaminated, self.record.sampling_rate_hz, "m/s²")
        result = run_method(METHOD_ID, record, self.parameters)
        self.assertLess(float(np.max(np.abs(result.displacement_m - self.truth))) /
                        float(np.max(np.abs(self.truth))), 0.1)
        self.assertLess(abs(float(result.displacement_m[-1])), 0.0001)
        self.assertFalse(np.array_equal(result.acceleration_mps2, contaminated))
        raw = next(step for step in result.steps if step.key == "raw_acceleration")
        self.assertTrue(any(np.array_equal(values, contaminated) for values in raw.series.values()))

    def test_optional_mean_removal_prevents_constant_bias_leakage_from_padding(self) -> None:
        parameters = {**self.parameters, "remove_acceleration_mean": True}
        baseline = run_method(METHOD_ID, self.record, parameters)
        biased = SignalRecord(self.record.source_path, "az", self.record.time_s,
                              self.record.acceleration_mps2 + 0.123, self.record.sampling_rate_hz, "m/s²")
        result = run_method(METHOD_ID, biased, parameters)
        np.testing.assert_allclose(result.displacement_m, baseline.displacement_m, rtol=1.0e-9, atol=1.0e-12)
        self.assertLess(float(np.mean(result.displacement_m)), -1.0e-5)

    def test_train_notches_inside_the_fit_band_do_not_make_the_fit_singular(self) -> None:
        result = run_method(METHOD_ID, self.record, {
            **self.parameters, "band_mode": "manual", "fit_min_hz": 0.5,
            "fit_max_hz": 3.0, "replacement_hz": 3.0,
        })
        self.assertTrue(np.all(np.isfinite(result.displacement_m)))
        self.assertAlmostEqual(abs(result.diagnostics["unit_static_displacement_m"]), 0.001, delta=5.0e-6)
        self.assertLess(result.diagnostics["fit_relative_error"], 0.01)

    def test_wrong_polarity_is_identified_as_a_poor_physical_fit_and_reported(self) -> None:
        result = run_method(METHOD_ID, self.record, {**self.parameters, "deflection_direction": "positive"})
        # Magnitudes alone cannot distinguish sign; the complex residual must.
        self.assertAlmostEqual(result.diagnostics["unit_static_displacement_m"], 0.001, delta=5.0e-6)
        self.assertGreater(result.diagnostics["fit_relative_error"], 1.5)
        warnings = result.diagnostics["quality_warnings"]
        self.assertTrue(warnings)
        report = build_report_html(self.record, [result], title="Polaridad incompatible", include_steps=False)
        self.assertIn("Advertencia de calidad", report)
        for warning in warnings:
            self.assertIn(html.escape(warning), report)

    def test_bad_geometry_band_and_sampling_are_rejected_with_raw_trace_preserved(self) -> None:
        cases = [
            {"bridge_span_m": 0.0}, {"train_speed_kmh": -1.0}, {"vehicle_count": 1.5},
            {"vehicle_length_m": 0.0}, {"axle_spacing_m": 15.0}, {"bogie_spacing_m": 18.0},
            {"natural_frequency_hz": 0.0}, {"damping_ratio": -0.02},
            {"padding_factor": 0}, {"padding_factor": 9},
            {"band_mode": "manual", "fit_min_hz": 3.0, "fit_max_hz": 2.0, "replacement_hz": 3.0},
            {"band_mode": "manual", "fit_min_hz": 1.001, "fit_max_hz": 1.002, "replacement_hz": 3.0},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                received = []
                result = run_method_traced(METHOD_ID, self.record, {**self.parameters, **changes}, received.append)
                self.assertIsInstance(result, PartialMethodResult)
                self.assertTrue(result.failure_message)
                self.assertIn("raw_acceleration", [step.key for step in result.steps])
                self.assertNotIn("final_displacement", [step.key for step in result.steps])
                self.assertEqual([step.key for step in received], [step.key for step in result.steps])
        nonuniform = self.record.time_s.copy()
        nonuniform[100] += 0.001
        for times, sampling_rate in ((nonuniform, 128.0), (self.record.time_s, 100.0)):
            record = SignalRecord(self.record.source_path, "az", times, self.record.acceleration_mps2, sampling_rate, "m/s²")
            self.assertIsInstance(run_method_traced(METHOD_ID, record, self.parameters), PartialMethodResult)

    def test_defaults_fail_instead_of_inventing_geometry(self) -> None:
        result = run_method_traced(METHOD_ID, self.record)
        self.assertIsInstance(result, PartialMethodResult)
        self.assertIn("raw_acceleration", [step.key for step in result.steps])

    def test_corrected_arrays_parameters_and_reference_survive_data_export(self) -> None:
        result = run_method(METHOD_ID, self.record, self.parameters)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = export_result_bundle(directory, self.record, [result])
            payload = json.loads(manifest.read_text(encoding="utf-8"))["results"][0]
            self.assertEqual(payload["parameters"]["vehicle_count"], 2)
            self.assertEqual(payload["summary"]["unit_static_displacement_m"], result.diagnostics["unit_static_displacement_m"])
            self.assertIn("quality_warnings", payload["summary"])
            self.assertEqual(payload["reference"]["citation"], METHOD_BY_ID[METHOD_ID].reference)
            self.assertEqual(payload["reference"]["url"], METHOD_BY_ID[METHOD_ID].reference_url)
            exported = np.loadtxt(directory / f"{METHOD_ID}.csv", delimiter=",", skiprows=1)
            np.testing.assert_allclose(exported, np.column_stack((result.time_s, result.acceleration_mps2,
                                                                 result.velocity_mps, result.displacement_m)), rtol=1.0e-14)
        report = build_report_html(self.record, [result], title="Validación física", include_steps=False)
        self.assertIn(html.escape(METHOD_BY_ID[METHOD_ID].reference), report)
        self.assertIn(html.escape(METHOD_BY_ID[METHOD_ID].reference_url), report)
        self.assertNotIn('href=""', report)

    def test_spectral_steps_styles_and_final_result_cross_the_process_boundary(self) -> None:
        received = []
        result = run_method_isolated(METHOD_ID, self.record, self.parameters, on_step=received.append, timeout_s=30.0)
        self.assertIsInstance(result, MethodResult)
        self.assertEqual([step.key for step in received], [step.key for step in result.steps])
        self.assertTrue(any("points" in step.series_styles.values() for step in received))
        for streamed, final in zip(received, result.steps, strict=True):
            np.testing.assert_array_equal(streamed.x, final.x)
            self.assertEqual(streamed.series_styles, final.series_styles)
            for label in final.series:
                np.testing.assert_array_equal(streamed.series[label], final.series[label])


if __name__ == "__main__":
    unittest.main()
