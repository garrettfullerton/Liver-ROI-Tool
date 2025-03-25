# roi_manager.py
import os
import numpy as np
import csv
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QListWidget, QListWidgetItem, QPushButton, 
                            QFileDialog, QAbstractItemView)
from PyQt5.QtCore import Qt

class ROIManager(QObject):
    """Manages ROI creation, manipulation, and analysis"""
    
    # Define signals
    rois_changed = pyqtSignal()
    
    def __init__(self, dicom_model):
        super().__init__()
        self.dicom_model = dicom_model
        self.rois = []  # List of ROIs: [(slice_idx, center_x, center_y, radius, segment)]
        self.current_segment = 1
        self.segmentation_scheme = "9-segment"  # Default to 9-segment scheme
        self.segment_labels = []
    
    def add_roi(self, slice_idx, center_x, center_y, radius, segment=None):
        """Add a new ROI"""
        if segment is None:
            segment = self.current_segment

        # check segments already in rois
        # delete if already in rois
        for i, roi in enumerate(self.rois):
            if roi[4] == segment:
                self.delete_roi(i)
            
        self.rois.append((slice_idx, center_x, center_y, radius, segment))
        self.rois_changed.emit()
        return True
    
    def delete_roi(self, roi_index):
        """Delete a specific ROI"""
        if 0 <= roi_index < len(self.rois):
            del self.rois[roi_index]
            self.rois_changed.emit()
            return True
        return False
    
    def delete_last_roi(self):
        """Remove the last drawn ROI on the current slice"""
        current_slice = self.dicom_model.current_slice_index
        
        # Find ROIs for the current slice
        current_slice_rois = [(i, roi) for i, roi in enumerate(self.rois) 
                             if roi[0] == current_slice]
        
        if current_slice_rois:
            # Remove the last ROI for the current slice
            idx, _ = current_slice_rois[-1]
            return self.delete_roi(idx)
        
        return False
    
    def clear_slice_rois(self, slice_idx):
        """Clear all ROIs for a specific slice"""
        to_delete = [i for i, roi in enumerate(self.rois) if roi[0] == slice_idx]
        
        # Delete from last to first to avoid index issues
        for idx in sorted(to_delete, reverse=True):
            self.delete_roi(idx)
        
        return len(to_delete) > 0
    
    def clear_all_rois(self):
        """Clear all ROIs"""
        if self.rois:
            self.rois = []
            self.rois_changed.emit()
            return True
        return False
    
    def set_current_segment(self, segment):
        """Set current segment for new ROIs"""
        self.current_segment = segment
    
    def set_segmentation_scheme(self, scheme):
        """Set segmentation scheme (9-segment or 4-segment)"""
        if scheme in ("9-segment", "4-segment"):
            self.segmentation_scheme = scheme
            self.clear_all_rois()
            return True
        return False
    
    def get_rois_for_slice(self, slice_idx):
        """Get ROIs for a specific slice"""
        return [roi for roi in self.rois if roi[0] == slice_idx]
    
    def calculate_roi_statistics(self, roi):
        """Calculate statistics for a ROI"""
        slice_idx, center_x, center_y, radius, segment = roi
        
        # Get the slice data
        pixel_array = self.dicom_model.get_slice_pixel_data(slice_idx)
        if pixel_array is None:
            return None
        
        # Get original dimensions
        height, width = pixel_array.shape
        
        # Convert normalized coordinates to pixel coordinates
        center_x_px = int(center_x * width)
        center_y_px = int(center_y * height)
        radius_px = int(radius * min(width, height))
        
        # Create a mask for the circular ROI
        y_indices, x_indices = np.ogrid[:height, :width]
        dist_from_center = np.sqrt((x_indices - center_x_px)**2 + (y_indices - center_y_px)**2)
        mask = dist_from_center <= radius_px
        
        # Get pixel values within the ROI
        roi_values = pixel_array[mask]
        
        if len(roi_values) == 0:
            return None
        
        # Calculate statistics
        mean_val = np.mean(roi_values)
        median_val = np.median(roi_values)
        min_val = np.min(roi_values)
        max_val = np.max(roi_values)
        size = len(roi_values)
        
        return {
            'mean': mean_val,
            'median': median_val,
            'min': min_val,
            'max': max_val,
            'size': size
        }
    
    def export_rois(self, filename=None):
        """Export ROIs to a CSV file"""
        if not self.rois:
            return False
            
        if filename is None:
            # Show file dialog
            filename, _ = QFileDialog.getSaveFileName(
                None, "Save ROIs", f"{self.dicom_model.current_series_name}_ROIs.csv", "CSV Files (*.csv);;All Files (*)"
            )
            
        if not filename:
            return False
        
        try:
            if not filename.endswith('.csv'):
                filename += '.csv'

            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                # Write header
                writer.writerow(["SliceIndex", "CenterX", "CenterY", "Radius", "Segment", 
                                "Mean", "Median", "Min", "Max", "Size"])
                
                # Write ROI data
                for roi in self.rois:
                    slice_idx, center_x, center_y, radius, segment = roi
                    
                    # Calculate statistics for this ROI
                    stats = self.calculate_roi_statistics(roi)
                    
                    if stats:
                        writer.writerow([
                            slice_idx, center_x, center_y, radius, segment,
                            stats['mean'], stats['median'], stats['min'], 
                            stats['max'], stats['size']
                        ])
                    else:
                        writer.writerow([
                            slice_idx, center_x, center_y, radius, segment,
                            "N/A", "N/A", "N/A", "N/A", "N/A"
                        ])
                
            return True
        except Exception as e:
            print(f"Error exporting ROIs: {e}")
            return False
    
    def show_copy_dialog(self, parent=None):
        """Show dialog to copy ROIs from another series"""
        if not self.dicom_model.current_series:
            return False
            
        anatomical_positions = self.dicom_model.get_anatomical_positions()
        current_series_path = self.dicom_model.get_current_series_path()
        
        if not anatomical_positions or not current_series_path:
            return False
            
        # Create a new dialog
        dialog = QDialog(parent)
        dialog.setWindowTitle("Copy ROIs from Series")
        dialog.setMinimumSize(600, 400)
        
        # Create layout
        layout = QVBoxLayout(dialog)
        
        # Add instruction label
        label = QLabel("Select a source series to copy ROIs from:")
        layout.addWidget(label)
        
        # Add list widget for series selection
        series_list = QListWidget()
        series_list.setSelectionMode(QAbstractItemView.SingleSelection)
        
        # Populate list with available series
        for series_path in anatomical_positions.keys():
            # Skip current series
            if series_path == current_series_path:
                continue
                
            # Get series name from path
            path_parts = series_path.split(os.sep)
            if len(path_parts) >= 3:
                series_name = f"{path_parts[-3]} > {path_parts[-2]} > {path_parts[-1]}"
            else:
                series_name = path_parts[-1]
                
            item = QListWidgetItem(series_name)
            item.setData(Qt.UserRole, series_path)
            series_list.addItem(item)
        
        layout.addWidget(series_list)
        
        # Add buttons
        button_layout = QHBoxLayout()
        copy_button = QPushButton("Copy ROIs")
        cancel_button = QPushButton("Cancel")
        
        copy_button.clicked.connect(lambda: self._copy_rois_from_selected(series_list, dialog))
        cancel_button.clicked.connect(dialog.reject)
        
        button_layout.addWidget(copy_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec_()
        return True
    
    def _copy_rois_from_selected(self, series_list, dialog):
        """Copy ROIs from selected series to current series, matching anatomical positions"""
        item = series_list.currentItem()
        if not item:
            dialog.reject()
            return
            
        source_series_path = item.data(Qt.UserRole)
        anatomical_positions = self.dicom_model.get_anatomical_positions()