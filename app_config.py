"""Advanced settings loaded from liver_roi_config.json (created with defaults next to the app on first run)"""
import json
import os
import subprocess

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "liver_roi_config.json")

DEFAULT_CONFIG = {
    # File extensions (case-insensitive) treated as DICOM when scanning folders
    "dicom_extensions": [".dcm", ".sdcopen"],
    # If true, also check every other file for the DICOM 'DICM' header (finds extensionless files; slower)
    "scan_all_files": False,
    # Flag ROIs whose coefficient of variation (std/mean) exceeds this (0 disables)
    "cv_warning_threshold": 0.2,
    # Flag ROIs whose inner-half vs outer-ring means differ by more than this fraction of the median,
    # suggesting an edge, vessel or artifact inside the ROI (0 disables)
    "edge_warning_threshold": 0.2,
}

APP_VERSION = "2.1"


def load_config():
    """Read the config file, falling back to defaults for missing/invalid entries"""
    config = dict(DEFAULT_CONFIG)

    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
        except OSError as e:
            print(f"Could not create {CONFIG_PATH}: {e}")
        return config

    try:
        with open(CONFIG_PATH) as f:
            user_config = json.load(f)
        config.update({key: value for key, value in user_config.items() if key in DEFAULT_CONFIG})

        # Add settings introduced in newer versions to the file (keeping the user's values)
        if set(DEFAULT_CONFIG) - set(user_config):
            with open(CONFIG_PATH, "w") as f:
                json.dump({**user_config, **{k: v for k, v in config.items() if k not in user_config}}, f, indent=4)
    except (OSError, ValueError) as e:
        print(f"Could not read {CONFIG_PATH}, using defaults: {e}")

    config["dicom_extensions"] = [ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                                  for ext in config["dicom_extensions"]]
    return config


CONFIG = load_config()


def get_version_string():
    """App version plus the git commit when running from a git checkout (recorded in exports)"""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=os.path.dirname(CONFIG_PATH),
                                capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    return f"{APP_VERSION} ({commit})" if commit else APP_VERSION


VERSION_STRING = get_version_string()


def get_settings():
    """Remembered UI state (last folder, fixed ROI size, window geometry)"""
    from PyQt5.QtCore import QSettings
    return QSettings("LiverROITool", "LiverROITool")
