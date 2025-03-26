from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt, QSize, QPointF
from PyQt5.QtGui import QPainter
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QSlider

import numpy as np

class ImageViewerPanel(QWidget):
    """UI panel for displaying and interacting with DICOM images"""
    window_level_changed = pyqtSignal(int, int)

    def __init__(self, parent, dicom_model, roi_manager, renderer):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        self.renderer = renderer
        self.drawing_roi = False
        self.roi_start_pos = None
        self.roi_current_pos = None
    
    def setup_ui(self):
        """Set up UI components for image viewing"""
        self.layout = QVBoxLayout(self)
        
        # Slice Navigation controls (at the top)
        self.nav_widget = QWidget()
        
        self.nav_widget_layout = QVBoxLayout(self.nav_widget)

        self.nav_click_widget = QWidget()
        self.nav_click_layout = QHBoxLayout(self.nav_click_widget)
        
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.on_previous_slice)
        self.prev_button.setMaximumSize(QSize(100, 30))
        
        self.slice_label = QLabel("Slice: 0/0")
        self.slice_label.setAlignment(Qt.AlignCenter)
        self.slice_label.setMaximumSize(QSize(100, 30))
        
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.on_next_slice)
        self.next_button.setMaximumSize(QSize(100, 30))
        
        self.nav_click_layout.addWidget(self.prev_button, alignment=Qt.AlignLeft)
        self.nav_click_layout.addWidget(self.slice_label, alignment=Qt.AlignCenter)
        self.nav_click_layout.addWidget(self.next_button, alignment=Qt.AlignRight)

        self.nav_click_layout.setAlignment(Qt.AlignTop)

        self.nav_slider_widget = QWidget()
        self.nav_slider_layout = QHBoxLayout(self.nav_slider_widget)

        self.nav_slider = QSlider(Qt.Horizontal)
        self.nav_slider.setMinimum(0)
        self.nav_slider.setMaximum(100)
        self.nav_slider.setTickInterval(1)
        self.nav_slider.valueChanged.connect(self.on_slider_changed)
        self.nav_slider_layout.addWidget(self.nav_slider)

        self.nav_widget_layout.addWidget(self.nav_click_widget)
        self.nav_widget_layout.addWidget(self.nav_slider_widget)

        self.layout.addWidget(self.nav_widget)

        self.series_label = QLabel("Series: None")
        self.series_label.setAlignment(Qt.AlignLeft)
        self.series_label.setAlignment(Qt.AlignVCenter)
        self.layout.addWidget(self.series_label)
        
        # Image display
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignTop)
        self.image_label.setMinimumSize(512, 512)
        
        # Override default event handlers
        self.image_label.mousePressEvent = self.on_mouse_press
        self.image_label.mouseMoveEvent = self.on_mouse_move
        self.image_label.mouseReleaseEvent = self.on_mouse_release
        self.image_label.wheelEvent = self.on_wheel
        self.image_label.paintEvent = self.on_paint
        
        # Enable mouse tracking for hovering effects
        self.image_label.setMouseTracking(True)
        
        # Enable focus to capture keyboard events
        self.image_label.setFocusPolicy(Qt.StrongFocus)
        self.image_label.keyPressEvent = self.on_key_press

        self.image_label.setAlignment(Qt.AlignCenter)
        
        self.layout.addWidget(self.image_label)

        # blank label for spacing
        self.layout.addWidget(QLabel(""))

    def update_series_label(self):
        """Update the series label with the current series name"""
        self.series_label.setText(f"Series: {self.dicom_model.current_series_name}")
        
    def on_slider_changed(self, value):
        """Handle slider value change"""
        # Only update if the value actually changed to avoid recursion
        current_slice = self.dicom_model.current_slice_index + 1  # +1 for UI display
        if value != current_slice:
            # -1 because slider is 1-based but model is 0-based
            self.dicom_model.set_slice_index(value - 1)

    def update_display(self):
        """Update the display with current slice"""
        if not self.dicom_model.current_series:
            self.image_label.setText("No image loaded")
            return
            
        # Get current slice pixel data
        pixel_array = self.dicom_model.get_slice_pixel_data(self.dicom_model.current_slice_index)
        if pixel_array is None:
            self.image_label.setText("Invalid slice")
            return
            
        # Update renderer with new image data
        self.renderer.set_image_data(pixel_array)
        
        # Update slice counter
        self.update_slice_info()
        
        # Force repaint
        self.image_label.update()
    
    def update_slice_info(self):
        """Update slice counter information"""
        if self.dicom_model.current_series:
            current = self.dicom_model.current_slice_index + 1
            total = self.dicom_model.get_num_slices()
            self.slice_label.setText(f"Slice: {current}/{total}")

            # Block signals to prevent recursive updates
            self.nav_slider.blockSignals(True)
            self.nav_slider.setMinimum(1)
            self.nav_slider.setMaximum(total)
            self.nav_slider.setValue(current)
            self.nav_slider.blockSignals(False)
        else:
            self.slice_label.setText("Slice: 0/0")
    
    def on_previous_slice(self):
        """Handle previous slice button click"""
        self.dicom_model.previous_slice()
    
    def on_next_slice(self):
        """Handle next slice button click"""
        self.dicom_model.next_slice()
    
    def on_mouse_press(self, event):
        """Handle mouse press on the image"""
        if event.button() == Qt.RightButton:
            # Window/level adjustment with right button
            self.mouse_pressed = True
            self.last_pos = event.pos()
        elif event.button() == Qt.LeftButton and self.drawing_roi:
            # Start drawing ROI with left button when in drawing mode
            self.roi_start_pos = event.pos()
            self.roi_current_pos = event.pos()
            self.image_label.update()
    
    def on_mouse_move(self, event):
        """Handle mouse movement on the image"""
        if hasattr(self, 'mouse_pressed') and self.mouse_pressed and hasattr(self, 'last_pos') and event.buttons() & Qt.RightButton:
            # Window/level adjustment with right button
            dx = event.x() - self.last_pos.x()
            dy = event.y() - self.last_pos.y()
            
            # Get current window/level
            window = self.renderer.window
            level = self.renderer.level
            
            # Update window/level based on mouse movement
            window += dx * 3
            window = max(1, min(4000, window))
            
            level -= dy * 3
            level = max(-2000, min(2000, level))
            
            # Update renderer
            self.renderer.set_window_level(window, level)

            # Force repaint
            self.image_label.update()

            self.window_level_changed.emit(window, level)
            
            self.last_pos = event.pos()
        elif self.drawing_roi and self.roi_start_pos:
            # Update ROI preview while drawing
            self.roi_current_pos = event.pos()
            self.image_label.update()
    
    def on_mouse_release(self, event):
        """Handle mouse release on the image"""
        if event.button() == Qt.RightButton:
            # End window/level adjustment
            self.mouse_pressed = False
            self.last_pos = None
        elif event.button() == Qt.LeftButton and self.drawing_roi and self.roi_start_pos:
            # Finalize ROI
            label_size = self.image_label.size()
            
            # Convert to normalized coordinates
            norm_x, norm_y = self.renderer.display_to_normalized(
                QPointF(self.roi_start_pos), label_size
            )
            
            if norm_x is not None and norm_y is not None:
                # Calculate radius in normalized units
                current_pt = QPointF(self.roi_current_pos)
                distance = (current_pt - QPointF(self.roi_start_pos)).manhattanLength() / 2
                normalized_radius = distance / min(label_size.width(), label_size.height())
                
                # Add ROI if it's valid
                if normalized_radius > 0.01:  # Minimum radius check
                    # get anatomical position and physical size
                    anat_pos = (0, 0, 0)
                    area_mm2 = 0

                    slice_data = self.dicom_model.get_slice(self.dicom_model.current_slice_index)
                    if slice_data:
                        # Get pixel spacing if available
                        pixel_spacing = getattr(slice_data, 'PixelSpacing', [1, 1])
                        rows = getattr(slice_data, 'Rows', 1)
                        cols = getattr(slice_data, 'Columns', 1)
                        spacing_x, spacing_y = float(pixel_spacing[1]), float(pixel_spacing[0])
                        
                        # Calculate physical area
                        pixel_radius = normalized_radius * min(slice_data.Columns, slice_data.Rows)
                        physical_radius_mm = pixel_radius * spacing_x  # Assuming square pixels
                        area_mm2 = np.pi * (physical_radius_mm ** 2)
                        
                        # Get anatomical position if available
                        if hasattr(slice_data, 'ImagePositionPatient'):
                            anat_pos = slice_data.ImagePositionPatient

                        if hasattr(slice_data, 'ImageOrientationPatient'):
                            orientation_vec = slice_data.ImageOrientationPatient
                            orientation_vec_cross = np.cross(orientation_vec[:3], orientation_vec[3:])
                            orientation_vec_cross_rounded = [round(abs(val), 0) for val in orientation_vec_cross]
                            orientation = orientation_vec_cross_rounded.index(1.0) + 1
                            if orientation == 1:
                                # sagittal
                                pos_LR = anat_pos[0]
                                pos_AP = anat_pos[1] + (spacing_y * (rows * (1 - norm_y)))
                                pos_SI = anat_pos[2] + (spacing_x * (cols * norm_x))
                            elif orientation == 2:
                                # coronal
                                pos_LR = anat_pos[0] + (spacing_x * (cols * norm_x))
                                pos_AP = anat_pos[1]
                                pos_SI = anat_pos[2] + (spacing_y * (rows * (1 - norm_y)))
                            elif orientation == 3:
                                # axial
                                pos_LR = anat_pos[0] + (spacing_x * (cols * norm_x))
                                pos_AP = anat_pos[1] + (spacing_y * (rows * (1 - norm_y)))
                                pos_SI = anat_pos[2]
                        else:
                            orientation = "N/A"
                            pos_LR = "N/A"
                            pos_AP = "N/A"
                            pos_SI = "N/A"

                    self.roi_manager.add_roi(
                        self.dicom_model.current_slice_index,
                        self.roi_manager.segment_labels[self.roi_manager.current_segment - 1],
                        self.dicom_model.current_series_path,
                        norm_x, norm_y, normalized_radius, 
                        pos_LR, pos_AP, pos_SI, orientation, area_mm2
                    )
            
            # Reset drawing state
            self.roi_start_pos = None
            self.roi_current_pos = None
            self.image_label.update()
    
    def on_wheel(self, event):
        """Handle mouse wheel for slice navigation"""
        # Calculate the number of steps (usually 1, but can be more for some mice)
        steps = event.angleDelta().y() // 120
        
        # Navigate slices based on wheel direction
        if steps > 0:
            for _ in range(steps):
                self.dicom_model.previous_slice()
        else:
            for _ in range(-steps):
                self.dicom_model.next_slice()
    
    def on_key_press(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key_Left or event.key() == Qt.Key_Up:
            self.dicom_model.previous_slice()
        elif event.key() == Qt.Key_Right or event.key() == Qt.Key_Down:
            self.dicom_model.next_slice()
        else:
            # Pass event to parent class for default handling
            super().keyPressEvent(event)
    
    def on_paint(self, event):
        """Custom paint event for image and ROIs"""
        # Start with standard paint event
        super().paintEvent(event)
        
        # Check if we have an image to display
        if self.renderer.get_pixmap() is None:
            return
            
        painter = QPainter(self.image_label)
        
        # Get ROIs for current slice
        current_rois = self.roi_manager.get_rois_for_slice(self.dicom_model.current_slice_index, self.dicom_model.current_series_path)
        
        # Create drawing ROI data if needed
        drawing_roi = None
        if self.drawing_roi and self.roi_start_pos and self.roi_current_pos:
            drawing_roi = {
                'start': self.roi_start_pos,
                'current': self.roi_current_pos
            }
        
        # Render the image and ROIs
        self.renderer.render(
            painter, 
            self.image_label.size(), 
            current_rois, 
            drawing_roi
        )
        
        painter.end()
    
    def set_drawing_mode(self, enabled):
        """Set whether we're in ROI drawing mode"""
        self.drawing_roi = enabled
        if enabled:
            self.image_label.setCursor(Qt.CrossCursor)
        else:
            self.image_label.setCursor(Qt.ArrowCursor)