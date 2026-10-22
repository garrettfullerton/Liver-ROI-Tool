import os
from collections import OrderedDict

import pydicom
import numpy as np
from pydicom.errors import InvalidDicomError
from pydicom.multival import MultiValue
from pydicom.uid import ExplicitVRBigEndian, ExplicitVRLittleEndian, ImplicitVRLittleEndian
from PyQt5.QtCore import QObject, pyqtSignal

from roi_geometry import get_orientation, get_pixel_values
from app_config import CONFIG

def is_dicom_file(path):
    """True for files with a configured DICOM extension; if scan_all_files is enabled, also for any
    other file with the DICOM 'DICM' header (e.g. extensionless exports)"""
    name = os.path.basename(path)
    if os.path.splitext(name)[1].lower() in CONFIG["dicom_extensions"]:
        return True
    if not CONFIG["scan_all_files"] or name.startswith('.') or name.upper() == 'DICOMDIR':
        return False
    try:
        with open(path, 'rb') as f:
            f.seek(128)
            return f.read(4) == b'DICM'
    except OSError:
        return False


def read_dicom(path, stop_before_pixels=False):
    """Read a DICOM file, retrying without the standard header check (some exports lack the preamble)"""
    try:
        ds = pydicom.dcmread(path, stop_before_pixels=stop_before_pixels)
    except InvalidDicomError:
        ds = pydicom.dcmread(path, stop_before_pixels=stop_before_pixels, force=True)

    # Files without a file meta header have no Transfer Syntax UID, so pydicom can't decode their pixels;
    # fill it in from how the file was actually parsed (uncompressed data only)
    if 'TransferSyntaxUID' not in ds.file_meta:
        implicit_vr, little_endian = ds.original_encoding
        if implicit_vr is not None:
            ds.file_meta.TransferSyntaxUID = (ImplicitVRLittleEndian if implicit_vr else
                                              ExplicitVRLittleEndian if little_endian else ExplicitVRBigEndian)
    return ds


def list_dicom_files(directory, filenames=None):
    """Full paths of DICOM files directly inside a directory"""
    if filenames is None:
        filenames = os.listdir(directory)
    return [os.path.join(directory, f) for f in sorted(filenames) if is_dicom_file(os.path.join(directory, f))]


def sort_slices(series_data):
    """Order slices by position along the slice normal, in the same direction as InstanceNumber.

    Falls back to InstanceNumber when any slice lacks position/orientation information.
    """
    instance_numbers = [int(getattr(ds, 'InstanceNumber', 0) or 0) for ds in series_data]
    try:
        iop = np.array([float(v) for v in series_data[0].ImageOrientationPatient])
        normal = np.cross(iop[:3], iop[3:])
        positions = [float(np.dot([float(v) for v in ds.ImagePositionPatient], normal)) for ds in series_data]
    except (AttributeError, ValueError, TypeError):
        return [ds for _, ds in sorted(zip(instance_numbers, series_data), key=lambda pair: pair[0])]

    order = sorted(range(len(series_data)), key=lambda i: (positions[i], instance_numbers[i]))
    # Keep the conventional direction: reverse if instance numbers decrease along the normal
    sorted_positions = [positions[i] for i in order]
    sorted_instances = [instance_numbers[i] for i in order]
    if (np.std(sorted_positions) > 0 and np.std(sorted_instances) > 0
            and np.corrcoef(sorted_positions, sorted_instances)[0, 1] < 0):
        order.reverse()
    return [series_data[i] for i in order]


class DicomSeriesModel(QObject):
    """Model class for loading and managing DICOM data"""
    
    # Define signals
    series_loaded = pyqtSignal()
    slice_changed = pyqtSignal(int)  # Current slice index
    
    def __init__(self):
        super().__init__()
        self.current_series = None
        self.current_slice_index = 0
        self.series_data = OrderedDict()  # Recently read series (least recently used first), see read_series
        self.series_meta = {}  # Series-level info keyed by path (filled by header scan, then on load)
        self.value_ranges = {}  # (min, max) rescaled pixel values keyed by path
        self.directory_structure = {}  
        self.current_series_path = None
        self.default_window = 2000
        self.default_level = 0
        self.current_series_name = ""
        self.current_study_name = ""
        self.current_exam_number = 0
    
    def load_directory(self, root_dir):
        """Scan directory structure recursively and find DICOM series at any level"""
        if not os.path.exists(root_dir):
            return False
            
        self.directory_structure = {}
        
        # Recursively scan the directory to find DICOM files
        dicom_directories = self._find_dicom_directories(root_dir)

        # Read series headers (series number, exam, etc.)
        self._scan_series_headers(dicom_directories)

        # Organize series in the folder tree
        self._build_directory_tree(root_dir, dicom_directories)
        
        return True
    
    def _find_dicom_directories(self, root_dir):
        """Find all directories containing DICOM files"""
        dicom_dirs = []
        
        for root, dirs, files in os.walk(root_dir):
            # Check if directory contains DICOM files
            dicom_files = list_dicom_files(root, files)
            
            if dicom_files:
                # This directory contains DICOM files
                dicom_dirs.append({
                    'path': root,
                    'dicom_count': len(dicom_files),
                })
        
        return dicom_dirs

    def _build_directory_tree(self, root_dir, dicom_directories):
        """Folder tree as on disk: {folder name: {...}, series path: series path}.

        Each series sits in its parent folder; keying series by full path keeps a folder that holds
        DICOM files and also has series subfolders from clashing with those subfolders.
        """
        self.directory_structure = {}
        for dir_info in dicom_directories:
            path = dir_info['path']
            relative = os.path.relpath(path, root_dir)
            node = self.directory_structure
            for folder in ([] if relative == os.curdir else relative.split(os.sep)[:-1]):
                node = node.setdefault(folder, {})
            node[path] = path

    def _scan_series_headers(self, dicom_directories):
        """Read one header per series folder (no pixel data) so series can be labeled and grouped by exam"""
        for dir_info in dicom_directories:
            path = dir_info['path']
            if path in self.series_meta:
                continue
            for dicom_file in list_dicom_files(path):
                try:
                    ds = read_dicom(dicom_file, stop_before_pixels=True)
                    self.series_meta[path] = self._extract_meta(ds)
                    break
                except Exception as e:
                    print(f"Error reading header {dicom_file}: {e}")

    @staticmethod
    def _tag(ds, name, default=""):
        """Return a DICOM attribute value, taking the first item of multi-valued attributes"""
        value = getattr(ds, name, default)
        if isinstance(value, MultiValue):
            value = value[0] if len(value) else default
        return value

    @staticmethod
    def _format_date(value):
        """YYYYMMDD -> YYYY-MM-DD (leaves other formats unchanged)"""
        value = str(value)
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 and value.isdigit() else value

    @staticmethod
    def _format_time(value):
        """HHMMSS(.ffffff) -> HH:MM:SS(.ffffff) so spreadsheets don't strip leading zeros"""
        value = str(value)
        if len(value) >= 6 and value[:6].isdigit():
            return f"{value[:2]}:{value[2:4]}:{value[4:]}"
        return value

    def _extract_meta(self, ds):
        """Series-level information stored with each ROI"""
        pixel_spacing = getattr(ds, 'PixelSpacing', [None, None])
        meta = {
            'PatientID': str(self._tag(ds, 'PatientID')),
            'StudyID': str(self._tag(ds, 'StudyID')),
            'StudyInstanceUID': str(self._tag(ds, 'StudyInstanceUID')),
            'StudyDate': self._format_date(self._tag(ds, 'StudyDate')),
            'AccessionNumber': str(self._tag(ds, 'AccessionNumber')),
            'SeriesInstanceUID': str(self._tag(ds, 'SeriesInstanceUID')),
            'SeriesDescription': str(self._tag(ds, 'SeriesDescription')),
            'SeriesNumber': self._tag(ds, 'SeriesNumber', None),
            'SeriesDate': self._format_date(self._tag(ds, 'SeriesDate')),
            'SeriesTime': self._format_time(self._tag(ds, 'SeriesTime')),
            'Modality': str(self._tag(ds, 'Modality')),
            'Manufacturer': str(self._tag(ds, 'Manufacturer')),
            'ManufacturerModelName': str(self._tag(ds, 'ManufacturerModelName')),
            'MagneticFieldStrength': self._tag(ds, 'MagneticFieldStrength', None),
            'RepetitionTime': self._tag(ds, 'RepetitionTime', None),
            'EchoTime': self._tag(ds, 'EchoTime', None),
            'FlipAngle': self._tag(ds, 'FlipAngle', None),
            'EchoNumbers': self._tag(ds, 'EchoNumbers', None),
            'SliceThickness': self._tag(ds, 'SliceThickness', None),
            'PixelSpacingRow': pixel_spacing[0],
            'PixelSpacingCol': pixel_spacing[1],
            'Rows': int(self._tag(ds, 'Rows', 0)),
            'Columns': int(self._tag(ds, 'Columns', 0)),
            'WindowCenter': None,
            'WindowWidth': None,
            'Orientation': get_orientation(ds),
        }
        if hasattr(ds, 'WindowCenter') and hasattr(ds, 'WindowWidth'):
            meta['WindowCenter'] = float(self._tag(ds, 'WindowCenter'))
            meta['WindowWidth'] = float(self._tag(ds, 'WindowWidth'))
        return meta

    def get_slice_meta(self, index, series_path=None):
        """Slice-level information stored with each ROI"""
        ds = self.get_slice(index, series_path)
        if ds is None:
            return {}
        return {
            'InstanceNumber': self._tag(ds, 'InstanceNumber', None),
            'SliceLocation': self._tag(ds, 'SliceLocation', None),
            'AcquisitionTime': self._format_time(self._tag(ds, 'AcquisitionTime')),
        }

    def read_series(self, series_path):
        """Read (or return cached) slices of a series without making it the current series.

        Only the current series and the most recently read ones (max_cached_series) stay in memory;
        keeping every opened series made large multi-exam folders run out of memory.
        """
        if series_path in self.series_data:
            self.series_data.move_to_end(series_path)
            return self.series_data[series_path]

        if not os.path.exists(series_path):
            return None
            
        # Load all DICOM files in the series
        dicom_files = list_dicom_files(series_path)
        
        series_data = []
        for dicom_file in dicom_files:
            try:
                series_data.append(read_dicom(dicom_file))
            except Exception as e:
                print(f"Error loading {dicom_file}: {e}")
        
        if not series_data:
            return None

        # Sort by slice position (consistent with instance number order)
        series_data = sort_slices(series_data)
            
        # Store the series data, releasing the least recently used series (never the current one)
        self.series_data[series_path] = series_data
        self.series_meta[series_path] = self._extract_meta(series_data[0])
        for old_path in list(self.series_data):
            if len(self.series_data) <= max(CONFIG["max_cached_series"], 2):
                break
            if old_path not in (series_path, self.current_series_path):
                del self.series_data[old_path]
        
        return series_data

    def load_series(self, series_path, slice_index=0):
        """Load a specific series and make it the current series, starting at slice_index"""
        series_data = self.read_series(series_path)
        if not series_data:
            return False

        meta = self.series_meta[series_path]
        self.current_series = series_data
        self.current_series_path = series_path
        self.current_slice_index = min(max(slice_index, 0), len(series_data) - 1)
        self.current_study_name = meta['PatientID']
        self.current_exam_number = meta['StudyID']
        self.current_series_name = meta['SeriesDescription']

        if meta['WindowCenter'] is not None:
            self.default_level = meta['WindowCenter']
            self.default_window = meta['WindowWidth']
        else:
            # No window tags: show the full range of the data
            value_min, value_max = self.get_value_range(series_path)
            self.default_level = (value_min + value_max) / 2
            self.default_window = max(1, value_max - value_min)
        
        # Emit signal that series has been loaded
        self.series_loaded.emit()
        
        return True

    def get_series_label(self, series_path):
        """Human-readable series name: '#<SeriesNumber> <SeriesDescription>' (falls back to folder name)"""
        meta = self.series_meta.get(series_path, {})
        description = meta.get('SeriesDescription') or os.path.basename(series_path)
        number = meta.get('SeriesNumber')
        return f"#{number} {description}" if number not in (None, "") else description

    def series_sort_key(self, series_path):
        """Sort key ordering series by SeriesNumber, then label"""
        number = self.series_meta.get(series_path, {}).get('SeriesNumber')
        try:
            return (0, int(number), self.get_series_label(series_path))
        except (TypeError, ValueError):
            return (1, 0, self.get_series_label(series_path))

    def get_exam_key(self, series_path):
        """Identifier of the exam a series belongs to (StudyInstanceUID, else its parent folder)"""
        return self.series_meta.get(series_path, {}).get('StudyInstanceUID') or os.path.dirname(series_path)

    def get_exam_label(self, series_path):
        """Human-readable exam name: '<PatientID> / exam <StudyID>'"""
        meta = self.series_meta.get(series_path, {})
        patient = meta.get('PatientID') or os.path.basename(os.path.dirname(series_path))
        return f"{patient} / exam {meta.get('StudyID')}" if meta.get('StudyID') else patient

    def get_exam_series(self, series_path):
        """All known series in the same exam (StudyInstanceUID) as series_path, sorted by series number"""
        study_uid = self.series_meta.get(series_path, {}).get('StudyInstanceUID')
        paths = [path for path, meta in self.series_meta.items()
                 if study_uid and meta.get('StudyInstanceUID') == study_uid]
        if series_path not in paths:
            paths.append(series_path)
        return sorted(paths, key=self.series_sort_key)

    def get_series(self, series_path):
        """Return the slices of a series (read from disk if not in memory)"""
        return self.read_series(series_path) or []

    def get_value_range(self, series_path=None):
        """(min, max) of rescaled pixel values over a series (cached)"""
        if series_path is None:
            series_path = self.current_series_path
        if series_path not in self.value_ranges:
            values = [get_pixel_values(ds) for ds in self.get_series(series_path)] if series_path else []
            if not values:
                return (0, 0)
            self.value_ranges[series_path] = (float(min(v.min() for v in values)),
                                              float(max(v.max() for v in values)))
        return self.value_ranges[series_path]

    def get_series_meta(self, series_path=None):
        """Return series-level information (defaults to current series)"""
        if series_path is None:
            series_path = self.current_series_path
        return self.series_meta.get(series_path, {})
    
    def get_current_slice(self):
        """Return current slice data"""
        return self.get_slice(self.current_slice_index)
    
    def get_slice(self, index, series_path=None):
        """Return slice at specified index (defaults to current series)"""
        series = self.current_series if series_path is None else self.read_series(series_path)
        if not series or not 0 <= index < len(series):
            return None
            
        return series[index]
    
    def get_slice_pixel_data(self, index, series_path=None):
        """Return rescaled pixel data for slice at specified index (defaults to current series)"""
        slice_data = self.get_slice(index, series_path)
        if slice_data is None:
            return None
            
        return get_pixel_values(slice_data)
    
    def next_slice(self):
        """Move to next slice"""
        if not self.current_series:
            return False
            
        if self.current_slice_index < len(self.current_series) - 1:
            self.current_slice_index += 1
            self.slice_changed.emit(self.current_slice_index)
            return True
            
        return False
    
    def previous_slice(self):
        """Move to previous slice"""
        if not self.current_series:
            return False
            
        if self.current_slice_index > 0:
            self.current_slice_index -= 1
            self.slice_changed.emit(self.current_slice_index)
            return True
            
        return False
    
    def set_slice_index(self, index):
        """Set the current slice index"""
        if not self.current_series:
            return False
            
        if 0 <= index < len(self.current_series):
            self.current_slice_index = index
            self.slice_changed.emit(self.current_slice_index)
            return True
            
        return False
    
    def get_num_slices(self):
        """Get the number of slices in the current series"""
        if not self.current_series:
            return 0
            
        return len(self.current_series)
    
    def get_directory_structure(self):
        """Return the folder tree: {folder name: {...}, series path: series path}"""
        return self.directory_structure
    
    def get_current_series_path(self):
        """Return the path to the current series"""
        return self.current_series_path
