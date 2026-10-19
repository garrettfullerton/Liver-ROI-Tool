"""Advanced settings loaded from liver_roi_config.json (created with defaults next to the app on first run)"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "liver_roi_config.json")

DEFAULT_CONFIG = {
    # File extensions (case-insensitive) treated as DICOM when scanning folders
    "dicom_extensions": [".dcm", ".sdcopen"],
    # If true, also check every other file for the DICOM 'DICM' header (finds extensionless files; slower)
    "scan_all_files": False,
}


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
    except (OSError, ValueError) as e:
        print(f"Could not read {CONFIG_PATH}, using defaults: {e}")

    config["dicom_extensions"] = [ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                                  for ext in config["dicom_extensions"]]
    return config


CONFIG = load_config()
