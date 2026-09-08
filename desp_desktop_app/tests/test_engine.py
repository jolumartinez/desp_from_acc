from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from desp_desktop_app.core.catalog import METHOD_SPECS
from desp_desktop_app.core.engine import run_method, run_method_traced
from desp_desktop_app.core.models import PartialMethodResult, SignalRecord


def harmonic_record() -> tuple[SignalRecord, np.ndarray]:
    sampling_rate = 100.0
    time_s = np.arange(0.0, 40.0, 1.0 / sampling_rate)
    angular_frequency = 2.0 * np.pi * 1.5
    truth = 0.006 * (1.0 - np.cos(angular_frequency * time_s))
    acceleration = 0.006 * angular_frequency**2 * np.cos(angular_frequency * time_s)
    return SignalRecord(Path("synthetic.txt"), "acceleration_x", time_s, acceleration, sampling_rate, "m/s²"), truth


class MethodEngineTests(unittest.TestCase):
    def test_every_catalog_method_produces_complete_finite_series(self) -> None:
        record, _ = harmonic_record()
        for spec in METHOD_SPECS:
            overrides = None
            if spec.method_id == "wang":
                overrides = {"grid_points": 4, "pre_event_s": 2.0}
            elif spec.method_id == "bunce_bridge":
                overrides = {
                    "event_mode": "manual",
                    "event_start_s": 2.0,
                    "event_end_s": 35.0,
                    "candidate_step_s": 0.2,
                    "max_candidates": 400,
                    "quality_mode": "shoulders",
                    "max_lift_mm": 1000.0,
                }
            with self.subTest(method=spec.method_id):
                result = run_method(spec.method_id, record, overrides)
                self.assertEqual(result.displacement_m.shape, record.time_s.shape)
                self.assertTrue(np.all(np.isfinite(result.displacement_m)))
                self.assertGreaterEqual(len(result.steps), 6)
                self.assertEqual(result.steps[-1].key, "final_displacement")

    def test_park_reconstructs_clean_harmonic_motion(self) -> None:
        record, truth = harmonic_record()
        result = run_method("park", record)
        correlation = float(np.corrcoef(truth, result.displacement_m)[0, 1])
        self.assertGreater(correlation, 0.9999)
        self.assertLess(float(np.max(np.abs(truth - result.displacement_m))), 5.0e-5)

    def test_unknown_method_is_rejected(self) -> None:
        record, _ = harmonic_record()
        with self.assertRaises(KeyError):
            run_method("missing", record)

    def test_wang_accepts_thesis_manual_step_range(self) -> None:
        record, _ = harmonic_record()
        result = run_method(
            "wang",
            record,
            {
                "grid_points": 4,
                "pre_event_s": 2.0,
                "step_search_mode": "manual_range",
                "step_min_m": -0.1,
                "step_max_m": 0.1,
                "step_increment_fraction": 0.025,
            },
        )
        self.assertEqual(result.diagnostics["step_search_mode"], "manual_range")
        self.assertGreaterEqual(result.diagnostics["step_target_m"], -0.1)
        self.assertLessEqual(result.diagnostics["step_target_m"], 0.1)

    def test_wang_detects_arrival_before_preevent_mean_correction(self) -> None:
        sampling_rate = 100.0
        time_s = np.arange(0.0, 5.0, 1.0 / sampling_rate)
        acceleration = np.full_like(time_s, 0.1)
        acceleration[100:150] += 1.0
        record = SignalRecord(Path("event.txt"), "ax", time_s, acceleration, sampling_rate, "m/s²")
        result = run_method("wang", record, {"grid_points": 4, "pre_event_s": 0.5})
        self.assertAlmostEqual(result.diagnostics["noise_level_mps2"], 0.1)
        self.assertAlmostEqual(result.diagnostics["arrival_s"], 1.0)
        self.assertAlmostEqual(result.diagnostics["pre_event_mean_mps2"], 0.1)

    def test_chiu_exposes_the_second_integration_from_the_thesis(self) -> None:
        record, _ = harmonic_record()
        result = run_method("chiu", record)
        keys = [step.key for step in result.steps]
        self.assertLess(keys.index("velocity_fit"), keys.index("integrated_displacement"))
        self.assertEqual(keys[-1], "final_displacement")

    def test_converse_brady_keeps_padding_through_integration(self) -> None:
        record, _ = harmonic_record()
        result = run_method("converse_brady", record)
        steps = {step.key: step for step in result.steps}
        self.assertGreater(steps["padded_displacement"].x.size, record.time_s.size)
        self.assertEqual(result.displacement_m.size, record.time_s.size)
        self.assertGreater(result.diagnostics["pad_samples"], 0)

    def test_bunce_bridge_recovers_transient_displacement_with_linear_bias(self) -> None:
        sampling_rate = 100.0
        time_s = np.arange(0.0, 10.0 + 1.0 / sampling_rate, 1.0 / sampling_rate)
        truth = np.zeros_like(time_s)
        forced = (time_s >= 3.0) & (time_s <= 7.0)
        normalized = (time_s[forced] - 3.0) / 4.0
        truth[forced] = -0.01 * np.sin(np.pi * normalized) ** 2
        velocity = np.gradient(truth, time_s)
        acceleration = np.gradient(velocity, time_s) + 2.0e-4 + 3.0e-5 * time_s
        record = SignalRecord(Path("bridge.txt"), "az", time_s, acceleration, sampling_rate, "m/s²")

        result = run_method(
            "bunce_bridge",
            record,
            {
                "event_start_s": 3.0,
                "event_end_s": 7.0,
                "event_mode": "manual",
                "search_zone_s": 2.0,
                "candidate_step_s": 0.05,
                "max_candidates": 3_000,
                "quality_mode": "shoulders",
            },
        )

        correlation = float(np.corrcoef(truth, result.displacement_m)[0, 1])
        rmse = float(np.sqrt(np.mean(np.square(truth - result.displacement_m))))
        self.assertGreater(correlation, 0.999)
        self.assertLess(rmse, 1.0e-5)
        self.assertGreater(result.diagnostics["accepted_windows"], 0)
        self.assertEqual(result.steps[-1].key, "final_displacement")
        step_keys = {step.key for step in result.steps}
        self.assertTrue(
            {
                "search_zones",
                "candidate_grid",
                "candidate_ranking",
                "uplift_control",
                "candidate_robustness",
                "selected_detrend",
                "corrected_acceleration",
                "shoulder_quality",
                "integrated_displacement",
            }.issubset(step_keys)
        )
        for step in result.steps:
            self.assertIn("Qué muestra:", step.description)
            self.assertIn("Por qué se hace:", step.description)
            self.assertIn("Cómo interpretarla:", step.description)
            self.assertIn("Referencia:", step.description)

    def test_bunce_bridge_can_detect_the_forced_interval(self) -> None:
        sampling_rate = 100.0
        time_s = np.arange(0.0, 10.01, 1.0 / sampling_rate)
        displacement = np.zeros_like(time_s)
        forced = (time_s >= 3.0) & (time_s <= 7.0)
        displacement[forced] = -0.005 * np.sin(np.pi * (time_s[forced] - 3.0) / 4.0) ** 2
        acceleration = np.gradient(np.gradient(displacement, time_s), time_s)
        record = SignalRecord(Path("automatic.txt"), "az", time_s, acceleration, sampling_rate, "m/s²")

        result = run_method(
            "bunce_bridge",
            record,
            {
                "event_mode": "automatic",
                "candidate_step_s": 0.1,
                "max_candidates": 1_000,
                "quality_mode": "shoulders",
            },
        )

        self.assertLess(result.diagnostics["event_start_s"], 3.1)
        self.assertGreater(result.diagnostics["event_end_s"], 6.9)
        self.assertEqual(result.diagnostics["event_source"], "detección auxiliar por energía")

    def test_bunce_bridge_does_not_invent_recoveries_on_one_trough(self) -> None:
        sampling_rate = 100.0
        time_s = np.arange(0.0, 10.01, 1.0 / sampling_rate)
        displacement = np.zeros_like(time_s)
        forced = (time_s >= 3.0) & (time_s <= 7.0)
        displacement[forced] = -0.005 * np.sin(np.pi * (time_s[forced] - 3.0) / 4.0) ** 2
        acceleration = np.gradient(np.gradient(displacement, time_s), time_s)
        record = SignalRecord(Path("train.txt"), "az", time_s, acceleration, sampling_rate, "m/s²")

        result = run_method(
            "bunce_bridge",
            record,
            {
                "event_mode": "manual",
                "event_start_s": 3.0,
                "event_end_s": 7.0,
                "candidate_step_s": 0.2,
                "max_candidates": 500,
                "max_lift_mm": 1000.0,
                "quality_mode": "train",
                "train_peak_source": "geometry",
                "bridge_span_m": 20.0,
                "sensor_position_m": 10.0,
                "train_length_m": 40.0,
                "peak_midpoint_distances_m": "5, 15, 25",
                "train_timing_basis": "event_duration",
            },
        )

        np.testing.assert_allclose(
            result.diagnostics["expected_peak_offsets_s"],
            [1.0, 5.0 / 3.0, 7.0 / 3.0],
        )
        np.testing.assert_allclose(
            result.diagnostics["expected_peak_times_s"],
            [4.0, 14.0 / 3.0, 16.0 / 3.0],
        )
        self.assertEqual(result.diagnostics["train_peak_source"], "geometry")
        self.assertAlmostEqual(result.diagnostics["train_effective_speed_kmh"], 54.0)
        self.assertTrue(result.diagnostics["specific_train_check"])
        self.assertIn("expected_train_peaks", [step.key for step in result.steps])
        self.assertIn("train_peak_quality", [step.key for step in result.steps])
        self.assertEqual(result.diagnostics["selected_peak_times_s"], [])
        self.assertEqual(result.diagnostics["detected_recovery_count"], 0)
        self.assertEqual(result.diagnostics["missing_recovery_count"], 3)
        self.assertFalse(result.diagnostics["train_peak_control_passed"])
        self.assertEqual(result.diagnostics["quality_status"], "warning")

    def test_bunce_bridge_distinguishes_six_troughs_from_five_recoveries(self) -> None:
        sampling_rate = 100.0
        time_s = np.arange(0.0, 16.01, 1.0 / sampling_rate)
        displacement = np.zeros_like(time_s)
        for start_s in np.arange(2.0, 14.0, 2.0):
            forced = (time_s >= start_s) & (time_s <= start_s + 2.0)
            phase = (time_s[forced] - start_s) / 2.0
            displacement[forced] = -0.005 * np.sin(np.pi * phase) ** 2
        acceleration = (
            np.gradient(np.gradient(displacement, time_s), time_s)
            + 1.0e-5
            + 2.0e-6 * time_s
        )
        record = SignalRecord(
            Path("six-axle-sets.txt"),
            "az",
            time_s,
            acceleration,
            sampling_rate,
            "m/s²",
        )

        result = run_method(
            "bunce_bridge",
            record,
            {
                "event_mode": "manual",
                "event_start_s": 2.0,
                "event_end_s": 14.0,
                "search_zone_s": 0.2,
                "candidate_step_s": 0.05,
                "max_candidates": 100,
                "max_lift_mm": 1000.0,
                "deflection_direction": "negative",
                "quality_mode": "train",
                "train_peak_source": "manual",
                "expected_peak_offsets_s": "2, 4, 6, 8, 10",
                "peak_tolerance_s": 0.25,
                "minimum_peak_spacing_s": 1.5,
                "minimum_peak_width_s": 0.5,
                "minimum_peak_prominence_mm": 1.0,
            },
        )

        self.assertEqual(result.diagnostics["expected_recovery_count"], 5)
        self.assertEqual(result.diagnostics["detected_recovery_count"], 5)
        self.assertEqual(result.diagnostics["matched_recovery_count"], 5)
        self.assertEqual(result.diagnostics["detected_load_trough_count"], 6)
        self.assertTrue(result.diagnostics["train_peak_control_passed"])
        self.assertEqual(result.diagnostics["quality_status"], "accepted")
        np.testing.assert_allclose(
            result.diagnostics["selected_peak_times_s"],
            [4.0, 6.0, 8.0, 10.0, 12.0],
            atol=1.0 / sampling_rate,
        )

    def test_bunce_bridge_rejects_incomplete_train_geometry(self) -> None:
        record, _ = harmonic_record()
        with self.assertRaisesRegex(ValueError, "luz del puente"):
            run_method(
                "bunce_bridge",
                record,
                {
                    "event_mode": "manual",
                    "event_start_s": 2.0,
                    "event_end_s": 35.0,
                    "quality_mode": "train",
                    "train_peak_source": "geometry",
                },
            )

    def test_bunce_bridge_continues_when_lift_check_rejects_every_window(self) -> None:
        sampling_rate = 100.0
        time_s = np.arange(0.0, 10.01, 1.0 / sampling_rate)
        displacement = np.zeros_like(time_s)
        forced = (time_s >= 3.0) & (time_s <= 7.0)
        displacement[forced] = -0.01 * np.sin(np.pi * (time_s[forced] - 3.0) / 4.0) ** 2
        acceleration = np.gradient(np.gradient(displacement, time_s), time_s)
        record = SignalRecord(Path("reversed-polarity.txt"), "az", time_s, acceleration, sampling_rate, "m/s²")

        result = run_method(
            "bunce_bridge",
            record,
            {
                "event_mode": "manual",
                "event_start_s": 3.0,
                "event_end_s": 7.0,
                "search_zone_s": 0.05,
                "candidate_step_s": 0.05,
                "max_candidates": 25,
                "deflection_direction": "positive",
                "max_lift_mm": 1.0,
                "quality_mode": "shoulders",
            },
        )

        self.assertEqual(result.diagnostics["accepted_windows"], 0)
        self.assertFalse(result.diagnostics["lift_control_passed"])
        self.assertEqual(result.diagnostics["quality_status"], "warning")
        self.assertTrue(result.diagnostics["quality_warnings"])
        self.assertEqual(result.steps[-1].key, "final_displacement")

    def test_traced_execution_retains_steps_before_a_configuration_failure(self) -> None:
        record, _ = harmonic_record()
        partial = run_method_traced(
            "bunce_bridge",
            record,
            {
                "event_mode": "manual",
                "event_start_s": 2.0,
                "event_end_s": 35.0,
                "quality_mode": "train",
                "train_peak_source": "geometry",
            },
        )

        self.assertIsInstance(partial, PartialMethodResult)
        assert isinstance(partial, PartialMethodResult)
        self.assertIn("luz del puente", partial.failure_message)
        self.assertEqual(
            [step.key for step in partial.steps],
            ["raw_acceleration", "raw_spectrum", "load_interval", "search_zones"],
        )


if __name__ == "__main__":
    unittest.main()
