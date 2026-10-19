import os
import re
import numpy as np
import csv
from dataclasses import dataclass, field
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from schemes import SCHEMES, DEFAULT_SCHEME, CUSTOM_PREFIX, register_custom_scheme, save_custom_schemes, default_custom_label
from app_config import CONFIG, VERSION_STRING, get_settings
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
    edge_diff: float = float('nan')  # |inner-half mean - outer-ring mean| / median
    reader: str = ""
    drawn_at: str = ""  # when the ROI was drawn or last edited (ISO format)

    @property
    def cv(self):
        """Coefficient of variation (std / |mean|)"""
        return self.std_val / abs(self.mean_val) if self.mean_val else float('nan')

    @property
    def flags(self):
        """Quality warnings (thresholds set in liver_roi_config.json)"""
        flags = []
        cv_threshold = CONFIG["cv_warning_threshold"]
        if cv_threshold and self.cv > cv_threshold:
            flags.append(f"high CV ({self.cv:.2f})")
        edge_threshold = CONFIG["edge_warning_threshold"]
        if edge_threshold and self.edge_diff > edge_threshold:
            flags.append(f"edge/heterogeneity ({self.edge_diff:.0%})")
        return "; ".join(flags)

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
    ("CV", lambda r: r.cv),
    ("Flags", lambda r: r.flags),
    ("Locked", None),  # filled from ROIManager lock state
    ("Reader", lambda r: r.reader),
    ("Drawn At", lambda r: r.drawn_at),
    ("App Version", lambda r: VERSION_STRING),
    # Full ordered label list, so imports can recreate custom layouts exactly
    ("Scheme Labels", lambda r: " | ".join(SCHEMES[r.scheme]["labels"]) if r.scheme in SCHEMES else ""),
]


def safe_filename(text):
    """Make a string safe to use in a file name"""
    return re.sub(r'[^\w.-]+', '_', str(text)).strip('_') or "ROIs"


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
    message = pyqtSignal(str, bool)  # text, is_error (shown in the status bar / a warning dialog)
    saved = pyqtSignal()  # no unexported changes remain (all changed series written to a user CSV)
    schemes_updated = pyqtSignal()  # a custom layout was added (e.g. recreated from an imported file)
    
    def __init__(self, dicom_model):
        super().__init__()
        self.dicom_model = dicom_model
        self.rois = []  # List of ROI objects
        self.current_segment = 0
        self.segmentation_scheme = DEFAULT_SCHEME
        self.segment_labels = SCHEMES[DEFAULT_SCHEME]["labels"]
        self.unsaved_series = set()  # series with changes not yet exported
        self.locked_series = set()  # series protected from edits
        self.reader = ""  # reader initials recorded with new ROIs

    def _changed(self, series_paths):
        """Record unexported changes for series and notify listeners"""
        self.unsaved_series |= set(series_paths)
        self.rois_changed.emit()

    def mark_saved(self, series_paths):
        """Mark series as exported; emits saved when nothing unexported remains"""
        self.unsaved_series -= set(series_paths)
        if not self.unsaved_series:
            self.saved.emit()

    def is_locked(self, series_path):
        return series_path in self.locked_series

    def set_locked(self, series_path, locked):
        """Lock/unlock a series against ROI edits"""
        if locked == self.is_locked(series_path):
            return
        if locked:
            self.locked_series.add(series_path)
        else:
            self.locked_series.discard(series_path)
        self._changed({series_path})

    def refuse_if_locked(self, series_path):
        if self.is_locked(series_path):
            self.message.emit("This series is locked; unlock it (Ctrl+L) to change its ROIs", False)
            return True
        return False
    
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
                   reader=self.reader,
                   drawn_at=datetime.now().isoformat(timespec='seconds'),
                   **stats)

    def add_roi(self, roi):
        """Add a new ROI, replacing any ROI of the same segment in the same series"""
        if self.refuse_if_locked(roi.series_path):
            return False
        self.rois = [r for r in self.rois
                     if not (r.segment == roi.segment and r.series_path == roi.series_path)]
        self.rois.append(roi)
        if roi.flags:
            self.message.emit(f"Check ROI {roi.segment_label}: {roi.flags}", False)
        self._changed({roi.series_path})
        return True
    
    def delete_roi(self, roi_index):
        """Delete a specific ROI"""
        if 0 <= roi_index < len(self.rois):
            series_path = self.rois[roi_index].series_path
            if self.refuse_if_locked(series_path):
                return False
            del self.rois[roi_index]
            self._changed({series_path})
            return True
        return False
    
    def delete_last_roi(self):
        """Remove the most recently added ROI on the current slice of the current series"""
        current_slice_rois = [i for i, roi in enumerate(self.rois)
                              if roi.slice_idx == self.dicom_model.current_slice_index
                              and roi.series_path == self.dicom_model.current_series_path]
        
        if current_slice_rois:
            # ROIs are kept in the order they were added
            return self.delete_roi(current_slice_rois[-1])
        
        return False
    
    def clear_all_rois(self):
        """Clear all ROIs (including locked series) and remove all locks"""
        if self.rois:
            series_paths = {roi.series_path for roi in self.rois}
            self.rois = []
            self.locked_series.clear()
            self._changed(series_paths)
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
    
    def default_export_name(self, series_paths=None, suffix="ROIs"):
        """Default file name '<PatientID>_<StudyID>_<scheme>_<suffix>.csv' for an exam (or the current series)"""
        series_path = sorted(series_paths)[0] if series_paths else self.dicom_model.current_series_path
        meta = self.dicom_model.get_series_meta(series_path)
        parts = [meta.get('PatientID') or self.dicom_model.current_study_name,
                 meta.get('StudyID') or self.dicom_model.current_exam_number,
                 self.segmentation_scheme, suffix]
        return "_".join(safe_filename(part) for part in parts if part) + ".csv"

    def _ask_save_path(self, title, default_name):
        """File dialog starting in the last export folder"""
        settings = get_settings()
        filename, _ = QFileDialog.getSaveFileName(
            None, title, os.path.join(settings.value("last_export_dir", ""), default_name), "CSV Files (*.csv)")
        if filename:
            settings.setValue("last_export_dir", os.path.dirname(filename))
        return filename

    def export_rois(self, filename=None, series_paths=None):
        """Export ROIs to a CSV file (all series, or only series_paths)"""
        rois = [roi for roi in self.rois if series_paths is None or roi.series_path in series_paths]
        if not rois:
            self.message.emit("No ROIs to export", True)
            return False
            
        if filename is None:
            filename = self._ask_save_path("Save ROIs", self.default_export_name(series_paths))
            
        if not filename:
            return False
        
        if not filename.lower().endswith('.csv'):
            filename += '.csv'
        
        try:
            self.write_csv(filename, series_paths)
            n_series = len({roi.series_path for roi in rois})
            self.message.emit(f"Exported {len(rois)} ROIs from {n_series} series to {os.path.basename(filename)}", False)
            self.mark_saved(self.unsaved_series if series_paths is None else series_paths)
            return True
        except Exception as e:
            self.message.emit(f"Error exporting ROIs: {e}", True)
            return False

    def write_csv(self, filename, series_paths=None):
        """Write ROIs (all, or only those in series_paths) to a CSV file, one row per ROI"""
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([header for header, _ in EXPORT_COLUMNS])
            for roi in self.rois:
                if series_paths is not None and roi.series_path not in series_paths:
                    continue
                writer.writerow(self.export_row(roi))

    def export_row(self, roi):
        """Formatted values of EXPORT_COLUMNS for one ROI"""
        return [("yes" if self.is_locked(roi.series_path) else "") if getter is None else format_value(getter(roi))
                for _, getter in EXPORT_COLUMNS]

    def export_wide(self, filename=None):
        """Export a summary CSV with one row per series and columns per segment"""
        if not self.rois:
            self.message.emit("No ROIs to export", True)
            return False

        if filename is None:
            filename = self._ask_save_path("Save Summary", self.default_export_name(suffix="summary"))
        if not filename:
            return False
        if not filename.lower().endswith('.csv'):
            filename += '.csv'

        series_columns = [("Study ID", 'PatientID'), ("Exam Number", 'StudyID'), ("Series Number", 'SeriesNumber'),
                          ("Series ID", 'SeriesDescription'), ("Series Date", 'SeriesDate'),
                          ("Series Time", 'SeriesTime'), ("Series UID", 'SeriesInstanceUID')]
        stat_columns = [("Mean", lambda r: r.mean_val), ("Median", lambda r: r.median_val),
                        ("Std", lambda r: r.std_val), ("CV", lambda r: r.cv), ("Area (mm2)", lambda r: r.area_mm2),
                        ("Slice", lambda r: r.slice_idx + 1)]

        header = ([name for name, _ in series_columns] + ["Series Path", "Scheme"]
                  + [f"{label} {stat}" for label in self.segment_labels for stat, _ in stat_columns])
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(header)
                for series_path in sorted(self.get_series_with_rois(), key=self.dicom_model.series_sort_key):
                    meta = self.dicom_model.get_series_meta(series_path)
                    rois_by_segment = {roi.segment: roi for roi in self.rois if roi.series_path == series_path}
                    row = [format_value(meta.get(key)) for _, key in series_columns] + [series_path, self.segmentation_scheme]
                    for segment in range(1, len(self.segment_labels) + 1):
                        roi = rois_by_segment.get(segment)
                        row += [format_value(getter(roi)) if roi else "" for _, getter in stat_columns]
                    writer.writerow(row)
            self.message.emit(f"Exported summary of {len(self.get_series_with_rois())} series to {os.path.basename(filename)}", False)
            return True
        except Exception as e:
            self.message.emit(f"Error exporting summary: {e}", True)
            return False

    def _detect_scheme(self, rows, current_scheme):
        """Pick the scheme for imported rows: 'Scheme' column if present, otherwise infer from labels"""
        self._register_imported_custom_schemes(rows)
        schemes = [row["scheme"] for row in rows if row.get("scheme") in SCHEMES]
        if schemes:
            counts = {scheme: schemes.count(scheme) for scheme in set(schemes)}
            if len(counts) > 1:
                self.message.emit(f"File contains ROIs from several schemes {counts}; "
                                  f"only {max(counts, key=counts.get)} ROIs can be imported", True)
            return max(counts, key=counts.get)

        # Older files: choose a scheme containing every label (prefer the current scheme)
        labels = {row.get("segment label") for row in rows}
        candidates = [current_scheme] + [scheme for scheme in SCHEMES if scheme != current_scheme]
        for scheme in candidates:
            if labels <= set(SCHEMES[scheme]["labels"]):
                return scheme
        return current_scheme
        
    def _register_imported_custom_schemes(self, rows):
        """Recreate custom layouts named in the file that don't exist on this computer"""
        for scheme in {row.get("scheme", "") for row in rows}:
            if not scheme.startswith(CUSTOM_PREFIX) or scheme in SCHEMES:
                continue
            scheme_rows = [row for row in rows if row.get("scheme") == scheme]
            full_labels = next((row["scheme labels"] for row in scheme_rows if row.get("scheme labels")), "")
            if full_labels:
                labels = [label.strip() for label in full_labels.split(" | ")]
            else:
                # Older files: rebuild from the labels that have ROIs
                labels_by_index = {}
                for row in scheme_rows:
                    try:
                        labels_by_index[int(row["segment index"])] = row["segment label"]
                    except (KeyError, ValueError):
                        pass
                if not labels_by_index:
                    continue
                labels = [labels_by_index.get(i, default_custom_label(i)) for i in range(1, max(labels_by_index) + 1)]
            register_custom_scheme(scheme[len(CUSTOM_PREFIX):], labels)
            save_custom_schemes()
            self.schemes_updated.emit()
            self.message.emit(f"Added custom layout '{scheme[len(CUSTOM_PREFIX):]}' from the imported file", False)

    def _ask_import_mode(self, scheme):
        """Ask whether imported ROIs replace or merge with existing ones; returns 'replace', 'merge' or None"""
        if not self.rois:
            return "replace"

        if scheme != self.segmentation_scheme:
            answer = QMessageBox.question(
                None, "Import ROIs",
                f"The file uses the {SCHEMES[scheme]['display_name']} scheme. Importing will switch to it "
                f"and clear the {len(self.rois)} current ROIs. Continue?")
            return "replace" if answer == QMessageBox.Yes else None

        box = QMessageBox(QMessageBox.Question, "Import ROIs",
                          f"There are {len(self.rois)} ROIs already loaded.\n\n"
                          "Replace: clear them and load the file.\n"
                          "Merge: keep them; imported ROIs replace the same segment in the same series.")
        replace_button = box.addButton("Replace", QMessageBox.DestructiveRole)
        merge_button = box.addButton("Merge", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        if box.clickedButton() == replace_button:
            return "replace"
        if box.clickedButton() == merge_button:
            return "merge"
        return None
        
    def import_rois(self, filename=None, mode=None):
        """Import ROIs from a CSV file (exported by any version of this tool) into all matching series.

        mode: 'replace' or 'merge' existing ROIs; None asks the user when ROIs already exist.
        """
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
            self.message.emit(f"Error importing ROIs: {e}", True)
            return False

        required_fields = ["segment label", "slice index", "center x", "center y", "series uid"]
        header = rows[0].keys() if rows else []
        missing = [field for field in required_fields if field not in header]
        if not rows or missing or not ({"radius", "radius (px)"} & set(header)):
            self.message.emit(f"Cannot import: CSV is empty or missing required columns {missing or ['radius']}", True)
            return False

        scheme = self._detect_scheme(rows, self.segmentation_scheme)

        if mode is None:
            mode = self._ask_import_mode(scheme)
            if mode is None:
                return False

        # Switch to the scheme the ROIs were drawn with (this also clears existing ROIs)
        if scheme != self.segmentation_scheme:
            self.set_segmentation_scheme(scheme)
        elif mode == "replace":
            self.clear_all_rois()

        # Match rows to series in the opened folder by Series Instance UID
        uid_to_path = {meta.get('SeriesInstanceUID'): path
                       for path, meta in self.dicom_model.series_meta.items()}
        imported, imported_series, skipped = 0, set(), {}
        lock_after_import = set()
        skip = lambda reason: skipped.__setitem__(reason, skipped.get(reason, 0) + 1)
        
        # Rebuild ROIs; statistics are recomputed from the image
        for i, row in enumerate(rows):
            try:
                series_path = uid_to_path.get(row["series uid"])
                if series_path is None or not self.dicom_model.read_series(series_path):
                    skip("series not in opened folder")
                    continue

                if self.is_locked(series_path):
                    skip("series locked")
                    continue
                
                if row["segment label"] not in self.segment_labels:
                    skip("label not in scheme")
                    continue

                slice_idx = int(row["slice index"])-1
                slice_data = self.dicom_model.get_slice(slice_idx, series_path)
                if slice_data is None:
                    skip("slice not in series")
                    continue

                if row.get("radius (px)"):
                    radius_px = float(row["radius (px)"])
                else:
                    # Older files store radius as a fraction of the smaller image dimension
                    radius_px = float(row["radius"]) * min(slice_data.Rows, slice_data.Columns)
                segment = self.segment_labels.index(row["segment label"]) + 1

                roi = self.create_roi(series_path, slice_idx, segment,
                                      float(row["center x"]), float(row["center y"]), radius_px)
                if roi is None:
                    skip("outside image")
                    continue
                # Keep who drew the ROI and when, if recorded in the file
                roi.reader = row.get("reader") or roi.reader
                roi.drawn_at = row.get("drawn at") or roi.drawn_at
                self.add_roi(roi)
                imported += 1
                imported_series.add(series_path)
                if row.get("locked", "").lower() == "yes":
                    lock_after_import.add(series_path)
                                       
            except (ValueError, IndexError):
                skip("unreadable row")

        self.locked_series |= lock_after_import
        if mode == "replace" and imported:
            # The ROIs now match the file
            self.mark_saved(set(self.unsaved_series))

        summary = f"Imported {imported} ROIs into {len(imported_series)} series"
        if skipped:
            summary += "; skipped " + ", ".join(f"{n} ({reason})" for reason, n in skipped.items())
        self.message.emit(summary, imported == 0)

        # Notify of changes
        self.rois_changed.emit()
        return True
    
    
    def copy_rois_from_series(self, source_series_path, target_series_path=None, max_distance_mm=5.0):
        """
        Copy ROIs from source to target series based on anatomical coordinates
        
        Args:
            source_series_path (str): Path to source series
            target_series_path (str): Path to target series (defaults to current series)
            max_distance_mm (float): Maximum allowed distance from ROI center to target slice in mm
            
        Returns:
            dict: 'copied' (number of ROIs copied), 'skipped' (reason -> count), 'error' (str or None)
        """
        result = {'copied': 0, 'skipped': {}, 'error': None}
        skip = lambda reason: result['skipped'].__setitem__(reason, result['skipped'].get(reason, 0) + 1)

        if target_series_path is None:
            target_series_path = self.dicom_model.get_current_series_path()
        
        if not source_series_path or not target_series_path or source_series_path == target_series_path:
            result['error'] = "invalid source/target series"
            return result

        if self.is_locked(target_series_path):
            result['error'] = "series is locked"
            return result

        # Make sure both series are read (target need not be the displayed series)
        if not self.dicom_model.read_series(source_series_path) or not self.dicom_model.read_series(target_series_path):
            result['error'] = "could not read series"
            return result
        
        target_series = self.dicom_model.get_series(target_series_path)
        target_orientations = {get_orientation(ds) for ds in target_series}
        
        # Get ROIs from source series
        source_rois = [roi for roi in self.rois if roi.series_path == source_series_path]
        
        if not source_rois:
            result['error'] = "source series has no ROIs"
            return result
        
        # Copy ROIs to target series
        new_rois = []

        for roi in source_rois:
            if roi.segment_label not in self.segment_labels:
                skip("label not in current scheme")
                continue

            center = (roi.center_LR_mm, roi.center_AP_mm, roi.center_SI_mm)
            if np.isnan(center).any():
                skip("no position information")
                continue

            if roi.orientation not in target_orientations:
                skip("different slice orientation")
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
                skip(f"no slice within {max_distance_mm:g} mm")
                continue

            target_slice_data = target_series[best_target_idx]

            # Convert ROI center (mm) to target image coordinates; keep physical radius
            target_center_x, target_center_y = patient_to_normalized(target_slice_data, *center)
            spacing_x, _ = get_pixel_spacing(target_slice_data)
            target_radius_px = np.sqrt(roi.area_mm2 / np.pi) / spacing_x

            new_roi = self.create_roi(target_series_path, best_target_idx, roi.segment,
                                      target_center_x, target_center_y, target_radius_px)
            if new_roi is None:
                skip("outside target image")
                continue
            new_rois.append(new_roi)
        
        # Add new ROIs, replacing any ROI with the same segment in the target series
        for new_roi in new_rois:
            self.rois = [r for r in self.rois
                         if not (r.segment == new_roi.segment and r.series_path == target_series_path)]
            self.rois.append(new_roi)

        # Update display
        self._changed({target_series_path} if new_rois else set())
        
        result['copied'] = len(new_rois)
        return result

    def get_series_with_rois(self):
        """Paths of all series that currently have ROIs"""
        return sorted({roi.series_path for roi in self.rois})
