# ai_panel.py
"""
UI panel for AI-related controls
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QFileDialog,
                           QLabel, QProgressBar, QGroupBox, QComboBox)
from PyQt5.QtCore import pyqtSignal, Qt

class AIControlPanel(QWidget):
    """UI panel for AI model controls"""
    
    # Define signals
    model_loaded = pyqtSignal(str)  # model path
    predict_rois_requested = pyqtSignal()
    
    def __init__(self, parent, dicom_model, roi_manager, ai_model_manager):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        self.ai_model_manager = ai_model_manager
    
    def setup_ui(self):
        """Set up UI components for AI controls"""
        self.layout = QVBoxLayout(self)
        
        # AI Model Group
        self.model_group = QGroupBox("AI Model")
        self.model_layout = QVBoxLayout()
        
        # Model selection
        self.load_model_button = QPushButton("Load AI Model")
        self.load_model_button.clicked.connect(self.on_load_model)
        
        self.model_label = QLabel("No model loaded")
        
        # Prediction controls
        self.predict_button = QPushButton("Predict ROIs")
        self.predict_button.clicked.connect(self.on_predict_rois)
        self.predict_button.setEnabled(False)  # Disabled until model is loaded
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        # Add widgets to layout
        self.model_layout.addWidget(self.load_model_button)
        self.model_layout.addWidget(self.model_label)
        self.model_layout.addWidget(self.predict_button)
        self.model_layout.addWidget(self.progress_bar)
        
        self.model_group.setLayout(self.model_layout)
        self.layout.addWidget(self.model_group)
    
    def on_load_model(self):
        """Handle load model button click"""
        model_path, _ = QFileDialog.getOpenFileName(
            self, "Load AI Model", "", "Model Files (*.pt *.pth);;All Files (*)"
        )
        
        if model_path and self.ai_model_manager.load_model(model_path):
            self.model_label.setText(f"Model: {os.path.basename(model_path)}")
            self.predict_button.setEnabled(True)
            self.model_loaded.emit(model_path)
    
    def on_predict_rois(self):
        """Handle predict ROIs button click"""
        self.progress_bar.setVisible(True)
        self.predict_button.setEnabled(False)
        self.predict_rois_requested.emit()
    
    def prediction_complete(self):
        """Handle prediction completion"""
        self.progress_bar.setVisible(False)
        self.predict_button.setEnabled(True)