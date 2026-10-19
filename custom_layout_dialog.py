from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
                             QSpinBox, QComboBox, QTableWidget, QTableWidgetItem, QPushButton,
                             QMessageBox, QHeaderView)
from PyQt5.QtCore import Qt

from schemes import (SCHEMES, CUSTOM_PREFIX, DEFAULT_SCHEME, register_custom_scheme, unregister_custom_scheme,
                     custom_scheme_names, save_custom_schemes, default_custom_label)

NEW_LAYOUT = "New layout"
MAX_ROIS = 99


class CustomLayoutDialog(QDialog):
    """Create, edit or delete custom ROI layouts with numbered, optionally named ROIs"""

    def __init__(self, parent, roi_manager):
        super().__init__(parent)
        self.roi_manager = roi_manager
        self.setWindowTitle("Custom ROI Layouts")
        self.resize(420, 520)
        self.setup_ui()

        # Start on the active layout if it is a custom one
        active = roi_manager.segmentation_scheme
        if active.startswith(CUSTOM_PREFIX):
            self.layout_combo.setCurrentText(active[len(CUSTOM_PREFIX):])
        self.on_layout_selected()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.layout_combo = QComboBox()
        self.layout_combo.addItems([NEW_LAYOUT] + custom_scheme_names())
        self.layout_combo.currentIndexChanged.connect(self.on_layout_selected)
        form.addRow("Edit:", self.layout_combo)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Spleen + liver")
        form.addRow("Layout name:", self.name_input)

        self.count_input = QSpinBox()
        self.count_input.setRange(1, MAX_ROIS)
        self.count_input.valueChanged.connect(self.set_row_count)
        form.addRow("Number of ROIs:", self.count_input)
        layout.addLayout(form)

        layout.addWidget(QLabel("ROI names are optional; blank names are shown as 'ROI <number>'.\n"
                                "ROIs 1–9 can be selected with Ctrl+1 … Ctrl+9."))

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["#", "Name (optional)"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        button_layout = QHBoxLayout()
        self.delete_button = QPushButton("Delete Layout")
        self.delete_button.clicked.connect(self.on_delete)
        save_button = QPushButton("Save")
        save_button.setDefault(True)
        save_button.clicked.connect(self.on_save)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def on_layout_selected(self):
        """Load the selected layout (or a blank one) into the editor"""
        name = self.layout_combo.currentText()
        is_new = name == NEW_LAYOUT
        labels = [] if is_new else SCHEMES[CUSTOM_PREFIX + name]["labels"]

        self.name_input.setText("" if is_new else name)
        self.delete_button.setEnabled(not is_new)
        self.count_input.blockSignals(True)
        self.count_input.setValue(len(labels) or 3)
        self.count_input.blockSignals(False)
        self.set_row_count(self.count_input.value())
        for row, label in enumerate(labels):
            self.table.item(row, 1).setText("" if label == default_custom_label(row + 1) else label)

    def set_row_count(self, count):
        """Add/remove ROI rows, keeping names already entered"""
        old_count = self.table.rowCount()
        self.table.setRowCount(count)
        for row in range(old_count, count):
            number = QTableWidgetItem(str(row + 1))
            number.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, number)
            self.table.setItem(row, 1, QTableWidgetItem(""))

    def current_labels(self):
        labels = []
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 1).text().strip()
            labels.append(name or default_custom_label(row + 1))
        return labels

    def on_save(self):
        name = self.name_input.text().strip()
        labels = self.current_labels()
        original = self.layout_combo.currentText()

        if not name:
            QMessageBox.warning(self, "Custom Layout", "Enter a layout name.")
            return
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            QMessageBox.warning(self, "Custom Layout", f"ROI names must be unique: {', '.join(duplicates)}")
            return
        if name != original and CUSTOM_PREFIX + name in SCHEMES:
            if QMessageBox.question(self, "Custom Layout",
                                    f"A layout named '{name}' already exists. Replace it?") != QMessageBox.Yes:
                return

        active = self.roi_manager.segmentation_scheme
        edited_keys = {CUSTOM_PREFIX + name} | ({CUSTOM_PREFIX + original} if original != NEW_LAYOUT else set())
        active_changes = active in edited_keys and (CUSTOM_PREFIX + name != active
                                                    or SCHEMES[active]["labels"] != labels)
        if active_changes and self.roi_manager.rois:
            if QMessageBox.question(
                    self, "Custom Layout",
                    f"This layout is in use. Saving will delete all {len(self.roi_manager.rois)} ROIs. "
                    "Continue?") != QMessageBox.Yes:
                return

        if original not in (NEW_LAYOUT, name):
            unregister_custom_scheme(original)
        key = register_custom_scheme(name, labels)
        save_custom_schemes()

        # Re-apply the active layout if it changed; switch to a new layout when no ROIs would be lost
        switched = active_changes or (original == NEW_LAYOUT and not self.roi_manager.rois)
        if switched:
            self.roi_manager.set_segmentation_scheme(key)

        self.layout_combo.blockSignals(True)
        self.layout_combo.clear()
        self.layout_combo.addItems([NEW_LAYOUT] + custom_scheme_names())
        self.layout_combo.setCurrentText(name)
        self.layout_combo.blockSignals(False)
        self.delete_button.setEnabled(True)
        QMessageBox.information(self, "Custom Layout", f"Saved layout '{name}' with {len(labels)} ROIs. " +
                                ("It is now the active scheme." if switched
                                 else "Select it under Segmentation Scheme to use it."))

    def on_delete(self):
        name = self.layout_combo.currentText()
        key = CUSTOM_PREFIX + name
        if key == self.roi_manager.segmentation_scheme:
            if self.roi_manager.rois:
                QMessageBox.warning(self, "Custom Layout", "This layout is in use. Switch to another scheme first.")
                return
            self.roi_manager.set_segmentation_scheme(DEFAULT_SCHEME)
        if QMessageBox.question(self, "Custom Layout", f"Delete layout '{name}'?") != QMessageBox.Yes:
            return
        unregister_custom_scheme(name)
        save_custom_schemes()
        self.layout_combo.removeItem(self.layout_combo.currentIndex())
