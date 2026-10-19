import os
import numpy as np
import csv
from dataclasses import dataclass, field
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QListWidget, QListWidgetItem, QPushButton, 
                            QFileDialog, QAbstractItemView)
from PyQt5.QtCore import Qt

from schemes import SCHEMES, DEFAULT_SCHEME
from roi_geometry import compute_roi_stats, patient_to_normalized, get_pixel_spacing


@dataclass(eq=False)
class ROI:
    scheme: str
    segment_label: str
    segment: int
    slice_idx: int
    center_x: float  # normalized (0-1) column position
    center_y: float  # normalized (0-1) row position
    radius_px: float  # radius in image pixels
    center_LR_mm: float
    center_AP_mm: float
    center_SI_mm: float
    orientation: int
    area_mm2: float
    mean_val: float
    median_val: float
    min_val: float
    max_val: float
    std_val: float
    size_px: int
    series_path: str
    meta: dict = field(default_factory=dict)  # series-level DICOM info (DicomSeriesModel.series_meta)

    @property
    def radius_norm(self):
        """Radius as a fraction of the smaller image dimension (format used in exported CSVs)"""
        return self.radius_px / min(self.meta['Rows'], self.meta['Columns'])
        

class ROIManager(QObject):
    """Manages ROI creation, manipulation, and analysis"""
    
    # Define signals
    rois_changed = pyqtSignal()
    
    def __init__(self, dicom_model):
        super().__init__()
        self.dicom_model = dicom_model
        self.rois = []  # List of ROI objects
        self.current_segment = 0
        self.segmentation_scheme = DEFAULT_SCHEME
        self.segment_labels = SCHEMES[DEFAULT_SCHEME]["labels"]
    
    def create_roi(self, series_path, slice_idx, segment, norm_x, norm_y, radius_px):
        """Build an ROI (with statistics) on a slice of any loaded series; returns None if invalid"""
        slice_data = self.dicom_model.get_slice(slice_idx, series_path)
        if slice_data is None or not 1 <= segment <= len(self.segment_labels):
            return None

        pixel_values = self.dicom_model.get_slice_pixel_data(slice_idx, series_path)
        stats = compute_roi_stats(slice_data, pixel_values, norm_x, norm_y, radius_px)
        if stats is None:
            return None

        return ROI(scheme=self.segmentation_scheme,
                   segment_label=self.segment_labels[segment - 1],
                   segment=segment,
                   slice_idx=slice_idx,
                   center_x=norm_x,
                   center_y=norm_y,
                   radius_px=radius_px,
                   series_path=series_path,
                   meta=self.dicom_model.get_series_meta(series_path),
                   **stats)

    def add_roi(self, roi):
        """Add a new ROI, replacing any ROI of the same segment in the same series"""
        self.rois = [r for r in self.rois
                     if not (r.segment == roi.segment and r.series_path == roi.series_path)]
        self.rois.append(roi)
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
        """Set segmentation scheme (one of the keys in SCHEMES)"""
        if scheme in SCHEMES:
            self.segmentation_scheme = scheme
            self.segment_labels = SCHEMES[scheme]["labels"]
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
                        f"{roi.radius_norm:.4f}",
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
                        roi.meta['PatientID'],
                        roi.meta['StudyID'],
                        roi.meta['SeriesDescription'],
                        roi.meta['SeriesInstanceUID'],
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
                
                # Get indices of the fields needed to rebuild ROIs
                segment_label_col = header_lower.index("segment label")
                slice_idx_col = header_lower.index("slice index")
                center_x_col = header_lower.index("center x")
                center_y_col = header_lower.index("center y")
                radius_col = header_lower.index("radius")
                series_uid_col = header_lower.index("series uid")
                
                # Clear existing ROIs if any
                self.clear_all_rois()
                
                series_path = self.dicom_model.current_series_path
                
                # Read ROI data; statistics are recomputed from the image
                for i, row in enumerate(reader):
                    try:
                        if row[series_uid_col] != self.dicom_model.current_series_uid:
                            print(f"skipping row {i+1} because series path does not match current series")
                            continue
                        
                        if row[segment_label_col] not in self.segment_labels:
                            print(f"can't find correct segment labels for row {i+1}. maybe change segmentation scheme?")
                            continue

                        slice_idx = int(row[slice_idx_col])-1
                        slice_data = self.dicom_model.get_slice(slice_idx, series_path)
                        if slice_data is None:
                            print(f"skipping row {i+1}: slice {slice_idx+1} not in current series")
                            continue

                        # Radius is stored as a fraction of the smaller image dimension
                        radius_px = float(row[radius_col]) * min(slice_data.Rows, slice_data.Columns)
                        segment = self.segment_labels.index(row[segment_label_col]) + 1

                        roi = self.create_roi(series_path, slice_idx, segment,
                                              float(row[center_x_col]), float(row[center_y_col]), radius_px)
                        if roi is not None:
                            self.add_roi(roi)
                                               
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
        if target_series_path is None:
            target_series_path = self.dicom_model.get_current_series_path()
        
        if not source_series_path or not target_series_path:
            return False

        # Make sure both series are read (target need not be the displayed series)
        if not self.dicom_model.read_series(source_series_path) or not self.dicom_model.read_series(target_series_path):
            return False
        
        # Get source and target positions
        anatomical_positions = self.dicom_model.get_anatomical_positions()
        source_positions = anatomical_positions.get(source_series_path, {})
        target_positions = anatomical_positions.get(target_series_path, {})

        target_orientations = self.dicom_model.get_slice_orientations(target_series_path)
        
        if not source_positions or not target_positions:
            return False
        
        # Get ROIs from source series
        source_rois = [roi for roi in self.rois if roi.series_path == source_series_path]
        
        if not source_rois:
            return False
        
        # Create a mapping from source to target slices based on closest anatomical positions
        slice_mapping = {}
        
        for source_idx, source_pos in source_positions.items():
            # Find closest target slice along the target's through-plane axis
            best_target_idx = None
            best_distance = float('inf')
            
            for target_idx, target_pos in target_positions.items():
                orientation = target_orientations.get(target_idx)
                if orientation is None:
                    continue

                axis = orientation - 1  # 0=LR (sagittal), 1=AP (coronal), 2=SI (axial)
                distance = abs(float(source_pos[axis]) - float(target_pos[axis]))
                
                # Only consider if within maximum distance threshold
                if distance <= max_distance_mm and distance < best_distance:
                    best_distance = distance
                    best_target_idx = target_idx
            
            if best_target_idx is not None:
                slice_mapping[source_idx] = (best_target_idx, best_distance, target_orientations[best_target_idx])
        
        # Copy ROIs to target series
        new_rois = []

        for roi in source_rois:
            if roi.slice_idx not in slice_mapping:
                continue

            target_slice_idx, distance, target_orientation = slice_mapping[roi.slice_idx]

            if target_orientation != roi.orientation:
                continue

            if roi.segment_label not in self.segment_labels:
                continue

            target_slice_data = self.dicom_model.get_slice(target_slice_idx, target_series_path)

            # Convert ROI center (mm) to target image coordinates; keep physical radius
            target_center_x, target_center_y = patient_to_normalized(
                target_slice_data, target_orientation, roi.center_LR_mm, roi.center_AP_mm, roi.center_SI_mm)
            spacing_x, _ = get_pixel_spacing(target_slice_data)
            target_radius_px = np.sqrt(roi.area_mm2 / np.pi) / spacing_x

            new_roi = self.create_roi(target_series_path, target_slice_idx, roi.segment,
                                      target_center_x, target_center_y, target_radius_px)
            if new_roi is not None:
                new_rois.append(new_roi)
        
        # Add new ROIs, replacing any ROI with the same segment in the target series
        for new_roi in new_rois:
            self.rois = [r for r in self.rois
                         if not (r.segment == new_roi.segment and r.series_path == target_series_path)]
            self.rois.append(new_roi)

        # Update display
        self.rois_changed.emit()
        
        return len(new_rois) > 0
