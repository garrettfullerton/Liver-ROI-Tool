"""Read-only check of which series the Liver ROI Tool lists for a folder, and why any are missing.

Usage (from the app's folder, in the app's Python environment):
    python check_dicom_folder.py <folder you open in the app>

Reads every file's DICOM header, runs the app's own folder scanner and builds its series list (without
opening a window), and compares them. Prints exams and
folders by number and series by number/description; no patient information or folder names.
"""
import os
import sys
import traceback

import pydicom

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # build the series list without showing a window
from PyQt5.QtWidgets import QApplication

from app_config import CONFIG, VERSION_STRING
from dicom_series_model import DicomSeriesModel
from roi_manager import ROIManager
from series_navigator_panel import SeriesNavigatorPanel

root = sys.argv[1]
print(f"App version {VERSION_STRING}")
print(f"App picks up extensions {CONFIG['dicom_extensions']}; scan_all_files={CONFIG['scan_all_files']}")

# 1. Every DICOM series actually on disk, by reading every file
on_disk = {}  # SeriesInstanceUID -> info
folder_numbers = {}
for folder, _, files in sorted(os.walk(root)):
    for name in sorted(files):
        try:
            ds = pydicom.dcmread(os.path.join(folder, name), stop_before_pixels=True, force=True)
            uid = str(ds.SeriesInstanceUID)
        except Exception:
            continue  # not DICOM
        info = on_disk.setdefault(uid, {"number": ds.get("SeriesNumber"), "description": str(ds.get("SeriesDescription", "")),
                                        "study": str(ds.get("StudyInstanceUID", "")), "folders": set(), "files": 0,
                                        "picked_up": 0, "extensions": set()})
        info["folders"].add(folder)
        info["files"] += 1
        info["picked_up"] += os.path.splitext(name)[1].lower() in CONFIG["dicom_extensions"] or CONFIG["scan_all_files"]
        info["extensions"].add(os.path.splitext(name)[1].lower() or "(no extension)")
        folder_numbers.setdefault(folder, len(folder_numbers) + 1)

# 2. What the app's scanner lists
model = DicomSeriesModel()
listed_folders = set()
try:
    model.load_directory(root)

    def collect(node):
        for value in node.values():
            if isinstance(value, dict):
                collect(value)
            else:
                listed_folders.add(value)
    collect(model.get_directory_structure())
except Exception:
    print("\n*** The app's folder scan FAILED (it would crash or show nothing):")
    traceback.print_exc()

# 2b. The series list the app shows (the tree you click series in)
app = QApplication.instance() or QApplication(sys.argv[:1])
on_screen = set()
try:
    panel = SeriesNavigatorPanel(None, model, ROIManager(model))
    panel.setup_ui()
    panel.load_folder(root)
    on_screen = set(panel.ordered_series_paths())
except Exception:
    print("\n*** Building the app's series list FAILED:")
    traceback.print_exc()

# 3. Compare
series_per_folder = {}
for uid, info in on_disk.items():
    for folder in info["folders"]:
        series_per_folder.setdefault(folder, []).append(uid)

studies = {}
missing = 0
for uid, info in sorted(on_disk.items(), key=lambda item: (item[1]["study"], str(item[1]["number"]))):
    study_no = studies.setdefault(info["study"], len(studies) + 1)
    reasons = []
    if info["picked_up"] == 0:
        reasons.append(f"all {info['files']} files skipped because of their extension {sorted(info['extensions'])}")
    elif info["picked_up"] < info["files"]:
        reasons.append(f"{info['files'] - info['picked_up']} of {info['files']} files skipped because of their extension")
    shared = [f for f in info["folders"] if len(series_per_folder[f]) > 1]
    if shared:
        reasons.append("shares folder " + ", ".join(str(folder_numbers[f]) for f in shared)
                       + " with other series (the app treats a folder as one series)")
    if len(info["folders"]) > 1:
        reasons.append("files are split over folders " + ", ".join(str(folder_numbers[f]) for f in info["folders"]))
    if not any(f in listed_folders for f in info["folders"]):
        reasons.insert(0, "NOT FOUND by the app's scan")
    elif not any(f in on_screen for f in info["folders"]):
        reasons.insert(0, "found by the scan but MISSING FROM THE SERIES LIST")
    if reasons:
        missing += 1
        print(f"Exam {study_no}, #{info['number']} {info['description']!r}: " + "; ".join(reasons))

print(f"\n{len(on_disk)} series in {len(studies)} exams on disk; the app's scan finds {len(listed_folders)} series "
      f"folders and its series list shows {len(on_screen)}; {missing} series with problems")
