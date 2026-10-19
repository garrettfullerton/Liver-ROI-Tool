# Liver ROI Tool — Edits Game Plan

Status key: `[ ]` todo · `[~]` in progress · `[x]` done
Priority: **Need** = need-to-have · **Nice** = nice-to-have

Confirmed: L/R scheme = Left lobe + Right lobe ROIs. No series contain multiple echoes/phases per folder.

B9 approved and done (Phase C commit): coronal/sagittal/oblique mm coordinates now use direction cosines.

---

## Implementation order
1. Phase A — Quick fixes: #2, #3
2. Phase B — Foundation refactor (F1–F4), enables #1 and #4
3. Phase C — #4 export fields + scheme stored in CSV
4. Phase D — #1 propagate ROIs
5. Phase E — Bug fixes (B1–B7)
6. Phase F — QOL features (Q1–Q10)
7. Phase G — #6 auto-ROI (Nice)

---

## Phase A — Quick fixes

### [x] #2 Scroll-up / up-key slice navigation (Need)
- **Cause:** `image_viewer_panel.py` `on_wheel` uses `angleDelta().y() // 120`. Floor division makes
  small positive deltas (touchpad / smooth-scroll mice, e.g. +15) round to 0, while small negative deltas
  round to -1, so scrolling down works but scrolling up doesn't.
- **Change:** accumulate `angleDelta` in `self._wheel_accum`; step one slice per ±120 and keep the
  remainder (truncate toward zero, not floor).
- **Also:** arrow keys only work while the image label has focus. Add window-level `QShortcut`s
  (Up/Left = previous, Down/Right = next) in `dicom_viewer_app.py`, with context set so they don't fire while
  a spinbox/text field is being edited.

### [x] #3 Single-ROI and Left/Right ROI schemes (Need)
- **Change:** add a `SCHEMES` dict (new `schemes.py`) that is the single source of truth:
  `name -> {labels, short_labels, button_columns}`, with "9-segment", "4-segment", "Whole Liver" (label "Liver"),
  and "Left/Right" (labels "Left", "Right").
- `control_panel.py`: build radio buttons and segment buttons from `SCHEMES` (removes the duplicated
  hardcoded lists in `setup_ui` / `on_scheme_changed`).
- `roi_manager.set_segmentation_scheme`: validate against `SCHEMES`; set `segment_labels` there.
- `dicom_image_renderer.render`: use `short_labels` instead of the 4-segment if/else.

---

## Phase B — Foundation refactor (supports #1, #4, Q3, B6)

### [x] F1 Header scan when a folder is opened
- `dicom_series_model.load_directory`: for each DICOM folder, read one file with
  `pydicom.dcmread(stop_before_pixels=True)` and store a `series_info` dict
  (SeriesNumber, SeriesDescription, SeriesInstanceUID, StudyInstanceUID, SeriesDate/Time, orientation, n_files).
- Lets the app group series by exam (StudyInstanceUID) and label the tree properly.

### [x] F2 Load series without making it current
- Split `load_series` into `read_series(path)` (reads, sorts, caches in `series_data` and returns it) and
  `load_series(path)` (calls `read_series`, then sets the current series and emits the signal). Reuse the cache if already loaded.
- Store per-series metadata (name, UID, exam number, etc.) in a dict keyed by path, instead of only the
  `current_*` attributes.

### [x] F3 Single ROI-stats function
- New `roi_geometry.py` with `compute_roi(ds, pixel_array, norm_x, norm_y, radius_px)` that returns center in mm,
  area, mean/median/min/max/**std**, and n_px. Apply RescaleSlope/Intercept here (B4).
- Used by drawing (`image_viewer_panel.on_mouse_release`), copy/propagate, and auto-ROI. Removes the
  duplicated math.
- Define the ROI radius in **image pixels** (not normalized by the label/pixmap min dimension) to remove
  the drawn vs. measured mismatch on non-square matrices.

### [x] F4 ROI data model
- `ROI` gets core fields (scheme, segment, label, slice_idx, center, radius, stats) plus a `meta` dict for
  series/acquisition info. Replace the 21 positional args with keyword args or a dataclass.

---

## Phase C — Export

### [x] #4 More series information in export (Need)
- Add columns from `meta`: SeriesNumber, SeriesDate, SeriesTime, AcquisitionTime, StudyDate,
  StudyInstanceUID, AccessionNumber, Modality, Manufacturer, ManufacturerModelName, MagneticFieldStrength,
  RepetitionTime, EchoTime, FlipAngle, EchoNumbers, SliceThickness, PixelSpacing, SliceLocation,
  InstanceNumber, plus ROI **Std**.
- Export: write the header from an ordered field list.
- Import: use `csv.DictReader`; fill missing (older-file) columns with defaults, so old CSVs still import.

### [x] #4b Store ROI scheme; auto-switch on import (Need — user request)
- Add a "Scheme" column to the export.
- On import: read the scheme(s) from the file. If one differs from the current scheme, switch the scheme
  programmatically (update the control panel radio buttons and segment buttons) **without** clearing the ROIs being imported.
  If the file has no Scheme column, infer it from the labels. If the file mixes schemes, warn and pick the most common one.

### [x] B1 One exporter
- The "Export Statistics to CSV" button in the stats dialog calls `roi_manager.export_rois` (its separate
  format had no Series UID, so its files couldn't be re-imported). The dialog table shows the same columns.

---

## Phase D — Propagation

### [x] #1 Propagate ROIs to all series / selected series in the exam (Need)
- New dialog (replaces "Copy ROIs from Another Series"). Source = current series. Target list = all series
  with the same StudyInstanceUID (from F1), shown as "#SeriesNumber Description", each with a checkbox, plus Select All / None.
  Keep a "pull from another series" mode for the existing behavior.
- `roi_manager.copy_rois_from_series(src, tgt)`: use `read_series(tgt)` (F2) and `compute_roi` (F3) for
  the target slice data/metadata, instead of the `current_*` attributes.
- Handle missing ImageOrientationPatient (no KeyError) and orientations other than 1–3.
- Show a summary: copied N ROIs to M series. Skipped series: different orientation, or no slice within 5 mm.
- Run large batches with a progress dialog (`QProgressDialog`) so the UI doesn't freeze.

---

## Phase E — Bug fixes

- [ ] **B2** `delete_last_roi` filters by slice only; also filter by `series_path` (currently it can delete an ROI from another series).
  Track insertion order so that "last" means the last ROI drawn. Add Ctrl+Z.
- [ ] **B3** Import keeps all rows (matched to series by UID, using the F1 scan), not just the current series,
  and asks "Replace or merge?" instead of always clearing.
- [x] **B4** Apply RescaleSlope/Intercept in `compute_roi_stats` (done in Phase B). Philips private scale not handled.
- [ ] **B5** Confirmation dialogs for Clear All and for scheme changes when ROIs exist.
- [ ] **B6** Sort slices by position along the slice normal (from ImagePositionPatient), with InstanceNumber as the fallback.
  (No multi-echo/multi-phase splitting needed.)
- [ ] **B7** DICOM detection: accept files without an extension (check the `DICM` preamble). Use the same file
  filter in the folder scan, `load_series`, and the navigator (`.sdcopen` is currently inconsistent).
- [x] **B9** Patient-coordinate (mm) math in `roi_geometry.normalized_to_patient` assumes a fixed convention that
  is only correct for standard axial slices. Coronal SI is offset by the FOV height. Sagittal swaps the AP/SI axes.
  Copying stays self-consistent within one series geometry, but copying between coronal/sagittal series with
  different FOV/position will misplace ROIs. Fix: compute positions from the ImageOrientationPatient direction cosines
  (P = IPP + col·Δc·row_cos + row·Δr·col_cos), and use the inverse for copying. Do this before Phase D.
- [ ] **B8** Window/level ranges: set the slider/spinbox ranges from the series' min/max instead of 4000/±2000.

---

## Phase F — QOL features

- [ ] **Q1 Fixed-size ROI mode:** a spinbox for diameter (mm) plus a toggle; click to place, using pixel spacing to convert mm to px.
- [ ] **Q2 Move/resize ROIs:** hit-test existing ROIs on mouse press; drag the center to move it, drag the edge to resize it;
  recompute stats on release.
- [ ] **Q3 Better series tree:** label leaf nodes "#SeriesNumber – Description" (from F1), sort by series number,
  and add an ROI-count badge ("✓ 9/9") that updates on `rois_changed`.
- [ ] **Q4 Segment checklist:** in the control panel, show which labels have ROIs in the current series; clicking one
  jumps to that ROI's slice.
- [ ] **Q5 Autosave + unsaved warning:** after each change, write a session CSV to a temp/app-data folder; prompt on
  `closeEvent` if there are unexported changes. Use `QSettings` to remember the last folder, scheme, and fixed ROI size.
- [ ] **Q6 Zoom/pan:** zoom factor and offset in the renderer (Ctrl+wheel to zoom, middle-drag to pan). Coordinate
  conversions go through a single transform.
- [ ] **Q7 Cursor readout:** status bar showing the pixel value (rescaled) and LR/AP/SI mm under the cursor, using
  the existing `renderer.get_pixel_value`.
- [ ] **Q8 Wide export:** an extra export option with one row per series and columns `<label>_mean`, `<label>_std`, …
- [ ] **Q9 In-app messages:** replace `print()` with a `QStatusBar` / `QMessageBox` for import, export, and copy results.
- [ ] **Q10 Euclidean drag radius:** the radius equals the drag distance (currently the Manhattan distance / 2). The preview matches the final ROI.

---

## Phase G — Auto-ROI (Nice)

### [ ] #6 Auto-ROI placement
- **Stage 1 (semi-auto, recommended):** "Auto ROI" mode for the Whole Liver scheme (later all schemes). The user
  clicks roughly inside the liver. Then:
  1. Build a local-homogeneity mask: local std from a uniform filter, thresholded against the local median around the seed.
  2. Build a vessel mask: Frangi/sato vesselness (scikit-image) plus an intensity outlier threshold.
     Bright or dark vessels can be chosen per sequence.
  3. allowed = homogeneous & ~vessels & ~edges, keeping the connected component that contains the seed.
  4. Distance transform (`scipy.ndimage.distance_transform_edt`); center = max within a search radius of
     the seed; radius = min(distance, user max radius in mm).
  5. Show a preview circle; the user accepts or adjusts it with Q2.
  - New deps: scipy, scikit-image. New module `auto_roi.py`; results go through `compute_roi` (F3).
- **Stage 2 (optional, fully automatic):** liver (and Couinaud segment) masks from TotalSegmentator MR
  tasks, which need PyTorch (verify which tasks are available first). Restrict step 3 to the liver/segment masks
  so the user doesn't need to click, and automatic per-segment placement becomes possible.
- Delete or replace the unused `ai_model/`, `ai_panel.py`, `ai_model_manager.py` placeholders when this lands.
