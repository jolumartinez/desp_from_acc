from __future__ import annotations

import re
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np
from PyQt5.QtCore import QObject, QProcess, Qt, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.analysis import comparison_envelope, comparison_rows, pairwise_correlation
from core.app_paths import output_dir, resource_dir
from core.catalog import METHOD_BY_ID, METHOD_SPECS
from core.engine import default_parameters
from core.execution import run_method_isolated
from core.io import available_channels, crop_signal, load_signal, scan_txt_files
from core.models import MethodResult, ParameterSpec, PartialMethodResult, ProcessStep, SignalRecord
from core.reporting import build_report_html, export_result_bundle, write_pdf_report, write_report
from core.signal_ops import displacement_scale, fft_spectrum
from gui.theme import COLORS
from gui.widgets import FlowDiagramWidget, PlotPanel


class AnalysisWorker(QObject):
    result_ready = pyqtSignal(object)
    partial_ready = pyqtSignal(object)
    step_ready = pyqtSignal(str, object)
    heartbeat = pyqtSignal(str, float)
    failed = pyqtSignal(str, str)
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()

    def __init__(self, record: SignalRecord, jobs: list[tuple[str, dict[str, Any]]]) -> None:
        super().__init__()
        self.record = record
        self.jobs = jobs
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    @pyqtSlot()
    def run(self) -> None:
        try:
            total = len(self.jobs)
            for index, (method_id, parameters) in enumerate(self.jobs, start=1):
                if self._cancel_event.is_set():
                    break
                self.progress.emit(index - 1, total, METHOD_BY_ID[method_id].name)
                try:
                    result = run_method_isolated(
                        method_id,
                        self.record,
                        parameters,
                        on_step=lambda step, current=method_id: self.step_ready.emit(current, step),
                        on_heartbeat=lambda elapsed, current=method_id: self.heartbeat.emit(
                            current, elapsed
                        ),
                        cancel_requested=self._cancel_event.is_set,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.failed.emit(method_id, f"{exc}\n\n{traceback.format_exc()}")
                    continue
                if isinstance(result, PartialMethodResult):
                    self.partial_ready.emit(result)
                else:
                    self.result_ready.emit(result)
                self.progress.emit(index, total, METHOD_BY_ID[method_id].name)
                if self._cancel_event.is_set():
                    break
        finally:
            self.finished.emit()


class SignalLoadWorker(QObject):
    loaded = pyqtSignal(object, object, object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, path: Path, channel: str, input_unit: str, sampling_rate_hz: float | None) -> None:
        super().__init__()
        self.path = path
        self.channel = channel
        self.input_unit = input_unit
        self.sampling_rate_hz = sampling_rate_hz

    @pyqtSlot()
    def run(self) -> None:
        try:
            record = load_signal(self.path, self.channel, self.input_unit, self.sampling_rate_hz)
            frequency, amplitude = fft_spectrum(record.acceleration_mps2, record.sampling_rate_hz)
            self.loaded.emit(record, frequency, amplitude)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


def _button(text: str, variant: str | None = None) -> QPushButton:
    button = QPushButton(text)
    if variant:
        button.setProperty("variant", variant)
    return button


def _page_heading(title: str, lead: str) -> tuple[QWidget, QHBoxLayout]:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    text = QVBoxLayout()
    label = QLabel(title)
    label.setObjectName("PageTitle")
    subtitle = QLabel(lead)
    subtitle.setObjectName("PageLead")
    subtitle.setWordWrap(True)
    text.addWidget(label)
    text.addWidget(subtitle)
    layout.addLayout(text, 1)
    return widget, layout


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DESP Studio | Desplazamientos desde aceleración")
        self.resize(1480, 920)
        self.setMinimumSize(1080, 700)
        self.record: SignalRecord | None = None
        self.full_record: SignalRecord | None = None
        self.results: dict[str, MethodResult] = {}
        self.partial_results: dict[str, PartialMethodResult] = {}
        self.method_parameters = {spec.method_id: default_parameters(spec.method_id) for spec in METHOD_SPECS}
        self.parameter_widgets: dict[str, QWidget] = {}
        self.current_method_id = METHOD_SPECS[0].method_id
        self.analysis_thread: QThread | None = None
        self.analysis_worker: AnalysisWorker | None = None
        self.load_thread: QThread | None = None
        self.load_worker: SignalLoadWorker | None = None
        self.last_report: Path | None = None
        self._close_when_idle = False
        self._rendered_method_id: str | None = None
        self._rendered_step_count = 0
        self._pending_step_plots: dict[QWidget, ProcessStep] = {}
        self._step_plot_timer = QTimer(self)
        self._step_plot_timer.setSingleShot(True)
        self._step_plot_timer.timeout.connect(self._render_current_step_plot)

        self.root = QWidget()
        self.root.setObjectName("AppRoot")
        self.setCentralWidget(self.root)
        outer = QVBoxLayout(self.root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        outer.addWidget(self._build_stage_bar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_data_page())
        self.pages.addWidget(self._build_methods_page())
        self.pages.addWidget(self._build_compare_page())
        self.pages.addWidget(self._build_report_page())
        outer.addWidget(self.pages, 1)

        status = QStatusBar()
        self.setStatusBar(status)
        self.status_message = QLabel("Listo")
        self.statusBar().addWidget(self.status_message, 1)
        self._show_method(METHOD_SPECS[0].method_id)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(76)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 10, 28, 10)
        identity = QVBoxLayout()
        product = QLabel("DESP Studio")
        product.setObjectName("Product")
        descriptor = QLabel("Laboratorio de desplazamientos derivados de aceleración")
        descriptor.setObjectName("HeaderContext")
        identity.addWidget(product)
        identity.addWidget(descriptor)
        layout.addLayout(identity)
        layout.addStretch()
        self.header_source = QLabel("Sin señal cargada")
        self.header_source.setObjectName("HeaderContext")
        self.header_source.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.header_source)
        return header

    def _build_stage_bar(self) -> QTabBar:
        bar = QTabBar()
        bar.setObjectName("StageBar")
        bar.setExpanding(True)
        for label in ("1  Datos", "2  Métodos", "3  Comparar", "4  Informe"):
            bar.addTab(label)
        bar.currentChanged.connect(self._set_page)
        return bar

    def _set_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if index == 2:
            self._refresh_comparison()
        elif index == 3:
            self._refresh_report_methods()

    def _build_data_page(self) -> QWidget:
        content = QWidget()
        content.setMinimumHeight(760)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)
        heading, heading_layout = _page_heading("Señal de trabajo", "Selección directa de un TXT y un canal; no se evalúa sincronía entre archivos.")
        self.open_folder_button = _button("Abrir carpeta", "primary")
        self.open_folder_button.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        self.open_folder_button.clicked.connect(self._choose_folder)
        heading_layout.addWidget(self.open_folder_button)
        layout.addWidget(heading)

        source = QFrame()
        source.setObjectName("SourceStrip")
        source_layout = QGridLayout(source)
        source_layout.setContentsMargins(16, 14, 16, 14)
        source_layout.setHorizontalSpacing(12)
        self.folder_line = QLineEdit()
        self.folder_line.setReadOnly(True)
        self.file_combo = QComboBox()
        self.file_combo.currentIndexChanged.connect(self._file_changed)
        self.channel_combo = QComboBox()
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["m/s²", "cm/s²", "g"])
        self.unit_combo.setCurrentText("m/s²")
        self.fs_override = QDoubleSpinBox()
        self.fs_override.setRange(0.0, 100000.0)
        self.fs_override.setDecimals(4)
        self.fs_override.setSpecialValueText("Automática")
        self.fs_override.setSuffix(" Hz")
        self.load_button = _button("Cargar señal", "accent")
        self.load_button.clicked.connect(self._load_selected_signal)
        source_layout.addWidget(QLabel("Carpeta"), 0, 0)
        source_layout.addWidget(self.folder_line, 0, 1, 1, 5)
        source_layout.addWidget(QLabel("Archivo"), 1, 0)
        source_layout.addWidget(self.file_combo, 1, 1)
        source_layout.addWidget(QLabel("Canal"), 1, 2)
        source_layout.addWidget(self.channel_combo, 1, 3)
        source_layout.addWidget(QLabel("Unidad"), 1, 4)
        source_layout.addWidget(self.unit_combo, 1, 5)
        source_layout.addWidget(QLabel("Muestreo"), 1, 6)
        source_layout.addWidget(self.fs_override, 1, 7)
        source_layout.addWidget(self.load_button, 1, 8)
        self.load_activity = QWidget()
        load_activity_layout = QHBoxLayout(self.load_activity)
        load_activity_layout.setContentsMargins(0, 4, 0, 0)
        self.load_activity_label = QLabel("Cargando y preparando la señal…")
        self.load_activity_label.setObjectName("PageLead")
        load_activity_layout.addWidget(self.load_activity_label)
        self.load_progress = QProgressBar()
        self.load_progress.setRange(0, 0)
        self.load_progress.setTextVisible(False)
        load_activity_layout.addWidget(self.load_progress, 1)
        self.load_activity.setVisible(False)
        source_layout.addWidget(self.load_activity, 2, 0, 1, 9)
        source_layout.setColumnStretch(1, 3)
        source_layout.setColumnStretch(3, 2)
        layout.addWidget(source)

        crop = QFrame()
        crop.setObjectName("SourceStrip")
        crop_layout = QHBoxLayout(crop)
        crop_layout.setContentsMargins(16, 9, 16, 9)
        crop_layout.addWidget(QLabel("Segmento de análisis"))
        self.crop_start = QDoubleSpinBox()
        self.crop_start.setDecimals(4)
        self.crop_start.setSuffix(" s")
        self.crop_start.setEnabled(False)
        self.crop_start.valueChanged.connect(self._crop_values_changed)
        crop_layout.addWidget(QLabel("Inicio"))
        crop_layout.addWidget(self.crop_start)
        self.crop_end = QDoubleSpinBox()
        self.crop_end.setDecimals(4)
        self.crop_end.setSuffix(" s")
        self.crop_end.setEnabled(False)
        self.crop_end.valueChanged.connect(self._crop_values_changed)
        crop_layout.addWidget(QLabel("Final"))
        crop_layout.addWidget(self.crop_end)
        crop_layout.addStretch()
        self.select_interval_button = _button("Seleccionar en gráfica")
        self.select_interval_button.setCheckable(True)
        self.select_interval_button.setEnabled(False)
        self.select_interval_button.setToolTip("Activa el cursor para arrastrar un intervalo sobre la historia temporal.")
        self.select_interval_button.toggled.connect(self._toggle_interval_selection)
        crop_layout.addWidget(self.select_interval_button)
        self.apply_crop_button = _button("Aplicar segmento", "accent")
        self.apply_crop_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.apply_crop_button.setEnabled(False)
        self.apply_crop_button.clicked.connect(self._apply_crop)
        crop_layout.addWidget(self.apply_crop_button)
        self.reset_crop_button = QToolButton()
        self.reset_crop_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.reset_crop_button.setToolTip("Restaurar la señal completa")
        self.reset_crop_button.setEnabled(False)
        self.reset_crop_button.clicked.connect(self._reset_crop)
        crop_layout.addWidget(self.reset_crop_button)
        layout.addWidget(crop)

        kpis = QFrame()
        kpis.setObjectName("KpiStrip")
        kpi_layout = QHBoxLayout(kpis)
        kpi_layout.setContentsMargins(18, 10, 18, 10)
        self.kpi_values: dict[str, QLabel] = {}
        for key, label in (("samples", "Muestras"), ("duration", "Duración"), ("sampling", "Frecuencia"), ("peak", "Pico |a|"), ("mean", "Media a")):
            block = QVBoxLayout()
            value = QLabel("—")
            value.setObjectName("KpiValue")
            caption = QLabel(label)
            caption.setObjectName("KpiLabel")
            block.addWidget(value)
            block.addWidget(caption)
            kpi_layout.addLayout(block)
            self.kpi_values[key] = value
        kpi_layout.addStretch()
        layout.addWidget(kpis)

        self.data_tabs = QTabWidget()
        self.data_time_plot = PlotPanel(animate=False)
        self.data_spectrum_plot = PlotPanel()
        self.data_tabs.addTab(self.data_time_plot, "Historia temporal")
        self.data_tabs.addTab(self.data_spectrum_plot, "Espectro")
        self.data_tabs.setMinimumHeight(340)
        layout.addWidget(self.data_tabs, 1)
        page = QScrollArea()
        page.setObjectName("DataPage")
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.NoFrame)
        page.setWidget(content)
        return page

    def _choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de aceleraciones", self.folder_line.text() or str(Path.home()))
        if not selected:
            return
        try:
            files = scan_txt_files(Path(selected))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Carpeta", str(exc))
            return
        self.folder_line.setText(selected)
        self.file_combo.clear()
        for path in files:
            self.file_combo.addItem(str(path.relative_to(Path(selected))), str(path))
        self.status_message.setText(f"{len(files)} archivos TXT disponibles")
        if not files:
            QMessageBox.information(self, "Carpeta", "No se encontraron archivos TXT.")

    def _file_changed(self) -> None:
        self.channel_combo.clear()
        path_text = self.file_combo.currentData()
        if not path_text:
            return
        try:
            self.channel_combo.addItems(available_channels(Path(path_text)))
        except Exception as exc:  # noqa: BLE001
            self.status_message.setText(f"No se pudo leer {Path(path_text).name}: {exc}")

    def _load_selected_signal(self) -> None:
        if self.load_thread is not None:
            return
        path_text = self.file_combo.currentData()
        channel = self.channel_combo.currentText()
        if not path_text or not channel:
            QMessageBox.information(self, "Datos", "Selecciona un archivo y un canal.")
            return
        override = self.fs_override.value() or None
        self._set_signal_loading(True)
        self.load_thread = QThread(self)
        self.load_worker = SignalLoadWorker(Path(path_text), channel, self.unit_combo.currentText(), override)
        self.load_worker.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.load_worker.run)
        self.load_worker.loaded.connect(self._signal_loaded)
        self.load_worker.failed.connect(self._signal_load_failed)
        self.load_worker.finished.connect(self.load_thread.quit)
        self.load_worker.finished.connect(self.load_worker.deleteLater)
        self.load_thread.finished.connect(self._signal_load_finished)
        self.load_thread.finished.connect(self.load_thread.deleteLater)
        self.load_thread.start()

    @pyqtSlot(object, object, object)
    def _signal_loaded(self, record: SignalRecord, frequency: np.ndarray, amplitude: np.ndarray) -> None:
        self.full_record = record
        self._configure_crop_controls(record)
        self._activate_record(record, spectrum=(frequency, amplitude))

    @pyqtSlot(str)
    def _signal_load_failed(self, details: str) -> None:
        self.status_message.setText("No se pudo cargar la señal")
        QMessageBox.critical(self, "No se pudo cargar la señal", details)

    def _signal_load_finished(self) -> None:
        self.load_thread = None
        self.load_worker = None
        self._set_signal_loading(False)
        self._finish_deferred_close()

    def _set_signal_loading(self, loading: bool) -> None:
        for widget in (
            self.open_folder_button,
            self.file_combo,
            self.channel_combo,
            self.unit_combo,
            self.fs_override,
            self.load_button,
        ):
            widget.setEnabled(not loading)
        self.load_button.setText("Cargando…" if loading else "Cargar señal")
        self.load_activity.setVisible(loading)
        if loading:
            self.status_message.setText("Leyendo el TXT y calculando el espectro…")

    def _configure_crop_controls(self, record: SignalRecord) -> None:
        duration = float(record.time_s[-1])
        step = max(float(np.median(np.diff(record.time_s))), 0.0001)
        self.select_interval_button.setChecked(False)
        self.data_time_plot.set_interval_selection(False)
        for control in (self.crop_start, self.crop_end):
            control.blockSignals(True)
            control.setRange(0.0, duration)
            control.setSingleStep(step)
            control.setEnabled(True)
        self.crop_start.setValue(0.0)
        self.crop_end.setValue(duration)
        for control in (self.crop_start, self.crop_end):
            control.blockSignals(False)
        self.select_interval_button.setEnabled(True)
        self.apply_crop_button.setEnabled(True)
        self.reset_crop_button.setEnabled(True)

    def _activate_record(
        self,
        record: SignalRecord,
        *,
        spectrum: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> None:
        self.record = record
        self.results.clear()
        self.partial_results.clear()
        crop_start = float(record.metadata.get("crop_start_s", 0.0))
        default_crop_end = self.full_record.time_s[-1] if self.full_record is not None else record.time_s[-1]
        crop_end = float(record.metadata.get("crop_end_s", default_crop_end))
        segment_text = ""
        has_crop = self.full_record is not None and (
            crop_start > 0.0 or crop_end < float(self.full_record.time_s[-1])
        )
        if has_crop:
            segment_text = f" · segmento {crop_start:.4g}-{crop_end:.4g} s"
        self.header_source.setText(
            f"{record.source_path.name}\n{record.channel} · {record.sampling_rate_hz:.4g} Hz{segment_text}"
        )
        self.kpi_values["samples"].setText(f"{record.time_s.size:,}")
        self.kpi_values["duration"].setText(f"{record.time_s[-1] - record.time_s[0]:.3f} s")
        self.kpi_values["sampling"].setText(f"{record.sampling_rate_hz:.4g} Hz")
        self.kpi_values["peak"].setText(f"{np.max(np.abs(record.acceleration_mps2)):.4g} m/s²")
        self.kpi_values["mean"].setText(f"{np.mean(record.acceleration_mps2):.4g} m/s²")
        display_record = self.full_record or record
        self.data_time_plot.set_plot(
            display_record.time_s,
            {display_record.channel: display_record.acceleration_mps2},
            title="Aceleración y segmento de análisis",
            x_label="Tiempo [s]",
            y_label="Aceleración [m/s²]",
        )
        if has_crop:
            self.data_time_plot.set_selection_bounds(crop_start, crop_end)
            self.data_time_plot.set_view_interval(crop_start, crop_end)
        if spectrum is None:
            frequency, amplitude = fft_spectrum(record.acceleration_mps2, record.sampling_rate_hz)
        else:
            frequency, amplitude = spectrum
        self.data_spectrum_plot.set_plot(
            frequency,
            {"Amplitud": amplitude},
            title="Espectro unilateral",
            x_label="Frecuencia [Hz]",
            y_label="Amplitud",
        )
        self._clear_result_steps("Ejecuta el método seleccionado para inspeccionar sus etapas.")
        self._refresh_comparison()
        self._refresh_report_methods()
        self.status_message.setText("Señal cargada; lista para procesamiento")

    def _crop_values_changed(self, *_args) -> None:
        if self.full_record is None:
            return
        start = self.crop_start.value()
        end = self.crop_end.value()
        full_end = float(self.full_record.time_s[-1])
        if end > start and (start > 0.0 or end < full_end):
            self.data_time_plot.set_selection_bounds(start, end)
        else:
            self.data_time_plot.set_selection_bounds(None, None)

    def _toggle_interval_selection(self, enabled: bool) -> None:
        self.data_tabs.setCurrentWidget(self.data_time_plot)
        self.data_time_plot.set_interval_selection(enabled, self._interval_selected)
        self.status_message.setText("Arrastra sobre la gráfica para definir el segmento" if enabled else "Selección gráfica desactivada")

    def _interval_selected(self, start: float, end: float) -> None:
        self.crop_start.setValue(start)
        self.crop_end.setValue(end)
        self.select_interval_button.setChecked(False)
        self.status_message.setText(f"Segmento propuesto: {start:.4g}-{end:.4g} s")

    def _apply_crop(self) -> None:
        if self.full_record is None:
            return
        if self.analysis_thread is not None:
            QMessageBox.information(self, "Segmento", "Espera a que termine el procesamiento actual.")
            return
        full_end = float(self.full_record.time_s[-1])
        if self.crop_start.value() <= 0.0 and self.crop_end.value() >= full_end:
            self._reset_crop()
            return
        try:
            selected = crop_signal(self.full_record, self.crop_start.value(), self.crop_end.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Segmento no válido", str(exc))
            return
        self.select_interval_button.setChecked(False)
        self.crop_start.blockSignals(True)
        self.crop_end.blockSignals(True)
        self.crop_start.setValue(float(selected.metadata["crop_start_s"]))
        self.crop_end.setValue(float(selected.metadata["crop_end_s"]))
        self.crop_start.blockSignals(False)
        self.crop_end.blockSignals(False)
        self._activate_record(selected)
        self.status_message.setText(
            f"Segmento activo: {selected.metadata['crop_start_s']:.4g}-{selected.metadata['crop_end_s']:.4g} s · "
            f"{selected.time_s.size:,} muestras"
        )

    def _reset_crop(self) -> None:
        if self.full_record is None:
            return
        if self.analysis_thread is not None:
            QMessageBox.information(self, "Segmento", "Espera a que termine el procesamiento actual.")
            return
        self.crop_start.blockSignals(True)
        self.crop_end.blockSignals(True)
        self.crop_start.setValue(0.0)
        self.crop_end.setValue(float(self.full_record.time_s[-1]))
        self.crop_start.blockSignals(False)
        self.crop_end.blockSignals(False)
        self.select_interval_button.setChecked(False)
        self._activate_record(self.full_record)
        self.status_message.setText("Señal completa restaurada")

    def _build_methods_page(self) -> QWidget:
        content = QWidget()
        content.setMinimumHeight(760)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 18, 28, 22)
        layout.setSpacing(12)
        heading, heading_layout = _page_heading("Banco de métodos", "Cada método conserva sus propios parámetros, etapas y supuestos de línea base.")
        self.run_all_button = _button(f"Ejecutar los {len(METHOD_SPECS)}", "primary")
        self.run_all_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.run_all_button.clicked.connect(self._run_all_methods)
        heading_layout.addWidget(self.run_all_button)
        layout.addWidget(heading)

        self.method_bar = QTabBar()
        self.method_bar.setObjectName("MethodBar")
        self.method_bar.setExpanding(True)
        for spec in METHOD_SPECS:
            index = self.method_bar.addTab(f"{spec.short_name} · {spec.year}")
            self.method_bar.setTabData(index, spec.method_id)
            self.method_bar.setTabToolTip(index, spec.name)
        self.method_bar.currentChanged.connect(self._method_tab_changed)
        layout.addWidget(self.method_bar)

        method_header = QWidget()
        method_header_layout = QHBoxLayout(method_header)
        method_header_layout.setContentsMargins(0, 2, 0, 0)
        self.method_code = QLabel("TL")
        self.method_code.setObjectName("MethodCode")
        method_header_layout.addWidget(self.method_code)
        method_text = QVBoxLayout()
        self.method_title = QLabel()
        self.method_title.setObjectName("MethodTitle")
        self.method_summary = QLabel()
        self.method_summary.setWordWrap(True)
        self.method_summary.setObjectName("PageLead")
        method_text.addWidget(self.method_title)
        method_text.addWidget(self.method_summary)
        method_header_layout.addLayout(method_text, 1)
        self.method_year = QLabel()
        self.method_year.setObjectName("Badge")
        method_header_layout.addWidget(self.method_year)
        layout.addWidget(method_header)
        self.flow_widget = FlowDiagramWidget()
        layout.addWidget(self.flow_widget)

        splitter = QSplitter()
        self.control_panel = QFrame()
        self.control_panel.setObjectName("ToolPanel")
        self.control_panel.setMinimumWidth(380)
        self.control_panel.setMaximumWidth(490)
        controls_layout = QVBoxLayout(self.control_panel)
        controls_layout.setContentsMargins(18, 14, 18, 16)
        self.control_tabs = QTabWidget()

        parameters_tab = QWidget()
        parameters_layout = QVBoxLayout(parameters_tab)
        parameters_layout.setContentsMargins(0, 8, 0, 4)
        controls_header = QHBoxLayout()
        controls_header.addWidget(QLabel("Configuración"))
        controls_header.addStretch()
        self.reset_method_button = _button("Restablecer referencia")
        self.reset_method_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.reset_method_button.setToolTip("Restaura la configuración base documentada para el método.")
        self.reset_method_button.clicked.connect(self._reset_current_method_defaults)
        controls_header.addWidget(self.reset_method_button)
        parameters_layout.addLayout(controls_header)
        self.method_preset = QLabel()
        self.method_preset.setObjectName("PageLead")
        self.method_preset.setWordWrap(True)
        parameters_layout.addWidget(self.method_preset)
        self.parameter_host = QWidget()
        self.parameter_form = QFormLayout(self.parameter_host)
        self.parameter_form.setContentsMargins(0, 6, 0, 6)
        self.parameter_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.parameter_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        parameter_scroll = QScrollArea()
        parameter_scroll.setWidgetResizable(True)
        parameter_scroll.setWidget(self.parameter_host)
        parameters_layout.addWidget(parameter_scroll, 1)
        self.control_tabs.addTab(parameters_tab, "Parámetros")

        foundation_tab = QWidget()
        foundation_layout = QVBoxLayout(foundation_tab)
        foundation_layout.setContentsMargins(4, 10, 4, 4)
        self.method_use = QLabel()
        self.method_use.setWordWrap(True)
        self.method_use.setObjectName("PageLead")
        foundation_layout.addWidget(self.method_use)
        foundation_layout.addStretch()
        references = QHBoxLayout()
        self.open_thesis_button = _button("Documento local")
        self.open_thesis_button.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.open_thesis_button.clicked.connect(self._open_local_thesis)
        references.addWidget(self.open_thesis_button)
        self.open_reference_button = _button("Publicación")
        self.open_reference_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogInfoView))
        self.open_reference_button.clicked.connect(self._open_method_reference)
        references.addWidget(self.open_reference_button)
        foundation_layout.addLayout(references)
        self.control_tabs.addTab(foundation_tab, "Fundamento")
        controls_layout.addWidget(self.control_tabs, 1)
        self.run_method_button = _button("Ejecutar método", "accent")
        self.run_method_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.run_method_button.clicked.connect(self._run_current_method)
        controls_layout.addWidget(self.run_method_button)
        self.cancel_method_button = _button("Cancelar cálculo")
        self.cancel_method_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserStop))
        self.cancel_method_button.setToolTip(
            "Detiene el método actual y conserva las etapas que ya terminaron."
        )
        self.cancel_method_button.setEnabled(False)
        self.cancel_method_button.hide()
        self.cancel_method_button.clicked.connect(self._cancel_jobs)
        controls_layout.addWidget(self.cancel_method_button)
        self.run_progress = QProgressBar()
        self.run_progress.setRange(0, 1)
        self.run_progress.setValue(0)
        controls_layout.addWidget(self.run_progress)
        splitter.addWidget(self.control_panel)

        result_host = QWidget()
        result_layout = QVBoxLayout(result_host)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(8)
        step_navigation = QFrame()
        step_navigation.setObjectName("SourceStrip")
        step_navigation_layout = QHBoxLayout(step_navigation)
        step_navigation_layout.setContentsMargins(12, 8, 12, 8)
        step_navigation_layout.addWidget(QLabel("Etapa del método"))
        self.previous_step_button = QToolButton()
        self.previous_step_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.previous_step_button.setToolTip("Etapa anterior")
        self.previous_step_button.clicked.connect(self._show_previous_step)
        step_navigation_layout.addWidget(self.previous_step_button)
        self.step_selector = QComboBox()
        self.step_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.step_selector.setToolTip("Selecciona directamente una etapa del procesamiento")
        self.step_selector.currentIndexChanged.connect(self._step_changed)
        step_navigation_layout.addWidget(self.step_selector, 1)
        self.step_counter = QLabel("0 / 0")
        self.step_counter.setObjectName("Badge")
        self.step_counter.setAlignment(Qt.AlignCenter)
        step_navigation_layout.addWidget(self.step_counter)
        self.next_step_button = QToolButton()
        self.next_step_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.next_step_button.setToolTip("Etapa siguiente")
        self.next_step_button.clicked.connect(self._show_next_step)
        step_navigation_layout.addWidget(self.next_step_button)
        result_layout.addWidget(step_navigation)
        self.result_warning = QLabel()
        self.result_warning.setObjectName("QualityWarning")
        self.result_warning.setWordWrap(True)
        self.result_warning.hide()
        result_layout.addWidget(self.result_warning)
        self.result_stack = QStackedWidget()
        self.result_stack.currentChanged.connect(lambda _index: self._step_plot_timer.start(0))
        result_layout.addWidget(self.result_stack, 1)
        splitter.addWidget(result_host)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        page = QScrollArea()
        page.setObjectName("MethodsPage")
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.NoFrame)
        page.setWidget(content)
        return page

    def _method_tab_changed(self, index: int) -> None:
        if self.current_method_id in self.method_parameters and self.parameter_widgets:
            self.method_parameters[self.current_method_id] = self._capture_parameters()
        method_id = self.method_bar.tabData(index)
        if method_id:
            self._show_method(str(method_id))

    def _clear_form(self) -> None:
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self.parameter_widgets.clear()

    def _parameter_widget(self, spec: ParameterSpec, value: Any) -> QWidget:
        if spec.kind == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(value))
        elif spec.kind == "int":
            widget = QSpinBox()
            widget.setRange(int(spec.minimum or 0), int(spec.maximum or 100000))
            widget.setValue(int(value))
        elif spec.kind == "choice":
            widget = QComboBox()
            for label, key in spec.choices:
                widget.addItem(label, key)
            selected = widget.findData(value)
            widget.setCurrentIndex(max(0, selected))
        elif spec.kind == "text":
            widget = QLineEdit(str(value))
            if spec.key == "axle_spacings_m":
                # Let the form wrap the field so all five preset gaps remain readable.
                widget.setMinimumWidth(250)
        else:
            widget = QDoubleSpinBox()
            widget.setRange(float(spec.minimum if spec.minimum is not None else -1.0e12), float(spec.maximum if spec.maximum is not None else 1.0e12))
            widget.setDecimals(spec.decimals)
            widget.setValue(float(value))
            widget.setSuffix(spec.suffix)
        widget.setToolTip(spec.help_text)
        return widget

    def _show_method(self, method_id: str) -> None:
        self.current_method_id = method_id
        spec = METHOD_BY_ID[method_id]
        self.method_code.setText(spec.short_name)
        self.method_code.setStyleSheet(f"background:{spec.accent};")
        self.method_title.setText(spec.name)
        self.method_summary.setText(spec.summary)
        self.method_year.setText(f"{spec.year} · {spec.thesis_pages}")
        dependent_note = {
            "boore": "T1 debe ajustarse al primer arribo de la señal.",
            "wang": "La ventana preevento debe ajustarse al registro analizado.",
            "darragh": "El quiebre Z sólo puede fijarse con conocimiento de la señal.",
        }.get(method_id, "")
        if spec.reference_basis == "tesis":
            preset_label = "Base del script" if dependent_note else "Preajuste del script"
            preset_text = (
                f"{preset_label} de la tesis · página {spec.thesis_page_label} "
                f"(página {spec.thesis_pdf_page} del PDF)"
            )
            self.open_thesis_button.setText("Ver tesis local")
        elif spec.reference_basis == "correo electrónico":
            preset_text = "Propuesta del autor y configuración del prototipo · " + spec.thesis_pages
            dependent_note = "El prototipo usa ζ = 0.002 (0.2%); el correo describe ζ = 0.035 (3.5%). El valor es editable."
            self.open_thesis_button.setText("Ver correo local")
        else:
            preset_text = f"Configuración base de la {spec.reference_basis} · {spec.thesis_pages}"
            self.open_thesis_button.setText("Ver publicación local")
        self.open_thesis_button.setVisible(spec.reference_basis == "tesis" or bool(spec.local_reference_file))
        self.open_reference_button.setVisible(bool(spec.reference_url))
        self.method_preset.setText(preset_text + (f"\n{dependent_note}" if dependent_note else ""))
        self.flow_widget.set_flow(spec.flow, spec.accent)
        self.method_use.setText(f"Uso: {spec.intended_use}\n\nLímite: {spec.limitation}\n\nReferencia: {spec.reference}")
        self._clear_form()
        values = self.method_parameters[method_id]
        for parameter in spec.parameters:
            widget = self._parameter_widget(parameter, values.get(parameter.key, parameter.default))
            self.parameter_widgets[parameter.key] = widget
            label = QLabel(parameter.label)
            label.setToolTip(parameter.help_text)
            self.parameter_form.addRow(label, widget)
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._sync_parameter_visibility)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._sync_parameter_visibility)
        self._sync_parameter_visibility()
        self._render_method_result(method_id)

    def _set_parameter_visible(self, key: str, visible: bool) -> None:
        widget = self.parameter_widgets.get(key)
        if widget is None:
            return
        widget.setVisible(visible)
        label = self.parameter_form.labelForField(widget)
        if label is not None:
            label.setVisible(visible)

    def _sync_parameter_visibility(self, *_args) -> None:
        design_widget = self.parameter_widgets.get("highpass_design")
        if isinstance(design_widget, QComboBox):
            specifications = design_widget.currentData() == "specifications"
            for key in ("passband_hz", "stopband_hz", "passband_ripple_db", "stopband_attenuation_db"):
                self._set_parameter_visible(key, specifications)
            for key in ("highpass_hz", "highpass_order"):
                self._set_parameter_visible(key, not specifications)

        baseline_widget = self.parameter_widgets.get("baseline")
        if isinstance(baseline_widget, QComboBox):
            self._set_parameter_visible("baseline_constant", baseline_widget.currentData() == "constant")

        lowpass_widget = self.parameter_widgets.get("use_lowpass")
        if isinstance(lowpass_widget, QCheckBox):
            for key in ("lowpass_hz", "lowpass_order"):
                self._set_parameter_visible(key, lowpass_widget.isChecked())

        highpass_widget = self.parameter_widgets.get("use_highpass")
        if isinstance(highpass_widget, QCheckBox):
            for key in ("highpass_hz", "highpass_order"):
                self._set_parameter_visible(key, highpass_widget.isChecked())

        fit_widget = self.parameter_widgets.get("fit_type")
        if isinstance(fit_widget, QComboBox):
            self._set_parameter_visible("breakpoint_s", fit_widget.currentData() in {"auto", "bilinear"})

        band_mode_widget = self.parameter_widgets.get("band_mode")
        if isinstance(band_mode_widget, QComboBox):
            manual_band = band_mode_widget.currentData() == "manual"
            for key in ("fit_min_hz", "fit_max_hz", "replacement_hz"):
                self._set_parameter_visible(key, manual_band)

        entry_mode_widget = self.parameter_widgets.get("entry_mode")
        if isinstance(entry_mode_widget, QComboBox):
            self._set_parameter_visible("entry_time_s", entry_mode_widget.currentData() == "manual")

        frequency_mode_widget = self.parameter_widgets.get("frequency_mode")
        if isinstance(frequency_mode_widget, QComboBox):
            self._set_parameter_visible("natural_frequency_hz", frequency_mode_widget.currentData() == "manual")

        geometry_widget = self.parameter_widgets.get("train_geometry_mode")
        if isinstance(geometry_widget, QComboBox):
            self._set_parameter_visible("axle_spacings_m", geometry_widget.currentData() == "axle_spacings")
            for key in ("vehicle_count", "vehicle_length_m", "axle_spacing_m", "bogie_spacing_m"):
                self._set_parameter_visible(key, geometry_widget.currentData() == "regular_vehicles")

        step_mode_widget = self.parameter_widgets.get("step_search_mode")
        if isinstance(step_mode_widget, QComboBox):
            manual_range = step_mode_widget.currentData() == "manual_range"
            for key in ("step_min_m", "step_max_m", "step_increment_fraction"):
                self._set_parameter_visible(key, manual_range)

        event_mode_widget = self.parameter_widgets.get("event_mode")
        if isinstance(event_mode_widget, QComboBox):
            manual_event = event_mode_widget.currentData() == "manual"
            for key in ("event_start_s", "event_end_s"):
                self._set_parameter_visible(key, manual_event)

        quality_mode_widget = self.parameter_widgets.get("quality_mode")
        if isinstance(quality_mode_widget, QComboBox):
            train_quality = quality_mode_widget.currentData() == "train"
            for key in (
                "train_peak_source",
                "peak_tolerance_s",
                "minimum_peak_spacing_s",
                "minimum_peak_width_s",
                "minimum_peak_prominence_mm",
            ):
                self._set_parameter_visible(key, train_quality)
            peak_source_widget = self.parameter_widgets.get("train_peak_source")
            geometry_source = (
                train_quality
                and isinstance(peak_source_widget, QComboBox)
                and peak_source_widget.currentData() == "geometry"
            )
            for key in (
                "bridge_span_m",
                "sensor_position_m",
                "train_geometry_mode",
                "train_timing_basis",
            ):
                self._set_parameter_visible(key, geometry_source)
            axle_geometry = isinstance(geometry_widget, QComboBox) and geometry_widget.currentData() == "axle_spacings"
            self._set_parameter_visible("axle_spacings_m", geometry_source and axle_geometry)
            for key in ("train_length_m", "peak_midpoint_distances_m"):
                self._set_parameter_visible(key, geometry_source and not axle_geometry)
            manual_source = train_quality and not geometry_source
            self._set_parameter_visible("expected_peak_offsets_s", manual_source)
            timing_widget = self.parameter_widgets.get("train_timing_basis")
            speed_basis = (
                geometry_source
                and isinstance(timing_widget, QComboBox)
                and timing_widget.currentData() == "speed"
            )
            self._set_parameter_visible("train_speed_kmh", speed_basis)

    def _reset_current_method_defaults(self) -> None:
        self.method_parameters[self.current_method_id] = default_parameters(self.current_method_id)
        self.results.pop(self.current_method_id, None)
        self.partial_results.pop(self.current_method_id, None)
        self._show_method(self.current_method_id)
        self._refresh_comparison()
        self._refresh_report_methods()
        self.status_message.setText("Configuración de referencia restaurada; ejecuta nuevamente el método")

    def _capture_parameters(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, widget in self.parameter_widgets.items():
            if isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                values[key] = widget.currentData()
            elif isinstance(widget, QLineEdit):
                values[key] = widget.text().strip()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[key] = widget.value()
        return values

    def _open_local_thesis(self) -> None:
        spec = METHOD_BY_ID[self.current_method_id]
        if not spec.local_reference_file and spec.reference_basis != "tesis":
            return
        document = resource_dir() / (spec.local_reference_file or "TESIS_DAMARIS_ARIAS_final.pdf")
        page = spec.local_reference_page or spec.thesis_pdf_page
        if not document.exists():
            QMessageBox.information(self, "Documento", "La referencia local no está disponible en esta distribución.")
            return

        if sys.platform.startswith("linux"):
            evince = shutil.which("evince")
            if evince:
                started = QProcess.startDetached(
                    evince,
                    [f"--page-index={page - 1}", str(document)],
                )
                started_ok = started[0] if isinstance(started, tuple) else started
                if started_ok:
                    return
            okular = shutil.which("okular")
            if okular:
                started = QProcess.startDetached(okular, ["--page", str(page), str(document)])
                started_ok = started[0] if isinstance(started, tuple) else started
                if started_ok:
                    return

        url = QUrl.fromLocalFile(str(document))
        url.setFragment(f"page={page}")
        QDesktopServices.openUrl(url)

    def _open_method_reference(self) -> None:
        spec = METHOD_BY_ID[self.current_method_id]
        if spec.reference_url:
            QDesktopServices.openUrl(QUrl(spec.reference_url))
        elif spec.local_reference_file or spec.reference_basis == "tesis":
            self._open_local_thesis()

    def _run_current_method(self) -> None:
        self.method_parameters[self.current_method_id] = self._capture_parameters()
        self._start_jobs([(self.current_method_id, self.method_parameters[self.current_method_id])])

    def _run_all_methods(self) -> None:
        self.method_parameters[self.current_method_id] = self._capture_parameters()
        jobs = [(spec.method_id, self.method_parameters[spec.method_id]) for spec in METHOD_SPECS]
        self._start_jobs(jobs)

    def _start_jobs(self, jobs: list[tuple[str, dict[str, Any]]]) -> None:
        if self.record is None:
            QMessageBox.information(self, "Métodos", "Carga primero una señal en la etapa Datos.")
            return
        if self.analysis_thread is not None:
            QMessageBox.information(self, "Métodos", "Ya existe un procesamiento en curso.")
            return
        self.run_method_button.setEnabled(False)
        self.run_all_button.setEnabled(False)
        self.cancel_method_button.setEnabled(True)
        self.cancel_method_button.show()
        for method_id, _parameters in jobs:
            self.results.pop(method_id, None)
            self.partial_results.pop(method_id, None)
        self.run_progress.setRange(0, len(jobs))
        self.run_progress.setValue(0)
        self.analysis_thread = QThread(self)
        self.analysis_worker = AnalysisWorker(self.record, jobs)
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.analysis_worker.run)
        self.analysis_worker.result_ready.connect(self._receive_result)
        self.analysis_worker.partial_ready.connect(self._receive_partial_result)
        self.analysis_worker.step_ready.connect(self._receive_live_step)
        self.analysis_worker.heartbeat.connect(self._method_heartbeat)
        self.analysis_worker.failed.connect(self._method_failed)
        self.analysis_worker.progress.connect(self._method_progress)
        self.analysis_worker.finished.connect(self.analysis_thread.quit)
        self.analysis_worker.finished.connect(self.analysis_worker.deleteLater)
        self.analysis_thread.finished.connect(self._jobs_finished)
        self.analysis_thread.finished.connect(self.analysis_thread.deleteLater)
        self.analysis_thread.start()

    def _method_progress(self, current: int, total: int, name: str) -> None:
        self.run_progress.setMaximum(total)
        self.run_progress.setValue(current)
        self.status_message.setText(f"Procesando {name} · {current}/{total}")

    def _method_heartbeat(self, method_id: str, elapsed_s: float) -> None:
        partial = self.partial_results.get(method_id)
        completed = len(partial.steps) if partial is not None else 0
        self.status_message.setText(
            f"Calculando {METHOD_BY_ID[method_id].name} · {elapsed_s:.0f} s · "
            f"{completed} etapas completadas"
        )

    def _receive_live_step(self, method_id: str, step: ProcessStep) -> None:
        current = self.partial_results.get(method_id)
        steps = list(current.steps) if current is not None else []
        steps.append(step)
        self.partial_results[method_id] = PartialMethodResult(
            method_id=method_id,
            method_name=METHOD_BY_ID[method_id].name,
            steps=steps,
            failure_message="",
            elapsed_s=current.elapsed_s if current is not None else 0.0,
        )
        if method_id == self.current_method_id:
            if (
                self._rendered_method_id == method_id
                and self._rendered_step_count == len(steps) - 1
            ):
                self.result_warning.setText(
                    f"Procesamiento en curso · {len(steps)} etapas completadas."
                )
                self.result_warning.show()
                self.step_selector.blockSignals(True)
                self._append_result_step(step, len(steps))
                self.step_selector.setEnabled(True)
                self.step_selector.setCurrentIndex(len(steps) - 1)
                self.result_stack.setCurrentIndex(len(steps) - 1)
                self.step_selector.blockSignals(False)
                self._rendered_step_count = len(steps)
                self._update_step_navigation()
            else:
                self._render_method_result(method_id)

    def _cancel_jobs(self) -> None:
        if self.analysis_worker is None:
            return
        self.analysis_worker.request_cancel()
        self.cancel_method_button.setEnabled(False)
        self.status_message.setText("Cancelando el cálculo y conservando las etapas completadas…")

    def _receive_result(self, result: MethodResult) -> None:
        self.partial_results.pop(result.method_id, None)
        self.results[result.method_id] = result
        if result.method_id == self.current_method_id:
            self._render_method_result(result.method_id)
        self._refresh_method_checks()

    def _receive_partial_result(self, result: PartialMethodResult) -> None:
        self.results.pop(result.method_id, None)
        self.partial_results[result.method_id] = result
        if result.method_id == self.current_method_id:
            self._render_method_result(result.method_id)
        self.status_message.setText(
            f"{result.method_name} se detuvo: {result.failure_message} · "
            f"{len(result.steps)} etapas conservadas"
        )
        self._refresh_method_checks()

    def _method_failed(self, method_id: str, details: str) -> None:
        first_line = details.splitlines()[0]
        self.status_message.setText(f"Falló {METHOD_BY_ID[method_id].name}: {first_line}")
        QMessageBox.warning(self, f"No se pudo ejecutar {METHOD_BY_ID[method_id].name}", first_line)

    def _jobs_finished(self) -> None:
        self.analysis_thread = None
        self.analysis_worker = None
        self.run_method_button.setEnabled(True)
        self.run_all_button.setEnabled(True)
        self.cancel_method_button.setEnabled(False)
        self.cancel_method_button.hide()
        cancelled = any(
            "cancelada por el usuario" in result.failure_message.lower()
            for result in self.partial_results.values()
        )
        if not cancelled:
            self.run_progress.setValue(self.run_progress.maximum())
        warning_count = sum(bool(result.diagnostics.get("quality_warnings")) for result in self.results.values())
        warning_text = f" · {warning_count} con advertencias" if warning_count else ""
        partial_text = f" · {len(self.partial_results)} parciales" if self.partial_results else ""
        outcome = "Procesamiento cancelado" if cancelled else "Procesamiento terminado"
        self.status_message.setText(
            f"{outcome} · {len(self.results)} resultados disponibles"
            f"{warning_text}{partial_text}"
        )
        self._refresh_comparison()
        self._refresh_report_methods()
        self._finish_deferred_close()

    def _clear_result_steps(self, message: str) -> None:
        self._step_plot_timer.stop()
        self._pending_step_plots.clear()
        self._rendered_method_id = None
        self._rendered_step_count = 0
        self.result_warning.clear()
        self.result_warning.hide()
        self.step_selector.blockSignals(True)
        self.step_selector.clear()
        while self.result_stack.count():
            widget = self.result_stack.widget(0)
            self.result_stack.removeWidget(widget)
            widget.deleteLater()
        placeholder = QLabel(message)
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setWordWrap(True)
        self.result_stack.addWidget(placeholder)
        self.step_selector.addItem("Sin etapas disponibles")
        self.step_selector.setEnabled(False)
        self.step_selector.blockSignals(False)
        self._update_step_navigation()

    def _append_result_step(self, step: ProcessStep, index: int) -> None:
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 8, 8, 8)
        caption = QLabel(step.description)
        caption.setObjectName("PageLead")
        caption.setWordWrap(True)
        container_layout.addWidget(caption)
        self._pending_step_plots[container] = step
        self.result_stack.addWidget(container)
        self.step_selector.addItem(f"{index}. {step.title}")

    def _render_current_step_plot(self) -> None:
        """Create a canvas only when its step is viewed, coalescing live updates."""
        container = self.result_stack.currentWidget()
        step = self._pending_step_plots.pop(container, None)
        if step is None:
            return
        panel = PlotPanel()
        panel.set_plot(
            step.x,
            step.series,
            title=step.title,
            x_label=step.x_label,
            y_label=step.y_label,
            series_styles=step.series_styles,
        )
        container.layout().addWidget(panel, 1)

    def _render_method_result(self, method_id: str) -> None:
        result = self.results.get(method_id)
        partial = self.partial_results.get(method_id)
        if result is None and partial is None:
            self._clear_result_steps("Aún no hay un resultado para este método.")
            return
        if result is not None:
            steps = result.steps
            warnings = result.diagnostics.get("quality_warnings", [])
            if isinstance(warnings, str):
                warnings = [warnings]
            self.result_warning.setText(
                "Advertencia de calidad: " + " ".join(str(item) for item in warnings)
            )
            self.result_warning.setVisible(bool(warnings))
        else:
            assert partial is not None
            steps = partial.steps
            if partial.failure_message:
                self.result_warning.setText(
                    f"Ejecución parcial: {partial.failure_message} "
                    f"Se conservan {len(steps)} etapas; no se incluye en comparación ni informe."
                )
            else:
                self.result_warning.setText(
                    f"Procesamiento en curso · {len(steps)} etapas completadas."
                )
            self.result_warning.show()
        if (
            self._rendered_method_id == method_id
            and self._rendered_step_count == len(steps)
        ):
            self.step_selector.setEnabled(bool(steps))
            self._update_step_navigation()
            return
        self.step_selector.blockSignals(True)
        self.step_selector.clear()
        self._step_plot_timer.stop()
        self._pending_step_plots.clear()
        while self.result_stack.count():
            widget = self.result_stack.widget(0)
            self.result_stack.removeWidget(widget)
            widget.deleteLater()
        for index, step in enumerate(steps, start=1):
            self._append_result_step(step, index)
        self.step_selector.setEnabled(bool(steps))
        last_index = max(0, len(steps) - 1)
        self.step_selector.setCurrentIndex(last_index)
        self.result_stack.setCurrentIndex(last_index)
        self.step_selector.blockSignals(False)
        self._rendered_method_id = method_id
        self._rendered_step_count = len(steps)
        self._update_step_navigation()

    def _step_changed(self, index: int) -> None:
        if 0 <= index < self.result_stack.count():
            self.result_stack.setCurrentIndex(index)
        self._update_step_navigation()

    def _show_previous_step(self) -> None:
        self.step_selector.setCurrentIndex(max(0, self.step_selector.currentIndex() - 1))

    def _show_next_step(self) -> None:
        self.step_selector.setCurrentIndex(min(self.step_selector.count() - 1, self.step_selector.currentIndex() + 1))

    def _update_step_navigation(self) -> None:
        count = self.step_selector.count() if self.step_selector.isEnabled() else 0
        index = self.step_selector.currentIndex() if count else -1
        self.step_counter.setText(f"{index + 1 if index >= 0 else 0} / {count}")
        self.previous_step_button.setEnabled(index > 0)
        self.next_step_button.setEnabled(0 <= index < count - 1)

    def _build_compare_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(12)
        heading, heading_layout = _page_heading("Mesa de comparación", "Superposición, envolvente y consistencia entre las estimaciones disponibles.")
        heading_layout.addWidget(QLabel("Unidad"))
        self.compare_unit = QComboBox()
        self.compare_unit.addItems(["mm", "cm", "m"])
        self.compare_unit.currentTextChanged.connect(self._refresh_comparison)
        heading_layout.addWidget(self.compare_unit)
        layout.addWidget(heading)
        selector = QFrame()
        selector.setObjectName("SourceStrip")
        selector_layout = QHBoxLayout(selector)
        selector_layout.setContentsMargins(14, 8, 14, 8)
        self.compare_checks: dict[str, QCheckBox] = {}
        for spec in METHOD_SPECS:
            check = QCheckBox(spec.short_name)
            check.setToolTip(spec.name)
            check.setChecked(True)
            check.setEnabled(False)
            check.stateChanged.connect(self._refresh_comparison)
            selector_layout.addWidget(check)
            self.compare_checks[spec.method_id] = check
        selector_layout.addStretch()
        layout.addWidget(selector)
        self.compare_tabs = QTabWidget()
        self.overlay_plot = PlotPanel()
        self.envelope_plot = PlotPanel()
        self.correlation_plot = PlotPanel(animate=False)
        self.compare_tabs.addTab(self.overlay_plot, "Superposición")
        self.compare_tabs.addTab(self.envelope_plot, "Envolvente")
        self.compare_tabs.addTab(self.correlation_plot, "Correlación")
        layout.addWidget(self.compare_tabs, 1)
        self.metrics_table = QTableWidget(0, 7)
        self.metrics_table.setHorizontalHeaderLabels(["Método", "Pico", "Residual", "RMS", "Corr. consenso", "NRMSE", "Tiempo [s]"])
        self.metrics_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.metrics_table.setAlternatingRowColors(True)
        self.metrics_table.horizontalHeader().setStretchLastSection(True)
        self.metrics_table.setMaximumHeight(230)
        layout.addWidget(self.metrics_table)
        return page

    def _selected_comparison_results(self) -> list[MethodResult]:
        return [self.results[spec.method_id] for spec in METHOD_SPECS if spec.method_id in self.results and self.compare_checks[spec.method_id].isChecked()]

    def _refresh_method_checks(self) -> None:
        for method_id, check in self.compare_checks.items():
            check.setEnabled(method_id in self.results)

    def _refresh_comparison(self, *_args) -> None:
        if not hasattr(self, "compare_checks"):
            return
        self._refresh_method_checks()
        items = self._selected_comparison_results()
        if not items:
            empty_x = np.array([0.0, 1.0])
            empty = {"Sin resultados": np.zeros(2)}
            for plot, title in ((self.overlay_plot, "Superposición"), (self.envelope_plot, "Envolvente"), (self.correlation_plot, "Correlación")):
                plot.set_plot(empty_x, empty, title=title, x_label="", y_label="")
            self.metrics_table.setRowCount(0)
            return
        factor, unit = displacement_scale(self.compare_unit.currentText())
        series = {item.method_name: item.displacement_m * factor for item in items}
        self.overlay_plot.set_plot(items[0].time_s, series, title="Desplazamientos en una escala común", x_label="Tiempo [s]", y_label=f"Desplazamiento [{unit}]")
        minimum, median, maximum = comparison_envelope(items)
        self.envelope_plot.set_plot(items[0].time_s, {"Mínimo": minimum * factor, "Mediana": median * factor, "Máximo": maximum * factor}, title="Dispersión entre métodos", x_label="Tiempo [s]", y_label=f"Desplazamiento [{unit}]")
        names, matrix = pairwise_correlation(items)
        self.correlation_plot._timer.stop()
        axis = self.correlation_plot.axis
        axis.clear()
        image = axis.imshow(matrix, vmin=-1.0, vmax=1.0, cmap="RdBu_r")
        axis.set_xticks(range(len(names)), names, rotation=35, ha="right")
        axis.set_yticks(range(len(names)), names)
        axis.set_title("Correlación de Pearson", loc="left")
        for i in range(len(names)):
            for j in range(len(names)):
                axis.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", color="white" if abs(matrix[i, j]) > 0.55 else COLORS["ink"])
        if not hasattr(self.correlation_plot, "_colorbar"):
            self.correlation_plot._colorbar = self.correlation_plot.figure.colorbar(image, ax=axis, fraction=0.035, pad=0.03)
        else:
            self.correlation_plot._colorbar.update_normal(image)
        self.correlation_plot.refresh_navigation()
        rows = comparison_rows(items)
        self.metrics_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [row["method"], f"{float(row['peak_m']) * factor:.5g}", f"{float(row['residual_m']) * factor:.5g}", f"{float(row['rms_m']) * factor:.5g}", f"{float(row['correlation_consensus']):.4f}", f"{float(row['nrmse_consensus']):.4f}", f"{float(row['elapsed_s']):.3f}"]
            for column, value in enumerate(values):
                self.metrics_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.metrics_table.resizeColumnsToContents()

    def _build_report_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)
        heading, _ = _page_heading("Informe de estudio", "Documento autocontenido con configuración, referencias, resultados y gráficas seleccionadas.")
        layout.addWidget(heading)
        splitter = QSplitter()
        controls = QFrame()
        controls.setObjectName("ToolPanel")
        controls.setMinimumWidth(350)
        controls.setMaximumWidth(430)
        form_layout = QVBoxLayout(controls)
        form_layout.setContentsMargins(18, 16, 18, 18)
        form = QFormLayout()
        self.report_title = QLineEdit("Informe de desplazamientos")
        self.report_unit = QComboBox()
        self.report_unit.addItems(["mm", "cm", "m"])
        self.report_steps = QCheckBox("Incluir gráficas de todas las etapas")
        self.report_steps.setChecked(True)
        self.report_folder = QLineEdit(str(output_dir()))
        choose_output = _button("Seleccionar carpeta")
        choose_output.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        choose_output.clicked.connect(self._choose_report_folder)
        form.addRow("Título", self.report_title)
        form.addRow("Unidad", self.report_unit)
        form.addRow("Contenido", self.report_steps)
        form.addRow("Destino", self.report_folder)
        form_layout.addLayout(form)
        form_layout.addWidget(choose_output)
        form_layout.addWidget(QLabel("Métodos con resultado"))
        self.report_checks: dict[str, QCheckBox] = {}
        for spec in METHOD_SPECS:
            check = QCheckBox(f"{spec.short_name} · {spec.name}")
            check.setEnabled(False)
            self.report_checks[spec.method_id] = check
            form_layout.addWidget(check)
        form_layout.addStretch()
        self.generate_report = _button("Generar HTML + PDF", "primary")
        self.generate_report.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.generate_report.clicked.connect(self._generate_report)
        form_layout.addWidget(self.generate_report)
        self.open_report = _button("Abrir último informe")
        self.open_report.setEnabled(False)
        self.open_report.clicked.connect(self._open_last_report)
        form_layout.addWidget(self.open_report)
        splitter.addWidget(controls)
        self.report_preview = QTextBrowser()
        self.report_preview.setOpenExternalLinks(False)
        self.report_preview.setHtml("<h2 style='color:#00205B'>Sin resultados</h2><p>Los métodos ejecutados aparecerán en este espacio.</p>")
        splitter.addWidget(self.report_preview)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return page

    def _refresh_report_methods(self) -> None:
        if not hasattr(self, "report_checks"):
            return
        available: list[str] = []
        for method_id, check in self.report_checks.items():
            enabled = method_id in self.results
            check.setEnabled(enabled)
            check.setChecked(enabled)
            if enabled:
                available.append(METHOD_BY_ID[method_id].name)
        if available:
            items = "".join(f"<li>{name}</li>" for name in available)
            self.report_preview.setHtml(f"<h2 style='color:#00205B'>Contenido disponible</h2><ul>{items}</ul><p>El HTML incorpora las gráficas y Plotly para comparación interactiva sin conexión.</p>")
        else:
            self.report_preview.setHtml("<h2 style='color:#00205B'>Sin resultados</h2><p>Ejecuta al menos un método para generar el informe.</p>")

    def _choose_report_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Carpeta del informe", self.report_folder.text())
        if selected:
            self.report_folder.setText(selected)

    def _generate_report(self) -> None:
        if self.record is None:
            QMessageBox.information(self, "Informe", "No hay una señal cargada.")
            return
        selected = [self.results[method_id] for method_id, check in self.report_checks.items() if check.isChecked() and method_id in self.results]
        if not selected:
            QMessageBox.information(self, "Informe", "Selecciona al menos un método con resultado.")
            return
        destination = Path(self.report_folder.text()).expanduser()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", self.report_title.text().strip()).strip("_") or "informe"
        run_dir = destination / f"{safe_title}_{stamp}"
        try:
            export_result_bundle(run_dir / "datos", self.record, selected)
            content = build_report_html(self.record, selected, title=self.report_title.text().strip() or "Informe de desplazamientos", displacement_unit=self.report_unit.currentText(), include_steps=self.report_steps.isChecked())
            self.last_report = write_report(run_dir / "informe.html", content)
            write_pdf_report(
                run_dir / "informe.pdf",
                self.record,
                selected,
                title=self.report_title.text().strip() or "Informe de desplazamientos",
                displacement_unit=self.report_unit.currentText(),
                include_steps=self.report_steps.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Informe", f"No se pudo generar el informe:\n{exc}")
            return
        self.open_report.setEnabled(True)
        self.report_preview.setHtml(f"<h2 style='color:#00205B'>Informes generados</h2><p>{self.last_report}</p><p>La misma carpeta contiene el PDF, los CSV y el manifiesto JSON de los métodos seleccionados.</p>")
        self.status_message.setText(f"Informe generado: {self.last_report}")

    def _open_last_report(self) -> None:
        if self.last_report and self.last_report.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_report)))

    def _finish_deferred_close(self) -> None:
        if self._close_when_idle and self.analysis_thread is None and self.load_thread is None:
            self._close_when_idle = False
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event: object) -> None:  # noqa: N802
        if self.analysis_thread is not None:
            self._close_when_idle = True
            if self.analysis_worker is not None:
                self.analysis_worker.request_cancel()
            self.cancel_method_button.setEnabled(False)
            self.status_message.setText("Cancelando el cálculo antes de cerrar…")
            event.ignore()
            return
        if self.load_thread is not None:
            self._close_when_idle = True
            self.status_message.setText("Terminando la carga antes de cerrar…")
            event.ignore()
            return
        event.accept()


def run_gui() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return app.exec_()
