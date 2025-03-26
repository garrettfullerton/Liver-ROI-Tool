import sys
from PyQt5.QtWidgets import QApplication

from dicom_viewer_app import DicomViewerApp
from dicom_series_model import DicomSeriesModel
from roi_manager import ROIManager
from ai_model_manager import AIModelManager

def main():
    app = QApplication(sys.argv)
    dicom_model = DicomSeriesModel()
    roi_manager = ROIManager(dicom_model=dicom_model)
    ai_model_manager = None
    viewer_app = DicomViewerApp(dicom_model=dicom_model, roi_manager=roi_manager, ai_model_manager=ai_model_manager)
    viewer_app.show()
    sys.exit(app.exec_())

if __name__=='__main__':
    main()