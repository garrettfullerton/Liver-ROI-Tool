from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                           QPushButton, QDialog, QHBoxLayout)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence, QColor

from roi_manager import EXPORT_COLUMNS

class StatisticsPanel(QWidget):
    """UI panel for displaying and exporting ROI statistics"""
    def __init__(self, parent, dicom_model, roi_manager):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
    
    def setup_ui(self):
        """Set up UI components for statistics"""
        self.layout = QVBoxLayout(self)
        
        # Per-series ROI checklist: one row per segment of the scheme; double-click jumps to the ROI's slice
        self.stats_table = QTableWidget(0, 9)  # Rows will be added dynamically
        self.stats_table.setHorizontalHeaderLabels(["Segment", "Slice", "Mean", "Median", "Std", "CV", "Min", "Max", "⚠"])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setToolTip("ROIs in the current series (bold = on this slice). Double-click to go to the slice.")
        self.stats_table.cellDoubleClicked.connect(self.on_row_double_clicked)
        
        # Set table properties
        self.stats_table.setEditTriggers(QTableWidget.NoEditTriggers)  # Read-only
        self.stats_table.setAlternatingRowColors(True)
        
        self.layout.addWidget(self.stats_table)
    
    def update_statistics(self):
        """Update the ROI checklist/statistics table for the current series"""
        # Clear the table
        self.stats_table.setRowCount(0)
        
        if not self.dicom_model.current_series:
            return
            
        current_slice = self.dicom_model.current_slice_index
        series_rois = {roi.segment: roi for roi in self.roi_manager.rois
                       if roi.series_path == self.dicom_model.current_series_path}
        
        for segment, label in enumerate(self.roi_manager.segment_labels, start=1):
            roi = series_rois.get(segment)
            if roi is None:
                values = [label, "—", "", "", "", "", "", "", ""]
            else:
                values = ([label, str(roi.slice_idx + 1)]
                          + [f"{v:.2f}" for v in (roi.mean_val, roi.median_val, roi.std_val, roi.cv,
                                                  roi.min_val, roi.max_val)]
                          + ["⚠" if roi.flags else ""])

            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if roi is None:
                    item.setForeground(QColor(Qt.gray))
                elif roi.flags:
                    # Quality warning: high CV or edge/heterogeneity
                    item.setForeground(QColor(220, 120, 0))
                    item.setToolTip(roi.flags)
                if roi is not None and roi.slice_idx == current_slice:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.stats_table.setItem(row, col, item)

    def on_row_double_clicked(self, row, column):
        """Jump to the slice of the ROI in the clicked row"""
        segment = row + 1
        for roi in self.roi_manager.rois:
            if roi.series_path == self.dicom_model.current_series_path and roi.segment == segment:
                self.dicom_model.set_slice_index(roi.slice_idx)
                return
    
    def show_detailed_statistics(self):
        """Show a detailed statistics window for all ROIs"""
        if not self.roi_manager.rois:
            return
            
        # Create a new dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("ROI Statistics")
        dialog.setMinimumSize(800, 600)
        
        # Create layout
        layout = QVBoxLayout(dialog)
        
        # Create table (same columns as the CSV export)
        table = QTableWidget(0, len(EXPORT_COLUMNS))
        table.setHorizontalHeaderLabels([header for header, _ in EXPORT_COLUMNS])
        
        # Set table properties
        table.setEditTriggers(QTableWidget.NoEditTriggers)  # Read-only
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        
        # Populate table with ROI data
        for roi in self.roi_manager.rois:
            row = table.rowCount()
            table.insertRow(row)
            for col, value in enumerate(self.roi_manager.export_row(roi)):
                table.setItem(row, col, QTableWidgetItem(value))
        
        # Add table to layout
        layout.addWidget(table)
        
        # Add button layout
        button_layout = QHBoxLayout()
        
        # Add export button
        export_button = QPushButton("Export Statistics to CSV")
        export_button.clicked.connect(lambda: self.roi_manager.export_rois())
        export_button.setShortcut(QKeySequence("Ctrl+s"))

        
        # Add close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        
        button_layout.addWidget(export_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec_()
