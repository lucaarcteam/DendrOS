from typing import Optional
import numpy as np
import pandas as pd

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QHeaderView, QSpinBox,
    QGroupBox, QMessageBox, QFormLayout, QCheckBox, QScrollArea,
    QWidget, QRadioButton, QButtonGroup,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .models.project import Project
from .models.series import Series
from .analysis import sliding_correlation, pearson_r, tvalue, gleichlaeufigkeit, build_master, pvalue_from_t


class CrossDateDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Cross-Dating")
        self.resize(950, 600)
        self._results = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Target samples: checkboxes in a scroll area
        self.sample_checkboxes: list[QCheckBox] = []
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(120)
        cw = QWidget()
        cbl = QVBoxLayout(cw)
        cbl.setContentsMargins(0, 0, 0, 0)
        for s in self.project.series_list:
            cb = QCheckBox(s.name)
            cb.setChecked(False)
            self.sample_checkboxes.append(cb)
            cbl.addWidget(cb)
        cbl.addStretch()
        scroll.setWidget(cw)
        form.addRow("Samples:", scroll)

        # Reference series
        self.cb_reference = QComboBox()
        for s in self.project.series_list:
            self.cb_reference.addItem(s.name)
        self.cb_reference.addItem("Master (auto-build)", "__master__")
        form.addRow("Reference:", self.cb_reference)

        self.spin_overlap = QSpinBox()
        self.spin_overlap.setRange(10, 500)
        self.spin_overlap.setValue(20)
        form.addRow("Min overlap:", self.spin_overlap)

        layout.addLayout(form)

        self.btn_run = QPushButton("Run Cross-Dating")
        self.btn_run.clicked.connect(self._run)
        layout.addWidget(self.btn_run)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Sample", "Offset", "Overlap", "r (Pearson)", "tBP", "p", "GLK (%)", "Notes", ""
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemClicked.connect(self._on_row_clicked)
        layout.addWidget(self.table)

        self.detail_label = QLabel("Select a row to see overlap detail")
        layout.addWidget(self.detail_label)

        # Overlap plot
        self.overlap_fig = Figure(figsize=(6, 2), tight_layout=True)
        self.overlap_canvas = FigureCanvas(self.overlap_fig)
        self.overlap_canvas.setMinimumHeight(150)
        layout.addWidget(self.overlap_canvas)

        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("Apply Best Offset")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._apply_offset)
        btn_row.addWidget(self.btn_apply)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _get_reference(self) -> Optional[Series]:
        data = self.cb_reference.currentData()
        if data == "__master__":
            return build_master(self.project.series_list)
        name = self.cb_reference.currentText()
        return self.project.get_series(name)

    def _run(self):
        reference = self._get_reference()
        if reference is None:
            QMessageBox.warning(self, "Error", "Could not build reference series.")
            return

        selected = []
        for cb in self.sample_checkboxes:
            if cb.isChecked():
                s = self.project.get_series(cb.text())
                if s:
                    selected.append(s)

        if not selected:
            QMessageBox.warning(self, "Error", "Select at least one sample.")
            return

        min_overlap = self.spin_overlap.value()
        all_results = []
        ref_name = self.cb_reference.currentText()

        for target in selected:
            results = sliding_correlation(target, reference, min_overlap=min_overlap)
            for r in results:
                r["sample"] = target.name
                all_results.append(r)

        all_results.sort(key=lambda x: x["t"] if x["t"] is not None else -1e9, reverse=True)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._results = all_results

        if not all_results:
            self.detail_label.setText("No overlapping positions found.")
            return

        for row_idx, res in enumerate(all_results):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(res["sample"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(res["offset"])))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(res["overlap"])))
            self.table.setItem(row_idx, 3, QTableWidgetItem(f"{res['r']:.4f}"))
            tv = res["t"]
            self.table.setItem(row_idx, 4, QTableWidgetItem(f"{tv:.2f}" if tv is not None else "N/A"))
            pv = res.get("p")
            self.table.setItem(row_idx, 5, QTableWidgetItem(f"{pv:.4f}" if pv is not None else "N/A"))
            self.table.setItem(row_idx, 6, QTableWidgetItem(f"{res['glk']:.1f}"))

            note = ""
            if res["offset"] == 0:
                note = "current position"
            self.table.setItem(row_idx, 7, QTableWidgetItem(note))
            self.table.setItem(row_idx, 8, QTableWidgetItem(""))

        self.table.setSortingEnabled(True)
        self.btn_apply.setEnabled(True)
        self.detail_label.setText(
            f"Cross-dated {len(selected)} samples against {ref_name} "
            f"({len(all_results)} positions, best tBP={all_results[0]['t']:.2f} "
            f"at offset {all_results[0]['offset']})"
        )

    def _on_row_clicked(self, item):
        row = item.row()
        if row >= len(self._results):
            return
        res = self._results[row]
        pv = res.get("p")
        p_str = f", p={pv:.4f}" if pv is not None else ""
        self.detail_label.setText(
            f"Sample: {res['sample']} | Offset {res['offset']}: overlap={res['overlap']} yrs, "
            f"r={res['r']:.4f}, tBP={res['t']:.2f}{p_str}, GLK={res['glk']:.1f}%"
        )
        self._draw_overlap(res)

    def _draw_overlap(self, res):
        self.overlap_fig.clear()
        ax = self.overlap_fig.add_subplot(111)

        sample_name = res["sample"]
        ref_name = self.cb_reference.currentText()
        offset = res["offset"]

        target = self.project.get_series(sample_name)
        if ref_name == "__master__":
            reference = build_master(self.project.series_list)
        else:
            reference = self.project.get_series(ref_name)
        if target is None or reference is None:
            ax.text(0.5, 0.5, "Missing data", ha="center", va="center")
            self.overlap_canvas.draw()
            return

        shifted_years = target.years + offset
        common_start = max(shifted_years[0], reference.years[0])
        common_end = min(shifted_years[-1], reference.years[-1])

        if common_start >= common_end:
            ax.text(0.5, 0.5, "No overlap", ha="center", va="center")
            self.overlap_canvas.draw()
            return

        mask_t = (shifted_years >= common_start) & (shifted_years <= common_end)
        mask_r = (reference.years >= common_start) & (reference.years <= common_end)

        common_yrs = shifted_years[mask_t]

        ax.plot(common_yrs, target.values[mask_t], label=sample_name, color="#1f77b4", linewidth=0.8)
        ax.plot(common_yrs, reference.values[mask_r], label=ref_name.replace("__master__", "Master"), color="#d62728", linewidth=0.8)
        ax.legend(fontsize=7)
        ax.set_xlabel("Year", fontsize=8)
        ax.set_ylabel("Ring width", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda v, _: "" if v == 0 else f"{v:.0f}")
        )
        self.overlap_canvas.draw()

    def _apply_offset(self):
        sel = self.table.currentRow()
        if sel < 0 or not self._results:
            return
        res = self._results[sel]
        offset = res["offset"]
        sample_name = res["sample"]

        target = self.project.get_series(sample_name)
        if target is None:
            QMessageBox.warning(self, "Error", f"Series '{sample_name}' not found.")
            return

        shifted_years = target.years + offset
        idx = self.project.series_list.index(target)
        new_series = Series(
            name=target.name,
            years=shifted_years,
            values=target.values.copy(),
            filename=target.filename,
        )
        self.project.series_list[idx] = new_series

        self.detail_label.setText(
            f"Applied: '{target.name}' shifted by offset {offset} "
            f"(new range: {new_series.start_year}–{new_series.end_year})"
        )

        # Remove applied results for this sample from the table
        kept = []
        for row_idx, r in enumerate(self._results):
            if r["sample"] == sample_name:
                continue
            kept.append(r)
        self._results = kept
        self.table.setRowCount(0)
        for row_idx, r in enumerate(self._results):
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(r["sample"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(r["offset"])))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(r["overlap"])))
            self.table.setItem(row_idx, 3, QTableWidgetItem(f"{r['r']:.4f}"))
            tv = r["t"]
            self.table.setItem(row_idx, 4, QTableWidgetItem(f"{tv:.2f}" if tv is not None else "N/A"))
            pv = r.get("p")
            self.table.setItem(row_idx, 5, QTableWidgetItem(f"{pv:.4f}" if pv is not None else "N/A"))
            self.table.setItem(row_idx, 6, QTableWidgetItem(f"{r['glk']:.1f}"))
            note = ""
            if r["offset"] == 0:
                note = "current position"
            self.table.setItem(row_idx, 7, QTableWidgetItem(note))
            self.table.setItem(row_idx, 8, QTableWidgetItem(""))

        if not self._results:
            self.btn_apply.setEnabled(False)
            self.detail_label.setText("All samples applied. Close the dialog.")


class SeriesInfoDialog(QDialog):
    def __init__(self, series: Series, project: Project, parent=None):
        super().__init__(parent)
        self.series = series
        self.project = project
        self.setWindowTitle(f"Series Info — {series.name}")
        self.resize(600, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        txt = (
            f"Name: {self.series.name}\n"
            f"File: {self.series.filename}\n"
            f"Span: {self.series.start_year} – {self.series.end_year}\n"
            f"Length: {self.series.length} years\n"
            f"Mean: {self.series.values.mean():.3f}\n"
            f"Std Dev: {self.series.values.std():.3f}\n"
            f"Min: {self.series.values.min():.3f}\n"
            f"Max: {self.series.values.max():.3f}\n"
        )

        lbl = QLabel(txt)
        lbl.setFont(self.font())
        layout.addWidget(lbl)

        # Compare with all other series
        title = QLabel("<b>Correlations with other series:</b>")
        layout.addWidget(title)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Series", "Overlap", "r", "GLK (%)"])
        row = 0
        for s in self.project.series_list:
            if s.name == self.series.name:
                continue
            common_yrs = min(self.series.end_year, s.end_year) - max(self.series.start_year, s.start_year) + 1
            if common_yrs < 2:
                continue

            r_val = pearson_r(self.series, s)
            glk_val = gleichlaeufigkeit(self.series, s)

            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(s.name))
            table.setItem(row, 1, QTableWidgetItem(str(common_yrs)))
            table.setItem(row, 2, QTableWidgetItem(f"{r_val:.4f}" if r_val else "N/A"))
            table.setItem(row, 3, QTableWidgetItem(f"{glk_val:.1f}" if glk_val else "N/A"))
            row += 1

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(table)


class BuildMasterDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Build Master Chronology")
        self.resize(400, 300)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        lbl = QLabel("Select series to include in the master:")
        layout.addWidget(lbl)

        self.checkboxes = []
        for s in self.project.series_list:
            cb = QCheckBox(s.name)
            cb.setChecked(True)
            self.checkboxes.append(cb)
            layout.addWidget(cb)

        self.spin_overlap = QSpinBox()
        self.spin_overlap.setRange(1, 50)
        self.spin_overlap.setValue(2)
        self.spin_overlap.setPrefix("Min series per year: ")
        layout.addWidget(self.spin_overlap)

        btn = QPushButton("Build Master")
        btn.clicked.connect(self._build)
        layout.addWidget(btn)

    def _build(self):
        selected = []
        for cb in self.checkboxes:
            if cb.isChecked():
                s = self.project.get_series(cb.text())
                if s:
                    selected.append(s)

        if not selected:
            QMessageBox.warning(self, "Error", "No series selected.")
            return

        master = build_master(selected, min_overlap=self.spin_overlap.value())
        if master is None:
            QMessageBox.warning(self, "Error", "Could not build master (no overlapping years).")
            return

        self.project.add_series(master)
        QMessageBox.information(
            self, "Done",
            f"Master chronology created: {master.start_year} – {master.end_year} "
            f"({master.length} years)"
        )
        self.accept()


class DetrendDialog(QDialog):
    FIT_MAP = {
        "Spline (default)": "spline",
        "Modified Negative Exponential": "ModNegex",
        "Hugershoff": "Hugershoff",
        "Linear": "linear",
        "Horizontal": "horizontal",
    }

    def __init__(self, project: "Project", parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Detrend / Index")
        self.resize(500, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Series selection
        lbl = QLabel("Select series to detrend:")
        layout.addWidget(lbl)

        self.series_checkboxes: list[QCheckBox] = []
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(150)
        cw = QWidget()
        cbl = QVBoxLayout(cw)
        cbl.setContentsMargins(0, 0, 0, 0)
        for s in self.project.series_list:
            cb = QCheckBox(s.name)
            cb.setChecked(s.has_indices() is False)
            self.series_checkboxes.append(cb)
            cbl.addWidget(cb)
        cbl.addStretch()
        scroll.setWidget(cw)
        layout.addWidget(scroll)

        # Fit method
        fit_group = QGroupBox("Fit method")
        fit_layout = QVBoxLayout(fit_group)
        self.fit_buttons = QButtonGroup(self)
        fit_names = list(self.FIT_MAP.keys())
        for i, name in enumerate(fit_names):
            rb = QRadioButton(name)
            if i == 0:
                rb.setChecked(True)
            self.fit_buttons.addButton(rb, i)
            fit_layout.addWidget(rb)
        layout.addWidget(fit_group)

        # Method type
        method_group = QGroupBox("Detrending method")
        method_layout = QVBoxLayout(method_group)
        self.method_buttons = QButtonGroup(self)
        rb_res = QRadioButton("Residual (indices = observed / fitted) — centered ~1.0")
        rb_res.setChecked(True)
        rb_diff = QRadioButton("Difference (indices = observed - fitted)")
        self.method_buttons.addButton(rb_res, 0)
        self.method_buttons.addButton(rb_diff, 1)
        method_layout.addWidget(rb_res)
        method_layout.addWidget(rb_diff)
        layout.addWidget(method_group)

        # Period
        period_layout = QHBoxLayout()
        period_layout.addWidget(QLabel("Spline period (years, 0 = auto):"))
        self.spin_period = QSpinBox()
        self.spin_period.setRange(0, 1000)
        self.spin_period.setValue(0)
        self.spin_period.setSpecialValueText("Auto")
        period_layout.addWidget(self.spin_period)
        period_layout.addStretch()
        layout.addLayout(period_layout)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("Detrend")
        self.btn_run.clicked.connect(self._run)
        btn_layout.addWidget(self.btn_run)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _run(self):
        selected = []
        for cb in self.series_checkboxes:
            if cb.isChecked():
                s = self.project.get_series(cb.text())
                if s:
                    selected.append(s)

        if not selected:
            QMessageBox.warning(self, "Error", "Select at least one series.")
            return

        fit_key = list(self.FIT_MAP.keys())[self.fit_buttons.checkedId()]
        fit = self.FIT_MAP[fit_key]
        method = "residual" if self.method_buttons.checkedId() == 0 else "difference"
        period = self.spin_period.value() or None

        import dplpy

        for series in selected:
            s = pd.Series(series.values, index=series.years, name=series.name)
            try:
                result = dplpy.detrend(s, fit=fit, method=method, plot=False, period=period)
                if result is not None and isinstance(result, pd.Series):
                    series.indices = result.values
                else:
                    series.indices = series.values.copy()
                series.detrend_method = f"{fit}-{method}"
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Detrend failed for '{series.name}': {e}"
                )
                continue

        QMessageBox.information(
            self, "Done",
            f"Detrended {len(selected)} series.\n"
            "Toggle 'Show Indices' in View menu to display detrended data."
        )
        self.accept()
