import hashlib
import os

from PyQt5.QtCore import QObject, QTimer, QStandardPaths
from PyQt5.QtWidgets import QMessageBox

AUTOSAVE_DELAY_MS = 2000


class SessionManager(QObject):
    """Tracks unexported ROI changes, autosaves them per opened folder, and offers recovery"""

    def __init__(self, roi_manager, dicom_model, parent_widget):
        super().__init__()
        self.roi_manager = roi_manager
        self.dicom_model = dicom_model
        self.parent_widget = parent_widget
        self.root_dir = None
        self.auto_export_dir = None  # folder for automatic per-exam exports (None = off)

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(AUTOSAVE_DELAY_MS)
        self.autosave_timer.timeout.connect(self.autosave)

        roi_manager.rois_changed.connect(self.on_rois_changed)
        roi_manager.saved.connect(self.on_saved)

    def autosave_path(self):
        """Autosave file for the opened folder (in the user's app-data directory)"""
        if not self.root_dir:
            return None
        directory = os.path.join(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or
                                 os.path.expanduser("~/.liver_roi_tool"), "autosave")
        digest = hashlib.md5(os.path.abspath(self.root_dir).encode()).hexdigest()[:8]
        return os.path.join(directory, f"{os.path.basename(os.path.normpath(self.root_dir))}_{digest}.csv")

    @property
    def dirty(self):
        """True while some series have unexported ROI changes"""
        return bool(self.roi_manager.unsaved_series)

    def set_auto_export_dir(self, directory):
        """Enable automatic per-exam export to directory (None disables)"""
        self.auto_export_dir = directory or None
        if self.auto_export_dir and self.dirty:
            self.autosave_timer.start()

    def on_rois_changed(self):
        if self.dirty:
            self.autosave_timer.start()

    def on_saved(self):
        """ROIs were exported (or replaced from a file): nothing left to recover"""
        self.autosave_timer.stop()
        self.remove_autosave()

    def flush(self):
        """Run a pending autosave/auto-export immediately"""
        if self.autosave_timer.isActive():
            self.autosave_timer.stop()
            self.autosave()

    def auto_export(self):
        """Write each exam with unexported changes to '<PatientID>_<StudyID>_<scheme>_ROIs.csv' in the auto-export folder"""
        exams = {}
        for series_path in self.roi_manager.unsaved_series:
            exams.setdefault(self.dicom_model.get_exam_key(series_path), set()).add(series_path)

        for exam_series in exams.values():
            # Export the whole exam, not just the changed series
            exam_key = self.dicom_model.get_exam_key(next(iter(exam_series)))
            exam_paths = {roi.series_path for roi in self.roi_manager.rois
                          if self.dicom_model.get_exam_key(roi.series_path) == exam_key} | exam_series
            filename = os.path.join(self.auto_export_dir, self.roi_manager.default_export_name(exam_paths))
            try:
                os.makedirs(self.auto_export_dir, exist_ok=True)
                self.roi_manager.write_csv(filename, exam_paths)
                self.roi_manager.mark_saved(exam_paths)
            except OSError as e:
                self.roi_manager.message.emit(f"Auto-export failed: {e}", True)
                return

    def autosave(self):
        if self.auto_export_dir and self.dirty:
            self.auto_export()

        path = self.autosave_path()
        if not path or not self.dirty:
            return
        if not self.roi_manager.rois:
            self.remove_autosave()
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.roi_manager.write_csv(path)
        except OSError as e:
            print(f"Autosave failed: {e}")

    def remove_autosave(self):
        path = self.autosave_path()
        if path and os.path.exists(path):
            os.remove(path)

    def on_folder_opened(self, root_dir):
        """Offer to restore unexported ROIs autosaved for this folder"""
        # Save pending changes for the previous folder before switching
        self.flush()

        self.root_dir = root_dir
        path = self.autosave_path()
        if not path or not os.path.exists(path):
            return

        answer = QMessageBox.question(
            self.parent_widget, "Restore ROIs",
            "Unexported ROIs from a previous session were found for this folder. Restore them?")
        if answer == QMessageBox.Yes:
            self.roi_manager.import_rois(path, mode="merge")
        else:
            self.remove_autosave()

    def confirm_close(self):
        """Ask before closing with unexported ROIs; returns True if the window may close"""
        self.flush()
        if not self.dirty or not self.roi_manager.rois:
            return True

        box = QMessageBox(QMessageBox.Warning, "Unexported ROIs",
                          f"There are {len(self.roi_manager.rois)} ROIs with changes that have not been exported.",
                          parent=self.parent_widget)
        export_button = box.addButton("Export...", QMessageBox.AcceptRole)
        discard_button = box.addButton("Close Without Exporting", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()

        if box.clickedButton() == export_button:
            return self.roi_manager.export_rois()
        if box.clickedButton() == discard_button:
            self.autosave_timer.stop()
            self.remove_autosave()
            return True
        return False
