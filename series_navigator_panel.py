# series_navigator_panel.py
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTreeWidget, 
                           QTreeWidgetItem, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal

class SeriesNavigatorPanel(QWidget):
    """UI panel for series navigation and selection"""
    
    # Define signals
    series_selected = pyqtSignal(str)  # Series path
    copy_rois_requested = pyqtSignal()
    
    def __init__(self, parent, dicom_model):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.root_dir = None
        
    def setup_ui(self):
        """Set up UI components for series navigation"""
        self.layout = QVBoxLayout(self)
        
        # Open folder button
        self.open_button = QPushButton("Open Folder")
        self.open_button.clicked.connect(self.open_folder)
        self.layout.addWidget(self.open_button)
        
        # Series tree
        self.series_tree = QTreeWidget()
        self.series_tree.setHeaderLabels(["Patient/Study/Series"])
        self.series_tree.itemClicked.connect(self.on_series_selected)
        self.layout.addWidget(self.series_tree)
        
        # Button to copy ROIs from another series
        self.copy_rois_button = QPushButton("Copy ROIs from Another Series")
        self.copy_rois_button.clicked.connect(self.on_copy_rois_requested)
        self.layout.addWidget(self.copy_rois_button)
    
    def open_folder(self):
        """Open a folder dialog and load the DICOM directory structure"""
        self.root_dir = QFileDialog.getExistingDirectory(self, "Select Patient Directory")
        if not self.root_dir:
            return
            
        self.dicom_model.load_directory(self.root_dir)
        self.update_tree()
    
    def update_tree(self):
        """Update the series tree based on model data"""
        self.series_tree.clear()
        
        # Get directory structure from model
        directory_structure = self.dicom_model.get_directory_structure()
        
        # Populate tree with patient > study > series structure
        for patient, studies in directory_structure.items():
            patient_item = QTreeWidgetItem(self.series_tree, [patient])
            
            for study, series_dict in studies.items():
                study_item = QTreeWidgetItem(patient_item, [study])
                
                for series, series_path in series_dict.items():
                    series_item = QTreeWidgetItem(study_item, [series])
                    series_item.setData(0, Qt.UserRole, series_path)
        
        # Expand first level
        self.series_tree.expandToDepth(0)
    
    def on_series_selected(self, item, column):
        """Handle series selection in the tree"""
        # Get the series path from the tree item
        series_path = item.data(0, Qt.UserRole)
        if not series_path:
            return
            
        # Emit signal with selected series path
        self.series_selected.emit(series_path)
    
    def on_copy_rois_requested(self):
        """Handle request to copy ROIs from another series"""
        # Emit signal to request ROI copying
        self.copy_rois_requested.emit()