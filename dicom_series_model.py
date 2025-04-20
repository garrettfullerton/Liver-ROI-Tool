import os
import pydicom
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal

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
        self.anatomical_positions = {}  # Mapping of anatomical positions
        self.directory_structure = {}  # Patient/Study/Series structure
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
        
        for top_level, dirs in top_level_groups.items():
            self.directory_structure[top_level] = {}
            
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
    
    def load_series(self, series_path):
        """Load a specific series"""
        if not os.path.exists(series_path):
            return False
            
        # Load all DICOM files in the series
        dicom_files = [os.path.join(series_path, f) for f in os.listdir(series_path) 
                      if f.endswith('.dcm') or f.endswith('.DCM')]
        
        if not dicom_files:
            return False
            
        # Load the series data
        series_data = []
        for dicom_file in dicom_files:
            try:
                ds = pydicom.dcmread(dicom_file)
                series_data.append(ds)

                # try to get window/level from first DICOM file
                if len(series_data) == 1:
                    # check for window center/width tags
                    if hasattr(ds, 'WindowCenter') and hasattr(ds, 'WindowWidth'):
                        # handle multiple values (pick first one)
                        if isinstance(ds.WindowCenter, list):
                            self.default_level = float(ds.WindowCenter[0])
                        else:
                            self.default_level = float(ds.WindowCenter)
                            
                        if isinstance(ds.WindowWidth, list):
                            self.default_window = float(ds.WindowWidth[0])
                        else:
                            self.default_window = float(ds.WindowWidth)
                            
                    if isinstance(ds.PatientID, list):
                        self.current_study_name = ds.PatientID[0]
                    else:
                        self.current_study_name = ds.PatientID
                        
                    if isinstance(ds.SeriesDescription, list):
                        self.current_series_name = ds.SeriesDescription[0]
                    else:
                        self.current_series_name = ds.SeriesDescription
                        
                    if isinstance(ds.SeriesInstanceUID, list):
                        self.current_series_uid = ds.SeriesInstanceUID[0]
                    else:
                        self.current_series_uid = ds.SeriesInstanceUID
                        
                    if isinstance(ds.StudyID, list):
                        self.current_exam_number = ds.StudyID[0]
                    else:
                        self.current_exam_number = ds.StudyID
                        
                        
            except Exception as e:
                print(f"Error loading {dicom_file}: {e}")
        
        # Sort by instance number if available
        series_data.sort(key=lambda x: getattr(x, 'InstanceNumber', 0))
       
        if not series_data:
            return False
            
        # Store the series data
        self.series_data[series_path] = series_data
        self.current_series = series_data
        self.current_series_path = series_path
        self.current_slice_index = 0
        
        # Update anatomical positions for this series
        self.update_anatomical_positions(series_path)
        
        # Emit signal that series has been loaded
        self.series_loaded.emit()
        
        return True
    
    def get_current_slice(self):
        """Return current slice data"""
        if not self.current_series or self.current_slice_index >= len(self.current_series):
            return None
            
        return self.current_series[self.current_slice_index]
    
    def get_slice(self, index):
        """Return slice at specified index"""
        if not self.current_series or index >= len(self.current_series):
            return None
            
        return self.current_series[index]
    
    def get_slice_pixel_data(self, index):
        """Return pixel data for slice at specified index"""
        slice_data = self.get_slice(index)
        if slice_data is None:
            return None
            
        return slice_data.pixel_array
    
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
        
        if series_path in self.series_data:
            for idx, ds in enumerate(self.series_data[series_path]):
                if hasattr(ds, 'ImageOrientationPatient'):
                    orientation_vec = ds.ImageOrientationPatient
                    orientation_vec_cross = np.cross(orientation_vec[:3], orientation_vec[3:])
                    orientation_vec_cross_rounded = [round(abs(val), 0) for val in orientation_vec_cross]
                    orientation = orientation_vec_cross_rounded.index(1.0) + 1
                    orientations[idx] = orientation
        
        return orientations