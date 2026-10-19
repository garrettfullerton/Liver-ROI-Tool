from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                           QPushButton, QDialog, QHBoxLayout)
from PyQt5.QtGui import QKeySequence

from roi_manager import EXPORT_COLUMNS, format_value

class StatisticsPanel(QWidget):
    """UI panel for displaying and exporting ROI statistics"""
    def __init__(self, parent, dicom_model, roi_manager):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
    
    def setup_ui(self):
        """Set up UI components for statistics"""
        self.layout = QVBoxLayout(self)
        
        # Statistics table
        self.stats_table = QTableWidget(0, 6)  # Rows will be added dynamically
        self.stats_table.setHorizontalHeaderLabels(["Segment", "Mean", "Median", "Std", "Min", "Max"])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        
        # Set table properties
        self.stats_table.setEditTriggers(QTableWidget.NoEditTriggers)  # Read-only
        self.stats_table.setAlternatingRowColors(True)
        
        self.layout.addWidget(self.stats_table)
    
    def update_statistics(self):
        """Update the ROI statistics table for current slice"""
        # Clear the table
        self.stats_table.setRowCount(0)
        
        # Get current slice index from the model
        if not self.dicom_model.current_series:
            return
            
        current_slice = self.dicom_model.current_slice_index
        
        # Get ROIs for current slice
        current_slice_rois = self.roi_manager.get_rois_for_slice(current_slice, self.dicom_model.current_series_path)
        
        
        # Add stats for each ROI
        for roi in current_slice_rois:            
            # Add a new row
            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
                        
            # Add data to the row
            self.stats_table.setItem(row, 0, QTableWidgetItem(roi.segment_label))
            self.stats_table.setItem(row, 1, QTableWidgetItem(f"{roi.mean_val:.2f}"))
            self.stats_table.setItem(row, 2, QTableWidgetItem(f"{roi.median_val:.2f}"))
            self.stats_table.setItem(row, 3, QTableWidgetItem(f"{roi.std_val:.2f}"))
            self.stats_table.setItem(row, 4, QTableWidgetItem(f"{roi.min_val:.2f}"))
            self.stats_table.setItem(row, 5, QTableWidgetItem(f"{roi.max_val:.2f}"))
    
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
            for col, (_, getter) in enumerate(EXPORT_COLUMNS):
                table.setItem(row, col, QTableWidgetItem(format_value(getter(roi))))
        
        # Add table to layout
        layout.addWidget(table)
        
        # Add button layout
        button_layout = QHBoxLayout()
        
        # Add export button
        export_button = QPushButton("Export Statistics to CSV")
        export_button.clicked.connect(lambda: self.roi_manager.export_rois())
        export_button.setShortcut(QKeySequence(f"Ctrl+s"))

        
        # Add close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        
        button_layout.addWidget(export_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec_()
