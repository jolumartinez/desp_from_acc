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

from core.catalog import METHOD_BY_ID  # noqa: E402
from core.engine import default_parameters, run_method_traced  # noqa: E402
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
        self.addCleanup(window.close)
        window._show_method("bunce_bridge")

        quality = window.parameter_widgets["quality_mode"]
        self.assertEqual(quality.currentData(), "train")
        self.assertFalse(window.parameter_widgets["bridge_span_m"].isHidden())
        self.assertFalse(window.parameter_widgets["train_speed_kmh"].isHidden())
        self.assertFalse(window.parameter_widgets["axle_spacings_m"].isHidden())
        self.assertTrue(window.parameter_widgets["train_length_m"].isHidden())
        self.assertTrue(window.parameter_widgets["peak_midpoint_distances_m"].isHidden())
        self.assertFalse(window.parameter_widgets["minimum_peak_spacing_s"].isHidden())
        self.assertFalse(window.parameter_widgets["minimum_peak_width_s"].isHidden())
        self.assertFalse(window.parameter_widgets["minimum_peak_prominence_mm"].isHidden())

        timing = window.parameter_widgets["train_timing_basis"]
        self.assertEqual(timing.currentData(), "speed")
        timing.setCurrentIndex(timing.findData("event_duration"))
        self.assertTrue(window.parameter_widgets["train_speed_kmh"].isHidden())
        timing.setCurrentIndex(timing.findData("speed"))
        self.assertFalse(window.parameter_widgets["train_speed_kmh"].isHidden())

        geometry = window.parameter_widgets["train_geometry_mode"]
        geometry.setCurrentIndex(geometry.findData("manual_midpoints"))
        self.assertTrue(window.parameter_widgets["axle_spacings_m"].isHidden())
        self.assertFalse(window.parameter_widgets["train_length_m"].isHidden())
        self.assertFalse(window.parameter_widgets["peak_midpoint_distances_m"].isHidden())

        source = window.parameter_widgets["train_peak_source"]
        source.setCurrentIndex(source.findData("manual"))
        for key in ("bridge_span_m", "train_geometry_mode", "train_length_m", "peak_midpoint_distances_m", "axle_spacings_m"):
            self.assertTrue(window.parameter_widgets[key].isHidden())
        self.assertFalse(window.parameter_widgets["expected_peak_offsets_s"].isHidden())

        quality.setCurrentIndex(quality.findData("shoulders"))
        self.assertTrue(window.parameter_widgets["expected_peak_offsets_s"].isHidden())
        self.assertTrue(window.parameter_widgets["train_peak_source"].isHidden())
        source.setCurrentIndex(source.findData("geometry"))
        geometry.setCurrentIndex(geometry.findData("axle_spacings"))
        self.assertTrue(window.parameter_widgets["axle_spacings_m"].isHidden())
        quality.setCurrentIndex(quality.findData("train"))
        self.assertFalse(window.parameter_widgets["axle_spacings_m"].isHidden())

    def test_both_train_methods_capture_six_axles_and_restore_the_preset(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)
        spacings = "17.4, 17.75, 17.75, 17.75, 17.4"
        for method_id, legacy_mode in (("bunce_bridge", "manual_midpoints"), ("tokunaga_bridge", "regular_vehicles")):
            with self.subTest(method_id=method_id):
                window._show_method(method_id)
                self.assertEqual(window._capture_parameters(), default_parameters(method_id))
                self.assertEqual(window._capture_parameters()["axle_spacings_m"], spacings)
                self.assertEqual(window._capture_parameters()["train_geometry_mode"], "axle_spacings")
                window.parameter_widgets["axle_spacings_m"].setText("10, 12, 10")
                window.parameter_widgets["bridge_span_m"].setValue(30.0)
                window.parameter_widgets["sensor_position_m"].setValue(12.0)
                window.parameter_widgets["train_speed_kmh"].setValue(90.0)
                geometry = window.parameter_widgets["train_geometry_mode"]
                geometry.setCurrentIndex(geometry.findData(legacy_mode))
                self.assertTrue(window.parameter_widgets["axle_spacings_m"].isHidden())
                captured = window._capture_parameters()
                self.assertEqual(captured["axle_spacings_m"], "10, 12, 10")
                self.assertEqual(captured["sensor_position_m"], 12.0)
                self.assertEqual(captured["bridge_span_m"], 30.0)
                self.assertEqual(captured["train_speed_kmh"], 90.0)
                geometry.setCurrentIndex(geometry.findData("axle_spacings"))
                self.assertEqual(window.parameter_widgets["axle_spacings_m"].text(), "10, 12, 10")
                window._reset_current_method_defaults()
                self.assertEqual(window._capture_parameters(), default_parameters(method_id))
                self.assertFalse(window.parameter_widgets["axle_spacings_m"].isHidden())

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

    @unittest.skipUnless(sys.platform.startswith("linux"), "La ruta de Evince sólo aplica en Linux")
    def test_modal_method_opens_its_local_email_reference(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)
        window._show_method("martinez_2024")
        self.assertEqual(window.method_code.text(), "JM")
        self.assertIn("correo", window.open_thesis_button.text().lower())
        self.assertEqual(
            window._capture_parameters(),
            {"num_modes": 20, "damping_ratio": 0.002, "welch_nperseg": 512, "peak_threshold_ratio": 0.001},
        )
        window.parameter_widgets["damping_ratio"].setValue(0.035)
        self.assertEqual(window._capture_parameters()["damping_ratio"], 0.035)
        with (
            patch("gui.main_window.shutil.which", return_value="/usr/bin/evince"),
            patch.object(QProcess, "startDetached", return_value=True) as start,
        ):
            window.open_thesis_button.click()
        program, arguments = start.call_args.args
        self.assertEqual(program, "/usr/bin/evince")
        self.assertEqual(arguments[0], "--page-index=0")
        self.assertTrue(arguments[1].endswith("references/metodoJorgeMartinezNoviembre2024.pdf"))

    def test_tokunaga_manual_band_controls_preserve_values_and_reset(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)
        window._show_method("tokunaga_bridge")
        self.assertEqual(window.method_code.text(), "TK")
        self.assertEqual(window._capture_parameters(), default_parameters("tokunaga_bridge"))
        band_mode = window.parameter_widgets["band_mode"]
        manual_keys = ("fit_min_hz", "fit_max_hz", "replacement_hz")

        self.assertEqual(band_mode.currentData(), "publication")
        for key in manual_keys:
            widget = window.parameter_widgets[key]
            self.assertTrue(widget.isHidden())
            self.assertTrue(window.parameter_form.labelForField(widget).isHidden())
        self.assertTrue(window.parameter_widgets["entry_time_s"].isHidden())
        self.assertFalse(window.parameter_widgets["bridge_span_m"].isHidden())

        entry_mode = window.parameter_widgets["entry_mode"]
        entry_mode.setCurrentIndex(entry_mode.findData("manual"))
        band_mode.setCurrentIndex(band_mode.findData("manual"))
        for key in manual_keys:
            widget = window.parameter_widgets[key]
            self.assertFalse(widget.isHidden())
            self.assertFalse(window.parameter_form.labelForField(widget).isHidden())
        window.parameter_widgets["fit_min_hz"].setValue(1.2)
        window.parameter_widgets["fit_max_hz"].setValue(4.0)
        window.parameter_widgets["replacement_hz"].setValue(0.5)
        window.parameter_widgets["entry_time_s"].setValue(6.5)
        captured = window._capture_parameters()
        self.assertEqual(captured["band_mode"], "manual")
        self.assertEqual(captured["fit_min_hz"], 1.2)
        self.assertEqual(captured["fit_max_hz"], 4.0)
        self.assertEqual(captured["replacement_hz"], 0.5)
        self.assertEqual(captured["entry_time_s"], 6.5)

        band_mode.setCurrentIndex(band_mode.findData("publication"))
        self.assertTrue(all(window.parameter_widgets[key].isHidden() for key in manual_keys))
        self.assertFalse(window.parameter_widgets["entry_time_s"].isHidden())
        band_mode.setCurrentIndex(band_mode.findData("manual"))
        self.assertEqual(window._capture_parameters(), captured)

        window._reset_current_method_defaults()
        self.assertEqual(window._capture_parameters(), default_parameters("tokunaga_bridge"))
        self.assertTrue(all(window.parameter_widgets[key].isHidden() for key in manual_keys))
        self.assertNotIn("tesis", window.status_message.text().lower())

    def test_tokunaga_estimates_and_regular_vehicle_controls_allow_manual_values(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)
        window._show_method("tokunaga_bridge")
        fields_by_mode = {
            "entry_mode": ("manual", {"entry_time_s": 6.5}),
            "frequency_mode": ("manual", {"natural_frequency_hz": 4.25}),
            "train_geometry_mode": ("regular_vehicles", {"vehicle_count": 2, "vehicle_length_m": 20.0, "axle_spacing_m": 2.0, "bogie_spacing_m": 14.0}),
        }
        for mode_key, (manual_choice, fields) in fields_by_mode.items():
            combo = window.parameter_widgets[mode_key]
            default_choice = combo.currentData()
            for key in fields:
                widget = window.parameter_widgets[key]
                self.assertTrue(widget.isHidden())
                self.assertTrue(window.parameter_form.labelForField(widget).isHidden())
            combo.setCurrentIndex(combo.findData(manual_choice))
            for key, value in fields.items():
                widget = window.parameter_widgets[key]
                self.assertFalse(widget.isHidden())
                self.assertFalse(window.parameter_form.labelForField(widget).isHidden())
                widget.setValue(value)
            combo.setCurrentIndex(combo.findData(default_choice))
            for key, value in fields.items():
                self.assertTrue(window.parameter_widgets[key].isHidden())
                self.assertEqual(window._capture_parameters()[key], value)
            combo.setCurrentIndex(combo.findData(manual_choice))
            for key, value in fields.items():
                self.assertFalse(window.parameter_widgets[key].isHidden())
                self.assertEqual(window._capture_parameters()[key], value)
        self.assertFalse(window.parameter_widgets["sensor_position_m"].isHidden())
        window._reset_current_method_defaults()
        self.assertEqual(window._capture_parameters(), default_parameters("tokunaga_bridge"))
        for _, fields in fields_by_mode.values():
            for key in fields:
                self.assertTrue(window.parameter_widgets[key].isHidden())

    def test_tokunaga_opens_its_local_article_and_editorial_reference(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)
        window._show_method("tokunaga_bridge")
        spec = METHOD_BY_ID["tokunaga_bridge"]
        self.assertEqual(spec.local_reference_file, "references/tokunaga_bridge_displacement_2022.pdf")
        self.assertEqual(spec.local_reference_page, 6)
        document = APP_DIR / spec.local_reference_file
        self.assertTrue(document.is_file())
        self.assertTrue(spec.reference_url)
        self.assertFalse(window.open_thesis_button.isHidden())
        self.assertFalse(window.open_reference_button.isHidden())
        with (
            patch("gui.main_window.shutil.which", return_value=None),
            patch("gui.main_window.QDesktopServices.openUrl") as open_url,
            patch.object(QProcess, "startDetached") as start,
        ):
            window.open_thesis_button.click()
            open_url.assert_called_once()
            local_url = open_url.call_args.args[0]
            self.assertTrue(local_url.isLocalFile())
            self.assertEqual(Path(local_url.toLocalFile()), document)
            self.assertEqual(local_url.fragment(), "page=6")
            start.assert_not_called()
            open_url.reset_mock()
            window.open_reference_button.click()
            open_url.assert_called_once()
            self.assertEqual(open_url.call_args.args[0].toString(), spec.reference_url)
            start.assert_not_called()

        window._show_method("martinez_2024")
        self.assertFalse(window.open_thesis_button.isHidden())
        self.assertTrue(window.open_reference_button.isHidden())
        window._show_method("park")
        self.assertFalse(window.open_thesis_button.isHidden())
        self.assertFalse(window.open_reference_button.isHidden())

    def test_many_modal_steps_render_only_when_viewed_and_keep_plot_controls(self) -> None:
        window = MainWindow()
        self.addCleanup(window.close)
        window._show_method("martinez_2024")
        time_s = np.arange(4096) / 128.0
        acceleration = sum(
            0.01 / index * np.cos(2.0 * np.pi * (index + 1) * time_s)
            for index in range(1, 21)
        )
        record = SignalRecord(Path("many_modes.txt"), "az", time_s, acceleration, 128.0, "m/s²")
        result = run_method_traced("martinez_2024", record)
        self.assertNotIsInstance(result, PartialMethodResult)
        self.assertEqual(result.diagnostics["selected_mode_count"], 20)
        window._receive_result(result)
        self.app.processEvents()

        def current_panels() -> list[PlotPanel]:
            return [
                panel
                for index in range(window.result_stack.count())
                for panel in window.result_stack.widget(index).findChildren(PlotPanel)
            ]

        self.assertEqual(window.step_selector.count(), len(result.steps))
        self.assertEqual(len(current_panels()), 1)
        np.testing.assert_array_equal(current_panels()[0].axis.lines[0].get_ydata(), result.displacement_m)

        contribution_index = next(index for index, step in enumerate(result.steps) if step.key.startswith("modal_contribution_"))
        contribution = result.steps[contribution_index]
        window.step_selector.setCurrentIndex(contribution_index)
        self.app.processEvents()
        self.assertEqual(len(current_panels()), 2)
        panel = window.result_stack.currentWidget().findChild(PlotPanel)
        np.testing.assert_array_equal(panel.axis.lines[0].get_xdata(), contribution.x)
        np.testing.assert_array_equal(panel.axis.lines[0].get_ydata(), next(iter(contribution.series.values())))
        actions = {action.text(): action for action in panel.toolbar.actions() if action.text()}
        self.assertTrue({"Pan", "Zoom", "Save"}.issubset(actions))
        actions["Pan"].trigger()
        self.assertTrue(panel.toolbar.mode)

        selection_index = next(index for index, step in enumerate(result.steps) if step.key == "modal_selection")
        window.step_selector.setCurrentIndex(selection_index)
        self.app.processEvents()
        selection_panel = window.result_stack.currentWidget().findChild(PlotPanel)
        self.assertTrue(any(line.get_marker() == "o" and line.get_linestyle() == "None" for line in selection_panel.axis.lines))

        # Switching methods before the next timer tick must not draw a queued
        # modal plot into the other method's empty result page.
        window.step_selector.setCurrentIndex(contribution_index + 1)
        window._show_method("park")
        self.app.processEvents()
        self.assertEqual(current_panels(), [])
        self.assertFalse(window.step_selector.isEnabled())


if __name__ == "__main__":
    unittest.main()
