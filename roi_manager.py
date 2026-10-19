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
from roi_geometry import (compute_roi_stats, patient_to_normalized, get_pixel_spacing,
                          get_orientation, distance_to_slice)


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
        

# Exported CSV columns: (header, value getter). Original column names are kept so existing
# analysis scripts and older CSVs remain compatible; new columns are appended.
EXPORT_COLUMNS = [
    ("Segment Label", lambda r: r.segment_label),
    ("Segment Index", lambda r: r.segment),
    ("Slice Index", lambda r: r.slice_idx + 1),
    ("Center X", lambda r: r.center_x),
    ("Center Y", lambda r: r.center_y),
    ("Radius", lambda r: r.radius_norm),
    ("Center LR (mm)", lambda r: r.center_LR_mm),
    ("Center AP (mm)", lambda r: r.center_AP_mm),
    ("Center SI (mm)", lambda r: r.center_SI_mm),
    ("Orientation", lambda r: r.orientation),
    ("Area (mm2)", lambda r: r.area_mm2),
    ("Mean", lambda r: r.mean_val),
    ("Median", lambda r: r.median_val),
    ("Min", lambda r: r.min_val),
    ("Max", lambda r: r.max_val),
    ("Size", lambda r: r.size_px),
    ("Study ID", lambda r: r.meta.get('PatientID')),
    ("Exam Number", lambda r: r.meta.get('StudyID')),
    ("Series ID", lambda r: r.meta.get('SeriesDescription')),
    ("Series UID", lambda r: r.meta.get('SeriesInstanceUID')),
    ("Series Path", lambda r: r.series_path),
    ("Scheme", lambda r: r.scheme),
    ("Std", lambda r: r.std_val),
    ("Radius (px)", lambda r: r.radius_px),
    ("Series Number", lambda r: r.meta.get('SeriesNumber')),
    ("Series Date", lambda r: r.meta.get('SeriesDate')),
    ("Series Time", lambda r: r.meta.get('SeriesTime')),
    ("Acquisition Time", lambda r: r.meta.get('AcquisitionTime')),
    ("Study Date", lambda r: r.meta.get('StudyDate')),
    ("Study Instance UID", lambda r: r.meta.get('StudyInstanceUID')),
    ("Accession Number", lambda r: r.meta.get('AccessionNumber')),
    ("Modality", lambda r: r.meta.get('Modality')),
    ("Manufacturer", lambda r: r.meta.get('Manufacturer')),
    ("Model", lambda r: r.meta.get('ManufacturerModelName')),
    ("Field Strength (T)", lambda r: r.meta.get('MagneticFieldStrength')),
    ("TR (ms)", lambda r: r.meta.get('RepetitionTime')),
    ("TE (ms)", lambda r: r.meta.get('EchoTime')),
    ("Flip Angle", lambda r: r.meta.get('FlipAngle')),
    ("Echo Number", lambda r: r.meta.get('EchoNumbers')),
    ("Slice Thickness (mm)", lambda r: r.meta.get('SliceThickness')),
    ("Pixel Spacing Row (mm)", lambda r: r.meta.get('PixelSpacingRow')),
    ("Pixel Spacing Col (mm)", lambda r: r.meta.get('PixelSpacingCol')),
    ("Rows", lambda r: r.meta.get('Rows')),
    ("Columns", lambda r: r.meta.get('Columns')),
    ("Instance Number", lambda r: r.meta.get('InstanceNumber')),
    ("Slice Location", lambda r: r.meta.get('SliceLocation')),
]


def format_value(value):
    """Format a value for CSV/table display (floats to 4 decimals, missing values blank)"""
    if value is None:
        return ""
    if isinstance(value, (float, np.floating)):
        return "" if np.isnan(value) else f"{value:.4f}"
    return str(value)


class ROIManager(QObject):
    """Manages ROI creation, manipulation, and analysis"""
    
    # Define signals
    rois_changed = pyqtSignal()
    scheme_changed = pyqtSignal(str)  # scheme name
    
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
                   meta={**self.dicom_model.get_series_meta(series_path),
                         **self.dicom_model.get_slice_meta(slice_idx, series_path)},
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
        """Set segmentation scheme (one of the keys in SCHEMES); clears all ROIs"""
        if scheme in SCHEMES:
            self.segmentation_scheme = scheme
            self.segment_labels = SCHEMES[scheme]["labels"]
            self.clear_all_rois()
            self.scheme_changed.emit(scheme)
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
                writer.writerow([header for header, _ in EXPORT_COLUMNS])
                for roi in self.rois:
                    writer.writerow([format_value(getter(roi)) for _, getter in EXPORT_COLUMNS])
            return True
        except Exception as e:
            print(f"Error exporting ROIs: {e}")
            return False

    @staticmethod
    def _detect_scheme(rows, current_scheme):
        """Pick the scheme for imported rows: 'Scheme' column if present, otherwise infer from labels"""
        schemes = [row["scheme"] for row in rows if row.get("scheme") in SCHEMES]
        if schemes:
            counts = {scheme: schemes.count(scheme) for scheme in set(schemes)}
            if len(counts) > 1:
                print(f"Warning: file contains ROIs from several schemes {counts}; using the most common")
            return max(counts, key=counts.get)

        # Older files: choose a scheme containing every label (prefer the current scheme)
        labels = {row.get("segment label") for row in rows}
        candidates = [current_scheme] + [scheme for scheme in SCHEMES if scheme != current_scheme]
        for scheme in candidates:
            if labels <= set(SCHEMES[scheme]["labels"]):
                return scheme
        return current_scheme
        
    def import_rois(self, filename=None):
        """Import ROIs from a CSV file (exported by any version of this tool)"""
        if filename is None:
            # Show file dialog
            filename, _ = QFileDialog.getOpenFileName(
                None, "Load ROIs", "", "CSV Files (*.csv)"
            )
            
        if not filename or not os.path.exists(filename):
            return False
        
        try:
            with open(filename, 'r', newline='') as f:
                # Lower-case headers so matching is case-insensitive
                rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                        for row in csv.DictReader(f)]
        except Exception as e:
            print(f"Error importing ROIs: {e}")
            return False

        required_fields = ["segment label", "slice index", "center x", "center y", "series uid"]
        header = rows[0].keys() if rows else []
        missing = [field for field in required_fields if field not in header]
        if not rows or missing or not ({"radius", "radius (px)"} & set(header)):
            print(f"Error: CSV is empty or missing required columns {missing or ['radius']}")
            return False

        # Switch to the scheme the ROIs were drawn with (this also clears existing ROIs)
        scheme = self._detect_scheme(rows, self.segmentation_scheme)
        if scheme != self.segmentation_scheme:
            print(f"Switching segmentation scheme to {scheme} to match imported ROIs")
            self.set_segmentation_scheme(scheme)
        else:
            self.clear_all_rois()
        
        series_path = self.dicom_model.current_series_path
        
        # Rebuild ROIs; statistics are recomputed from the image
        for i, row in enumerate(rows):
            try:
                if row["series uid"] != self.dicom_model.current_series_uid:
                    print(f"skipping row {i+1} because series path does not match current series")
                    continue
                
                if row["segment label"] not in self.segment_labels:
                    print(f"can't find correct segment labels for row {i+1}. maybe change segmentation scheme?")
                    continue

                slice_idx = int(row["slice index"])-1
                slice_data = self.dicom_model.get_slice(slice_idx, series_path)
                if slice_data is None:
                    print(f"skipping row {i+1}: slice {slice_idx+1} not in current series")
                    continue

                if row.get("radius (px)"):
                    radius_px = float(row["radius (px)"])
                else:
                    # Older files store radius as a fraction of the smaller image dimension
                    radius_px = float(row["radius"]) * min(slice_data.Rows, slice_data.Columns)
                segment = self.segment_labels.index(row["segment label"]) + 1

                roi = self.create_roi(series_path, slice_idx, segment,
                                      float(row["center x"]), float(row["center y"]), radius_px)
                if roi is not None:
                    self.add_roi(roi)
                                       
            except (ValueError, IndexError) as e:
                print(f"Error parsing ROI row {i+1}: {e}")
                # Continue with next row

        # Notify of changes
        self.rois_changed.emit()
        return True
    
    
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
            max_distance_mm (float): Maximum allowed distance from ROI center to target slice in mm
            
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
        
        target_series = self.dicom_model.get_series(target_series_path)
        
        # Get ROIs from source series
        source_rois = [roi for roi in self.rois if roi.series_path == source_series_path]
        
        if not source_rois:
            return False
        
        # Copy ROIs to target series
        new_rois = []

        for roi in source_rois:
            if roi.segment_label not in self.segment_labels:
                continue

            center = (roi.center_LR_mm, roi.center_AP_mm, roi.center_SI_mm)
            if np.isnan(center).any():
                continue

            # Find the target slice (same orientation) closest to the ROI center along the slice normal
            best_target_idx = None
            best_distance = float('inf')
            
            for target_idx, target_slice_data in enumerate(target_series):
                if get_orientation(target_slice_data) != roi.orientation:
                    continue

                distance = distance_to_slice(target_slice_data, center)
                
                # Only consider if within maximum distance threshold
                if distance <= max_distance_mm and distance < best_distance:
                    best_distance = distance
                    best_target_idx = target_idx
            
            if best_target_idx is None:
                continue

            target_slice_data = target_series[best_target_idx]

            # Convert ROI center (mm) to target image coordinates; keep physical radius
            target_center_x, target_center_y = patient_to_normalized(target_slice_data, *center)
            spacing_x, _ = get_pixel_spacing(target_slice_data)
            target_radius_px = np.sqrt(roi.area_mm2 / np.pi) / spacing_x

            new_roi = self.create_roi(target_series_path, best_target_idx, roi.segment,
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
