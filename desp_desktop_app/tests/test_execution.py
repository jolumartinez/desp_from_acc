from __future__ import annotations

import unittest
from pathlib import Path
from threading import Event

import numpy as np

from desp_desktop_app.core.execution import run_method_isolated
from desp_desktop_app.core.models import MethodResult, PartialMethodResult, SignalRecord


def harmonic_record() -> SignalRecord:
    sampling_rate = 100.0
    time_s = np.arange(0.0, 10.0, 1.0 / sampling_rate)
    angular_frequency = 2.0 * np.pi * 1.5
    acceleration = 0.006 * angular_frequency**2 * np.cos(angular_frequency * time_s)
    return SignalRecord(
        Path("isolated.txt"),
        "acceleration_x",
        time_s,
        acceleration,
        sampling_rate,
        "m/s²",
    )


def bridge_record() -> SignalRecord:
    sampling_rate = 100.0
    time_s = np.arange(0.0, 10.01, 1.0 / sampling_rate)
    displacement = np.zeros_like(time_s)
    forced = (time_s >= 3.0) & (time_s <= 7.0)
    displacement[forced] = -0.005 * np.sin(
        np.pi * (time_s[forced] - 3.0) / 4.0
    ) ** 2
    acceleration = np.gradient(np.gradient(displacement, time_s), time_s)
    return SignalRecord(
        Path("isolated_bridge.txt"),
        "acceleration_z",
        time_s,
        acceleration,
        sampling_rate,
        "m/s²",
    )


class IsolatedExecutionTests(unittest.TestCase):
    def test_result_and_completed_steps_cross_the_process_boundary(self) -> None:
        received_steps = []
        heartbeats = []

        result = run_method_isolated(
            "park",
            harmonic_record(),
            {},
            on_step=received_steps.append,
            on_heartbeat=heartbeats.append,
            timeout_s=30.0,
        )

        self.assertIsInstance(result, MethodResult)
        assert isinstance(result, MethodResult)
        self.assertGreaterEqual(len(received_steps), 6)
        self.assertEqual(
            [step.key for step in received_steps],
            [step.key for step in result.steps],
        )
        self.assertTrue(heartbeats)
        self.assertTrue(np.all(np.isfinite(result.displacement_m)))

    def test_preemptive_cancellation_returns_a_partial_result(self) -> None:
        cancellation = Event()
        cancellation.set()

        result = run_method_isolated(
            "park",
            harmonic_record(),
            {},
            cancel_requested=cancellation.is_set,
        )

        self.assertIsInstance(result, PartialMethodResult)
        assert isinstance(result, PartialMethodResult)
        self.assertEqual(result.steps, [])
        self.assertIn("cancelada", result.failure_message)

    def test_timeout_terminates_the_disposable_process(self) -> None:
        result = run_method_isolated(
            "park",
            harmonic_record(),
            {},
            timeout_s=0.001,
        )

        self.assertIsInstance(result, PartialMethodResult)
        assert isinstance(result, PartialMethodResult)
        self.assertIn("Tiempo máximo", result.failure_message)

    def test_bunce_visual_steps_and_styles_cross_the_process_boundary(self) -> None:
        received_steps = []
        result = run_method_isolated(
            "bunce_bridge",
            bridge_record(),
            {
                "event_mode": "manual",
                "event_start_s": 3.0,
                "event_end_s": 7.0,
                "candidate_step_s": 0.2,
                "max_candidates": 500,
                "quality_mode": "shoulders",
                "max_lift_mm": 1000.0,
            },
            on_step=received_steps.append,
            timeout_s=30.0,
        )

        self.assertIsInstance(result, MethodResult)
        assert isinstance(result, MethodResult)
        by_key = {step.key: step for step in received_steps}
        self.assertIn("candidate_grid", by_key)
        self.assertEqual(
            by_key["candidate_grid"].series_styles["Ventanas evaluadas"],
            "points",
        )
        self.assertIn("integrated_displacement", by_key)


if __name__ == "__main__":
    unittest.main()
