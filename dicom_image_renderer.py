import numpy as np
from PyQt5.QtCore import QObject, Qt, QRectF, QPointF
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QBrush, QColor

class DicomImageRenderer(QObject):
    """Handles rendering of DICOM images with window/level and overlays"""
    def __init__(self, parent_widget, dicom_model, roi_manager):
        super().__init__()
        self.parent = parent_widget
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        self.window = self.dicom_model.default_window
        self.level = self.dicom_model.default_level
        self.pixel_array = None
        self.pixmap = None
        self.dicom_size = (0, 0)  # Original DICOM image size
    
    def set_image_data(self, pixel_array):
        """Set the image data to render"""
        if pixel_array is None:
            self.pixel_array = None
            self.pixmap = None
            self.dicom_size = (0, 0)
            return False
        
        self.pixel_array = pixel_array
        self.dicom_size = pixel_array.shape
        self.apply_window_level()
        return True
    
    def set_window_level(self, window, level):
        """Set window/level parameters"""
        if window <= 0:
            window = 1
            
        self.window = window
        self.level = level
       
        if self.pixel_array is not None:
            self.apply_window_level()
            return True
            
        return False
    
    def apply_window_level(self):
        """Apply window/level to the image data and create a pixmap"""
        if self.pixel_array is None:
            return False
            
        # Apply window/level settings
        lower_bound = self.level - self.window/2
        upper_bound = self.level + self.window/2
        
        display_image = np.clip(self.pixel_array, lower_bound, upper_bound)
        display_image = ((display_image - lower_bound) / (upper_bound - lower_bound) * 255).astype(np.uint8)
        
        # Convert to QImage and then to pixmap
        height, width = display_image.shape
        bytes_per_line = width
        q_image = QImage(display_image.data, width, height, bytes_per_line, QImage.Format_Grayscale8)
        
        self.pixmap = QPixmap.fromImage(q_image)
        return True
    
    def get_pixmap(self):
        """Get the current pixmap"""
        return self.pixmap
    
    def get_pixmap_rect(self, label_size):
        """Calculate the rectangle where the pixmap will be drawn"""
        if self.pixmap is None:
            return QRectF()
            
        # Calculate scaled size maintaining aspect ratio
        pixmap_size = self.pixmap.size()
        scaled_size = pixmap_size
        scaled_size.scale(label_size, Qt.KeepAspectRatio)
        
        # Calculate position to center the pixmap
        x = (label_size.width() - scaled_size.width()) / 2
        y = (label_size.height() - scaled_size.height()) / 2
        
        return QRectF(x, y, scaled_size.width(), scaled_size.height())
    
    def render(self, painter, label_size, rois=None, drawing_roi=None):
        """Render the image with current window/level settings and ROIs"""
        if self.pixmap is None:
            return False
        
        # Get the rectangle where the pixmap will be drawn
        pixmap_rect = self.get_pixmap_rect(label_size)
        
        # Draw the pixmap
        painter.drawPixmap(
            pixmap_rect.toRect(),
            self.pixmap,
            self.pixmap.rect()
        )
        
        # Draw ROIs if provided
        if rois:
            for roi in rois:
                if self.roi_manager.segmentation_scheme == "4-segment":
                    if roi.segment_label == "Left Lateral":
                        segment_label_disp = "LL"
                    elif roi.segment_label == "Left Medial":
                        segment_label_disp = "LM"
                    elif roi.segment_label == "Right Anterior":
                        segment_label_disp = "RA"
                    elif roi.segment_label == "Right Posterior":
                        segment_label_disp = "RP"
                    else:
                        segment_label_disp = roi.segment_label
                else:
                    segment_label_disp = roi.segment_label
                
                
                # Scale ROI coordinates to current display
                scaled_x = pixmap_rect.x() + (roi.center_x * pixmap_rect.width())
                scaled_y = pixmap_rect.y() + (roi.center_y * pixmap_rect.height())
                scaled_radius = roi.radius_px * min(pixmap_rect.width(), pixmap_rect.height())
                
                # Set color based on segment
                color = self.get_segment_color(roi.segment)
                
                # Draw circle
                painter.setPen(QPen(color, 2, Qt.SolidLine))
                painter.setBrush(QBrush(color, Qt.NoBrush))
                painter.drawEllipse(QPointF(scaled_x, scaled_y), scaled_radius, scaled_radius)
                
                # Draw segment label
                painter.setPen(QPen(Qt.white, 1))
                painter.drawText(QRectF(scaled_x - 10, scaled_y - 10, 20, 20), 
                                Qt.AlignCenter, segment_label_disp)
        
        # Draw ROI being created
        if drawing_roi and 'start' in drawing_roi and 'current' in drawing_roi:
            start_pos = drawing_roi['start']
            current_pos = drawing_roi['current']
            
            # Calculate center and radius
            center = QPointF(start_pos)
            radius = (current_pos - start_pos).manhattanLength() / 2
            
            # Draw preview circle
            painter.setPen(QPen(Qt.yellow, 2, Qt.DashLine))
            painter.setBrush(QBrush(Qt.yellow, Qt.NoBrush))
            painter.drawEllipse(center, radius, radius)
        
        return True
    
    def get_segment_color(self, segment):
        """Get color based on liver segment"""
        colors = {
            1: QColor(255, 0, 0, 128),    # Red
            2: QColor(0, 255, 0, 128),    # Green
            3: QColor(0, 0, 255, 128),    # Blue
            4: QColor(255, 255, 0, 128),  # Yellow
            5: QColor(255, 0, 255, 128),  # Magenta
            6: QColor(0, 255, 255, 128),  # Cyan
            7: QColor(255, 128, 0, 128),  # Orange
            8: QColor(128, 0, 255, 128),  # Purple
            9: QColor(0, 128, 128, 128),  # Teal
        }
        return colors.get(segment, QColor(255, 255, 255, 128))
    
    def pixel_to_normalized(self, pixel_x, pixel_y):
        """Convert pixel coordinates to normalized coordinates (0-1)"""
        if self.dicom_size[0] == 0 or self.dicom_size[1] == 0:
            return None, None
            
        norm_x = pixel_x / self.dicom_size[1]
        norm_y = pixel_y / self.dicom_size[0]
        
        return norm_x, norm_y
    
    def normalized_to_pixel(self, norm_x, norm_y):
        """Convert normalized coordinates (0-1) to pixel coordinates"""
        if self.dicom_size[0] == 0 or self.dicom_size[1] == 0:
            return None, None
            
        pixel_x = int(norm_x * self.dicom_size[1])
        pixel_y = int(norm_y * self.dicom_size[0])
        
        return pixel_x, pixel_y
    
    def display_to_normalized(self, display_pos, label_size):
        """Convert display coordinates to normalized coordinates"""
        pixmap_rect = self.get_pixmap_rect(label_size)
        
        if not pixmap_rect.isValid():
            return None, None
            
        # Calculate normalized coordinates (0-1 range)
        norm_x = (display_pos.x() - pixmap_rect.x()) / pixmap_rect.width()
        norm_y = (display_pos.y() - pixmap_rect.y()) / pixmap_rect.height()
        
        # Ensure coordinates are within valid range
        if 0 <= norm_x <= 1 and 0 <= norm_y <= 1:
            return norm_x, norm_y
            
        return None, None
    
    def get_pixel_value(self, norm_x, norm_y):
        """Get original pixel value at given normalized coordinates"""
        if self.pixel_array is None or not (0 <= norm_x <= 1 and 0 <= norm_y <= 1):
            return None
            
        pixel_x, pixel_y = self.normalized_to_pixel(norm_x, norm_y)
        
        if pixel_x is None or pixel_y is None:
            return None
            
        # Ensure coordinates are within bounds
        if 0 <= pixel_y < self.dicom_size[0] and 0 <= pixel_x < self.dicom_size[1]:
            return self.pixel_array[pixel_y, pixel_x]
            
        return None