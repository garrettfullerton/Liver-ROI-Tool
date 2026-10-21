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


def _plane_geometry(ds):
    """Return (position of first pixel, row direction, column direction) as numpy arrays.

    Row direction is the direction of increasing column index; column direction is increasing row index.
    """
    ipp = np.array([float(v) for v in ds.ImagePositionPatient])
    iop = np.array([float(v) for v in ds.ImageOrientationPatient])
    return ipp, iop[:3], iop[3:]


def normalized_to_patient(ds, norm_x, norm_y):
    """Convert normalized in-plane coordinates (0-1) to DICOM patient coordinates (x=LR, y=AP, z=SI) in mm.

    Uses ImagePositionPatient/ImageOrientationPatient, so any slice orientation (including oblique) works.
    Returns ((LR, AP, SI), orientation); coordinates are NaN if position/orientation tags are missing.
    """
    orientation = get_orientation(ds)
    if orientation is None or not hasattr(ds, 'ImagePositionPatient'):
        return (np.nan, np.nan, np.nan), orientation

    ipp, row_dir, col_dir = _plane_geometry(ds)
    spacing_x, spacing_y = get_pixel_spacing(ds)
    pos = ipp + row_dir * spacing_x * (norm_x * ds.Columns) + col_dir * spacing_y * (norm_y * ds.Rows)

    return tuple(float(v) for v in pos), orientation


def patient_to_normalized(ds, pos_LR, pos_AP, pos_SI):
    """Inverse of normalized_to_patient: project a patient-coordinate point onto the slice plane"""
    ipp, row_dir, col_dir = _plane_geometry(ds)
    spacing_x, spacing_y = get_pixel_spacing(ds)
    offset = np.array([pos_LR, pos_AP, pos_SI]) - ipp

    norm_x = offset.dot(row_dir) / spacing_x / ds.Columns
    norm_y = offset.dot(col_dir) / spacing_y / ds.Rows

    return float(norm_x), float(norm_y)


def distance_to_slice(ds, pos):
    """Distance (mm) from a patient-coordinate point to the slice plane, along the slice normal"""
    ipp, row_dir, col_dir = _plane_geometry(ds)
    normal = np.cross(row_dir, col_dir)
    return float(abs((np.array(pos) - ipp).dot(normal)))


def get_slice_thickness(ds):
    """SliceThickness in mm (0 if missing)"""
    try:
        return float(getattr(ds, 'SliceThickness', 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def closest_overlapping_slice(reference, slices):
    """Index of the slice (same orientation) closest to the reference slice's center, or None.

    Returns None unless the closest slice overlaps the reference, i.e. lies within half the larger
    slice thickness (half the slice spacing if thickness is missing).
    """
    orientation = get_orientation(reference)
    if orientation is None or not hasattr(reference, 'ImagePositionPatient'):
        return None
    center, _ = normalized_to_patient(reference, 0.5, 0.5)

    candidates = [(distance_to_slice(ds, center), i) for i, ds in enumerate(slices)
                  if get_orientation(ds) == orientation and hasattr(ds, 'ImagePositionPatient')]
    if not candidates:
        return None
    distance, best = min(candidates)

    tolerance = max(get_slice_thickness(reference), get_slice_thickness(slices[best])) / 2
    if not tolerance and len(candidates) > 1:
        neighbor = slices[best + 1] if best + 1 < len(slices) else slices[best - 1]
        tolerance = distance_to_slice(neighbor, _plane_geometry(slices[best])[0]) / 2
    return best if distance <= tolerance else None


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

    # Inner half-radius vs outer ring: a large difference suggests an edge, vessel or artifact in the ROI
    inner = (x_indices - center_x_px)**2 + (y_indices - center_y_px)**2 <= (radius_px / 2)**2
    inner_values, outer_values = pixel_values[mask & inner], pixel_values[mask & ~inner]
    median = float(np.median(roi_values))
    if inner_values.size >= 5 and outer_values.size >= 5 and median != 0:
        edge_diff = abs(float(np.mean(inner_values)) - float(np.mean(outer_values))) / abs(median)
    else:
        edge_diff = float('nan')

    return {
        'center_LR_mm': pos_LR,
        'center_AP_mm': pos_AP,
        'center_SI_mm': pos_SI,
        'orientation': orientation,
        'area_mm2': np.pi * (radius_px * spacing_x) ** 2,  # Assuming square pixels
        'mean_val': float(np.mean(roi_values)),
        'median_val': median,
        'min_val': float(np.min(roi_values)),
        'max_val': float(np.max(roi_values)),
        'std_val': float(np.std(roi_values, ddof=1)) if roi_values.size > 1 else 0.0,
        'size_px': int(roi_values.size),
        'edge_diff': edge_diff,
    }
