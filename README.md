# Liver ROI Tool
A Python application for drawing and exporting ROI statistics, primarily intended for quantitative liver MRI. It loads DICOM series, lets you draw circular ROIs labeled by liver segment, copies them across series in an exam, and exports statistics with series/acquisition information.

## Features
- **DICOM browser:** finds series at any folder depth; lists them as `#SeriesNumber Description` with ROI progress (e.g. `5/9`, `✓ 9/9`)
- **Viewer:** window/level, zoom/pan, and a readout of pixel value and patient position (mm) under the cursor
- **ROI schemes:** 9-segment (Couinaud), 4-segment, left/right lobe, a single whole-liver ROI, or **custom layouts** with any number of numbered, optionally named ROIs
- **ROI drawing:** drag to draw, or click to place a fixed-diameter ROI; drag an ROI to move it or its edge to resize it
- **Statistics:** mean, median, std, min, max, area and pixel count, computed on rescaled pixel values (RescaleSlope/Intercept). Mean/median verified against Horos.
- **ROI checklist:** table of every segment for the current series; double-click to jump to its slice
- **Quality flags:** CV (std/mean) per ROI, with ⚠ warnings for high CV or an inner/outer mismatch suggesting the ROI crosses an edge, vessel or artifact
- **Locking:** lock finished series so ROIs can't be accidentally drawn, moved, resized or overwritten
- **Batch mode:** step through many exams in a parent folder; you're asked to export each exam before moving on. Jump between series or to the next incomplete series. Switching series within an exam keeps the same slice position when the slices overlap (same orientation); otherwise a series opens on its first slice with ROIs
- **Audit fields:** reader initials, date/time drawn and app version (with git commit) are stored with every ROI
- **Copy / propagate:** copy ROIs to all or selected series in the same exam (or into the current series), matched by patient position for axial, coronal, sagittal or oblique series
- **Export:** one row per ROI with statistics and series/acquisition info (series number/date/time, scanner, TR/TE/flip angle, slice thickness, etc.), or a summary with one row per series
- **Import:** reload ROIs from any exported CSV (including older versions) into every matching series, replacing or merging; the scheme switches to match
- **Autosave / auto-export:** unexported ROIs are autosaved per folder and offered for restore; optionally, every exam is exported automatically to a chosen folder after each change; with auto-export on, all ROIs in the folder are cached and loaded automatically when the folder is reopened

## Requirements
- Python 3.10+
- PyQt5, pydicom 3, NumPy (see `requirements.txt`)

## Installation
```bash
git clone https://github.com/garrettfullerton/Liver-ROI-Tool.git
cd Liver-ROI-Tool
pip install -r requirements.txt
```

## Usage
1. Run `python liver-app.py`
2. Click **Open Folder** and select a patient/exam folder, then click a series to load it
3. Choose a segmentation scheme, select a segment (button or Ctrl+number), and draw ROIs
4. Use **Copy / Propagate ROIs...** to put the ROIs on other series in the exam
5. **Export ROIs** (Ctrl+S) writes every ROI in every series to one CSV; **Export Summary** writes one row per series

Click **Info / Shortcuts** (or press **F1**) in the app for a full guide to features, keyboard shortcuts and mouse controls.

## Key Shortcuts
| Input | Action |
|---|---|
| Arrow keys / mouse wheel | Change slice |
| Ctrl+1 … Ctrl+9 | Select segment (per scheme) |
| E | Toggle ROI drawing |
| Ctrl+Z | Clear last ROI on the current slice |
| Ctrl+S | Export ROIs |
| Right-drag | Window/level |
| Ctrl+wheel / middle-drag / Ctrl+0 | Zoom / pan / reset view |
| Ctrl+↑/↓ or PageUp/PageDown | Previous / next series |
| Ctrl+J | Next incomplete series |
| Ctrl+PageUp / Ctrl+PageDown | Previous / next exam |
| Ctrl+L | Lock / unlock series |
| F1 | Info / shortcuts window |

## Advanced Settings
`liver_roi_config.json` is created next to the app on first run (restart to apply changes):
```json
{
    "dicom_extensions": [".dcm", ".sdcopen"],
    "scan_all_files": false,
    "cv_warning_threshold": 0.2,
    "edge_warning_threshold": 0.2
}
```
- `dicom_extensions`: file extensions treated as DICOM (case-insensitive)
- `scan_all_files`: also check every other file for a DICOM header (finds extensionless files; slower on large folders)
- `cv_warning_threshold` / `edge_warning_threshold`: when to flag an ROI (0 disables). Maps with values near zero (e.g. low PDFF) may need higher values

## Project Structure
- `liver-app.py`: entry point
- `dicom_viewer_app.py`: main window; connects the panels
- `dicom_series_model.py`: folder scanning, series loading and metadata
- `dicom_image_renderer.py`: image display, window/level, zoom/pan, ROI overlays
- `roi_manager.py`: ROI creation, copying, import/export
- `roi_geometry.py`: ROI statistics and pixel/mm conversion
- `schemes.py`: segmentation scheme definitions
- `series_navigator_panel.py`, `image_viewer_panel.py`, `control_panel.py`, `statistics_panel.py`: UI panels
- `propagate_dialog.py`, `custom_layout_dialog.py`, `info_dialog.py`: copy/propagate, custom layout and help dialogs
- `session_manager.py`: autosave, auto-export, restore and unexported-changes warning
- `app_config.py`: advanced settings and remembered UI settings
- `check_dicom_folder.py`: read-only diagnostic that reports series on disk the app does not list, and why (`python check_dicom_folder.py <folder>`)

## Potential Future Developments
- **Auto-advance segment:** after drawing an ROI, automatically select the next segment (saves a hotkey press per ROI).
- **Whole-liver average in the summary export:** mean of the segment means (optionally area-weighted), as reported in most liver fat/iron studies.
- **Multi-slice ROIs:** place the same circle on N adjacent slices and pool the statistics, for protocols that average over 2–3 slices.
- **Auto-ROI (semi-automatic):** click inside the liver and the tool places the largest circle in a homogeneous, artifact-free region that avoids large vessels (local-variance + vesselness masks, distance transform). Would add scipy/scikit-image.
- **Auto-ROI (fully automatic):** use a liver/Couinaud segmentation model (e.g. TotalSegmentator MR tasks) to place ROIs per segment without clicking. Would add PyTorch.

## Disclaimer
This is just a project I made for the purposes of my own research projects. I make no guarantees on the quality of this code since it's just my way of learning PyQt5.
