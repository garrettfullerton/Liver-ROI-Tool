import hashlib
import os

from PyQt5.QtCore import QObject, QTimer, QStandardPaths
from PyQt5.QtWidgets import QMessageBox

AUTOSAVE_DELAY_MS = 2000


class SessionManager(QObject):
    """Tracks unexported ROI changes, autosaves them per opened folder, and offers recovery"""

    def __init__(self, roi_manager, parent_widget):
        super().__init__()
        self.roi_manager = roi_manager
        self.parent_widget = parent_widget
        self.root_dir = None
        self.dirty = False

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

    def on_rois_changed(self):
        self.dirty = True
        self.autosave_timer.start()

    def on_saved(self):
        """ROIs were exported (or replaced from a file): nothing left to recover"""
        self.dirty = False
        self.autosave_timer.stop()
        self.remove_autosave()

    def autosave(self):
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
        if self.autosave_timer.isActive():
            self.autosave_timer.stop()
            self.autosave()

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
