from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QStyle, QToolButton, QVBoxLayout, QWidget

from .theme import COLORS


class PlotPanel(QWidget):
    MAX_RENDER_POINTS = 20_000

    def __init__(self, parent: QWidget | None = None, *, animate: bool = True) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(8, 4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.axis = self.figure.add_subplot(111)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setIconSize(self.toolbar.iconSize())
        self._x = np.array([], dtype=float)
        self._series: dict[str, np.ndarray] = {}
        self._series_styles: dict[str, str] = {}
        self._title = ""
        self._x_label = ""
        self._y_label = ""
        self._cursor = 0
        self._selection_enabled = False
        self._selection_start: float | None = None
        self._selection_bounds: tuple[float, float] | None = None
        self._selection_artist = None
        self._selection_callback: Callable[[float, float], None] | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._advance)
        self.canvas.mpl_connect("button_press_event", self._selection_press)
        self.canvas.mpl_connect("button_release_event", self._selection_release)
        for action in self.toolbar.actions():
            action.triggered.connect(self.stop_animation)

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.addWidget(self.toolbar)
        tools.addStretch()
        self.restart = QToolButton()
        self.restart.setIcon(self.style().standardIcon(QStyle.SP_MediaSkipBackward))
        self.restart.setToolTip("Reiniciar animación")
        self.restart.clicked.connect(self.start_animation)
        self.play = QToolButton()
        self.play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play.setToolTip("Reproducir o pausar animación")
        self.play.clicked.connect(self.toggle_animation)
        if animate:
            tools.addWidget(self.restart)
            tools.addWidget(self.play)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        layout.addLayout(tools)
        layout.addWidget(self.canvas, 1)

    def set_plot(
        self,
        x: np.ndarray,
        series: Mapping[str, np.ndarray],
        *,
        title: str,
        x_label: str,
        y_label: str,
        series_styles: Mapping[str, str] | None = None,
    ) -> None:
        self._timer.stop()
        self._x = np.asarray(x, dtype=float)
        self._series = {str(label): np.asarray(values, dtype=float) for label, values in series.items()}
        self._series_styles = {
            str(label): str(style) for label, style in (series_styles or {}).items()
        }
        self._title = title
        self._x_label = x_label
        self._y_label = y_label
        self._cursor = self._x.size
        self._selection_bounds = None
        self._draw(None)
        self.toolbar.update()
        self.toolbar.push_current()

    def _draw(self, stop: int | None) -> None:
        self.axis.clear()
        self._selection_artist = None
        end = self._x.size if stop is None else max(2, min(stop, self._x.size))
        if end > self.MAX_RENDER_POINTS:
            indices = np.linspace(0, end - 1, self.MAX_RENDER_POINTS, dtype=int)
        else:
            indices = np.arange(end)
        for label, values in self._series.items():
            style = self._series_styles.get(label, "line")
            if style == "points":
                plot_indices = np.flatnonzero(np.isfinite(values[:end]))
                if plot_indices.size > self.MAX_RENDER_POINTS:
                    positions = np.linspace(
                        0, plot_indices.size - 1, self.MAX_RENDER_POINTS, dtype=int
                    )
                    plot_indices = plot_indices[positions]
                self.axis.plot(
                    self._x[plot_indices],
                    values[plot_indices],
                    linestyle="none",
                    marker="o",
                    markersize=5,
                    label=label,
                )
            else:
                self.axis.plot(
                    self._x[indices],
                    values[indices],
                    linestyle="--" if style == "dashed" else "-",
                    label=label,
                )
        self.axis.set_title(self._title, loc="left")
        self.axis.set_xlabel(self._x_label)
        self.axis.set_ylabel(self._y_label)
        if len(self._series) > 1:
            self.axis.legend(loc="upper right", ncol=min(3, len(self._series)))
        if self._x.size:
            lower = float(self._x[0])
            upper = float(self._x[-1])
            if np.isclose(lower, upper):
                padding = max(0.5, abs(lower) * 0.05)
                lower -= padding
                upper += padding
            self.axis.set_xlim(lower, upper)
        self._draw_selection()
        self.canvas.draw_idle()

    def stop_animation(self, *_args) -> None:
        self._timer.stop()
        self.play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def refresh_navigation(self) -> None:
        self.stop_animation()
        self.toolbar.update()
        self.toolbar.push_current()
        self.canvas.draw_idle()

    def set_view_interval(self, start: float, end: float) -> None:
        if end <= start:
            return
        self.stop_animation()
        self.axis.set_xlim(float(start), float(end))
        self.toolbar.push_current()
        self.canvas.draw_idle()

    def set_interval_selection(
        self,
        enabled: bool,
        callback: Callable[[float, float], None] | None = None,
    ) -> None:
        if enabled:
            for action in self.toolbar.actions():
                if action.isCheckable() and action.isChecked():
                    action.trigger()
        self._selection_enabled = bool(enabled)
        if callback is not None:
            self._selection_callback = callback
        self.stop_animation()
        self.canvas.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)

    def set_selection_bounds(self, start: float | None, end: float | None) -> None:
        if start is None or end is None or end <= start:
            self._selection_bounds = None
        else:
            self._selection_bounds = (float(start), float(end))
        self._draw_selection()
        self.canvas.draw_idle()

    def _draw_selection(self) -> None:
        if self._selection_artist is not None:
            try:
                self._selection_artist.remove()
            except ValueError:
                pass
            self._selection_artist = None
        if self._selection_bounds is not None:
            start, end = self._selection_bounds
            self._selection_artist = self.axis.axvspan(start, end, color=COLORS["cyan"], alpha=0.14)

    def _selection_press(self, event) -> None:
        if not self._selection_enabled or event.inaxes is not self.axis or event.xdata is None:
            return
        if event.button != 1 or self.toolbar.mode:
            return
        self._selection_start = float(event.xdata)

    def _selection_release(self, event) -> None:
        if self._selection_start is None:
            return
        start = self._selection_start
        self._selection_start = None
        if not self._selection_enabled or event.inaxes is not self.axis or event.xdata is None:
            return
        end = float(event.xdata)
        lower, upper = sorted((start, end))
        if self._x.size:
            lower = max(lower, float(self._x[0]))
            upper = min(upper, float(self._x[-1]))
        if upper <= lower:
            return
        self.set_selection_bounds(lower, upper)
        if self._selection_callback is not None:
            self._selection_callback(lower, upper)

    def start_animation(self) -> None:
        if self._x.size < 3:
            return
        self._cursor = 2
        self._draw(self._cursor)
        self._timer.start()
        self.play.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def toggle_animation(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        elif self._cursor >= self._x.size:
            self.start_animation()
        else:
            self._timer.start()
            self.play.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def _advance(self) -> None:
        increment = max(1, self._x.size // 180)
        self._cursor += increment
        if self._cursor >= self._x.size:
            self._cursor = self._x.size
            self._timer.stop()
            self.play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self._draw(self._cursor)


class FlowDiagramWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._steps: tuple[str, ...] = ()
        self._accent = COLORS["cyan"]
        self.setMinimumHeight(116)
        self.setMaximumHeight(142)

    def set_flow(self, steps: tuple[str, ...], accent: str) -> None:
        self._steps = steps
        self._accent = accent
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._steps:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        margin = 8.0
        gap = 18.0
        count = len(self._steps)
        width = max(82.0, (self.width() - 2 * margin - gap * (count - 1)) / count)
        height = 64.0
        y = 18.0
        accent = QColor(self._accent)
        for index, label in enumerate(self._steps):
            x = margin + index * (width + gap)
            rect = QRectF(x, y, width, height)
            painter.setPen(QPen(accent, 1.4))
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawRoundedRect(rect, 4.0, 4.0)
            painter.setPen(QColor(COLORS["navy"]))
            painter.drawText(rect.adjusted(7, 6, -7, -6), Qt.AlignCenter | Qt.TextWordWrap, f"{index + 1}\n{label}")
            if index < count - 1:
                start_x = rect.right() + 3
                end_x = rect.right() + gap - 3
                center_y = rect.center().y()
                painter.setPen(QPen(accent, 2.0))
                painter.drawLine(int(start_x), int(center_y), int(end_x), int(center_y))
                arrow = QPainterPath()
                arrow.moveTo(end_x, center_y)
                arrow.lineTo(end_x - 6, center_y - 4)
                arrow.lineTo(end_x - 6, center_y + 4)
                arrow.closeSubpath()
                painter.fillPath(arrow, accent)
