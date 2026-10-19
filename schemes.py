"""ROI labeling schemes (single source of truth for labels, abbreviations and button layout)"""
import json

SCHEMES = {
    "9-segment": {
        "display_name": "9-Segment",
        "labels": ["1", "2", "3", "4a", "4b", "5", "6", "7", "8"],
        "short_labels": ["1", "2", "3", "4a", "4b", "5", "6", "7", "8"],
        "button_format": "Segment {}",
        "columns": 3,
    },
    "4-segment": {
        "display_name": "4-Segment",
        "labels": ["Left Lateral", "Left Medial", "Right Anterior", "Right Posterior"],
        "short_labels": ["LL", "LM", "RA", "RP"],
        "button_format": "{}",
        "columns": 2,
    },
    "left-right": {
        "display_name": "Left/Right Lobe",
        "labels": ["Left Lobe", "Right Lobe"],
        "short_labels": ["L", "R"],
        "button_format": "{}",
        "columns": 2,
    },
    "whole-liver": {
        "display_name": "Whole Liver (single ROI)",
        "labels": ["Whole Liver"],
        "short_labels": ["WL"],
        "button_format": "{}",
        "columns": 1,
    },
}

DEFAULT_SCHEME = "9-segment"
CUSTOM_PREFIX = "custom:"


def default_custom_label(number):
    return f"ROI {number}"


def register_custom_scheme(name, labels):
    """Add (or replace) a user-defined layout; returns its scheme key"""
    key = CUSTOM_PREFIX + name
    SCHEMES[key] = {
        "display_name": f"{name} (custom)",
        "labels": list(labels),
        "short_labels": [str(i) for i in range(1, len(labels) + 1)],
        "button_format": "{}",
        "columns": 3,
        "custom": True,
    }
    return key


def unregister_custom_scheme(name):
    SCHEMES.pop(CUSTOM_PREFIX + name, None)


def custom_scheme_names():
    return [key[len(CUSTOM_PREFIX):] for key in SCHEMES if key.startswith(CUSTOM_PREFIX)]


def button_text(scheme, segment):
    """Segment button text; custom layouts show the ROI number with the optional name"""
    scheme_def = SCHEMES[scheme]
    label = scheme_def["labels"][segment - 1]
    if scheme_def.get("custom") and label != default_custom_label(segment):
        return f"{segment}: {label}"
    return scheme_def["button_format"].format(label)


def load_custom_schemes():
    """Register custom layouts saved in the user's settings"""
    from app_config import get_settings
    try:
        layouts = json.loads(get_settings().value("custom_schemes", "[]"))
    except (TypeError, ValueError):
        layouts = []
    for layout in layouts:
        register_custom_scheme(layout["name"], layout["labels"])


def save_custom_schemes():
    """Persist custom layouts to the user's settings"""
    from app_config import get_settings
    layouts = [{"name": name, "labels": SCHEMES[CUSTOM_PREFIX + name]["labels"]} for name in custom_scheme_names()]
    get_settings().setValue("custom_schemes", json.dumps(layouts))


def get_short_label(scheme, label):
    """Return the on-image abbreviation for a label (falls back to the label itself)"""
    scheme_def = SCHEMES.get(scheme)
    if scheme_def is None or label not in scheme_def["labels"]:
        return label
    return scheme_def["short_labels"][scheme_def["labels"].index(label)]
