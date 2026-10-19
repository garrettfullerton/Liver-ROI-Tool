import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTreeWidget, 
                           QTreeWidgetItem, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal

from app_config import get_settings

class SeriesNavigatorPanel(QWidget):
    """UI panel for series navigation and selection"""
    
    # Define signals
    series_selected = pyqtSignal(str)  # Series path
    copy_rois_requested = pyqtSignal()
    folder_opened = pyqtSignal(str)  # root directory
    
    def __init__(self, parent, dicom_model, roi_manager):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        self.root_dir = None
        self.series_items = {}  # series path -> tree item
        
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
        
        # Button to copy/propagate ROIs between series
        self.copy_rois_button = QPushButton("Copy / Propagate ROIs...")
        self.copy_rois_button.clicked.connect(self.on_copy_rois_requested)
        self.layout.addWidget(self.copy_rois_button)
    
    def open_folder(self):
        """Open a folder dialog and load the DICOM directory structure"""
        settings = get_settings()
        root_dir = QFileDialog.getExistingDirectory(self, "Select Patient Directory",
                                                    settings.value("last_folder", ""))
        if not root_dir:
            return

        # Start the next dialog in the parent folder, so sibling patients are one click away
        settings.setValue("last_folder", os.path.dirname(os.path.normpath(root_dir)))
        self.load_folder(root_dir)

    def load_folder(self, root_dir):
        """Scan a folder for DICOM series and show them in the tree"""
        self.root_dir = root_dir
        self.dicom_model.load_directory(self.root_dir)
        self.update_tree()
        self.folder_opened.emit(self.root_dir)
    
    def update_tree(self):
        """Update the series tree based on model data"""
        self.series_tree.clear()
        self.series_items = {}
        
        # Get directory structure from model
        directory_structure = self.dicom_model.get_directory_structure()
        
        # Get sorted top-level keys
        sorted_top_level = sorted(directory_structure.keys())
        
        # Populate tree with the hierarchical structure
        for top_level in sorted_top_level:
            top_item = QTreeWidgetItem(self.series_tree, [top_level])
            self._add_tree_items(top_item, directory_structure[top_level])
        
        # Expand first level
        self.series_tree.expandToDepth(0)
        self.update_series_status()
        
    def _add_tree_items(self, parent_item, structure):
        """Recursively add items: folders alphabetically, then series by series number"""
        folders = sorted(name for name, content in structure.items() if isinstance(content, dict))
        series = sorted((content for content in structure.values() if not isinstance(content, dict)),
                        key=self.dicom_model.series_sort_key)
        
        for name in folders:
            # This is an intermediate directory
            child_item = QTreeWidgetItem(parent_item, [name])
            self._add_tree_items(child_item, structure[name])

        for series_path in series:
            # This is a series directory with DICOM files
            child_item = QTreeWidgetItem(parent_item, [self.dicom_model.get_series_label(series_path)])
            child_item.setData(0, Qt.UserRole, series_path)  # Store full path
            child_item.setToolTip(0, series_path)
            self.series_items[series_path] = child_item

    def update_series_status(self):
        """Refresh series labels with ROI progress (e.g. '5/9', '✓ 9/9') and bold the current series"""
        n_labels = len(self.roi_manager.segment_labels)
        segments_by_series = {}
        for roi in self.roi_manager.rois:
            segments_by_series.setdefault(roi.series_path, set()).add(roi.segment)

        for series_path, item in self.series_items.items():
            text = self.dicom_model.get_series_label(series_path)
            n_done = len(segments_by_series.get(series_path, ()))
            if n_done:
                text += f"   {'✓ ' if n_done >= n_labels else ''}{n_done}/{n_labels}"
            item.setText(0, text)

            font = item.font(0)
            font.setBold(series_path == self.dicom_model.current_series_path)
            item.setFont(0, font)
    
    def on_series_selected(self, item, column):
        """Handle series selection in the tree"""
        # Get the series path from the tree item
        series_path = item.data(0, Qt.UserRole)
        
        # Only leaf items (folders containing DICOM files) carry a path
        if series_path:
            self.series_selected.emit(series_path)
    
    def on_copy_rois_requested(self):
        """Handle request to copy ROIs from another series"""
        # Emit signal to request ROI copying
        self.copy_rois_requested.emit()