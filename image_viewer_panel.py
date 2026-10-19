from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QShortcut
from PyQt5.QtCore import Qt, QSize, QPointF, QLineF
from PyQt5.QtGui import QPainter, QKeySequence
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QSlider
import numpy as np

from roi_geometry import get_pixel_spacing, normalized_to_patient


EDGE_TOLERANCE_PX = 6  # display pixels from an ROI's edge that count as "resize"
ZOOM_STEP = 1.25  # zoom factor per wheel notch (Ctrl+wheel)


class ImageViewerPanel(QWidget):
    """UI panel for displaying and interacting with DICOM images"""
    window_level_changed = pyqtSignal(int, int)
    cursor_info_changed = pyqtSignal(str)  # pixel position/value/mm under the cursor

    def __init__(self, parent, dicom_model, roi_manager, renderer):
        super().__init__(parent)
        self.dicom_model = dicom_model
        self.roi_manager = roi_manager
        self.renderer = renderer
        self.drawing_roi = False
        self.roi_start_pos = None
        self.roi_current_pos = None
        self.wheel_accum = 0
        self.mode = None  # current mouse interaction: 'draw', 'move', 'resize', 'pan', 'window_level'
        self.last_pos = None
        self.hover_pos = None
        self.drag_roi = None
        self.drag_start = None
        self.drag_original = None
        self.fixed_diameter_mm = 0  # 0 = draw ROIs by dragging

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
        self.image_label.leaveEvent = self.on_leave
        self.image_label.paintEvent = self.on_paint
        
        # Enable mouse tracking for hovering effects
        self.image_label.setMouseTracking(True)
        
        # Arrow-key slice navigation is handled app-wide in DicomViewerApp.eventFilter
        self.image_label.setFocusPolicy(Qt.StrongFocus)

        self.image_label.setAlignment(Qt.AlignCenter)
        
        self.layout.addWidget(self.image_label)

        # Reset zoom/pan
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.reset_view)

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
    
    def hit_test(self, display_pos):
        """Return (roi, 'edge' | 'inside') for an ROI on the current slice under display_pos, else (None, None)"""
        label_size = self.image_label.size()
        rois = self.roi_manager.get_rois_for_slice(self.dicom_model.current_slice_index,
                                                   self.dicom_model.current_series_path)
        # Edges first, so small ROIs can still be resized
        for part in ('edge', 'inside'):
            for roi in reversed(rois):
                center, radius = self.renderer.roi_display_geometry(roi, label_size)
                distance = QLineF(center, display_pos).length()
                if part == 'edge' and abs(distance - radius) <= EDGE_TOLERANCE_PX:
                    return roi, part
                if part == 'inside' and distance < radius:
                    return roi, part
        return None, None

    def fixed_radius_px(self):
        """Radius in image pixels for fixed-size ROIs on the current slice (None if fixed size is off)"""
        slice_data = self.dicom_model.get_current_slice()
        if not self.fixed_diameter_mm or slice_data is None:
            return None
        spacing_x, _ = get_pixel_spacing(slice_data)
        return self.fixed_diameter_mm / 2 / spacing_x

    def set_fixed_diameter(self, diameter_mm):
        """Set fixed ROI diameter in mm (0 = draw by dragging)"""
        self.fixed_diameter_mm = diameter_mm
        self.image_label.update()

    def on_mouse_press(self, event):
        """Handle mouse press on the image"""
        pos = QPointF(event.pos())
        if event.button() == Qt.RightButton:
            # Window/level adjustment with right button
            self.mode = 'window_level'
            self.last_pos = pos
        elif event.button() == Qt.MiddleButton:
            # Pan with middle button
            self.mode = 'pan'
            self.last_pos = pos
        elif event.button() == Qt.LeftButton:
            roi, part = self.hit_test(pos)
            if roi is not None:
                # Move (inside) or resize (edge) an existing ROI
                self.mode = 'move' if part == 'inside' else 'resize'
                self.drag_roi = roi
                self.drag_start = pos
                self.drag_original = (roi.center_x, roi.center_y, roi.radius_px)
            elif self.drawing_roi:
                # Start drawing ROI with left button when in drawing mode
                self.mode = 'draw'
                self.roi_start_pos = pos
                self.roi_current_pos = pos
            self.image_label.update()
    
    def on_mouse_move(self, event):
        """Handle mouse movement on the image"""
        pos = QPointF(event.pos())
        self.hover_pos = pos
        self.update_cursor_info(pos)

        if self.mode == 'window_level':
            # Window/level adjustment with right button
            dx = pos.x() - self.last_pos.x()
            dy = pos.y() - self.last_pos.y()
            
            # Update window/level based on mouse movement
            window = self.renderer.window + dx * self.renderer.drag_step
            window = int(max(1, min(self.renderer.window_max, window)))
            
            level = self.renderer.level - dy * self.renderer.drag_step
            level = int(max(self.renderer.level_min, min(self.renderer.level_max, level)))
            
            # Update renderer
            self.renderer.set_window_level(window, level)
            self.window_level_changed.emit(window, level)
            self.last_pos = pos
        elif self.mode == 'pan':
            self.renderer.pan += pos - self.last_pos
            self.last_pos = pos
        elif self.mode in ('move', 'resize'):
            pixmap_rect = self.renderer.get_pixmap_rect(self.image_label.size())
            center_x, center_y, radius_px = self.drag_original
            if self.mode == 'move':
                delta = pos - self.drag_start
                self.drag_roi.center_x = center_x + delta.x() / pixmap_rect.width()
                self.drag_roi.center_y = center_y + delta.y() / pixmap_rect.height()
            else:
                center, _ = self.renderer.roi_display_geometry(self.drag_roi, self.image_label.size())
                scale = self.renderer.display_to_image_scale(self.image_label.size())
                self.drag_roi.radius_px = max(1.0, QLineF(center, pos).length() * scale)
        elif self.mode == 'draw':
            # Update ROI preview while drawing
            self.roi_current_pos = pos
        else:
            # Hover: show move/resize cursor over ROIs
            _, part = self.hit_test(pos)
            if part == 'inside':
                self.image_label.setCursor(Qt.SizeAllCursor)
            elif part == 'edge':
                self.image_label.setCursor(Qt.SizeFDiagCursor)
            else:
                self.image_label.setCursor(Qt.CrossCursor if self.drawing_roi else Qt.ArrowCursor)

        self.image_label.update()
    
    def on_mouse_release(self, event):
        """Handle mouse release on the image"""
        mode, self.mode = self.mode, None
        if mode in ('move', 'resize'):
            self.finish_roi_edit()
        elif mode == 'draw' and event.button() == Qt.LeftButton:
            self.finish_roi_drawing()
        self.image_label.update()

    def finish_roi_edit(self):
        """Recompute statistics for a moved/resized ROI (restore it if the edit is invalid)"""
        roi = self.drag_roi
        self.drag_roi = None
        if (roi.center_x, roi.center_y, roi.radius_px) == self.drag_original:
            return
        
        new_roi = self.roi_manager.create_roi(roi.series_path, roi.slice_idx, roi.segment,
                                              roi.center_x, roi.center_y, roi.radius_px)
        if new_roi is None or not (0 <= roi.center_x <= 1 and 0 <= roi.center_y <= 1):
            roi.center_x, roi.center_y, roi.radius_px = self.drag_original
            return
        self.roi_manager.add_roi(new_roi)

    def finish_roi_drawing(self):
        """Create an ROI from the drag (or click, in fixed-size mode)"""
        label_size = self.image_label.size()
        fixed_radius_px = self.fixed_radius_px()
        
        # Fixed size: centered where the mouse is released; otherwise where the drag started
        center_pos = self.roi_current_pos if fixed_radius_px else self.roi_start_pos
        norm_x, norm_y = self.renderer.display_to_normalized(center_pos, label_size)
        
        if norm_x is not None and norm_y is not None:
            if fixed_radius_px:
                radius_px = fixed_radius_px
            else:
                # Convert drag distance from display pixels to image pixels
                distance = QLineF(self.roi_start_pos, self.roi_current_pos).length()
                radius_px = distance * self.renderer.display_to_image_scale(label_size)
            
            # Add ROI if it's valid
            if fixed_radius_px or radius_px > 0.01 * min(self.renderer.dicom_size):  # Minimum radius check
                roi = self.roi_manager.create_roi(
                    self.dicom_model.current_series_path,
                    self.dicom_model.current_slice_index,
                    self.roi_manager.current_segment,
                    norm_x, norm_y, radius_px
                )
                if roi is not None:
                    self.roi_manager.add_roi(roi)
        
        # Reset drawing state
        self.roi_start_pos = None
        self.roi_current_pos = None

    def update_cursor_info(self, display_pos):
        """Emit pixel coordinates, value and patient position (mm) under the cursor"""
        norm_x, norm_y = self.renderer.display_to_normalized(display_pos, self.image_label.size())
        slice_data = self.dicom_model.get_current_slice()
        if norm_x is None or slice_data is None:
            self.cursor_info_changed.emit("")
            return
        
        col, row = self.renderer.normalized_to_pixel(norm_x, norm_y)
        value = self.renderer.get_pixel_value(norm_x, norm_y)
        (pos_LR, pos_AP, pos_SI), _ = normalized_to_patient(slice_data, norm_x, norm_y)
        text = f"x {col}, y {row}"
        if value is not None:
            text += f"  |  value {float(value):.2f}"
        if not np.isnan(pos_LR):
            text += f"  |  LR {pos_LR:.1f}  AP {pos_AP:.1f}  SI {pos_SI:.1f} mm"
        self.cursor_info_changed.emit(text)

    def on_leave(self, event):
        """Clear hover preview and cursor readout when the mouse leaves the image"""
        self.hover_pos = None
        self.cursor_info_changed.emit("")
        self.image_label.update()

    def reset_view(self):
        """Reset zoom/pan"""
        self.renderer.reset_view()
        self.image_label.update()
    
    def on_wheel(self, event):
        """Handle mouse wheel: slice navigation, or zoom with Ctrl held"""
        if event.modifiers() & Qt.ControlModifier:
            factor = ZOOM_STEP ** (event.angleDelta().y() / 120)
            self.renderer.zoom_at(QPointF(event.pos()), factor, self.image_label.size())
            self.image_label.update()
            return

        # Accumulate wheel delta so high-resolution wheels/touchpads (small deltas) still step;
        # int() truncates toward zero so up and down behave symmetrically
        self.wheel_accum += event.angleDelta().y()
        steps = int(self.wheel_accum / 120)
        self.wheel_accum -= steps * 120

        # Navigate slices based on wheel direction
        if steps > 0:
            for _ in range(steps):
                self.dicom_model.previous_slice()
        else:
            for _ in range(-steps):
                self.dicom_model.next_slice()
    
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
        
        # Preview of the ROI being created (display coordinates)
        drawing_roi = None
        fixed_radius_px = self.fixed_radius_px()
        if self.drawing_roi and fixed_radius_px and self.mode is None and self.hover_pos is not None:
            scale = self.renderer.display_to_image_scale(self.image_label.size())
            drawing_roi = {'center': self.hover_pos, 'radius': fixed_radius_px / scale}
        elif self.mode == 'draw' and self.roi_current_pos is not None:
            if fixed_radius_px:
                scale = self.renderer.display_to_image_scale(self.image_label.size())
                drawing_roi = {'center': self.roi_current_pos, 'radius': fixed_radius_px / scale}
            else:
                drawing_roi = {'center': self.roi_start_pos,
                               'radius': QLineF(self.roi_start_pos, self.roi_current_pos).length()}
        
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