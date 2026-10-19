from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QFileDialog, QDialog,
                             QApplication, QAbstractSpinBox, QLineEdit, QMessageBox, QLabel,
                             QShortcut)
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

# from ai_panel import AIControlPanel
# from ai_model_manager import AIModelManager

class DicomViewerApp(QMainWindow):
    """Main application class that orchestrates components"""
    def __init__(self, dicom_model, roi_manager, ai_model_manager):
        super().__init__()
        
        # Store references to core components
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        # self.ai_model_manager = ai_model_manager()
        
        # Set window properties
        self.setWindowTitle("Liver MRI Viewer")
        self.setGeometry(100, 100, 1400, 800)
        
        # Initialize UI components
        self.setup_ui()
        
        # Connect signals between components
        self.connect_signals()

        # Apply the remembered fixed-size ROI setting
        self.control_panel.on_fixed_size_changed()

        # Route arrow keys to slice navigation regardless of which widget has focus
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        """Navigate slices with arrow keys unless a text/number field is being edited"""
        if event.type() == QEvent.KeyPress and self.isActiveWindow():
            key = event.key()
            if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
                if not isinstance(QApplication.focusWidget(), (QAbstractSpinBox, QLineEdit)):
                    if key in (Qt.Key_Up, Qt.Key_Left):
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

        # self.ai_panel = AIControlPanel(
        #     self.central_widget, self.dicom_model, self.roi_manager, self.ai_model_manager
        # )
        
        # Set up UI for each panel
        self.navigator_panel.setup_ui()
        self.image_viewer.setup_ui()
        self.control_panel.setup_ui()
        self.stats_panel.setup_ui()
        # self.ai_panel.setup_ui()
        
        # Add panels to main layout
        self.main_layout.addWidget(self.navigator_panel, 1)
        self.main_layout.addWidget(self.image_viewer, 3)
        self.main_layout.addWidget(self.control_panel, 1)
        # self.main_layout.addWidget(self.ai_panel, 1)
        
        # Stats panel can be in control panel or separate
        self.control_panel.layout.addWidget(self.stats_panel)

        # Status bar for import/export/copy results, with a permanent cursor readout
        self.cursor_label = QLabel()
        self.statusBar().addPermanentWidget(self.cursor_label)

        # Autosave / unexported-changes tracking
        self.session_manager = SessionManager(self.roi_manager, self)

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

        # Connect AI panel signals
        # self.ai_panel.model_loaded.connect(self.ai_model_manager.load_model)
        # self.ai_panel.predict_rois_requested.connect(self.ai_model_manager.predict_rois)


    
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

    def show_info_dialog(self):
        """Show features, keyboard shortcuts and mouse controls"""
        InfoDialog(self).exec_()

    @pyqtSlot()
    def show_copy_rois_dialog(self):
        """Show dialog to copy ROIs between series"""
        if not self.dicom_model.current_series:
            return
        PropagateROIsDialog(self, self.dicom_model, self.roi_manager).exec_()