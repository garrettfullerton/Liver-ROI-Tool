# control_panel.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                            QGroupBox, QLabel, QSlider, QSpinBox, QRadioButton,
                            QButtonGroup, QPushButton)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence

class ControlPanel(QWidget):
    """UI panel for controls (windowing, ROI drawing, segments)"""
    # Define signals
    window_level_changed = pyqtSignal(int, int)  # window, level
    segment_changed = pyqtSignal(int)  # segment number
    roi_drawing_toggled = pyqtSignal(bool)  # drawing enabled
    clear_last_roi_requested = pyqtSignal()
    clear_all_rois_requested = pyqtSignal()
    export_rois_requested = pyqtSignal()
    show_stats_requested = pyqtSignal()
    
    def __init__(self, parent, dicom_model, roi_manager, renderer):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        self.renderer = renderer
    
    def setup_ui(self):
        """Set up UI components for controls"""
        self.layout = QVBoxLayout(self)
        
        # Window/Level controls with both sliders and input boxes
        self.wl_group = QGroupBox("Window/Level")
        self.wl_layout = QGridLayout()
        
        # Window controls
        self.window_label = QLabel("Window:")
        self.window_slider = QSlider(Qt.Horizontal)
        self.window_slider.setRange(1, 4000)
        self.window_slider.setValue(2000)
        self.window_slider.valueChanged.connect(self.on_window_slider_changed)
        
        self.window_input = QSpinBox()
        self.window_input.setRange(1, 4000)
        self.window_input.setValue(2000)
        self.window_input.editingFinished.connect(self.on_window_input_changed)
        
        # Level controls
        self.level_label = QLabel("Level:")
        self.level_slider = QSlider(Qt.Horizontal)
        self.level_slider.setRange(-2000, 2000)
        self.level_slider.setValue(0)
        self.level_slider.valueChanged.connect(self.on_level_slider_changed)
        
        self.level_input = QSpinBox()
        self.level_input.setRange(-2000, 2000)
        self.level_input.setValue(0)
        self.level_input.editingFinished.connect(self.on_level_input_changed)
        
        # Add widgets to grid layout
        self.wl_layout.addWidget(self.window_label, 0, 0)
        self.wl_layout.addWidget(self.window_slider, 0, 1)
        self.wl_layout.addWidget(self.window_input, 0, 2)
        self.wl_layout.addWidget(self.level_label, 1, 0)
        self.wl_layout.addWidget(self.level_slider, 1, 1)
        self.wl_layout.addWidget(self.level_input, 1, 2)
        
        self.wl_group.setLayout(self.wl_layout)
        self.layout.addWidget(self.wl_group)
        
        # Segmentation scheme selection
        self.scheme_group = QGroupBox("Segmentation Scheme")
        self.scheme_layout = QVBoxLayout()
        self.scheme_buttons = QButtonGroup()
        
        self.nine_segment_radio = QRadioButton("9-Segment")
        self.nine_segment_radio.setChecked(True)
        self.four_segment_radio = QRadioButton("4-Segment")
        
        self.scheme_buttons.addButton(self.nine_segment_radio, 9)
        self.scheme_buttons.addButton(self.four_segment_radio, 4)
        self.scheme_buttons.buttonClicked.connect(self.on_scheme_changed)
        
        self.scheme_layout.addWidget(self.nine_segment_radio)
        self.scheme_layout.addWidget(self.four_segment_radio)
        self.scheme_group.setLayout(self.scheme_layout)
        self.layout.addWidget(self.scheme_group)
        
        # Segment selection
        self.segment_group = QGroupBox("Liver Segment")
        self.segment_layout = QGridLayout()
        
        # Create segment buttons for 9-segment scheme
        self.segment_buttons = {}
        segments_9 = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        segment_labels = ["1", "2", "3", "4a", "4b", "5", "6", "7", "8"]
        self.roi_manager.segment_labels = segment_labels
        row, col = 0, 0
        for segment in segments_9:
            btn = QPushButton(f"Segment {segment_labels[segment-1]}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=segment: self.on_segment_selected(s))
            
            if segment < 10:
                # Create shortcut using the number key (1-9)
                btn.setShortcut(QKeySequence(f"Ctrl+{segment}"))

            self.segment_buttons[segment] = btn
            self.segment_layout.addWidget(btn, row, col)
            col += 1
            if col > 2:  # 3 columns layout
                col = 0
                row += 1
        
        self.segment_group.setLayout(self.segment_layout)
        self.layout.addWidget(self.segment_group)
        
        # ROI Controls
        self.roi_group = QGroupBox("ROI Controls")
        self.roi_layout = QVBoxLayout()
        
        self.draw_roi_button = QPushButton("Draw Circular ROI")
        self.draw_roi_button.setCheckable(True)
        self.draw_roi_button.toggled.connect(self.on_roi_drawing_toggled)

        # draw ROI shortcut ("e" key)
        self.draw_roi_button.setShortcut("e")
        
        self.clear_last_roi_button = QPushButton("Clear Last ROI")
        self.clear_last_roi_button.clicked.connect(self.on_clear_last_roi)
        
        self.clear_all_rois_button = QPushButton("Clear All ROIs")
        self.clear_all_rois_button.clicked.connect(self.on_clear_all_rois)
        
        self.export_rois_button = QPushButton("Export ROIs")
        self.export_rois_button.clicked.connect(self.on_export_rois)
        self.export_rois_button.setShortcut(QKeySequence(f"Ctrl+s"))

        
        self.show_stats_button = QPushButton("Show ROI Statistics")
        self.show_stats_button.clicked.connect(self.on_show_stats)

        
        self.roi_layout.addWidget(self.draw_roi_button)
        self.roi_layout.addWidget(self.clear_last_roi_button)
        self.roi_layout.addWidget(self.clear_all_rois_button)
        self.roi_layout.addWidget(self.export_rois_button)
        self.roi_layout.addWidget(self.show_stats_button)
        
        self.roi_group.setLayout(self.roi_layout)
        self.layout.addWidget(self.roi_group)

    def update_window_level(self, window, level):
        """Update window/level controls when changed from outside"""
        # Update inputs and sliders without triggering their signals
        self.window_input.blockSignals(True)
        self.window_slider.blockSignals(True)
        self.level_input.blockSignals(True)
        self.level_slider.blockSignals(True)
        
        self.window_input.setValue(window)
        self.window_slider.setValue(window)
        self.level_input.setValue(level)
        self.level_slider.setValue(level)
        
        self.window_input.blockSignals(False)
        self.window_slider.blockSignals(False)
        self.level_input.blockSignals(False)
        self.level_slider.blockSignals(False)
    
    def on_window_slider_changed(self):
        """Handle window slider value change"""
        window = self.window_slider.value()
        
        # Update input without triggering signals
        self.window_input.blockSignals(True)
        self.window_input.setValue(window)
        self.window_input.blockSignals(False)
        
        # Emit signal with new window/level values
        self.window_level_changed.emit(window, self.level_slider.value())
    
    def on_level_slider_changed(self):
        """Handle level slider value change"""
        level = self.level_slider.value()
        
        # Update input without triggering signals
        self.level_input.blockSignals(True)
        self.level_input.setValue(level)
        self.level_input.blockSignals(False)
        
        # Emit signal with new window/level values
        self.window_level_changed.emit(self.window_slider.value(), level)
    
    def on_window_input_changed(self):
        """Handle window input value change"""
        window = self.window_input.value()
        
        # Update slider without triggering signals
        self.window_slider.blockSignals(True)
        self.window_slider.setValue(window)
        self.window_slider.blockSignals(False)
        
        # Emit signal with new window/level values
        self.window_level_changed.emit(window, self.level_input.value())
    
    def on_level_input_changed(self):
        """Handle level input value change"""
        level = self.level_input.value()
        
        # Update slider without triggering signals
        self.level_slider.blockSignals(True)
        self.level_slider.setValue(level)
        self.level_slider.blockSignals(False)
        
        # Emit signal with new window/level values
        self.window_level_changed.emit(self.window_input.value(), level)
    
    def on_scheme_changed(self, button):
        """Handle segmentation scheme change"""
        scheme = self.scheme_buttons.id(button)
        
        # Clear existing segment buttons
        for i in reversed(range(self.segment_layout.count())): 
            self.segment_layout.itemAt(i).widget().setParent(None)
        
        self.segment_buttons = {}
        
        if scheme == 9:
            # 9-segment scheme
            self.roi_manager.set_segmentation_scheme("9-segment")
            segments = [1, 2, 3, 4, 5, 6, 7, 8, 9]
            segment_labels = ["1", "2", "3", "4a", "4b", "5", "6", "7", "8"]
            self.roi_manager.segment_labels = segment_labels
        else:
            # 4-segment scheme
            self.roi_manager.set_segmentation_scheme("4-segment")
            segments = [1, 2, 3, 4]
            segment_labels = ["1", "2", "3", "4"]
            self.roi_manager.segment_labels = segment_labels
        
        # Create new segment buttons
        row, col = 0, 0
        for segment in segments:
            btn = QPushButton(f"Segment {segment_labels[segment-1]}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=segment: self.on_segment_selected(s))
            
            if segment < 10:
                # Create shortcut using the number key (1-9)
                btn.setShortcut(QKeySequence(f"Ctrl+{segment}"))

            self.segment_buttons[segment] = btn
            self.segment_layout.addWidget(btn, row, col)
            col += 1
            if (col > 2 and scheme == 9) or (col > 1 and scheme == 4):
                col = 0
                row += 1
        
        # Select first segment
        self.on_segment_selected(segments[0])
    
    def on_segment_selected(self, segment):
        """Handle segment selection"""
        # Update UI
        for seg, button in self.segment_buttons.items():
            button.setChecked(seg == segment)
        
        # Emit signal with selected segment
        self.segment_changed.emit(segment)
    
    def on_roi_drawing_toggled(self, enabled):
        """Handle ROI drawing toggle"""
        # Emit signal with drawing state
        self.roi_drawing_toggled.emit(enabled)

        # if turning on drawing for the first time, automatically check segment 1
        if enabled and self.roi_manager.current_segment == 0:
            self.on_segment_selected(1)

    
    def on_clear_last_roi(self):
        """Handle clear last ROI button"""
        # Emit signal to clear last ROI
        self.clear_last_roi_requested.emit()
    
    def on_clear_all_rois(self):
        """Handle clear all ROIs button"""
        # Emit signal to clear all ROIs
        self.clear_all_rois_requested.emit()
    
    def on_export_rois(self):
        """Handle export ROIs button"""
        # Emit signal to export ROIs
        self.export_rois_requested.emit()
    
    def on_show_stats(self):
        """Handle show statistics button"""
        # Emit signal to show statistics
        self.show_stats_requested.emit()