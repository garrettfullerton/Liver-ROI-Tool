from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout

from schemes import SCHEMES
from app_config import CONFIG_PATH


def _rows(pairs):
    return "".join(f"<tr><td><b>{key}</b></td><td>{text}</td></tr>" for key, text in pairs)


def _segment_hotkeys_html():
    """Ctrl+number mapping for every scheme (built from SCHEMES so it always matches the buttons)"""
    rows = ""
    for scheme_def in SCHEMES.values():
        keys = ", ".join(f"Ctrl+{i} = {label}" for i, label in enumerate(scheme_def["labels"], start=1))
        rows += f"<tr><td><b>{scheme_def['display_name']}</b></td><td>{keys}</td></tr>"
    return rows


def build_help_html():
    keyboard = [
        ("Up / Left arrow", "Previous slice"),
        ("Down / Right arrow", "Next slice (arrow keys work from any panel, except while typing in a number field)"),
        ("Ctrl+1 … Ctrl+9", "Select segment 1–9 of the current scheme (see table below); also turns on ROI drawing"),
        ("E", "Toggle ROI drawing mode"),
        ("Ctrl+Z", "Clear the most recent ROI on the current slice of the current series"),
        ("Ctrl+S", "Export ROIs to CSV (all series)"),
        ("Ctrl+0", "Reset zoom and pan"),
        ("Ctrl+Up / Ctrl+Down, PageUp / PageDown", "Previous / next series (in tree order)"),
        ("Ctrl+J", "Jump to the next incomplete series (unlocked and missing ROIs)"),
        ("Ctrl+PageUp / Ctrl+PageDown", "Previous / next exam (batch mode; offers to export the exam you leave)"),
        ("Ctrl+L", "Lock / unlock the current series"),
        ("F1", "Open this help window"),
    ]
    mouse = [
        ("Mouse wheel / touchpad", "Scroll through slices (up = previous slice)"),
        ("Ctrl + mouse wheel", "Zoom in/out around the cursor"),
        ("Middle-button drag", "Pan the image"),
        ("Right-button drag", "Window/level: left/right changes window width, up/down changes level"),
        ("Left-drag (drawing mode)", "Draw a circular ROI: press at the center, drag out to the radius"),
        ("Left-click (drawing mode + Fixed size)", "Place an ROI of the fixed diameter where you click "
                                                   "(a dashed preview follows the cursor)"),
        ("Left-drag inside an ROI", "Move it (statistics are recomputed on release)"),
        ("Left-drag on an ROI's edge", "Resize it (the cursor changes when hovering over an ROI or its edge)"),
        ("Click a series in the tree", "Load that series (at the overlapping slice if in the same exam and "
                                       "orientation, otherwise at its first ROI)"),
        ("Double-click a row in the ROI table", "Jump to the slice containing that segment's ROI"),
    ]

    return f"""
<h2>Liver ROI Tool</h2>
<p>Draw circular ROIs on liver MRI, label them by segment, copy them across series, and export statistics.</p>

<h3>Basic workflow</h3>
<ol>
<li><b>Open Folder</b> and pick a patient/exam folder. Series appear as <i>#SeriesNumber Description</i>,
with ROI progress (e.g. <i>5/9</i>, <i>✓ 9/9</i>); the current series is bold.</li>
<li>Choose a <b>Segmentation Scheme</b>: 9-segment, 4-segment, left/right lobe, or a single whole-liver ROI.</li>
<li>Select a segment (button or Ctrl+number) and draw the ROI. Drawing another ROI for the same segment
in the same series replaces the old one.</li>
<li>Use <b>Copy / Propagate ROIs</b> to put the same ROIs on other series in the exam.</li>
<li><b>Export ROIs</b> (Ctrl+S) writes every ROI in every series to one CSV.</li>
</ol>

<h3>Keyboard shortcuts</h3>
<table cellspacing="6">{_rows(keyboard)}</table>

<h3>Mouse controls</h3>
<table cellspacing="6">{_rows(mouse)}</table>

<h3>Segment hotkeys by scheme</h3>
<p>Custom layouts: Ctrl+1 … Ctrl+9 select ROIs 1–9; ROIs 10 and up are selected with their buttons.</p>
<table cellspacing="6">{_segment_hotkeys_html()}</table>

<h3>ROI controls</h3>
<ul>
<li><b>Draw Circular ROI</b> (E): drawing mode on/off. Moving/resizing ROIs works in either mode.</li>
<li><b>Fixed size</b>: tick it and set a diameter (area shown in cm²); then click to place ROIs of that size.</li>
<li><b>Clear Last ROI</b> (Ctrl+Z) / <b>Clear All ROIs</b> (asks first; clears every series).</li>
<li><b>Import ROIs</b>: loads a CSV from any version of this tool into every matching series (matched by
Series UID). Asks whether to replace or merge with existing ROIs, and switches to the file's scheme.</li>
<li><b>Export ROIs</b>: one row per ROI with statistics (mean, median, std, min, max, area) and series/acquisition info.</li>
<li><b>Export Summary (1 row/series)</b>: one row per series with Mean/Median/Std/Area/Slice columns per segment.</li>
<li><b>Show ROI Statistics</b>: table of all ROIs (same columns as the export).</li>
<li>Changing the <b>scheme</b> deletes all ROIs (asks first).</li>
</ul>

<h3>ROI table and quality flags</h3>
<p>Lists every segment of the scheme for the current series: slice, statistics and CV (std/mean), <i>—</i> if not
drawn yet, <b>bold</b> if on the current slice. Segment buttons also show ✓ once drawn. Double-click a row to go to its slice.</p>
<p>ROIs are flagged <b>⚠</b> (orange) when the CV is high, or when the inner half and outer ring of the ROI differ a lot
(the ROI may cross the liver edge, a vessel or an artifact). Hover over a flagged row for details. Flags are also
exported (CV and Flags columns). Thresholds are set in the advanced settings file.</p>

<h3>Custom layouts</h3>
<p><b>Custom Layout...</b> (under Segmentation Scheme) creates a layout with any number of ROIs, numbered 1…N, each with
an optional name. Saved layouts appear in the scheme list and are remembered. They can be edited or deleted later.
Importing a CSV drawn with a custom layout recreates the layout if it doesn't exist on this computer.</p>

<h3>Locking series</h3>
<p>Tick <b>🔒 Lock series</b> above the image (or press Ctrl+L) when a series is done. Locked series can't have ROIs drawn,
moved, resized, deleted, copied or imported into them. They show 🔒 in the series tree, and the lock is saved in exports
and restored on import. Clear All ROIs and scheme changes still clear locked series (after asking).</p>

<h3>Batch mode (many exams)</h3>
<p>Open a parent folder containing many exams. The ◀ / ▶ buttons (Ctrl+PageUp / Ctrl+PageDown) step through exams in tree
order and show <i>Exam i/N</i>. When you leave an exam with unexported changes, you are asked to export that exam (or it
is auto-exported). <b>Next Incomplete Series</b> (Ctrl+J) jumps to the next unlocked series missing ROIs.</p>

<h3>Reader, auto-export and audit fields</h3>
<ul>
<li><b>Reader</b>: your initials, recorded with every ROI you draw, move or copy (remembered between sessions).</li>
<li>Each ROI also records <b>Drawn At</b> (date/time drawn or last edited) and the <b>App Version</b>; all are exported.</li>
<li><b>Auto-export to folder</b>: a few seconds after each change, every changed exam is written to
<i>&lt;Patient&gt;_&lt;Exam&gt;_&lt;scheme&gt;_ROIs.csv</i> in the chosen folder, so you never need to export manually.</li>
</ul>

<h3>Copy / Propagate ROIs</h3>
<ul>
<li><b>Propagate to other series</b>: copies the current series' ROIs to the checked series in the same exam
(Select All / None). ROIs are matched by patient position (mm) and keep their physical size.</li>
<li><b>Copy into current series</b>: pulls ROIs from one other series.</li>
<li>Series with a different slice orientation, or no slice within the max distance, are skipped;
a summary lists what was copied or skipped for each series.</li>
</ul>

<h3>Status bar</h3>
<p>Shows import/export/copy results, and (on the right) the pixel position, value and LR/AP/SI position in mm under the cursor.</p>

<h3>Autosave</h3>
<p>Unexported ROIs are autosaved a few seconds after each change. Reopening the same folder offers to restore them.
Closing the app with unexported ROIs asks whether to export first.
With auto-export on, every ROI in the folder is also cached, and reopening the folder loads them automatically,
so you can pick up where you left off.</p>

<h3>Advanced settings</h3>
<p>Edit <code>{CONFIG_PATH}</code> (restart to apply):</p>
<ul>
<li><code>dicom_extensions</code>: file extensions treated as DICOM (default <code>.dcm</code>, <code>.sdcopen</code>).</li>
<li><code>scan_all_files</code>: also check every other file for a DICOM header (finds extensionless files; slower).</li>
<li><code>cv_warning_threshold</code>: flag ROIs with CV above this (default 0.2; 0 disables).</li>
<li><code>edge_warning_threshold</code>: flag ROIs whose inner/outer means differ by more than this fraction of the
median (default 0.2; 0 disables). Maps with values near zero (e.g. low PDFF) may need higher thresholds or 0.</li>
</ul>
"""


class InfoDialog(QDialog):
    """Help window describing features, keyboard shortcuts and mouse controls"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Liver ROI Tool – Info & Shortcuts")
        self.resize(760, 700)

        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(build_help_html())
        layout.addWidget(browser)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
