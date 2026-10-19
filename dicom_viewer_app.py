from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout,
                             QApplication, QAbstractSpinBox, QLineEdit, QMessageBox, QLabel,
                             QShortcut, QScrollArea)
from PyQt5.QtCore import Qt, QEvent, pyqtSlot
from PyQt5.QtGui import QKeySequence

from dicom_image_renderer import DicomImageRenderer
from series_navigator_panel import SeriesNavigatorPanel
from image_viewer_panel import ImageViewerPanel
from control_panel import ControlPanel
from statistics_panel import StatisticsPanel
from propagate_dialog import PropagateROIsDialog
from session_manager import SessionManager
from info_dialog import InfoDialog
from app_config import get_settings

class DicomViewerApp(QMainWindow):
    """Main application class that orchestrates components"""
    def __init__(self, dicom_model, roi_manager):
        super().__init__()
        
        # Store references to core components
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        
        # Set window properties
        self.setWindowTitle("Liver ROI Tool")
        self.setGeometry(100, 100, 1400, 800)
        
        # Initialize UI components
        self.setup_ui()
        
        # Connect signals between components
        self.connect_signals()

        # Apply remembered settings (fixed ROI size, reader initials, auto-export folder)
        self.control_panel.on_fixed_size_changed()
        self.control_panel.on_reader_changed(self.control_panel.reader_input.text())
        self.control_panel.on_auto_export_toggled()

        # Route arrow keys to slice navigation regardless of which widget has focus
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        """Navigate slices with arrow keys unless a text/number field is being edited"""
        if event.type() == QEvent.KeyPress and self.isActiveWindow():
            key = event.key()
            if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
                if not isinstance(QApplication.focusWidget(), (QAbstractSpinBox, QLineEdit)):
                    if event.modifiers() & Qt.ControlModifier and key in (Qt.Key_Up, Qt.Key_Down):
                        # Ctrl+Up/Down: previous/next series
                        self.step_series(-1 if key == Qt.Key_Up else 1)
                    elif key in (Qt.Key_Up, Qt.Key_Left):
                        self.dicom_model.previous_slice()
                    else:
                        self.dicom_model.next_slice()
                    return True
        return super().eventFilter(obj, event)

    def setup_ui(self):
        """Initialize and layout UI components"""
        # Main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # Create renderer
        self.renderer = DicomImageRenderer(
            self.central_widget, self.dicom_model, self.roi_manager
            )
        
        # Create UI panels
        self.navigator_panel = SeriesNavigatorPanel(
            self.central_widget, self.dicom_model, self.roi_manager
        )
        
        self.image_viewer = ImageViewerPanel(
            self.central_widget, self.dicom_model, self.roi_manager, self.renderer
        )
        
        self.control_panel = ControlPanel(
            self.central_widget, self.dicom_model, self.roi_manager, self.renderer
        )
        
        self.stats_panel = StatisticsPanel(
            self.central_widget, self.dicom_model, self.roi_manager
        )
        
        # Set up UI for each panel
        self.navigator_panel.setup_ui()
        self.image_viewer.setup_ui()
        self.control_panel.setup_ui()
        self.stats_panel.setup_ui()
        
        # Add panels to main layout
        self.main_layout.addWidget(self.navigator_panel, 1)
        self.main_layout.addWidget(self.image_viewer, 3)
        # Controls scroll vertically so the window fits on smaller screens
        self.control_scroll = QScrollArea()
        self.control_scroll.setWidget(self.control_panel)
        self.control_scroll.setWidgetResizable(True)
        self.control_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.control_scroll.setFrameShape(QScrollArea.NoFrame)
        self.control_scroll.setMinimumWidth(self.control_panel.minimumSizeHint().width()
                                            + self.control_scroll.verticalScrollBar().sizeHint().width())
        self.main_layout.addWidget(self.control_scroll, 1)
        
        # Stats panel can be in control panel or separate
        self.control_panel.layout.addWidget(self.stats_panel)

        # Status bar for import/export/copy results, with a permanent cursor readout
        self.cursor_label = QLabel()
        self.statusBar().addPermanentWidget(self.cursor_label)

        # Autosave / unexported-changes tracking
        self.session_manager = SessionManager(self.roi_manager, self.dicom_model, self)

        # Restore window geometry and fixed-size ROI setting
        geometry = get_settings().value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
    
    def connect_signals(self):
        """Connect signals between components"""
        # Connect navigator panel signals
        self.navigator_panel.series_selected.connect(self.dicom_model.load_series)
        self.navigator_panel.copy_rois_requested.connect(self.show_copy_rois_dialog)
        self.navigator_panel.folder_opened.connect(self.session_manager.on_folder_opened)
        self.navigator_panel.info_requested.connect(self.show_info_dialog)
        QShortcut(QKeySequence("F1"), self, activated=self.show_info_dialog)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.image_viewer.toggle_lock)
        QShortcut(QKeySequence("PgUp"), self, activated=lambda: self.step_series(-1))
        QShortcut(QKeySequence("PgDown"), self, activated=lambda: self.step_series(1))
        QShortcut(QKeySequence("Ctrl+PgUp"), self, activated=lambda: self.step_exam(-1))
        QShortcut(QKeySequence("Ctrl+PgDown"), self, activated=lambda: self.step_exam(1))
        QShortcut(QKeySequence("Ctrl+J"), self, activated=self.go_to_next_incomplete)
        self.navigator_panel.exam_step_requested.connect(self.step_exam)
        self.navigator_panel.next_incomplete_requested.connect(self.go_to_next_incomplete)
        self.navigator_panel.folder_opened.connect(lambda _: self.update_exam_label())
        self.dicom_model.series_loaded.connect(self.update_exam_label)
        self.dicom_model.series_loaded.connect(self.image_viewer.update_lock_state)
        self.roi_manager.rois_changed.connect(self.image_viewer.update_lock_state)
        self.roi_manager.schemes_updated.connect(self.control_panel.rebuild_scheme_radios)
        self.control_panel.auto_export_changed.connect(self.session_manager.set_auto_export_dir)
        
        # Connect model signals
        self.dicom_model.series_loaded.connect(self.image_viewer.update_display)
        self.dicom_model.series_loaded.connect(self.stats_panel.update_statistics)
        self.dicom_model.series_loaded.connect(self.on_series_loaded)
        self.dicom_model.series_loaded.connect(self.image_viewer.update_series_label)
        self.dicom_model.slice_changed.connect(self.image_viewer.update_display)
        self.dicom_model.slice_changed.connect(self.stats_panel.update_statistics)
        
        # Connect ROI manager signals
        self.roi_manager.rois_changed.connect(self.image_viewer.update_display)
        self.roi_manager.rois_changed.connect(self.stats_panel.update_statistics)
        self.roi_manager.scheme_changed.connect(self.control_panel.on_manager_scheme_changed)
        self.roi_manager.message.connect(self.show_message)
        self.roi_manager.rois_changed.connect(self.navigator_panel.update_series_status)
        self.dicom_model.series_loaded.connect(self.navigator_panel.update_series_status)
        self.roi_manager.rois_changed.connect(self.control_panel.update_segment_status)
        self.dicom_model.series_loaded.connect(self.control_panel.update_segment_status)
        self.roi_manager.scheme_changed.connect(self.stats_panel.update_statistics)
        self.roi_manager.scheme_changed.connect(self.navigator_panel.update_series_status)
        
        # Connect control panel signals
        self.control_panel.window_level_changed.connect(self.renderer.set_window_level)
        self.control_panel.window_level_changed.connect(self.image_viewer.update_display)
        self.control_panel.segment_changed.connect(self.roi_manager.set_current_segment)
        self.control_panel.roi_drawing_toggled.connect(self.image_viewer.set_drawing_mode)
        self.control_panel.clear_last_roi_requested.connect(self.roi_manager.delete_last_roi)
        self.control_panel.clear_all_rois_requested.connect(self.roi_manager.clear_all_rois)
        self.control_panel.export_rois_requested.connect(self.roi_manager.export_rois)
        self.control_panel.show_stats_requested.connect(self.stats_panel.show_detailed_statistics)
        self.control_panel.import_rois_requested.connect(self.roi_manager.import_rois)
        self.control_panel.export_summary_requested.connect(self.roi_manager.export_wide)
        self.control_panel.fixed_size_changed.connect(self.image_viewer.set_fixed_diameter)

        self.image_viewer.cursor_info_changed.connect(self.cursor_label.setText)
        self.dicom_model.series_loaded.connect(self.image_viewer.reset_view)

        self.image_viewer.window_level_changed.connect(self.control_panel.update_window_level)


    
    def on_series_loaded(self):
        window = int(round(self.dicom_model.default_window))
        level = int(round(self.dicom_model.default_level))

        # Size window/level ranges to the data (at least the previous fixed 4000 / +-2000)
        value_min, value_max = self.dicom_model.get_value_range()
        span = max(value_max - value_min, 1)
        window_max = int(max(4000, 2 * span, window))
        level_min = int(min(-2000, value_min - span, level))
        level_max = int(max(2000, value_max + span, level))
        self.renderer.set_window_level_limits(window_max, level_min, level_max, max(3, span / 300))
        self.control_panel.set_window_level_limits(window_max, level_min, level_max)

        self.renderer.set_window_level(window, level)
        self.control_panel.update_window_level(window, level)

        self.image_viewer.update_display()

    def closeEvent(self, event):
        """Warn about unexported ROIs and remember window geometry"""
        if not self.session_manager.confirm_close():
            event.ignore()
            return
        get_settings().setValue("geometry", self.saveGeometry())
        event.accept()

    def show_message(self, text, is_error=False):
        """Show a message in the status bar; errors also get a warning dialog"""
        self.statusBar().showMessage(text, 15000)
        if is_error:
            QMessageBox.warning(self, "Liver ROI Tool", text)

    def step_series(self, step):
        """Load the previous (-1) or next (+1) series in tree order"""
        paths = self.navigator_panel.ordered_series_paths()
        if not paths:
            return
        current = self.dicom_model.current_series_path
        index = paths.index(current) + step if current in paths else 0
        if 0 <= index < len(paths):
            self.navigator_panel.select_series(paths[index])

    def is_incomplete(self, series_path):
        """Unlocked series missing at least one segment of the current scheme"""
        done = {roi.segment for roi in self.roi_manager.rois if roi.series_path == series_path}
        return len(done) < len(self.roi_manager.segment_labels) and not self.roi_manager.is_locked(series_path)

    def go_to_next_incomplete(self):
        """Jump to the next incomplete series after the current one (wrapping around)"""
        paths = self.navigator_panel.ordered_series_paths()
        current = self.dicom_model.current_series_path
        start = paths.index(current) + 1 if current in paths else 0
        for series_path in paths[start:] + paths[:start]:
            if series_path != current and self.is_incomplete(series_path):
                self.navigator_panel.select_series(series_path)
                return
        self.show_message("No other incomplete series (all have every segment, or are locked)")

    def exams_in_order(self):
        """{exam key: [series paths]} in tree order"""
        exams = {}
        for series_path in self.navigator_panel.ordered_series_paths():
            exams.setdefault(self.dicom_model.get_exam_key(series_path), []).append(series_path)
        return exams

    def update_exam_label(self):
        """Show 'Exam i/N: <patient / exam>' in the navigator"""
        exams = self.exams_in_order()
        current = self.dicom_model.current_series_path
        if not exams:
            self.navigator_panel.set_exam_label("No exam")
        elif current is None:
            self.navigator_panel.set_exam_label(f"{len(exams)} exams — press ▶ to start")
        else:
            index = list(exams).index(self.dicom_model.get_exam_key(current)) + 1 \
                if self.dicom_model.get_exam_key(current) in exams else 0
            self.navigator_panel.set_exam_label(f"Exam {index}/{len(exams)}: {self.dicom_model.get_exam_label(current)}")

    def step_exam(self, step):
        """Move to the first series of the previous (-1) / next (+1) exam, offering to export the current one"""
        exams = self.exams_in_order()
        keys = list(exams)
        if not keys:
            return
        current = self.dicom_model.current_series_path
        if current is None or self.dicom_model.get_exam_key(current) not in exams:
            self.navigator_panel.select_series(exams[keys[0]][0])
            return

        current_key = self.dicom_model.get_exam_key(current)
        index = keys.index(current_key) + step
        if not 0 <= index < len(keys):
            self.show_message("This is the " + ("first" if step < 0 else "last") + " exam")
            return
        if not self.confirm_leave_exam(exams[current_key]):
            return
        self.navigator_panel.select_series(exams[keys[index]][0])

    def confirm_leave_exam(self, exam_paths):
        """Before leaving an exam with unexported changes, offer to export it; returns False to stay"""
        self.session_manager.flush()  # auto-export, if enabled, runs now
        exam_paths = set(exam_paths)
        if not (self.roi_manager.unsaved_series & exam_paths):
            return True

        box = QMessageBox(QMessageBox.Question, "Export Exam",
                          f"{self.dicom_model.get_exam_label(next(iter(exam_paths)))} has ROI changes "
                          "that have not been exported.", parent=self)
        export_button = box.addButton("Export Exam...", QMessageBox.AcceptRole)
        continue_button = box.addButton("Continue Without Exporting", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        if box.clickedButton() == export_button:
            return self.roi_manager.export_rois(series_paths=exam_paths)
        return box.clickedButton() == continue_button

    def show_info_dialog(self):
        """Show features, keyboard shortcuts and mouse controls"""
        InfoDialog(self).exec_()

    @pyqtSlot()
    def show_copy_rois_dialog(self):
        """Show dialog to copy ROIs between series"""
        if not self.dicom_model.current_series:
            return
        PropagateROIsDialog(self, self.dicom_model, self.roi_manager).exec_()