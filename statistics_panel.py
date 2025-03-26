from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                           QPushButton, QDialog, QFileDialog, QHBoxLayout)
from PyQt5.QtCore import Qt
import csv
from PyQt5.QtGui import QKeySequence

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
        self.stats_table = QTableWidget(0, 5)  # Rows will be added dynamically
        self.stats_table.setHorizontalHeaderLabels(["Segment", "Mean", "Median", "Min", "Max"])
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
            stats = self.roi_manager.calculate_roi_statistics(roi)
            
            if stats:
                # Add a new row
                row = self.stats_table.rowCount()
                self.stats_table.insertRow(row)
                
                # Get segment from ROI
                segment_label = roi[0]
                
                # Add data to the row
                self.stats_table.setItem(row, 0, QTableWidgetItem(segment_label))
                self.stats_table.setItem(row, 1, QTableWidgetItem(f"{stats['mean']:.2f}"))
                self.stats_table.setItem(row, 2, QTableWidgetItem(f"{stats['median']:.2f}"))
                self.stats_table.setItem(row, 3, QTableWidgetItem(f"{stats['min']:.2f}"))
                self.stats_table.setItem(row, 4, QTableWidgetItem(f"{stats['max']:.2f}"))
    
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
        
        # Create table
        table = QTableWidget()
        table.setColumnCount(17)
        table.setHorizontalHeaderLabels([
            "Segment", "Segment Index", "Slice Index", "Center X", "Center Y", "Radius", 
            "Center LR (mm)", "Center AP (mm)", "Center SI (mm)", "Orientation", 
            "Area (mm2)", "Mean", "Median", "Min", "Max", "Size", "Series Path"
            ])

        
        # Set table properties
        table.setEditTriggers(QTableWidget.NoEditTriggers)  # Read-only
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        
        # Populate table with ROI data
        for roi in self.roi_manager.rois:
            segment_label, segment, slice_idx, center_x, center_y, radius, center_LR_mm, center_AP_mm, center_SI_mm, orientation, area_mm2, series_path = roi
            stats = self.roi_manager.calculate_roi_statistics(roi)
            
            if not stats:
                continue
                
            # Add a new row
            row = table.rowCount()
            table.insertRow(row)
            
            # Add data to the row
            table.setItem(row, 0, QTableWidgetItem(segment_label))
            table.setItem(row, 1, QTableWidgetItem(str(segment)))  # 1-based slice index for display
            table.setItem(row, 2, QTableWidgetItem(str(slice_idx + 1)))  # 1-based slice index for display
            table.setItem(row, 3, QTableWidgetItem(f"{center_x:.4f}"))
            table.setItem(row, 4, QTableWidgetItem(f"{center_y:.4f}"))
            table.setItem(row, 5, QTableWidgetItem(f"{radius:.4f}"))
            table.setItem(row, 6, QTableWidgetItem(f"{center_LR_mm:.4f}"))
            table.setItem(row, 7, QTableWidgetItem(f"{center_AP_mm:.4f}"))
            table.setItem(row, 8, QTableWidgetItem(f"{center_SI_mm:.4f}"))
            table.setItem(row, 9, QTableWidgetItem(f"{orientation}"))
            table.setItem(row, 10, QTableWidgetItem(f"{area_mm2:.2f}"))
            table.setItem(row, 11, QTableWidgetItem(f"{stats['mean']:.2f}"))
            table.setItem(row, 12, QTableWidgetItem(f"{stats['median']:.2f}"))
            table.setItem(row, 13, QTableWidgetItem(f"{stats['min']:.2f}"))
            table.setItem(row, 14, QTableWidgetItem(f"{stats['max']:.2f}"))
            table.setItem(row, 15, QTableWidgetItem(str(stats['size'])))
            table.setItem(row, 16, QTableWidgetItem(series_path))
        
        # Add table to layout
        layout.addWidget(table)
        
        # Add button layout
        button_layout = QHBoxLayout()
        
        # Add export button
        export_button = QPushButton("Export Statistics to CSV")
        export_button.clicked.connect(lambda: self.export_statistics(table))
        export_button.setShortcut(QKeySequence(f"Ctrl+s"))

        
        # Add close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        
        button_layout.addWidget(export_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec_()
    
    def export_statistics(self, table):
        """Export statistics table to CSV"""
        default_path = f"{self.dicom_model.current_study_name}/{self.dicom_model.current_series_name}_ROIs.csv"

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Statistics", default_path, "CSV Files (*.csv)"
        )
        
        if not filename:
            return
        
        if not filename.lower().endswith(".csv"):
            filename += ".csv"

        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                headers = []
                for col in range(table.columnCount()):
                    headers.append(table.horizontalHeaderItem(col).text())
                writer.writerow(headers)
                
                # Write data
                for row in range(table.rowCount()):
                    row_data = []
                    for col in range(table.columnCount()):
                        item = table.item(row, col)
                        if item:
                            row_data.append(item.text())
                        else:
                            row_data.append("")
                    writer.writerow(row_data)
                
            print(f"Statistics exported to {filename}")
            return True
        except Exception as e:
            print(f"Error exporting statistics: {e}")
            return False