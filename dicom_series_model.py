import os
import pydicom
from pydicom.multival import MultiValue
from PyQt5.QtCore import QObject, pyqtSignal

from roi_geometry import get_orientation, get_pixel_values

class DicomSeriesModel(QObject):
    """Model class for loading and managing DICOM data"""
    
    # Define signals
    series_loaded = pyqtSignal()
    slice_changed = pyqtSignal(int)  # Current slice index
    
    def __init__(self):
        super().__init__()
        self.current_series = None
        self.current_slice_index = 0
        self.series_data = {}  # Dictionary of loaded series
        self.series_meta = {}  # Series-level info keyed by path (filled by header scan, then on load)
        self.anatomical_positions = {}  # Mapping of anatomical positions
        self.directory_structure = {}  
        self.current_series_path = None
        self.default_window = 2000
        self.default_level = 0
        self.current_series_name = ""
        self.current_study_name = ""
        self.current_exam_number = 0
        self.current_series_uid = ""
    
    def load_directory(self, root_dir):
        """Scan directory structure recursively and find DICOM series at any level"""
        if not os.path.exists(root_dir):
            return False
            
        self.directory_structure = {}
        
        # Recursively scan the directory to find DICOM files
        dicom_directories = self._find_dicom_directories(root_dir)
        
        # Organize found directories in a tree structure
        self._build_directory_tree(dicom_directories)

        # Read series headers (series number, exam, etc.)
        self._scan_series_headers(dicom_directories)
        
        return True
    
    def _find_dicom_directories(self, root_dir):
        """Find all directories containing DICOM files"""
        dicom_dirs = []
        
        for root, dirs, files in os.walk(root_dir):
            # Check if directory contains DICOM files
            dicom_files = [f for f in files if f.endswith('.dcm') or f.endswith('.DCM') or f.endswith('.sdcopen')]
            
            if dicom_files:
                # This directory contains DICOM files
                dicom_dirs.append({
                    'path': root,
                    'dicom_count': len(dicom_files),
                    # Get relative path components for tree structure
                    'components': os.path.relpath(root, root_dir).split(os.sep)
                })
        
        return dicom_dirs

    def _build_directory_tree(self, dicom_directories):
        """Build a tree structure from found DICOM directories"""
        # Group directories by their top-level component
        top_level_groups = {}
        
        for dir_info in dicom_directories:
            components = dir_info['components']
            if components[0] == '.':  # Root directory
                top_level = 'Root'
            else:
                top_level = components[0]
                
            if top_level not in top_level_groups:
                top_level_groups[top_level] = []
                
            top_level_groups[top_level].append(dir_info)
        
        # Build the tree structure
        self.directory_structure = {}
        
        # Get top-level keys in alphabetical order
        sorted_top_level = sorted(top_level_groups.keys())
        
        for top_level in sorted_top_level:
            self.directory_structure[top_level] = {}
            dirs = top_level_groups[top_level]
            
            for dir_info in dirs:
                components = dir_info['components']
                path = dir_info['path']
                
                # Skip the top-level component (already used)
                if components[0] == '.':
                    # Handle root directory specially
                    name = os.path.basename(path)
                    self.directory_structure[top_level][name] = path
                elif len(components) == 1:
                    # Single level deep, add directly
                    self.directory_structure[top_level][components[0]] = path
                else:
                    # Create intermediate levels
                    current_level = self.directory_structure[top_level]
                    for i in range(1, len(components)):
                        component = components[i]
                        
                        if i == len(components) - 1:
                            # Last component, store the path
                            current_level[component] = path
                        else:
                            # Intermediate level, create if needed
                            if component not in current_level:
                                current_level[component] = {}
                            
                            current_level = current_level[component]
   
    def _scan_series_headers(self, dicom_directories):
        """Read one header per series folder (no pixel data) so series can be labeled and grouped by exam"""
        for dir_info in dicom_directories:
            path = dir_info['path']
            if path in self.series_meta:
                continue
            for f in sorted(os.listdir(path)):
                if self._is_dicom_filename(f):
                    try:
                        ds = pydicom.dcmread(os.path.join(path, f), stop_before_pixels=True)
                        self.series_meta[path] = self._extract_meta(ds)
                        break
                    except Exception as e:
                        print(f"Error reading header {f}: {e}")

    @staticmethod
    def _is_dicom_filename(filename):
        return filename.endswith('.dcm') or filename.endswith('.DCM')

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
        """Read (or return cached) slices of a series without making it the current series"""
        if series_path in self.series_data:
            return self.series_data[series_path]

        if not os.path.exists(series_path):
            return None
            
        # Load all DICOM files in the series
        dicom_files = [os.path.join(series_path, f) for f in os.listdir(series_path) 
                      if self._is_dicom_filename(f)]
        
        series_data = []
        for dicom_file in dicom_files:
            try:
                series_data.append(pydicom.dcmread(dicom_file))
            except Exception as e:
                print(f"Error loading {dicom_file}: {e}")
        
        if not series_data:
            return None

        # Sort by instance number if available
        series_data.sort(key=lambda x: getattr(x, 'InstanceNumber', 0))
            
        # Store the series data
        self.series_data[series_path] = series_data
        self.series_meta[series_path] = self._extract_meta(series_data[0])
        
        # Update anatomical positions for this series
        self.update_anatomical_positions(series_path)
        
        return series_data

    def load_series(self, series_path):
        """Load a specific series and make it the current series"""
        series_data = self.read_series(series_path)
        if not series_data:
            return False

        meta = self.series_meta[series_path]
        self.current_series = series_data
        self.current_series_path = series_path
        self.current_slice_index = 0
        self.current_study_name = meta['PatientID']
        self.current_exam_number = meta['StudyID']
        self.current_series_name = meta['SeriesDescription']
        self.current_series_uid = meta['SeriesInstanceUID']

        if meta['WindowCenter'] is not None:
            self.default_level = meta['WindowCenter']
            self.default_window = meta['WindowWidth']
        else:
            self.default_level = 0
            self.default_window = 2000
        
        # Emit signal that series has been loaded
        self.series_loaded.emit()
        
        return True

    def get_series_label(self, series_path):
        """Human-readable series name: '#<SeriesNumber> <SeriesDescription>' (falls back to folder name)"""
        meta = self.series_meta.get(series_path, {})
        description = meta.get('SeriesDescription') or os.path.basename(series_path)
        number = meta.get('SeriesNumber')
        return f"#{number} {description}" if number not in (None, "") else description

    def _series_number_key(self, series_path):
        """Sort key ordering series by SeriesNumber, then label"""
        number = self.series_meta.get(series_path, {}).get('SeriesNumber')
        try:
            return (0, int(number), self.get_series_label(series_path))
        except (TypeError, ValueError):
            return (1, 0, self.get_series_label(series_path))

    def get_exam_series(self, series_path):
        """All known series in the same exam (StudyInstanceUID) as series_path, sorted by series number"""
        study_uid = self.series_meta.get(series_path, {}).get('StudyInstanceUID')
        paths = [path for path, meta in self.series_meta.items()
                 if study_uid and meta.get('StudyInstanceUID') == study_uid]
        if series_path not in paths:
            paths.append(series_path)
        return sorted(paths, key=self._series_number_key)

    def get_series(self, series_path):
        """Return the (already read) slices of a series"""
        return self.series_data.get(series_path, [])

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
        series = self.current_series if series_path is None else self.series_data.get(series_path)
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
    
    def update_anatomical_positions(self, series_path):
        """Map anatomical positions for a series"""
        if series_path not in self.anatomical_positions:
            self.anatomical_positions[series_path] = {}
            
            # Map slice indices to anatomical positions
            for idx, ds in enumerate(self.series_data[series_path]):
                if hasattr(ds, 'ImagePositionPatient'):
                    pos = ds.ImagePositionPatient
                    self.anatomical_positions[series_path][idx] = pos
                else:
                    # If no position info, use slice index as z-coordinate
                    self.anatomical_positions[series_path][idx] = (0, 0, idx)
    
    def get_directory_structure(self):
        """Return the directory structure"""
        return self.directory_structure
    
    def get_current_series_path(self):
        """Return the path to the current series"""
        return self.current_series_path
    
    def get_anatomical_positions(self):
        """Return the anatomical positions mapping"""
        return self.anatomical_positions
    
    def get_slice_orientations(self, series_path):
        """Return the slice orientations for a series"""
        orientations = {}
        
        for idx, ds in enumerate(self.series_data.get(series_path, [])):
            orientation = get_orientation(ds)
            if orientation is not None:
                orientations[idx] = orientation
        
        return orientations
