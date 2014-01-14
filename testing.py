__author__ = 'Fish'

from PyQt4.QtCore import Qt, QSize, QString, SIGNAL
from PyQt4.QtGui import QImage, QDialog,\
    QApplication, QSlider, QPushButton,\
    QLabel, QPixmap, QPainter, qRgba,\
    QComboBox, QIcon, QStatusBar,\
    QHBoxLayout, QVBoxLayout, QFrame,\
    QSizePolicy, QButtonGroup, QRadioButton,\
    QGroupBox

number_group = QGroupBox(QString('Class markers'))
vbox_NG = QVBoxLayout()
r1 = QRadioButton('1')
r1.setChecked(True)
r2 = QRadioButton('2')
r3 = QRadioButton('3')
r4 = QRadioButton('4')
r5 = QRadioButton('5')
r6 = QRadioButton('6')

vbox_NG.addWidget(r1)
vbox_NG.addWidget(r2)
vbox_NG.addWidget(r3)
vbox_NG.addWidget(r4)
vbox_NG.addWidget(r5)
vbox_NG.addWidget(r6)

number_group.setLayout(vbox_NG)

