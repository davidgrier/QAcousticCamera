from QPolargraph import QScanner
from QInstrument.instruments import (QSR830Widget, QDS345Widget)
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QDesktopWidget
import numpy as np


class QAcousticCamera(QScanner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle('QAcousticCamera')
        self.addInstruments()
        self.connectSignals()
        self.adjustSize()

    def adjustSize(self):
        self.resize(QDesktopWidget().availableGeometry(self).size() * 0.8)
        # width1 = self.ui.controls.minimumSize().width()
        # width2 = self.ui.scanWidget.minimumSize().width()
        width = 512  # max(width1, width2)
        self.ui.splitter.setSizes({width, width})
#        super().adjustSize()

    def addInstruments(self):
        self.source = QDS345Widget()
        self.lockin = QSR830Widget()
        self.ui.controlsLayout.addWidget(self.source)
        self.ui.controlsLayout.addWidget(self.lockin)

    def connectSignals(self):
        self.scanner.dataReady.connect(self.readData)

    @pyqtSlot()
    def saveSettings(self):
        # self.config.save(self.source)
        # self.config.save(self.lockin)
        super().saveSettings()

    @pyqtSlot()
    def restoreSettings(self):
        # self.config.restore(self.source)
        # self.config.restore(self.lockin)
        super().restoreSettings()

    @pyqtSlot(np.ndarray)
    def readData(self, position):
        freq, amplitude, phase = self.lockin.device.report()
        print(freq, amplitude, phase)


def main():
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    camera = QAcousticCamera()
    camera.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
