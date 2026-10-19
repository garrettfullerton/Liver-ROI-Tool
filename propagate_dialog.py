from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QTabWidget, QWidget,
                             QDoubleSpinBox, QAbstractItemView, QProgressDialog,
                             QMessageBox, QApplication)
from PyQt5.QtCore import Qt

ORIENTATION_NAMES = {1: "Sagittal", 2: "Coronal", 3: "Axial"}


class PropagateROIsDialog(QDialog):
    """Copy ROIs from the current series to other series in the exam, or into the current series"""

    def __init__(self, parent, dicom_model, roi_manager):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        self.current_path = dicom_model.get_current_series_path()

        self.setWindowTitle("Copy / Propagate ROIs")
        self.setMinimumSize(600, 500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_push_tab(), "Propagate to other series")
        self.tabs.addTab(self._build_pull_tab(), "Copy into current series")
        layout.addWidget(self.tabs)

        # Maximum distance between ROI center and target slice
        distance_layout = QHBoxLayout()
        distance_layout.addWidget(QLabel("Max distance from ROI to target slice (mm):"))
        self.distance_input = QDoubleSpinBox()
        self.distance_input.setRange(0.1, 50.0)
        self.distance_input.setSingleStep(0.5)
        self.distance_input.setValue(5.0)
        distance_layout.addWidget(self.distance_input)
        distance_layout.addStretch()
        layout.addLayout(distance_layout)

        layout.addWidget(QLabel("Existing ROIs for the same segments in target series will be replaced."))

        # Buttons
        button_layout = QHBoxLayout()
        copy_button = QPushButton("Copy ROIs")
        cancel_button = QPushButton("Cancel")
        copy_button.clicked.connect(self.on_copy)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(copy_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        # Default to propagating when the current series has ROIs, otherwise to copying into it
        if not self._rois_in(self.current_path):
            self.tabs.setCurrentIndex(1)

    def _rois_in(self, series_path):
        return [roi for roi in self.roi_manager.rois if roi.series_path == series_path]

    def _series_text(self, series_path):
        """List entry text: label, orientation and existing ROI count"""
        meta = self.dicom_model.get_series_meta(series_path)
        text = self.dicom_model.get_series_label(series_path)
        orientation = ORIENTATION_NAMES.get(meta.get('Orientation'))
        if orientation:
            text += f"  [{orientation}]"
        n_rois = len(self._rois_in(series_path))
        if n_rois:
            text += f"  ({n_rois} ROIs)"
        return text

    def _build_push_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        n_rois = len(self._rois_in(self.current_path))
        layout.addWidget(QLabel(f"Source (current series): {self.dicom_model.get_series_label(self.current_path)} "
                                f"— {n_rois} ROIs"))
        layout.addWidget(QLabel("Target series in this exam:"))

        self.target_list = QListWidget()
        for series_path in self.dicom_model.get_exam_series(self.current_path):
            if series_path == self.current_path:
                continue
            item = QListWidgetItem(self._series_text(series_path))
            item.setData(Qt.UserRole, series_path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.target_list.addItem(item)
        # Clicking anywhere on a row toggles its checkbox
        self.target_list.itemClicked.connect(
            lambda item: item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked))
        layout.addWidget(self.target_list)

        select_layout = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_none = QPushButton("Select None")
        select_all.clicked.connect(lambda: self._set_all_checked(Qt.Checked))
        select_none.clicked.connect(lambda: self._set_all_checked(Qt.Unchecked))
        select_layout.addWidget(select_all)
        select_layout.addWidget(select_none)
        select_layout.addStretch()
        layout.addLayout(select_layout)
        return tab

    def _build_pull_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel(f"Target (current series): {self.dicom_model.get_series_label(self.current_path)}"))
        layout.addWidget(QLabel("Select a source series to copy ROIs from:"))

        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QAbstractItemView.SingleSelection)
        for series_path in self.roi_manager.get_series_with_rois():
            if series_path == self.current_path:
                continue
            item = QListWidgetItem(self._series_text(series_path))
            item.setData(Qt.UserRole, series_path)
            self.source_list.addItem(item)
        layout.addWidget(self.source_list)
        return tab

    def _set_all_checked(self, state):
        for i in range(self.target_list.count()):
            self.target_list.item(i).setCheckState(state)

    def on_copy(self):
        """Run the copy for the active tab and show a summary"""
        if self.tabs.currentIndex() == 0:
            targets = [self.target_list.item(i).data(Qt.UserRole) for i in range(self.target_list.count())
                       if self.target_list.item(i).checkState() == Qt.Checked]
            if not self._rois_in(self.current_path):
                QMessageBox.warning(self, "Copy ROIs", "The current series has no ROIs to propagate.")
                return
            if not targets:
                QMessageBox.warning(self, "Copy ROIs", "Select at least one target series.")
                return
            jobs = [(self.current_path, target) for target in targets]
        else:
            item = self.source_list.currentItem()
            if item is None:
                QMessageBox.warning(self, "Copy ROIs", "Select a source series.")
                return
            jobs = [(item.data(Qt.UserRole), self.current_path)]

        summary = self.run_jobs(jobs, self.distance_input.value())
        QMessageBox.information(self, "Copy ROIs", "\n".join(summary))
        self.accept()

    def run_jobs(self, jobs, max_distance_mm):
        """Copy ROIs for each (source, target) pair with a progress dialog; returns summary lines"""
        progress = QProgressDialog("Copying ROIs...", "Cancel", 0, len(jobs), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        summary = []
        for i, (source, target) in enumerate(jobs):
            if progress.wasCanceled():
                summary.append("Cancelled; remaining series were not copied.")
                break
            label = self.dicom_model.get_series_label(target)
            progress.setLabelText(f"Copying to {label} ({i + 1}/{len(jobs)})...")
            progress.setValue(i)
            QApplication.processEvents()

            result = self.roi_manager.copy_rois_from_series(source, target, max_distance_mm)
            line = f"{label}: {result['error']}" if result['error'] else f"{label}: {result['copied']} copied"
            if result['skipped']:
                line += "; skipped " + ", ".join(f"{n} ({reason})" for reason, n in result['skipped'].items())
            summary.append(line)

        progress.setValue(len(jobs))
        return summary
