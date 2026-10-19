"""ROI labeling schemes (single source of truth for labels, abbreviations and button layout)"""

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


def get_short_label(scheme, label):
    """Return the on-image abbreviation for a label (falls back to the label itself)"""
    scheme_def = SCHEMES.get(scheme)
    if scheme_def is None or label not in scheme_def["labels"]:
        return label
    return scheme_def["short_labels"][scheme_def["labels"].index(label)]
