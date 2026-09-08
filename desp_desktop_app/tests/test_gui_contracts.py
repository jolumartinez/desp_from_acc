from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from matplotlib.backends import backend_qt  # noqa: E402
from PyQt5.QtCore import QProcess  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from core.engine import run_method_traced  # noqa: E402
from core.models import PartialMethodResult, ProcessStep, SignalRecord  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from gui.widgets import PlotPanel  # noqa: E402


class GuiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_plot_toolbar_is_interactive_and_saves(self) -> None:
        panel = PlotPanel(animate=False)
        x = np.linspace(0.0, 100.0, 50_000)
        panel.set_plot(x, {"Señal": np.sin(x)}, title="Prueba", x_label="t", y_label="a")
        panel.canvas.draw()
        actions = {action.text(): action for action in panel.toolbar.actions() if action.text()}

        actions["Pan"].trigger()
        self.assertTrue(panel.toolbar.mode)
        panel.set_interval_selection(True)
        self.assertFalse(panel.toolbar.mode)
        self.assertFalse(actions["Pan"].isChecked())
        self.assertEqual(len(panel.axis.lines[0].get_xdata()), panel.MAX_RENDER_POINTS)

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "plot.png"
            with patch.object(
                backend_qt.QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(str(output), "Portable Network Graphics (*.png)"),
            ):
                actions["Save"].trigger()
            self.assertGreater(output.stat().st_size, 1_000)

    def test_single_candidate_plot_gets_a_stable_horizontal_range(self) -> None:
        panel = PlotPanel(animate=False)
        panel.set_plot(
            np.array([1.0]),
            {"Indicador": np.array([0.5])},
            title="Candidato",
            x_label="Orden",
            y_label="Calidad",
        )

        lower, upper = panel.axis.get_xlim()
        self.assertLess(lower, 1.0)
        self.assertGreater(upper, 1.0)

    def test_reset_allows_selecting_a_second_interval_after_pan(self) -> None:
        window = MainWindow()
        time_s = np.linspace(0.0, 10.0, 1_001)
        record = SignalRecord(
            Path("record.txt"),
            "ax",
            time_s,
            np.sin(time_s),
            100.0,
            "m/s²",
        )
        window.full_record = record
        window._configure_crop_controls(record)
        window._activate_record(record)

        window._interval_selected(1.0, 3.0)
        window._apply_crop()
        window._reset_crop()

        actions = {
            action.text(): action
            for action in window.data_time_plot.toolbar.actions()
            if action.text()
        }
        actions["Pan"].trigger()
        window.select_interval_button.click()

        self.assertIs(window.record, window.full_record)
        self.assertTrue(window.select_interval_button.isChecked())
        self.assertTrue(window.data_time_plot._selection_enabled)
        self.assertFalse(window.data_time_plot.toolbar.mode)
        self.assertIsNone(window.data_time_plot._selection_bounds)

    def test_signal_loading_state_is_visible_and_blocks_source_controls(self) -> None:
        window = MainWindow()
        window._set_signal_loading(True)

        self.assertFalse(window.load_button.isEnabled())
        self.assertEqual(window.load_button.text(), "Cargando…")
        self.assertFalse(window.load_activity.isHidden())
        self.assertEqual(window.load_progress.minimum(), 0)
        self.assertEqual(window.load_progress.maximum(), 0)

        window._set_signal_loading(False)
        self.assertTrue(window.load_button.isEnabled())
        self.assertTrue(window.load_activity.isHidden())

    def test_bunce_train_controls_follow_the_selected_peak_source(self) -> None:
        window = MainWindow()
        window._show_method("bunce_bridge")

        self.assertTrue(window.parameter_widgets["bridge_span_m"].isHidden())
        quality = window.parameter_widgets["quality_mode"]
        quality.setCurrentIndex(quality.findData("train"))
        self.assertFalse(window.parameter_widgets["bridge_span_m"].isHidden())
        self.assertTrue(window.parameter_widgets["train_speed_kmh"].isHidden())
        self.assertFalse(window.parameter_widgets["minimum_peak_spacing_s"].isHidden())
        self.assertFalse(window.parameter_widgets["minimum_peak_width_s"].isHidden())
        self.assertFalse(window.parameter_widgets["minimum_peak_prominence_mm"].isHidden())

        timing = window.parameter_widgets["train_timing_basis"]
        timing.setCurrentIndex(timing.findData("speed"))
        self.assertFalse(window.parameter_widgets["train_speed_kmh"].isHidden())

        source = window.parameter_widgets["train_peak_source"]
        source.setCurrentIndex(source.findData("manual"))
        self.assertTrue(window.parameter_widgets["bridge_span_m"].isHidden())
        self.assertFalse(window.parameter_widgets["expected_peak_offsets_s"].isHidden())

    def test_partial_execution_keeps_completed_charts_but_not_a_result(self) -> None:
        window = MainWindow()
        record = SignalRecord(
            Path("partial.txt"),
            "az",
            np.linspace(0.0, 40.0, 4_001),
            np.sin(np.linspace(0.0, 40.0, 4_001)),
            100.0,
            "m/s²",
        )
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

        window.current_method_id = "bunce_bridge"
        window._receive_partial_result(partial)

        self.assertEqual(window.step_selector.count(), 4)
        self.assertIn("Ejecución parcial", window.result_warning.text())
        self.assertNotIn("bunce_bridge", window.results)
        self.assertIn("bunce_bridge", window.partial_results)
        self.assertFalse(window.compare_checks["bunce_bridge"].isEnabled())

    def test_live_step_is_visible_before_the_method_finishes(self) -> None:
        window = MainWindow()
        x = np.linspace(0.0, 1.0, 101)
        step = ProcessStep(
            "preview",
            "Etapa disponible",
            "Resultado intermedio",
            x,
            {"Señal": np.sin(x)},
            "Tiempo [s]",
            "Amplitud",
        )
        window.current_method_id = "park"

        window._receive_live_step("park", step)

        self.assertEqual(window.step_selector.count(), 1)
        self.assertIn("Procesamiento en curso", window.result_warning.text())
        self.assertEqual(window.partial_results["park"].steps[0].key, "preview")
        first_widget = window.result_stack.widget(0)
        second_step = ProcessStep(
            "preview_2",
            "Segunda etapa",
            "Segundo resultado intermedio",
            x,
            {"Señal": np.cos(x)},
            "Tiempo [s]",
            "Amplitud",
        )

        window._receive_live_step("park", second_step)

        self.assertEqual(window.step_selector.count(), 2)
        self.assertIs(window.result_stack.widget(0), first_widget)
        self.assertEqual(window._rendered_step_count, 2)

    def test_analysis_worker_uses_isolated_process_end_to_end(self) -> None:
        window = MainWindow()
        time_s = np.arange(0.0, 5.0, 0.01)
        record = SignalRecord(
            Path("threaded.txt"),
            "az",
            time_s,
            np.cos(2.0 * np.pi * time_s),
            100.0,
            "m/s²",
        )
        window.record = record

        window._start_jobs([("park", {})])
        deadline = time.monotonic() + 20.0
        while window.analysis_thread is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

        self.assertIsNone(window.analysis_thread)
        self.assertIn("park", window.results)
        self.assertTrue(window.cancel_method_button.isHidden())

    @unittest.skipUnless(sys.platform.startswith("linux"), "La ruta de Evince sólo aplica en Linux")
    def test_thesis_opens_known_document_at_physical_page(self) -> None:
        window = MainWindow()
        window.current_method_id = "chiu"
        with (
            patch("gui.main_window.shutil.which", return_value="/usr/bin/evince"),
            patch.object(QProcess, "startDetached", return_value=True) as start,
            patch("gui.main_window.QFileDialog.getOpenFileName") as file_picker,
        ):
            window._open_local_thesis()

        program, arguments = start.call_args.args
        self.assertEqual(program, "/usr/bin/evince")
        self.assertEqual(arguments[0], "--page-index=73")
        self.assertTrue(arguments[1].endswith("TESIS_DAMARIS_ARIAS_final.pdf"))
        file_picker.assert_not_called()

    @unittest.skipUnless(sys.platform.startswith("linux"), "La ruta de Evince sólo aplica en Linux")
    def test_publication_method_opens_its_own_local_pdf(self) -> None:
        window = MainWindow()
        window.current_method_id = "bunce_bridge"
        with (
            patch("gui.main_window.shutil.which", return_value="/usr/bin/evince"),
            patch.object(QProcess, "startDetached", return_value=True) as start,
        ):
            window._open_local_thesis()

        program, arguments = start.call_args.args
        self.assertEqual(program, "/usr/bin/evince")
        self.assertEqual(arguments[0], "--page-index=4")
        self.assertTrue(arguments[1].endswith("references/bunce_bridge_displacement_2023.pdf"))


if __name__ == "__main__":
    unittest.main()
