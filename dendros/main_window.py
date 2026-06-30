import json
import os

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QStatusBar,
    QToolBar, QFileDialog, QMessageBox, QTabWidget, QTextEdit,
    QHeaderView,
)

from .models.project import Project
from .models.series import Series
from .data_import import read_rwl, read_txt_single, read_fh
from .plot_widget import SeriesPlotWidget
import numpy as np
from .dialogs import CrossDateDialog, SeriesInfoDialog, BuildMasterDialog, DetrendDialog
from .analysis import compute_pointer_years


# Column indices in the series tree
COL_VIEW = 0
COL_NAME = 1
COL_START = 2
COL_END = 3
COL_LENGTH = 4
COL_EDIT = 5
COL_REF = 6
COL_INFO = 7


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project(name="Untitled")
        self._current_file = None
        self.setWindowTitle("DendrOS - Untitled")
        self.resize(1200, 800)
        self._sort_column = -1
        self._sort_order = Qt.SortOrder.AscendingOrder

        self._setup_actions()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_ui()
        self._setup_statusbar()

    def _setup_actions(self):
        self.act_open = QAction("Open files...", self)
        self.act_open.triggered.connect(self._on_open)

        self.act_open_project = QAction("Open Project...", self)
        self.act_open_project.triggered.connect(self._on_open_project)

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut("Ctrl+S")
        self.act_save.triggered.connect(self._on_save)

        self.act_save_as = QAction("Save As...", self)
        self.act_save_as.setShortcut("Ctrl+Shift+S")
        self.act_save_as.triggered.connect(self._on_save_as)

        self.act_quit = QAction("Quit", self)
        self.act_quit.triggered.connect(self.close)

        self.act_clear = QAction("Clear All", self)
        self.act_clear.triggered.connect(self._on_clear)

        self.act_crossdate = QAction("Cross-Dating...", self)
        self.act_crossdate.triggered.connect(self._on_crossdate)

        self.act_master = QAction("Build Master...", self)
        self.act_master.triggered.connect(self._on_build_master)

        self.act_detrend = QAction("Detrend / Index...", self)
        self.act_detrend.triggered.connect(self._on_detrend)

        self.act_series_info = QAction("Series Info...", self)
        self.act_series_info.triggered.connect(self._on_series_info)

        self.act_log_scale = QAction("Log Scale Y", self)
        self.act_log_scale.setCheckable(True)
        self.act_log_scale.triggered.connect(self._on_toggle_log)

        self.act_show_indices = QAction("Show Indices", self)
        self.act_show_indices.setCheckable(True)
        self.act_show_indices.triggered.connect(self._on_toggle_indices)

        self.act_concordance = QAction("Concordance Bands", self)
        self.act_concordance.setCheckable(True)
        self.act_concordance.triggered.connect(self._on_toggle_concordance)

        self.act_pointer_years = QAction("Show Pointer Years", self)
        self.act_pointer_years.setCheckable(True)
        self.act_pointer_years.triggered.connect(self._on_toggle_pointer_years)

    def _setup_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_open_project)
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self.act_clear)

        analysis_menu = menubar.addMenu("Analysis")
        analysis_menu.addAction(self.act_crossdate)
        analysis_menu.addAction(self.act_master)
        analysis_menu.addSeparator()
        analysis_menu.addAction(self.act_detrend)
        analysis_menu.addSeparator()
        analysis_menu.addAction(self.act_series_info)

        view_menu = menubar.addMenu("View")
        view_menu.addAction(self.act_log_scale)
        view_menu.addAction(self.act_show_indices)
        view_menu.addAction(self.act_concordance)
        view_menu.addAction(self.act_pointer_years)
        menubar.addMenu("Help")

    def _setup_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction(self.act_open)
        toolbar.addAction(self.act_save)

    def _setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.series_tree = QTreeWidget()
        self.series_tree.setHeaderLabels(["View", "Series", "Start", "End", "Length", "Edit", "Ref", "Info"])
        self.series_tree.setMinimumWidth(250)
        self.series_tree.setSortingEnabled(False)
        self.series_tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.series_tree.itemClicked.connect(self._on_tree_clicked)
        self.series_tree.itemDoubleClicked.connect(self._on_tree_double_clicked)

        self.series_tree.header().viewport().installEventFilter(self)
        self.series_tree.installEventFilter(self)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        self.plot_widget = SeriesPlotWidget()
        self.plot_widget.home_requested.connect(lambda: self._update_plot(reset_zoom=True))

        self.tabs = QTabWidget()
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setFont(QFont("Monospace", 10))
        self.tabs.addTab(self.info_text, "Info")

        right_splitter.addWidget(self.plot_widget)
        right_splitter.addWidget(self.tabs)
        right_splitter.setSizes([500, 200])

        splitter.addWidget(self.series_tree)
        splitter.addWidget(right_splitter)
        splitter.setSizes([300, 900])

        self.setCentralWidget(splitter)

    def _setup_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)

    def _on_open(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open dendro files", "",
            "Dendro files (*.rwl *.txt *.fh);;All files (*)"
        )
        if not paths:
            return

        total = 0
        for path in paths:
            ext = os.path.splitext(path)[1].lower()
            try:
                if ext == ".rwl":
                    series_list = read_rwl(path)
                elif ext == ".fh":
                    series_list = read_fh(path)
                else:
                    s = read_txt_single(path)
                    series_list = [s] if s else []

                for series in series_list:
                    if series:
                        self.project.add_series(series)
                        self._add_series_to_tree(series)
                        total += 1
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not load {path}:\n{e}")

        if total:
            self._update_plot(reset_zoom=True)
            self.status_label.setText(f"Loaded {total} series")

    def _current_tree_state(self):
        states = {}
        for i in range(self.series_tree.topLevelItemCount()):
            item = self.series_tree.topLevelItem(i)
            name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
            states[name] = {
                "view": item.checkState(COL_VIEW) == Qt.CheckState.Checked,
                "edit": item.checkState(COL_EDIT) == Qt.CheckState.Checked,
                "ref": item.checkState(COL_REF) == Qt.CheckState.Checked,
                "info": item.checkState(COL_INFO) == Qt.CheckState.Checked,
            }
        return states

    def _apply_tree_state(self, states):
        for i in range(self.series_tree.topLevelItemCount()):
            item = self.series_tree.topLevelItem(i)
            name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
            s = states.get(name, {})
            item.setCheckState(COL_VIEW, Qt.CheckState.Checked if s.get("view", True) else Qt.CheckState.Unchecked)
            item.setCheckState(COL_EDIT, Qt.CheckState.Checked if s.get("edit", False) else Qt.CheckState.Unchecked)
            item.setCheckState(COL_REF, Qt.CheckState.Checked if s.get("ref", False) else Qt.CheckState.Unchecked)
            item.setCheckState(COL_INFO, Qt.CheckState.Checked if s.get("info", False) else Qt.CheckState.Unchecked)

    def _save_project(self, path: str):
        data = {
            "version": 2,
            "name": self.project.name,
            "log_scale": self.act_log_scale.isChecked(),
            "show_indices": self.act_show_indices.isChecked(),
            "concordance": self.act_concordance.isChecked(),
            "pointer_years": self.act_pointer_years.isChecked(),
            "sort_column": self._sort_column,
            "sort_order": self._sort_order.value,
            "tree_states": self._current_tree_state(),
            "series": [
                {
                    "name": s.name,
                    "filename": s.filename,
                    "species": s.species,
                    "notes": s.notes,
                    "years": s.years.tolist(),
                    "values": s.values.tolist(),
                    "indices": s.indices.tolist() if s.has_indices() else None,
                    "detrend_method": s.detrend_method,
                }
                for s in self.project.series_list
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_project(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._on_clear()
        self.project.name = data.get("name", "Untitled")

        for sd in data.get("series", []):
            import numpy as np
            indices_raw = sd.get("indices")
            s = Series(
                name=sd["name"],
                filename=sd.get("filename", ""),
                species=sd.get("species", ""),
                notes=sd.get("notes", ""),
                years=np.array(sd["years"], dtype=int),
                values=np.array(sd["values"], dtype=float),
                indices=np.array(indices_raw, dtype=float) if indices_raw is not None else None,
                detrend_method=sd.get("detrend_method", ""),
            )
            self.project.add_series(s)
            self._add_series_to_tree(s)

        self._apply_tree_state(data.get("tree_states", {}))

        self._sort_column = data.get("sort_column", -1)
        self._sort_order = Qt.SortOrder(data.get("sort_order", 0))

        log_scale = data.get("log_scale", False)
        self.act_log_scale.setChecked(log_scale)
        self.plot_widget.set_log_scale(log_scale)
        show_indices = data.get("show_indices", False)
        self.act_show_indices.setChecked(show_indices)
        concordance = data.get("concordance", False)
        self.act_concordance.setChecked(concordance)
        self.plot_widget.set_show_concordance(concordance)
        pointer_years = data.get("pointer_years", False)
        self.act_pointer_years.setChecked(pointer_years)
        self.plot_widget.set_show_pointer_years(pointer_years)

        self._update_plot(reset_zoom=True)

    def _on_save(self):
        if self._current_file:
            self._save_project(self._current_file)
            self.status_label.setText(f"Saved to {os.path.basename(self._current_file)}")
        else:
            self._on_save_as()

    def _on_save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "",
            "DendroApp Project (*.dendro);;All files (*)"
        )
        if not path:
            return
        if not path.endswith(".dendro"):
            path += ".dendro"
        self._save_project(path)
        self._current_file = path
        self.project.name = os.path.splitext(os.path.basename(path))[0]
        self.setWindowTitle(f"DendroApp - {os.path.basename(path)}")
        self.status_label.setText(f"Saved to {os.path.basename(path)}")

    def _on_open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "",
            "DendroApp Project (*.dendro);;All files (*)"
        )
        if not path:
            return
        try:
            self._load_project(path)
            self._current_file = path
            self.project.name = os.path.splitext(os.path.basename(path))[0]
            self.setWindowTitle(f"DendroApp - {os.path.basename(path)}")
            self.status_label.setText(f"Loaded {len(self.project.series_list)} series from project")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load project:\n{e}")

    def _on_clear(self):
        self.project.series_list.clear()
        self.series_tree.clear()
        self.plot_widget.clear_series()
        self.plot_widget.plot_all(reset_zoom=True)
        self.info_text.clear()
        self.status_label.setText("Cleared all series")

    def _on_crossdate(self):
        if len(self.project.series_list) < 2:
            QMessageBox.warning(self, "Warning", "Need at least 2 series for cross-dating.")
            return
        dlg = CrossDateDialog(self.project, self)
        dlg.exec()
        self._refresh_project_ui()

    def _on_build_master(self):
        if not self.project.series_list:
            QMessageBox.warning(self, "Warning", "No series loaded.")
            return
        dlg = BuildMasterDialog(self.project, self)
        if dlg.exec():
            self._refresh_project_ui()

    def _on_detrend(self):
        if not self.project.series_list:
            QMessageBox.warning(self, "Warning", "No series loaded.")
            return
        dlg = DetrendDialog(self.project, self)
        if dlg.exec():
            self._refresh_project_ui()

    def _on_series_info(self):
        name = self._selected_series_name()
        if name is None:
            QMessageBox.warning(self, "Warning", "Select a series first.")
            return
        series = self.project.get_series(name)
        if series is None:
            return
        dlg = SeriesInfoDialog(series, self.project, self)
        dlg.exec()

    def _edit_end_year(self, item):
        from PyQt6.QtWidgets import QInputDialog
        name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        series = self.project.get_series(name)
        if series is None:
            return
        new_end, ok = QInputDialog.getInt(
            self, f"Edit End Year — {name}",
            f"Current: {series.start_year} – {series.end_year}  (length={series.length})\nNew end year:",
            series.end_year, -9999, 9999, 1
        )
        if not ok or new_end == series.end_year:
            return

        offset = new_end - series.end_year
        new_start = series.start_year + offset
        new_years = np.arange(new_start, new_end + 1, dtype=int)
        updated = Series(
            name=series.name,
            years=new_years,
            values=series.values.copy(),
            filename=series.filename,
        )
        idx = self.project.series_list.index(series)
        self.project.series_list[idx] = updated

        item.setText(COL_START, str(new_start))
        item.setText(COL_END, str(new_end))
        self._update_plot()
        self.status_label.setText(f"Series '{name}' shifted to {new_start}–{new_end} (length={series.length})")

    def _shift_edited_series(self, delta: int):
        for i in range(self.series_tree.topLevelItemCount()):
            item = self.series_tree.topLevelItem(i)
            if item.checkState(COL_EDIT) == Qt.CheckState.Checked:
                if item.checkState(COL_REF) == Qt.CheckState.Checked:
                    return
                name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
                series = self.project.get_series(name)
                if series is None:
                    return
                new_end = series.end_year + delta
                new_start = series.start_year + delta
                new_years = np.arange(new_start, new_end + 1, dtype=int)
                updated = Series(
                    name=series.name,
                    years=new_years,
                    values=series.values.copy(),
                    filename=series.filename,
                )
                idx = self.project.series_list.index(series)
                self.project.series_list[idx] = updated
                item.setText(COL_START, str(new_start))
                item.setText(COL_END, str(new_end))
                self._update_plot()
                direction = "forward" if delta > 0 else "backward"
                self.status_label.setText(
                    f"Series '{name}' shifted {direction} to {new_start}–{new_end}"
                )
                return

    def _on_toggle_log(self):
        self.plot_widget.set_log_scale(self.act_log_scale.isChecked())
        self._update_plot()

    def _on_toggle_indices(self):
        self._update_plot()

    def _on_toggle_concordance(self):
        self.plot_widget.set_show_concordance(self.act_concordance.isChecked())
        self._update_plot()

    def _on_toggle_pointer_years(self):
        self._update_plot()

    def _on_tree_double_clicked(self, item, column):
        if column == COL_END and item.checkState(COL_EDIT) == Qt.CheckState.Checked:
            if item.checkState(COL_REF) == Qt.CheckState.Checked:
                self.status_label.setText("Cannot edit a reference series")
                return
            self._edit_end_year(item)
        else:
            self._on_series_info()

    def _selected_series_name(self):
        sel = self.series_tree.selectedItems()
        if not sel:
            return None
        return sel[0].data(COL_NAME, Qt.ItemDataRole.UserRole)

    def _refresh_project_ui(self):
        self.series_tree.clear()
        for s in self.project.series_list:
            self._add_series_to_tree(s)
        self._update_plot(reset_zoom=True)

    def _add_series_to_tree(self, series: Series):
        item = QTreeWidgetItem()
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(COL_VIEW, Qt.CheckState.Checked)
        item.setText(COL_NAME, series.name)
        item.setText(COL_START, str(series.start_year))
        item.setText(COL_END, str(series.end_year))
        item.setText(COL_LENGTH, str(series.length))
        item.setData(COL_NAME, Qt.ItemDataRole.UserRole, series.name)
        for col in (COL_EDIT, COL_REF, COL_INFO):
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(col, Qt.CheckState.Unchecked)
        self.series_tree.addTopLevelItem(item)

    def _on_header_clicked(self, column):
        if column == COL_VIEW:
            total = self.series_tree.topLevelItemCount()
            if total == 0:
                return
            checked = sum(
                1 for i in range(total)
                if self.series_tree.topLevelItem(i).checkState(COL_VIEW) == Qt.CheckState.Checked
            )
            new_state = Qt.CheckState.Unchecked if checked == total else Qt.CheckState.Checked
            for i in range(total):
                self.series_tree.topLevelItem(i).setCheckState(COL_VIEW, new_state)
            self._update_plot()
        elif column in (COL_NAME, COL_START, COL_END, COL_LENGTH):
            self._sort_tree(column)

    def _sort_tree(self, column):
        total = self.series_tree.topLevelItemCount()
        if total < 2:
            return
        data = []
        for i in range(total):
            item = self.series_tree.topLevelItem(i)
            name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
            series = self.project.get_series(name)
            if column == COL_NAME:
                key = (name.lower(),)
            elif column == COL_START:
                key = (series.start_year if series else 0, name.lower())
            elif column == COL_END:
                key = (series.end_year if series else 0, name.lower())
            elif column == COL_LENGTH:
                key = (series.length if series else 0, name.lower())
            data.append((key, item))

        if self._sort_column == column:
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder

        data.sort(key=lambda x: x[0], reverse=(self._sort_order == Qt.SortOrder.DescendingOrder))

        self.series_tree.blockSignals(True)
        while self.series_tree.topLevelItemCount() > 0:
            self.series_tree.takeTopLevelItem(0)
        for _, item in data:
            self.series_tree.addTopLevelItem(item)
        self.series_tree.blockSignals(False)
        self._update_plot()

    def eventFilter(self, obj, event):
        if obj is self.series_tree and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                delta = -1 if key == Qt.Key.Key_Left else 1
                self._shift_edited_series(delta)
                return True
            return super().eventFilter(obj, event)
        vp = self.series_tree.header().viewport()
        if obj is vp and event.type() == QEvent.Type.MouseButtonPress:
            sec = self.series_tree.header().logicalIndexAt(event.pos())
            if sec >= 0:
                self._on_header_clicked(sec)
        return super().eventFilter(obj, event)

    def _on_tree_clicked(self, item, column):
        if column == COL_VIEW:
            self._update_plot()
            return
        if column == COL_EDIT:
            if item.checkState(COL_REF) == Qt.CheckState.Checked:
                item.setCheckState(COL_EDIT, Qt.CheckState.Unchecked)
                self.status_label.setText("Remove Ref flag first to edit this series")
                return
            if item.checkState(COL_EDIT) == Qt.CheckState.Checked:
                reply = QMessageBox.question(
                    self, "Confirm Editing",
                    "Warning! You are enabling series editing!\n"
                    "Are you sure you want to proceed?",
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
                )
                if reply != QMessageBox.StandardButton.Ok:
                    item.setCheckState(COL_EDIT, Qt.CheckState.Unchecked)
                    return
                # Exclusive: uncheck Edit on all other series
                for i in range(self.series_tree.topLevelItemCount()):
                    other = self.series_tree.topLevelItem(i)
                    if other is not item:
                        other.setCheckState(COL_EDIT, Qt.CheckState.Unchecked)
            return
        if column == COL_REF:
            if item.checkState(COL_REF) == Qt.CheckState.Checked:
                item.setCheckState(COL_EDIT, Qt.CheckState.Unchecked)
                self.status_label.setText(f"'{item.text(COL_NAME)}' set as reference (protected)")
            else:
                self.status_label.setText(f"'{item.text(COL_NAME)}' reference flag removed")
            return
        if column == COL_INFO:
            self._update_plot()
            return
        name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        if column == COL_NAME:
            self.plot_widget.zoom_to_series(name)
            self.status_label.setText(f"Zoomed to: {name}")
            return
        series = self.project.get_series(name)
        if series is None:
            return

        mean = series.values.mean()
        std = series.values.std()
        info = (
            f"Series: {series.name}\n"
            f"File: {series.filename}\n"
            f"Span: {series.start_year} - {series.end_year}\n"
            f"Length: {series.length} years\n"
            f"Mean: {mean:.3f}\n"
            f"Std Dev: {std:.3f}\n"
            f"Min: {series.values.min():.3f}\n"
            f"Max: {series.values.max():.3f}"
        )
        self.info_text.setText(info)
        self.status_label.setText(f"Selected: {series.name}")

    def _update_plot(self, reset_zoom: bool = False):
        self.plot_widget.clear_series()
        use_indices = self.act_show_indices.isChecked()
        self.plot_widget.set_show_indices(use_indices)
        info_names = set()
        for i in range(self.series_tree.topLevelItemCount()):
            item = self.series_tree.topLevelItem(i)
            if item.checkState(COL_VIEW) == Qt.CheckState.Checked:
                name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
                series = self.project.get_series(name)
                if series is not None:
                    if use_indices and series.has_indices():
                        self.plot_widget.add_series(
                            series.name, series.years, series.indices
                        )
                    else:
                        self.plot_widget.add_series(
                            series.name, series.years, series.values
                        )
                if item.checkState(COL_INFO) == Qt.CheckState.Checked:
                    info_names.add(name)

        show_py = self.act_pointer_years.isChecked()
        self.plot_widget.set_show_pointer_years(show_py)
        if show_py and self.project.series_list:
            visible = []
            for i in range(self.series_tree.topLevelItemCount()):
                item = self.series_tree.topLevelItem(i)
                if item.checkState(COL_VIEW) == Qt.CheckState.Checked:
                    name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
                    s = self.project.get_series(name)
                    if s:
                        visible.append(s)
            if len(visible) >= 2:
                py_data = compute_pointer_years(visible, threshold=75.0, min_series=2)
                self.plot_widget.set_pointer_years_data(py_data)
            else:
                self.plot_widget.set_pointer_years_data({})
        else:
            self.plot_widget.set_pointer_years_data({})

        self.plot_widget.plot_all(info_labels=info_names, reset_zoom=reset_zoom)
