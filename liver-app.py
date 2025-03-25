import sys
from PyQt5.QtWidgets import QApplication

from dicom_viewer_app import DicomViewerApp
from dicom_series_model import DicomSeriesModel
from roi_manager import ROIManager

def main():
    app = QApplication(sys.argv)
    dicom_model = DicomSeriesModel()
    roi_manager = ROIManager(dicom_model=dicom_model)
    viewer_app = DicomViewerApp(dicom_model=dicom_model, roi_manager=roi_manager)
    viewer_app.show()
    sys.exit(app.exec_())

if __name__=='__main__':
    main()