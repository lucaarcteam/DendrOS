import os
from typing import Optional
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QFont, QPen, QColor
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QToolBar, QStyle


ZOOM_FACTOR = 1.3


def _make_pan_icon(size: int = 22) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#333"), 2)
    p.setPen(pen)
    cx, cy = size // 2, size // 2
    r = size // 2 - 3
    # circle
    p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
    # up arrow
    p.drawLine(cx, cy - r + 3, cx, cy - 3)
    p.drawLine(cx - 3, cy - r + 6, cx, cy - r + 3)
    p.drawLine(cx + 3, cy - r + 6, cx, cy - r + 3)
    # down arrow
    p.drawLine(cx, cy + r - 3, cx, cy + 3)
    p.drawLine(cx - 3, cy + r - 6, cx, cy + r - 3)
    p.drawLine(cx + 3, cy + r - 6, cx, cy + r - 3)
    # left arrow
    p.drawLine(cx - r + 3, cy, cx - 3, cy)
    p.drawLine(cx - r + 6, cy - 3, cx - r + 3, cy)
    p.drawLine(cx - r + 6, cy + 3, cx - r + 3, cy)
    # right arrow
    p.drawLine(cx + r - 3, cy, cx + 3, cy)
    p.drawLine(cx + r - 6, cy - 3, cx + r - 3, cy)
    p.drawLine(cx + r - 6, cy + 3, cx + r - 3, cy)
    p.end()
    return QIcon(pix)


def _make_cursor_icon(size: int = 24) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#333"), 2)
    p.setPen(pen)
    cx = size // 2
    p.drawLine(cx, 4, cx, size - 4)
    p.drawLine(cx - 5, 6, cx + 5, 6)
    p.drawLine(cx - 4, 6, cx, 1)
    p.drawLine(cx + 4, 6, cx, 1)
    p.end()
    return QIcon(pix)


def _make_icon(text: str, size: int = 22) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = QFont("Monospace", 13, QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QPen(QColor("#333")))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return QIcon(pix)


class SeriesPlotWidget(QWidget):
    home_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(figsize=(8, 4), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)
        self.axes = self.fig.add_subplot(111)
        self._series_data: dict[str, np.ndarray] = {}
        self._colors = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd"]
        self._log_scale = False
        self._panning = True
        self._drag_start = None
        self._tracking = False
        self._track_vline = None
        self._track_label = None
        self._show_concordance = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.toolbar = QToolBar("Plot")
        self._setup_toolbar()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)

    def _setup_toolbar(self):
        icon_home = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        act_home = QAction(icon_home, "Home", self)
        act_home.triggered.connect(self._on_home)
        self.toolbar.addAction(act_home)

        self.toolbar.addSeparator()

        self.act_pan = QAction(_make_pan_icon(), "Pan", self)
        self.act_pan.setCheckable(True)
        self.act_pan.setChecked(True)
        self.act_pan.triggered.connect(self._on_pan)
        self.toolbar.addAction(self.act_pan)

        self.toolbar.addSeparator()

        act_zoomin = QAction(_make_icon("+", 24), "Zoom In", self)
        act_zoomin.triggered.connect(lambda: self._zoom(ZOOM_FACTOR))
        self.toolbar.addAction(act_zoomin)

        act_zoomout = QAction(_make_icon("\u2212", 24), "Zoom Out", self)
        act_zoomout.triggered.connect(lambda: self._zoom(1.0 / ZOOM_FACTOR))
        self.toolbar.addAction(act_zoomout)

        self.toolbar.addSeparator()

        self.act_track = QAction(_make_cursor_icon(), "Year Cursor", self)
        self.act_track.setCheckable(True)
        self.act_track.triggered.connect(self._on_track_toggle)
        self.toolbar.addAction(self.act_track)

        self.toolbar.addSeparator()

        icon_save = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        act_save = QAction(icon_save, "Save", self)
        act_save.triggered.connect(self._on_save)
        self.toolbar.addAction(act_save)

    def _on_home(self):
        self.home_requested.emit()
        self.act_pan.setChecked(True)
        self._panning = True

    def _on_pan(self, checked):
        self._panning = checked

    def _on_track_toggle(self, checked):
        self._tracking = checked
        if not checked:
            self._remove_track_artists()
            self.canvas.draw_idle()

    def _remove_track_artists(self):
        if self._track_vline is not None:
            try:
                self._track_vline.remove()
            except (ValueError, AttributeError):
                pass
            self._track_vline = None
        if self._track_label is not None:
            try:
                self._track_label.remove()
            except (ValueError, AttributeError):
                pass
            self._track_label = None

    def _on_scroll(self, event):
        if event.inaxes != self.axes:
            return
        x, y = event.xdata, event.ydata
        scale = ZOOM_FACTOR if event.button == "up" else 1.0 / ZOOM_FACTOR
        xlim = self.axes.get_xlim()
        ylim = self.axes.get_ylim()
        self.axes.set_xlim([x - (x - xlim[0]) * scale, x + (xlim[1] - x) * scale])
        self.axes.set_ylim([y - (y - ylim[0]) * scale, y + (ylim[1] - y) * scale])
        self.canvas.draw()

    def _on_press(self, event):
        if self._panning and event.button == 1 and event.inaxes == self.axes:
            self._drag_start = (event.xdata, event.ydata)

    def _on_release(self, event):
        if self._panning:
            self._drag_start = None

    def _on_motion(self, event):
        if self._panning and self._drag_start and event.inaxes == self.axes:
            x0, y0 = self._drag_start
            dx = x0 - event.xdata
            dy = y0 - event.ydata
            xlim = self.axes.get_xlim()
            ylim = self.axes.get_ylim()
            self.axes.set_xlim([xlim[0] + dx, xlim[1] + dx])
            if not self._log_scale:
                self.axes.set_ylim([ylim[0] + dy, ylim[1] + dy])
            self.canvas.draw_idle()
            self._drag_start = (event.xdata, event.ydata)
            return

        if self._tracking:
            if event.inaxes == self.axes:
                year = int(np.round(event.xdata))
                _, ymax = self.axes.get_ylim()
                if self._track_vline is None:
                    self._track_vline = self.axes.axvline(
                        year, color="gray", linestyle="--", linewidth=0.8, zorder=5
                    )
                    self._track_label = self.axes.annotate(
                        str(year), xy=(year, ymax),
                        xytext=(0, -6), textcoords="offset points",
                        ha="center", va="top", fontsize=9, color="gray",
                        bbox=dict(boxstyle="round,pad=0.15",
                                  facecolor="white", edgecolor="gray", alpha=0.8),
                    )
                else:
                    self._track_vline.set_xdata([year, year])
                    self._track_label.set_text(str(year))
                    self._track_label.xy = (year, ymax)
                self._track_vline.set_visible(True)
                self._track_label.set_visible(True)
                self.canvas.draw_idle()
            else:
                if self._track_vline is not None:
                    self._track_vline.set_visible(False)
                    self._track_label.set_visible(False)
                    self.canvas.draw_idle()

    def _zoom(self, factor):
        xlim = self.axes.get_xlim()
        ylim = self.axes.get_ylim()
        xmid = (xlim[0] + xlim[1]) / 2
        ymid = (ylim[0] + ylim[1]) / 2
        self.axes.set_xlim([xmid - (xmid - xlim[0]) * factor,
                            xmid + (xlim[1] - xmid) * factor])
        self.axes.set_ylim([ymid - (ymid - ylim[0]) * factor,
                            ymid + (ylim[1] - ymid) * factor])
        self.canvas.draw()

    def _on_save(self):
        from PyQt6.QtWidgets import QFileDialog
        path, filtr = QFileDialog.getSaveFileName(
            self, "Save plot", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if not path:
            return
        ext_map = {".png", ".pdf", ".svg"}
        ext = os.path.splitext(path)[1].lower()
        if ext not in ext_map:
            if "SVG" in filtr:
                path += ".svg"
            elif "PDF" in filtr:
                path += ".pdf"
            else:
                path += ".png"
        self.fig.savefig(path, dpi=300)

    def add_series(self, name: str, years: np.ndarray, values: np.ndarray):
        self._series_data[name] = (years, values)

    def zoom_to_series(self, name: str):
        data = self._series_data.get(name)
        if data is None:
            return
        years, values = data
        xpad = max(1, (years[-1] - years[0]) * 0.05)
        self.axes.set_xlim(years[0] - xpad, years[-1] + xpad)
        ymin, ymax = values.min(), values.max()
        ypad = (ymax - ymin) * 0.1 if ymax > ymin else 1
        self.axes.set_ylim(ymin - ypad, ymax + ypad)
        self.canvas.draw()

    def set_log_scale(self, enabled: bool):
        self._log_scale = enabled

    def set_show_concordance(self, enabled: bool):
        self._show_concordance = enabled

    def clear_series(self):
        self._series_data.clear()

    def _clean_xaxis(self):
        self.axes.xaxis.set_major_formatter(
            FuncFormatter(lambda v, _: "" if v == 0 else f"{v:.0f}")
        )

    def _draw_concordance(self):
        if len(self._series_data) != 2 or not self._show_concordance:
            return
        names = list(self._series_data.keys())
        y1, v1 = self._series_data[names[0]]
        y2, v2 = self._series_data[names[1]]
        common_start = max(y1[0], y2[0])
        common_end = min(y1[-1], y2[-1])
        if common_start >= common_end:
            return
        y_common = np.arange(common_start, common_end + 1)
        if len(y_common) < 2:
            return
        v1_interp = np.interp(y_common, y1, v1)
        v2_interp = np.interp(y_common, y2, v2)
        d1 = np.diff(v1_interp)
        d2 = np.diff(v2_interp)
        same_dir = (d1 > 0) == (d2 > 0)
        for i, agree in enumerate(same_dir):
            if agree:
                self.axes.axvspan(
                    y_common[i] - 0.5, y_common[i + 1] - 0.5,
                    color="#e0e0e0", zorder=0
                )

    def plot_all(self, info_labels: Optional[set[str]] = None, reset_zoom: bool = False):
        if not reset_zoom:
            xlim = self.axes.get_xlim()
            ylim = self.axes.get_ylim()
            has_limits = not (xlim == (0.0, 1.0) and ylim == (0.0, 1.0))
        self.axes.clear()
        self._track_vline = None
        self._track_label = None
        self._draw_concordance()
        for i, (name, (years, values)) in enumerate(self._series_data.items()):
            color = self._colors[i % len(self._colors)]
            self.axes.plot(years, values, label=name, color=color, linewidth=0.8)
        if self._series_data:
            self.axes.legend(fontsize=8)
            self.axes.set_xlabel("Year")
            self.axes.set_ylabel("Ring width")
        self.axes.set_yscale("log" if self._log_scale else "linear")
        self._clean_xaxis()
        if reset_zoom:
            self.axes.autoscale(True)
        elif has_limits:
            self.axes.set_xlim(xlim)
            self.axes.set_ylim(ylim)

        if info_labels:
            for i, (name, (years, values)) in enumerate(self._series_data.items()):
                if name in info_labels:
                    color = self._colors[i % len(self._colors)]
                    self.axes.annotate(
                        name, xy=(years[0], values[0]),
                        xytext=(-5, 0), textcoords="offset points",
                        fontsize=8, color=color, va="center", ha="right",
                    )
                    self.axes.annotate(
                        str(years[-1]), xy=(years[-1], values[-1]),
                        xytext=(5, 0), textcoords="offset points",
                        fontsize=8, color=color, va="center", ha="left",
                    )

        self.canvas.draw()

    def plot_series(self, years: np.ndarray, values: np.ndarray,
                    label: str = "", color: Optional[str] = None):
        self.axes.clear()
        self._track_vline = None
        self._track_label = None
        if color is None:
            color = self._colors[0]
        self.axes.plot(years, values, label=label, color=color, linewidth=0.8)
        if label:
            self.axes.legend(fontsize=8)
        self.axes.set_xlabel("Year")
        self.axes.set_ylabel("Ring width")
        self._clean_xaxis()
        self.canvas.draw()
