from PyQt5.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QFileDialog, QDialog
from PyQt5.QtCore import Qt, pyqtSlot

from dicom_image_renderer import DicomImageRenderer
from series_navigator_panel import SeriesNavigatorPanel
from image_viewer_panel import ImageViewerPanel
from control_panel import ControlPanel
from statistics_panel import StatisticsPanel

class DicomViewerApp(QMainWindow):
    """Main application class that orchestrates components"""
    def __init__(self, dicom_model, roi_manager):
        super().__init__()
        
        # Store references to core components
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        
        # Set window properties
        self.setWindowTitle("Liver MRI Viewer")
        self.setGeometry(100, 100, 1400, 800)
        
        # Initialize UI components
        self.setup_ui()
        
        # Connect signals between components
        self.connect_signals()
    
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
            self.central_widget, self.dicom_model
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
        self.main_layout.addWidget(self.control_panel, 1)
        
        # Stats panel can be in control panel or separate
        self.control_panel.layout.addWidget(self.stats_panel)
    
    def connect_signals(self):
        """Connect signals between components"""
        # Connect navigator panel signals
        self.navigator_panel.series_selected.connect(self.dicom_model.load_series)
        self.navigator_panel.copy_rois_requested.connect(self.show_copy_rois_dialog)
        
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
        
        # Connect control panel signals
        self.control_panel.window_level_changed.connect(self.renderer.set_window_level)
        self.control_panel.window_level_changed.connect(self.image_viewer.update_display)
        self.control_panel.segment_changed.connect(self.roi_manager.set_current_segment)
        self.control_panel.roi_drawing_toggled.connect(self.image_viewer.set_drawing_mode)
        self.control_panel.clear_last_roi_requested.connect(self.roi_manager.delete_last_roi)
        self.control_panel.clear_all_rois_requested.connect(self.roi_manager.clear_all_rois)
        self.control_panel.export_rois_requested.connect(self.roi_manager.export_rois)
        self.control_panel.show_stats_requested.connect(self.stats_panel.show_detailed_statistics)

        self.image_viewer.window_level_changed.connect(self.control_panel.update_window_level)
    
    def on_series_loaded(self):
        window = int(round(self.dicom_model.default_window))
        level = int(round(self.dicom_model.default_level))

        self.renderer.set_window_level(window, level)
        self.control_panel.update_window_level(window, level)

        self.image_viewer.update_display()

    @pyqtSlot()
    def show_copy_rois_dialog(self):
        """Show dialog to copy ROIs from another series"""
        self.roi_manager.show_copy_dialog(self)