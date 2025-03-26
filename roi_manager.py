import os
import numpy as np
import csv
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QListWidget, QListWidgetItem, QPushButton, 
                            QFileDialog, QAbstractItemView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

class ROIManager(QObject):
    """Manages ROI creation, manipulation, and analysis"""
    
    # Define signals
    rois_changed = pyqtSignal()
    
    def __init__(self, dicom_model):
        super().__init__()
        self.dicom_model = dicom_model
        self.rois = []  # List of ROIs: [(segment, slice_index, center_x_px, center_y_px, radius_px, 
                        # center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2)]
        self.current_segment = 0
        self.segmentation_scheme = "9-segment"  # Default to 9-segment scheme
        self.segment_labels = []
    
    def add_roi(self, slice_idx, segment_label, series_path, center_x, center_y, radius, 
                center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2, segment=None):
        """Add a new ROI"""
        if segment is None:
            segment = self.current_segment


        # check segments already in rois
        # delete if already in rois
        for i, roi in enumerate(self.rois):
            if roi[1] == segment and roi[-1] == series_path:
                self.delete_roi(i)
            
        self.rois.append((segment_label, segment, slice_idx, center_x, center_y, radius, 
                          center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2,
                          series_path))
        self.rois_changed.emit()
        return True
    
    def delete_roi(self, roi_index):
        """Delete a specific ROI"""
        if 0 <= roi_index < len(self.rois):
            del self.rois[roi_index]
            self.rois_changed.emit()
            return True
        return False
    
    def delete_roi_duplicates(self):
        """Delete duplicate ROIs"""
        unique_rois = []
        for roi in self.rois:
            if roi not in unique_rois:
                unique_rois.append(roi)
        
        if len(unique_rois) < len(self.rois):
            self.rois = unique_rois
            self.rois_changed.emit()
            return True
        
        return False
    
    def delete_last_roi(self):
        """Remove the last drawn ROI on the current slice"""
        current_slice = self.dicom_model.current_slice_index
        
        # Find ROIs for the current slice
        current_slice_rois = [(i, roi) for i, roi in enumerate(self.rois) 
                             if roi[1] == current_slice]
        
        if current_slice_rois:
            # Remove the last ROI for the current slice
            idx, _ = current_slice_rois[-1]
            return self.delete_roi(idx)
        
        return False
    
    def clear_slice_rois(self, slice_idx):
        """Clear all ROIs for a specific slice"""
        to_delete = [i for i, roi in enumerate(self.rois) if roi[1] == slice_idx]
        
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
    
    def get_rois_for_slice(self, slice_idx, series_path=None):
        """Get ROIs for a specific slice"""
        return [roi for roi in self.rois if roi[2] == slice_idx and roi[-1] == series_path]
    
    def calculate_roi_statistics(self, roi):
        """Calculate statistics for a ROI"""
        segment_label, segment, slice_idx, center_x, center_y, radius, center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2, series_path = roi
        
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
            default_path = f"{self.dicom_model.current_study_name}/{self.dicom_model.current_series_name}_ROIs.csv"

            filename, _ = QFileDialog.getSaveFileName(
                None, "Save Statistics", default_path, "CSV Files (*.csv)"
            )
            
        if not filename:
            return False
        
        if not filename.lower().endswith('.csv'):
            filename += '.csv'
        
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                # Write extended header
                writer.writerow([
                    "Segment Label", "Segment Index", "Slice Index", "Center X", "Center Y", "Radius", 
                    "Center LR (mm)", "Center AP (mm)", "Center SI (mm)", "Orientation", 
                    "Area (mm2)", "Mean", "Median", "Min", "Max", "Size", "Series Path"
                    ])
                
                # Write ROI data
                for idx, roi in enumerate(self.rois):
                    segment_label, segment, slice_idx, center_x, center_y, radius, center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2, series_path = roi
                    
                    # Get anatomical position and physical size
                    anat_pos = (0, 0, 0)
                    area_mm2 = 0
                    
                    # Get slice metadata for physical calculations
                    slice_data = self.dicom_model.get_slice(slice_idx)
                    if slice_data:
                        # Get pixel spacing if available
                        pixel_spacing = getattr(slice_data, 'PixelSpacing', [1, 1])
                        rows = getattr(slice_data, 'Rows', 1)
                        cols = getattr(slice_data, 'Columns', 1)
                        spacing_x, spacing_y = float(pixel_spacing[1]), float(pixel_spacing[0])
                        
                        # Calculate physical area
                        pixel_radius = radius * min(slice_data.Columns, slice_data.Rows)
                        physical_radius_mm = pixel_radius * spacing_x  # Assuming square pixels
                        area_mm2 = np.pi * (physical_radius_mm ** 2)
                        
                        # Get anatomical position if available
                        if hasattr(slice_data, 'ImagePositionPatient'):
                            anat_pos = slice_data.ImagePositionPatient

                        if hasattr(slice_data, 'ImageOrientationPatient'):
                            orientation_vec = slice_data.ImageOrientationPatient
                            orientation_vec_cross = np.cross(orientation_vec[:3], orientation_vec[3:])
                            orientation_vec_cross_rounded = [round(abs(val), 0) for val in orientation_vec_cross]
                            orientation = orientation_vec_cross_rounded.index(1.0) + 1
                            if orientation == 1:
                                # sagittal
                                pos_LR = anat_pos[0]
                                pos_AP = anat_pos[1] + (spacing_y * (rows * (center_y)))
                                pos_SI = anat_pos[2] + (spacing_x * (cols * (center_x)))
                            elif orientation == 2:
                                # coronal
                                pos_LR = anat_pos[0] + (spacing_x * (cols * center_x))
                                pos_AP = anat_pos[1]
                                pos_SI = anat_pos[2] + (spacing_y * (rows * (center_y)))
                            elif orientation == 3:
                                # axial
                                pos_LR = anat_pos[0] + (spacing_x * (cols * center_x))
                                pos_AP = anat_pos[1] + (spacing_y * (rows * (center_y)))
                                pos_SI = anat_pos[2]
                        else:
                            orientation = "N/A"
                            pos_LR = "N/A"
                            pos_AP = "N/A"
                            pos_SI = "N/A"


                        
                    
                    # Calculate statistics
                    stats = self.calculate_roi_statistics(roi)
                    
                    if stats:
                        writer.writerow([
                            segment_label,
                            str(segment), 
                            str(slice_idx+1), 
                            f"{center_x:.4f}", 
                            f"{center_y:.4f}", 
                            f"{radius:.4f}",
                            f"{pos_LR:.4f}",
                            f"{pos_AP:.4f}",
                            f"{pos_SI:.4f}",
                            f"{orientation}",
                            f"{area_mm2:.4f}",
                            f"{stats['mean']:.4f}",
                            f"{stats['median']:.4f}",
                            f"{stats['min']:.4f}",
                            f"{stats['max']:.4f}",
                            str(stats['size']),
                            series_path
                        ])
                    else:
                        writer.writerow([
                            segment_label,
                            str(segment),
                            str(slice_idx+1), 
                            f"{center_x:.4f}", 
                            f"{center_y:.4f}", 
                            f"{radius:.4f}",
                            f"{pos_LR:.4f}",
                            f"{pos_AP:.4f}",
                            f"{pos_SI:.4f}",
                            f"{orientation}",
                            f"{area_mm2:.4f}",
                            "N/A",
                            "N/A",
                            "N/A",
                            "N/A",
                            "N/A",
                            series_path
                        ])
                
            return True
        except Exception as e:
            print(f"Error exporting ROIs: {e}")
            return False
        
    def import_rois(self, filename=None):
        """Import ROIs from a CSV file"""
        if filename is None:
            # Show file dialog
            filename, _ = QFileDialog.getOpenFileName(
                None, "Load ROIs", "", "CSV Files (*.csv)"
            )
            
        if not filename or not os.path.exists(filename):
            return False
        
        try:
            with open(filename, 'r', newline='') as f:
                reader = csv.reader(f)
                
                # Read header
                header = next(reader)
                
                # Check file format
                required_fields = ["Segment Label", "Segment Index", "Slice Index", "Center X", "Center Y", "Radius", 
                    "Center LR (mm)", "Center AP (mm)", "Center SI (mm)", "Orientation", 
                    "Area (mm2)", "Mean", "Median", "Min", "Max", "Size", "Series Path"
                    ]
                
                # Verify all required fields are present (allowing for case differences)
                header_lower = [h.lower() for h in header]
                for field in required_fields:
                    if field.lower() not in header_lower:
                        print(f"Error: Required field '{field}' missing in CSV header")
                        return False
                
                # Get indices of required fields
                segment_label_col = header_lower.index("segment label")
                segment_col = header_lower.index("segment index")
                slice_idx_col = header_lower.index("slice index")
                center_x_col = header_lower.index("center x")
                center_y_col = header_lower.index("center y")
                radius_col = header_lower.index("radius")
                anat_x_col = header_lower.index("center lr (mm)")
                anat_y_col = header_lower.index("center ap (mm)")
                anat_z_col = header_lower.index("center si (mm)")
                orientation_col = header_lower.index("orientation")
                area_col = header_lower.index("area (mm2)")
                series_col = header_lower.index("series path")
                
                # Clear existing ROIs if any
                self.clear_all_rois()
                
                # Read ROI data
                for i, row in enumerate(reader):
                    try:
                        if row[series_col] != self.dicom_model.current_series_path:
                            print(f"skipping row {i+2} because series path does not match current series")
                            continue

                        # Extract required fields
                        slice_idx = int(row[slice_idx_col])
                        center_x = float(row[center_x_col])
                        center_y = float(row[center_y_col])
                        radius = float(row[radius_col])
                        segment = int(row[segment_col])
                        segment_label = row[segment_label_col]
                        center_LR_mm = float(row[anat_x_col])
                        center_AP_mm = float(row[anat_y_col])
                        center_SI_mm = float(row[anat_z_col])
                        orientation = int(row[orientation_col])
                        area_mm2 = float(row[area_col])
                        series_path = self.dicom_model.current_series_path

                        # Add the ROI
                        self.add_roi(slice_idx, segment_label, series_path, center_x, center_y, radius, 
                                     center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2, segment)
                                               
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing ROI row {i+2}: {e}")
                        # Continue with next row
                
               
                self.delete_roi_duplicates()

                # Notify of changes
                self.rois_changed.emit()

                
                return True
                
        except Exception as e:
            print(f"Error importing ROIs: {e}")
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
        self.copy_rois_from_series(source_series_path)
        dialog.accept()
    
    def copy_rois_from_series(self, source_series_path, target_series_path=None, max_distance_mm=5.0):
        """
        Copy ROIs from source to target series based on anatomical coordinates
        
        Args:
            source_series_path (str): Path to source series
            target_series_path (str): Path to target series (defaults to current series)
            max_distance_mm (float): Maximum allowed distance between slices in mm
            
        Returns:
            bool: True if any ROIs were copied, False otherwise
        """
        anatomical_positions = self.dicom_model.get_anatomical_positions()
        
        if target_series_path is None:
            target_series_path = self.dicom_model.get_current_series_path()
        
        if not source_series_path or not target_series_path:
            return False
        
        # Get source and target positions
        source_positions = anatomical_positions.get(source_series_path, {})
        target_positions = anatomical_positions.get(target_series_path, {})

        target_orientations = self.dicom_model.get_slice_orientations(target_series_path)
        
        if not source_positions or not target_positions:
            return False
        
        # Get ROIs from source series
        # source_rois = [roi for roi in self.rois if roi[1] in source_positions and roi[-1] == source_series_path]
        source_rois = [roi for roi in self.rois if roi[-1] == source_series_path]
        
        if not source_rois:
            return False
                

        
        # Create a mapping from source to target slices based on closest anatomical positions
        slice_mapping = {}
        source_to_xyz = {}  # Store anatomical coordinates for each source slice
        
        for source_idx, source_pos in source_positions.items():
                
            source_to_xyz[source_idx] = source_pos
                        
            # Find closest target slice 
            best_target_idx = None
            best_distance = float('inf')
            
            for target_idx, target_pos in target_positions.items():
                orientation = target_orientations[target_idx]

                if orientation == 1:
                    distance = abs(source_pos[0] - target_pos[0])
                elif orientation == 2:
                    distance = abs(source_pos[1] - target_pos[1])
                elif orientation == 3:
                    distance = abs(source_pos[2] - target_pos[2])
                    
               
                
                # Only consider if within maximum distance threshold
                if distance <= max_distance_mm and distance < best_distance:
                    best_distance = distance
                    best_target_idx = target_idx
            
            if best_target_idx is not None:
                slice_mapping[source_idx] = (best_target_idx, best_distance, target_orientations[best_target_idx])
        
        # Copy ROIs to target series
        new_rois = []
        for roi in source_rois:
            segment_label, segment, slice_idx, center_x, center_y, radius, center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2, series_id = roi
            
            if slice_idx in slice_mapping:
                target_slice_idx, distance, target_orientation = slice_mapping[slice_idx]

                if target_orientation != orientation:
                    continue

                if segment_label not in self.segment_labels:
                    continue

                # convert center_LR_mm, center_AP_mm, center_SI_mm to pixel coordinates
                target_slice_data = self.dicom_model.get_slice(target_slice_idx)
                if target_slice_data:
                    pixel_spacing = getattr(target_slice_data, 'PixelSpacing', [1, 1])
                    rows = getattr(target_slice_data, 'Rows', 1)
                    cols = getattr(target_slice_data, 'Columns', 1)
                    spacing_x, spacing_y = float(pixel_spacing[1]), float(pixel_spacing[0])
                    if target_orientation == 1:
                        # sagittal
                        center_x = 1 - (center_SI_mm - target_slice_data.ImagePositionPatient[2]) / spacing_x / cols
                        center_y = (center_AP_mm - target_slice_data.ImagePositionPatient[1]) / spacing_y / rows
                    elif target_orientation == 2:
                        # coronal
                        center_x = (center_LR_mm - target_slice_data.ImagePositionPatient[0]) / spacing_x / cols
                        center_y = 1 - (center_SI_mm - target_slice_data.ImagePositionPatient[2]) / spacing_y / rows
                    elif target_orientation == 3:
                        # axial
                        center_x = (center_LR_mm - target_slice_data.ImagePositionPatient[0]) / spacing_x / cols
                        center_y = (center_AP_mm - target_slice_data.ImagePositionPatient[1]) / spacing_y / rows

                    # get radius from area_mm2 to pixel radius
                    radius_mm = np.sqrt(area_mm2 / np.pi)

                    # convert radius (mm) to pixel radius then convert to proportion of image size
                    radius = radius_mm / spacing_x / cols




                # Copy ROI to target series
                new_roi = (
                    segment_label,
                    segment, 
                    target_slice_idx, 
                    center_x, 
                    center_y, 
                    radius, 
                    center_LR_mm, 
                    center_AP_mm, 
                    center_SI_mm, 
                    orientation, 
                    area_mm2,
                    target_series_path  # Use target series path as series_id
                )
                new_rois.append(new_roi)
        
        # Add new ROIs to current list
        for new_roi in new_rois:
            # First check if an ROI with same segment already exists in target series
            for i, roi in enumerate(self.rois):
                if roi[0] == new_roi[0] and roi[-1] == target_series_path:
                    self.delete_roi(i)
                    break
            
            # Add the new ROI
            self.rois.append(new_roi)
        

        self.delete_roi_duplicates()

        # Update display
        self.rois_changed.emit()
        
        return len(new_rois) > 0
        
    def get_segment_color(self, segment):
        """Get color based on liver segment"""
        colors = {
            1: QColor(255, 0, 0, 128),    # Red
            2: QColor(0, 255, 0, 128),    # Green
            3: QColor(0, 0, 255, 128),    # Blue
            4: QColor(255, 255, 0, 128),  # Yellow
            5: QColor(255, 0, 255, 128),  # Magenta
            6: QColor(0, 255, 255, 128),  # Cyan
            7: QColor(255, 128, 0, 128),  # Orange
            8: QColor(128, 0, 255, 128),  # Purple
            9: QColor(0, 128, 128, 128),  # Teal
        }
        return colors.get(segment, QColor(255, 255, 255, 128))