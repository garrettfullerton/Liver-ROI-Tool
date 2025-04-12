import os
import numpy as np
import csv
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QListWidget, QListWidgetItem, QPushButton, 
                            QFileDialog, QAbstractItemView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class ROI():
    def __init__(self, segment_label, segment, slice_idx, center_x, center_y, radius, 
                center_LR_mm, center_AP_mm, center_SI_mm, orientation, 
                area_mm2, mean_val, median_val, min_val, max_val, size_px, 
                study_id, exam_number, series_id, series_uid, series_path):
        self.segment_label = segment_label
        self.segment = segment
        self.slice_idx = slice_idx
        self.center_x = center_x
        self.center_y = center_y
        self.radius_px = radius
        self.center_LR_mm = center_LR_mm
        self.center_AP_mm = center_AP_mm
        self.center_SI_mm = center_SI_mm
        self.orientation = orientation
        self.area_mm2 = area_mm2
        self.mean_val = mean_val
        self.median_val = median_val
        self.min_val = min_val
        self.max_val = max_val
        self.size_px = size_px
        self.study_id = study_id
        self.exam_number = exam_number
        self.series_id = series_id
        self.series_uid = series_uid
        self.series_path = series_path
        

class ROIManager(QObject):
    """Manages ROI creation, manipulation, and analysis"""
    
    # Define signals
    rois_changed = pyqtSignal()
    
    def __init__(self, dicom_model):
        super().__init__()
        self.dicom_model = dicom_model
        self.rois = []  # List of ROIs: [(segment, slice_index, center_x_px, center_y_px, radius_px, 
                        #                   center_LR_mm, center_AP_mm, center_SI_mm, orientation, 
                        #                   area_mm2, mean_val, median_val, min_val, max_val, size_px, 
                        #                   study_id, exam_number, series_id, series_path)]
        self.current_segment = 0
        self.segmentation_scheme = "9-segment"  # Default to 9-segment scheme
        self.segment_labels = []
    
    def add_roi(self, segment_label, segment, slice_idx, center_x, center_y, radius, 
                center_LR_mm, center_AP_mm, center_SI_mm, orientation, 
                area_mm2, mean_val, median_val, min_val, max_val, size_px, 
                study_id, exam_number, series_id, series_uid, series_path):
        
        """Add a new ROI"""
        # check segments already in rois
        # delete if already in rois
        for i, roi in enumerate(self.rois):
            if roi.segment == segment and roi.series_path == series_path:
                self.delete_roi(i)
                
        new_roi = ROI(segment_label, segment, slice_idx, center_x, center_y, radius, 
                        center_LR_mm, center_AP_mm, center_SI_mm, orientation, 
                        area_mm2, mean_val, median_val, min_val, max_val, size_px, 
                        study_id, exam_number, series_id, series_uid, series_path)
            
        self.rois.append(new_roi)
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
                             if roi.slice_idx == current_slice]
        
        if current_slice_rois:
            # Remove the last ROI for the current slice
            idx, _ = current_slice_rois[-1]
            return self.delete_roi(idx)
        
        return False
    
    def clear_slice_rois(self, slice_idx):
        """Clear all ROIs for a specific slice"""
        to_delete = [i for i, roi in enumerate(self.rois) if roi.slice_idx == slice_idx]
        
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
        return [roi for roi in self.rois if roi.slice_idx == slice_idx and roi.series_path == series_path]
    
    def export_rois(self, filename=None):
        """Export ROIs to a CSV file"""
        if not self.rois:
            return False
            
        if filename is None:
            # Show file dialog
            default_path = f"{self.dicom_model.current_study_name}_{self.dicom_model.current_exam_number}_{self.segmentation_scheme}_ROIs.csv"

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
                    "Area (mm2)", "Mean", "Median", "Min", "Max", "Size", 
                    "Study ID", "Exam Number", "Series ID", "Series UID", "Series Path"
                    ])
                
                # Write ROI data
                for idx, roi in enumerate(self.rois):
                    writer.writerow([
                        roi.segment_label,
                        str(roi.segment), 
                        str(roi.slice_idx+1), 
                        f"{roi.center_x:.4f}", 
                        f"{roi.center_y:.4f}", 
                        f"{roi.radius_px:.4f}",
                        f"{roi.center_LR_mm:.4f}",
                        f"{roi.center_AP_mm:.4f}",
                        f"{roi.center_SI_mm:.4f}",
                        f"{roi.orientation}",
                        f"{roi.area_mm2:.4f}",
                        f"{roi.mean_val:.4f}",
                        f"{roi.median_val:.4f}",
                        f"{roi.min_val:.4f}",
                        f"{roi.max_val:.4f}",
                        str(roi.size_px),
                        roi.study_id,
                        roi.exam_number,
                        roi.series_id,
                        roi.series_uid,
                        roi.series_path
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
                    "Area (mm2)", "Mean", "Median", "Min", "Max", "Size", 
                    "Study ID", "Exam Number", "Series ID", "Series UID", "Series Path"
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
                mean_col = header_lower.index("mean")
                median_col = header_lower.index("median")
                min_col = header_lower.index("min")
                max_col = header_lower.index("max")
                size_col = header_lower.index("size")
                study_id_col = header_lower.index("study id")
                exam_number_col = header_lower.index("exam number")
                series_id_col = header_lower.index("series id")
                series_uid_col = header_lower.index("series uid")
                series_col = header_lower.index("series path")
                
                # Clear existing ROIs if any
                self.clear_all_rois()
                
                # Read ROI data
                for i, row in enumerate(reader):
                    try:
                        if row[series_uid_col] != self.dicom_model.current_series_uid:
                            print(f"skipping row {i+1} because series path does not match current series")
                            continue
                        
                        if row[segment_label_col] not in self.segment_labels:
                            print(f"can't find correct segment labels for row {i+1}. maybe change segmentation scheme?")
                            continue

                        # Extract required fields
                        slice_idx = int(row[slice_idx_col])-1
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
                        mean_val = float(row[mean_col])
                        median_val = float(row[median_col])
                        min_val = float(row[min_col])
                        max_val = float(row[max_col])
                        size_px = int(row[size_col])
                        study_id = row[study_id_col]
                        exam_number = row[exam_number_col]
                        series_id = row[series_id_col]
                        series_uid = row[series_uid_col]
                        series_path = row[series_col]

                        # Add the ROI
                        self.add_roi(segment_label, segment, slice_idx, center_x, center_y, radius, 
                                     center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2, 
                                     mean_val, median_val, min_val, max_val, size_px, 
                                     study_id, exam_number, series_id, series_uid, series_path)
                                               
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing ROI row {i+1}: {e}")
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
        # for series_path in anatomical_positions.keys():
        series_paths_with_rois = []
        
        for roi in self.rois:
            if roi.series_path in series_paths_with_rois:
                continue
            
            series_paths_with_rois.append(roi.series_path)
        
        for series_path in sorted(series_paths_with_rois):
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
        source_rois = [roi for roi in self.rois if roi.series_path == source_series_path]
        
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
            
            if roi.slice_idx in slice_mapping:
                target_slice_idx, distance, target_orientation = slice_mapping[roi.slice_idx]

                if target_orientation != roi.orientation:
                    continue

                if roi.segment_label not in self.segment_labels:
                    continue

                # convert center_LR_mm, center_AP_mm, center_SI_mm to pixel coordinates
                target_slice_data = self.dicom_model.get_slice(target_slice_idx)
                target_pixel_array = self.dicom_model.get_slice_pixel_data(target_slice_idx)

                pixel_spacing = getattr(target_slice_data, 'PixelSpacing', [1, 1])
                rows = getattr(target_slice_data, 'Rows', 1)
                cols = getattr(target_slice_data, 'Columns', 1)
                spacing_x, spacing_y = float(pixel_spacing[1]), float(pixel_spacing[0])
                if target_orientation == 1:
                    # sagittal
                    target_center_x = 1 - (roi.center_SI_mm - target_slice_data.ImagePositionPatient[2]) / spacing_x / cols
                    target_center_y = (roi.center_AP_mm - target_slice_data.ImagePositionPatient[1]) / spacing_y / rows
                elif target_orientation == 2:
                    # coronal
                    target_center_x = (roi.center_LR_mm - target_slice_data.ImagePositionPatient[0]) / spacing_x / cols
                    target_center_y = 1 - (roi.center_SI_mm - target_slice_data.ImagePositionPatient[2]) / spacing_y / rows
                elif target_orientation == 3:
                    # axial
                    target_center_x = (roi.center_LR_mm - target_slice_data.ImagePositionPatient[0]) / spacing_x / cols
                    target_center_y = (roi.center_AP_mm - target_slice_data.ImagePositionPatient[1]) / spacing_y / rows

                # get radius from area_mm2 to pixel radius
                radius_mm = np.sqrt(roi.area_mm2 / np.pi)

                # convert radius (mm) to pixel radius then convert to proportion of image size
                target_radius = radius_mm / spacing_x / cols
                
                height, width = target_pixel_array.shape
                target_center_x_px = int(target_center_x * width)
                target_center_y_px = int(target_center_y * height)
                
                # Create a mask for the circular ROI
                target_y_indices, target_x_indices = np.ogrid[:height, :width]
                dist_from_center = np.sqrt((target_x_indices - target_center_x_px)**2 + (target_y_indices - target_center_y_px)**2)
                mask = dist_from_center <= (target_radius * min(cols, rows))
                
                # Get pixel values within the ROI
                roi_values = target_pixel_array[mask]
                    
                # Calculate statistics
                target_mean_val = np.mean(roi_values)
                target_median_val = np.median(roi_values)
                target_min_val = np.min(roi_values)
                target_max_val = np.max(roi_values)
                target_size_px = len(roi_values)




                # Copy ROI to target series
                new_roi = ROI(roi.segment_label, roi.segment, target_slice_idx, target_center_x, target_center_y, target_radius, 
                                roi.center_LR_mm, roi.center_AP_mm, roi.center_SI_mm, target_orientation, 
                                roi.area_mm2, target_mean_val, target_median_val, target_min_val, target_max_val, target_size_px, 
                                self.dicom_model.current_study_name, self.dicom_model.current_exam_number, 
                                self.dicom_model.current_series_name, self.dicom_model.current_series_uid, target_series_path)

                new_rois.append(new_roi)
        
        # Add new ROIs to current list
        for new_roi in new_rois:
            # First check if an ROI with same segment already exists in target series
            for i, roi in enumerate(self.rois):
                if roi.segment == new_roi.segment and roi.series_path == target_series_path:
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