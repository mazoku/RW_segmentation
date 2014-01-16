
import numpy as np

import sys
import os

from PyQt4.QtGui import QApplication, QMainWindow, QWidget,\
     QGridLayout, QLabel, QPushButton, QFrame, QFileDialog,\
     QFont, QPixmap, QComboBox
from PyQt4.Qt import QString

path_to_script = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(path_to_script, "../extern/pyseg_base/src"))

import dcmreaddata as dcmreader
from interactiv_editor import QTSeedEditor
# import pycut
import datareader

from seg2mesh import gen_mesh_from_voxels, mesh2vtk, smooth_mesh

try:
    from viewer import QVTKViewer
    viewer3D_available = True

except ImportError:
    viewer3D_available = False

import logging
logger = logging.getLogger(__name__)

scaling_modes = {
    'original': (None, None, None),
    'double': (None, 'x2', 'x2'),
    '3mm': (None, '3', '3'),
    }

import time

# version comparison
from pkg_resources import parse_version
import sklearn
if parse_version(sklearn.__version__) > parse_version('0.10'):
    #new versions
    cvtype_name = 'covariance_type'
else:
    cvtype_name = 'cvtype'

class OrganSegmentationWindow(QMainWindow):

    def __init__(self):

        self.roi = None
        self.input_wvx_size = 3
        self.autocrop_margin_mm = np.array((10,10,10))
        self.seeds = None

        QMainWindow.__init__(self)
        self.initUI()

        self.statusBar().showMessage('Ready')

    def initUI(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        grid = QGridLayout()
        grid.setSpacing(15)

        # status bar
        self.statusBar().showMessage('Ready')

        font_label = QFont()
        font_label.setBold(True)
        font_info = QFont()
        font_info.setItalic(True)
        font_info.setPixelSize(10)

        #############

        lisa_title = QLabel('Organ Segmentation with Random Walker')
        info = QLabel('Developed by:\n' +
                      'University of West Bohemia\n' +
                      'Faculty of Applied Sciences\n' +
                      QString.fromUtf8('M. Jirik, V. Lukes, T. Ryba - 2013')
                      )
        info.setFont(font_info)
        lisa_title.setFont(font_label)
        lisa_logo = QLabel()
        logopath = os.path.join(path_to_script, 'kky_small.png')
        logo = QPixmap(logopath)
        lisa_logo.setPixmap(logo)
        grid.addWidget(lisa_title, 0, 1)
        grid.addWidget(info, 1, 1)
        grid.addWidget(lisa_logo, 0, 2, 2, 1)
        grid.setColumnMinimumWidth(1, logo.width())

        ### dicom reader
        rstart = 2
        hr = QFrame()
        hr.setFrameShape(QFrame.HLine)
        text_dcm = QLabel('DICOM reader')
        text_dcm.setFont(font_label)
        btn_dcmdir = QPushButton("Load DICOM", self)
        btn_dcmdir.clicked.connect(self.loadDcmDir)
        btn_dcmcrop = QPushButton("Crop", self)
        btn_dcmcrop.clicked.connect(self.cropDcm)

        self.text_dcm_dir = QLabel('DICOM dir:')
        self.text_dcm_data = QLabel('DICOM data:')
        grid.addWidget(hr, rstart + 0, 0, 1, 4)
        grid.addWidget(text_dcm, rstart + 1, 1, 1, 2)
        grid.addWidget(btn_dcmdir, rstart + 2, 1)
        grid.addWidget(btn_dcmcrop, rstart + 2, 2)
        grid.addWidget(self.text_dcm_dir, rstart + 5, 1, 1, 2)
        grid.addWidget(self.text_dcm_data, rstart + 6, 1, 1, 2)
        rstart += 8

        # ################ segmentation
        hr = QFrame()
        hr.setFrameShape(QFrame.HLine)
        text_seg = QLabel('Segmentation')
        text_seg.setFont(font_label)
        btn_segauto = QPushButton("Automatic seg.", self)
        btn_segauto.clicked.connect(self.autoSeg)
        btn_segman = QPushButton("Manual seg.", self)
        btn_segman.clicked.connect(self.manualSeg)
        self.text_seg_data = QLabel('segmented data:')
        grid.addWidget(hr, rstart + 0, 0, 1, 4)
        grid.addWidget(text_seg, rstart + 1, 1)
        grid.addWidget(btn_segauto, rstart + 2, 1)
        grid.addWidget(btn_segman, rstart + 2, 2)
        grid.addWidget(self.text_seg_data, rstart + 3, 1, 1, 2)
        rstart += 4

        # ################ save/view
        btn_segsave = QPushButton("Save", self)
        btn_segsave.clicked.connect(self.saveOut)
        btn_segsavedcm = QPushButton("Save Dicom", self)
        btn_segsavedcm.clicked.connect(self.saveOutDcm)
        btn_segview = QPushButton("View3D", self)
        if viewer3D_available:
            btn_segview.clicked.connect(self.view3D)

        else:
            btn_segview.setEnabled(False)

        grid.addWidget(btn_segsave, rstart + 0, 1)
        grid.addWidget(btn_segview, rstart + 0, 2)
        grid.addWidget(btn_segsavedcm, rstart + 1, 1)
        rstart += 2

        hr = QFrame()
        hr.setFrameShape(QFrame.HLine)
        grid.addWidget(hr, rstart + 0, 0, 1, 4)

        # quit
        btn_quit = QPushButton("Quit", self)
        btn_quit.clicked.connect(self.quit)
        grid.addWidget(btn_quit, rstart + 1, 1, 1, 2)

        cw.setLayout(grid)
        self.setWindowTitle('Organ Segmentation with Random Walker')
        self.show()


    def quit(self, event):
        self.close()


    def changeVoxelSize(self, val):
        self.scaling_mode = str(val)


    def setLabelText(self, obj, text):
        dlab = str(obj.text())
        obj.setText(dlab[:dlab.find(':')] + ': %s' % text)


    def getDcmInfo(self):
        vx_size = self.voxelsize_mm
        vsize = tuple([float(ii) for ii in vx_size])
        ret = ' %dx%dx%d,  %fx%fx%f mm' % (self.data3d.shape + vsize)

        return ret


    def loadDcmDir(self):
        self.statusBar().showMessage('Reading DICOM directory...')
        QApplication.processEvents()

        # oseg = self.oseg
        # if oseg.datapath is None:
        #    oseg.datapath = dcmreader.get_dcmdir_qt(app=True)
        self.datapath = dcmreader.get_dcmdir_qt(app=True)

        # if oseg.datapath is None:
        #     self.statusBar().showMessage('No DICOM directory specified!')
        #     return

        if self.datapath is None:
            self.statusBar().showMessage('No DICOM directory specified!')
            return

        reader = datareader.DataReader()

        # oseg.data3d, oseg.metadata = reader.Get3DData(oseg.datapath)
        self.data3d, self.metadata = reader.Get3DData(self.datapath)
        # oseg.process_dicom_data()
        self.process_dicom_data()
        # self.setLabelText(self.text_dcm_dir, oseg.datapath)
        self.setLabelText(self.text_dcm_dir, self.datapath)
        self.setLabelText(self.text_dcm_data, self.getDcmInfo())
        self.statusBar().showMessage('Ready')


    def process_dicom_data(self):
        if self.roi is not None:
            self.crop(self.roi)

        self.voxelsize_mm = np.array(self.metadata['voxelsize_mm'])
        self.process_wvx_size_mm()
        self.autocrop_margin = self.autocrop_margin_mm / self.voxelsize_mm
        self.zoom = self.voxelsize_mm / (1.0 * self.working_voxelsize_mm)
        self.orig_shape = self.data3d.shape
        self.segmentation = np.zeros(self.data3d.shape, dtype=np.int8)

        if self.seeds is None:
            self.seeds = np.zeros(self.data3d.shape, dtype=np.int8)
        logger.info('dir ' + str(self.datapath) + ", series_number" +\
            str(self.metadata['series_number']) +'voxelsize_mm' +\
            str(self.voxelsize_mm))
        self.time_start = time.time()


    def process_wvx_size_mm(self):
        vx_size = self.input_wvx_size
        if vx_size == 'orig':
            vx_size = self.metadata['voxelsize_mm']
        elif vx_size == 'orig*2':
            vx_size = np.array(self.metadata['voxelsize_mm']) * 2
        elif vx_size == 'orig*4':
            vx_size = np.array(self.metadata['voxelsize_mm']) * 4
        if np.isscalar(vx_size):
            vx_size = ([vx_size] * 3)

        vx_size = np.array(vx_size).astype(float)
        self.working_voxelsize_mm = vx_size


    def cropDcm(self):
        if self.data3d is None:
            self.statusBar().showMessage('No DICOM data!')
            return

        self.statusBar().showMessage('Cropping DICOM data...')
        QApplication.processEvents()

        pyed = QTSeedEditor(self.data3d, mode='crop',
                            voxelSize=self.voxelsize_mm)
        pyed.exec_()

        crinfo = pyed.getROI()
        if crinfo is not None:
            tmpcrinfo = []
            for ii in crinfo:
                tmpcrinfo.append([ii.start, ii.stop])

            oseg.crop(tmpcrinfo)

        self.setLabelText(self.text_dcm_data, self.getDcmInfo())
        self.statusBar().showMessage('Ready')


    def autoSeg(self):
        if self.data3d is None:
            self.statusBar().showMessage('No DICOM data!')
            return

        pyed = QTSeedEditor(self.data3d, mode='seed',
                            voxelSize=self.voxelsize_mm)
        pyed.exec_()

        self.segmentation = pyed.segmentation
        self.checkSegData('manual seg., ')


    def manualSeg(self):
        oseg = self.oseg
        if  oseg.data3d is None:
            self.statusBar().showMessage('No DICOM data!')
            return

        pyed = QTSeedEditor(oseg.data3d,
                            seeds=oseg.segmentation,
                            mode='draw',
                            voxelSize=oseg.voxelsize_mm)
        pyed.exec_()

        oseg.segmentation = pyed.getSeeds()
        self.checkSegData('manual seg., ')


    def checkSegData(self, msg):
        oseg = self.oseg
        if oseg.segmentation is None:
            self.statusBar().showMessage('No segmentation!')
            return

        nzs = oseg.segmentation.nonzero()
        nn = nzs[0].shape[0]
        if nn > 0:
            voxelvolume_mm3 = np.prod(oseg.voxelsize_mm)

            aux = 'volume = %.6e mm3' % (nn * voxelvolume_mm3, )
            self.setLabelText(self.text_seg_data, msg + aux)
            self.statusBar().showMessage('Ready')
        else:
            self.statusBar().showMessage('No segmentation!')


    def saveOut(self, event=None, filename=None):
        if self.oseg.segmentation is not None:
            self.statusBar().showMessage('Saving segmentation data...')
            QApplication.processEvents()

            self.oseg.save_outputs()
            self.statusBar().showMessage('Ready')
        else:
            self.statusBar().showMessage('No segmentation data!')


    def saveOutDcm(self, event=None, filename=None):
        if self.oseg.segmentation is not None:
            self.statusBar().showMessage('Saving segmentation data...')
            QApplication.processEvents()

            self.oseg.save_outputs_dcm()
            self.statusBar().showMessage('Ready')
        else:
            self.statusBar().showMessage('No segmentation data!')


    def view3D(self):
        oseg = self.oseg
        if oseg.segmentation is not None:
            pts, els, et = gen_mesh_from_voxels(oseg.segmentation,
                                                oseg.voxelsize_mm,
                                                etype='q', mtype='s')
            pts = smooth_mesh(pts, els, et, n_iter=10)
            vtkdata = mesh2vtk(pts, els, et)
            view = QVTKViewer(vtk_data=vtkdata)
            view.exec_()

        else:
            self.statusBar().showMessage('No segmentation data!')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = OrganSegmentationWindow()
    sys.exit(app.exec_())