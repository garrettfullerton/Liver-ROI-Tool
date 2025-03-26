# ai_model_manager.py
"""
Manager class to integrate AI model with the Liver MRI Viewer
"""
from ai_model.model_inference import ROIPredictor

class AIModelManager:
    def __init__(self, model_path=None):
        self.predictor = None
        if model_path:
            self.load_model(model_path)
    
    def load_model(self, model_path):
        """Load AI model from specified path"""
        self.predictor = ROIPredictor(model_path)
        return self.predictor is not None
    
    def predict_rois(self, dicom_series):
        """Predict ROIs for a series of DICOM images"""
        if not self.predictor:
            return None
            
        rois = []
        for slice_idx, dicom_data in enumerate(dicom_series):
            # Get prediction for this slice
            slice_rois = self.predictor.predict(dicom_data)
            
            # Add slice index to ROIs
            for roi in slice_rois:
                rois.append((slice_idx,) + roi)
                
        return rois