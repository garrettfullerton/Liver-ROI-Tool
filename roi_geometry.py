"""Geometry and statistics helpers shared by ROI drawing, copying and importing"""
import numpy as np
from pydicom.pixels import apply_modality_lut


def get_orientation(ds):
    """Slice orientation from ImageOrientationPatient: 1=sagittal, 2=coronal, 3=axial (None if unknown)"""
    if not hasattr(ds, 'ImageOrientationPatient'):
        return None
    iop = [float(v) for v in ds.ImageOrientationPatient]
    normal = np.abs(np.cross(iop[:3], iop[3:]))
    return int(np.argmax(normal)) + 1


def get_pixel_spacing(ds):
    """Return (spacing_x, spacing_y) in mm, i.e. (column spacing, row spacing)"""
    pixel_spacing = getattr(ds, 'PixelSpacing', [1, 1])
    return float(pixel_spacing[1]), float(pixel_spacing[0])


def get_pixel_values(ds):
    """Return pixel data with RescaleSlope/RescaleIntercept applied"""
    return apply_modality_lut(ds.pixel_array, ds)


def normalized_to_patient(ds, norm_x, norm_y):
    """Convert normalized in-plane coordinates (0-1) to patient (LR, AP, SI) mm.

    Returns ((LR, AP, SI), orientation); coordinates are NaN if position/orientation tags are missing.
    """
    orientation = get_orientation(ds)
    if orientation is None or not hasattr(ds, 'ImagePositionPatient'):
        return (np.nan, np.nan, np.nan), orientation

    anat_pos = [float(v) for v in ds.ImagePositionPatient]
    spacing_x, spacing_y = get_pixel_spacing(ds)
    rows, cols = ds.Rows, ds.Columns

    if orientation == 1:
        # sagittal
        pos_LR = anat_pos[0]
        pos_AP = anat_pos[1] + (spacing_y * (rows * norm_y))
        pos_SI = anat_pos[2] + (spacing_x * (cols * (1 - norm_x)))
    elif orientation == 2:
        # coronal
        pos_LR = anat_pos[0] + (spacing_x * (cols * norm_x))
        pos_AP = anat_pos[1]
        pos_SI = anat_pos[2] + (spacing_y * (rows * (1 - norm_y)))
    else:
        # axial
        pos_LR = anat_pos[0] + (spacing_x * (cols * norm_x))
        pos_AP = anat_pos[1] + (spacing_y * (rows * norm_y))
        pos_SI = anat_pos[2]

    return (pos_LR, pos_AP, pos_SI), orientation


def patient_to_normalized(ds, orientation, pos_LR, pos_AP, pos_SI):
    """Inverse of normalized_to_patient for a slice with the given orientation"""
    anat_pos = [float(v) for v in ds.ImagePositionPatient]
    spacing_x, spacing_y = get_pixel_spacing(ds)
    rows, cols = ds.Rows, ds.Columns

    if orientation == 1:
        # sagittal
        norm_x = 1 - (pos_SI - anat_pos[2]) / spacing_x / cols
        norm_y = (pos_AP - anat_pos[1]) / spacing_y / rows
    elif orientation == 2:
        # coronal
        norm_x = (pos_LR - anat_pos[0]) / spacing_x / cols
        norm_y = 1 - (pos_SI - anat_pos[2]) / spacing_y / rows
    else:
        # axial
        norm_x = (pos_LR - anat_pos[0]) / spacing_x / cols
        norm_y = (pos_AP - anat_pos[1]) / spacing_y / rows

    return norm_x, norm_y


def compute_roi_stats(ds, pixel_values, norm_x, norm_y, radius_px):
    """Compute position, size and statistics of a circular ROI.

    norm_x/norm_y are the normalized (0-1) center; radius_px is the radius in image pixels.
    Returns a dict of ROI fields, or None if the ROI contains no pixels.
    """
    height, width = pixel_values.shape
    center_x_px = int(norm_x * width)
    center_y_px = int(norm_y * height)

    # Create a mask for the circular ROI
    y_indices, x_indices = np.ogrid[:height, :width]
    mask = (x_indices - center_x_px)**2 + (y_indices - center_y_px)**2 <= radius_px**2
    roi_values = pixel_values[mask]
    if roi_values.size == 0:
        return None

    spacing_x, _ = get_pixel_spacing(ds)
    (pos_LR, pos_AP, pos_SI), orientation = normalized_to_patient(ds, norm_x, norm_y)

    return {
        'center_LR_mm': pos_LR,
        'center_AP_mm': pos_AP,
        'center_SI_mm': pos_SI,
        'orientation': orientation,
        'area_mm2': np.pi * (radius_px * spacing_x) ** 2,  # Assuming square pixels
        'mean_val': float(np.mean(roi_values)),
        'median_val': float(np.median(roi_values)),
        'min_val': float(np.min(roi_values)),
        'max_val': float(np.max(roi_values)),
        'std_val': float(np.std(roi_values, ddof=1)) if roi_values.size > 1 else 0.0,
        'size_px': int(roi_values.size),
    }
