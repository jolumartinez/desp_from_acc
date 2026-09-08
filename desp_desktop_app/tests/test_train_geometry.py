from __future__ import annotations

import unittest

import numpy as np

from desp_desktop_app.core.engine import _resolve_train_peak_offsets
from desp_desktop_app.core.train_geometry import DEFAULT_AXLE_SPACINGS_M, parse_axle_spacings


class TrainGeometryTests(unittest.TestCase):
    def test_six_axle_defaults_preserve_repeated_and_decreasing_spacings(self) -> None:
        positions = parse_axle_spacings(DEFAULT_AXLE_SPACINGS_M)
        np.testing.assert_allclose(positions, [0.0, 17.4, 35.15, 52.9, 70.65, 88.05])
        self.assertEqual(positions.size, 6)

    def test_spacings_accept_the_user_diagram_and_common_separators(self) -> None:
        positions = parse_axle_spacings("|17.4|17.75; 17.75\n17.75, 17.4|")
        np.testing.assert_allclose(positions, [0.0, 17.4, 35.15, 52.9, 70.65, 88.05])

    def test_empty_nonfinite_and_nonpositive_spacings_are_rejected(self) -> None:
        for value in ("", "| , ;", "1, nan", "inf, 1", "1, -inf", "2, 0", "2, -1", "a, 2", "1e309", "1e308, 1e308", "1e20, 1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_axle_spacings(value)

    def test_axle_count_limit_bounds_spectral_work(self) -> None:
        self.assertEqual(parse_axle_spacings(",".join(["1"] * 799)).size, 800)
        with self.assertRaisesRegex(ValueError, "800 ejes"):
            parse_axle_spacings(",".join(["1"] * 800))

    def test_bunce_defaults_compute_five_sensor_passage_times(self) -> None:
        # Six point axles travelling at 10 m/s past a sensor 10 m from entry.
        # Consecutive midpoint passages must not be mistaken for six recoveries.
        offsets, diagnostics = _resolve_train_peak_offsets({
            "quality_mode": "train", "train_peak_source": "geometry",
            "bridge_span_m": 20.0, "sensor_position_m": 10.0,
            "train_timing_basis": "speed", "train_speed_kmh": 36.0,
        }, 2.0, 12.805)
        np.testing.assert_allclose(offsets, [1.87, 3.6275, 5.4025, 7.1775, 8.935])
        self.assertEqual(diagnostics["train_axle_count"], 6)
        self.assertAlmostEqual(diagnostics["train_first_to_last_axle_m"], 88.05)
        np.testing.assert_allclose(diagnostics["train_peak_midpoints_m"], [8.7, 26.275, 44.025, 61.775, 79.35])
        self.assertAlmostEqual(diagnostics["train_predicted_passage_s"], 10.805)
        self.assertAlmostEqual(diagnostics["train_passage_difference_s"], 0.0)

    def test_bunce_sensor_offset_and_observed_duration_use_the_same_geometry(self) -> None:
        parameters = {
            "quality_mode": "train", "train_peak_source": "geometry",
            "train_geometry_mode": "axle_spacings", "axle_spacings_m": DEFAULT_AXLE_SPACINGS_M,
            "bridge_span_m": 20.0, "sensor_position_m": 6.0,
            "train_timing_basis": "event_duration",
            # Explicit axle geometry must ignore unrelated legacy values.
            "train_length_m": 1.0, "peak_midpoint_distances_m": "not used",
        }
        offsets, diagnostics = _resolve_train_peak_offsets(parameters, 2.0, 23.61)
        np.testing.assert_allclose(offsets, [2.94, 6.455, 10.005, 13.555, 17.07])
        self.assertAlmostEqual(diagnostics["train_effective_speed_mps"], 5.0)
        self.assertEqual(diagnostics["train_geometry_mode"], "axle_spacings")

    def test_bunce_legacy_direct_calls_keep_manual_midpoints(self) -> None:
        offsets, diagnostics = _resolve_train_peak_offsets({
            "quality_mode": "train", "train_peak_source": "geometry",
            "bridge_span_m": 20.0, "sensor_position_m": 10.0,
            "train_length_m": 40.0, "peak_midpoint_distances_m": "5, 15, 25",
            "train_timing_basis": "event_duration",
        }, 3.0, 7.0)
        np.testing.assert_allclose(offsets, [1.0, 5.0 / 3.0, 7.0 / 3.0])
        self.assertEqual(diagnostics["train_geometry_mode"], "manual_midpoints")
        self.assertNotIn("train_axle_count", diagnostics)

    def test_bunce_rejects_bad_geometry_before_proposing_times(self) -> None:
        parameters = {
            "quality_mode": "train", "train_peak_source": "geometry",
            "train_geometry_mode": "axle_spacings", "axle_spacings_m": DEFAULT_AXLE_SPACINGS_M,
            "bridge_span_m": 20.0, "sensor_position_m": 10.0,
            "train_timing_basis": "speed", "train_speed_kmh": 36.0,
        }
        for change in (
            {"axle_spacings_m": "17.4, nan"},
            {"axle_spacings_m": "17.4, -1"},
            {"axle_spacings_m": "17.4"},  # Only one midpoint, not enough for train control.
            {"bridge_span_m": float("nan")},
            {"sensor_position_m": float("inf")},
            {"train_speed_kmh": float("nan")},
            {"train_geometry_mode": "unknown"},
            {"train_geometry_mode": "manual_midpoints", "train_length_m": 40.0,
             "peak_midpoint_distances_m": "5, nan, 25"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                _resolve_train_peak_offsets({**parameters, **change}, 2.0, 12.805)


if __name__ == "__main__":
    unittest.main()
