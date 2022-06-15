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
        width = 512
        self.ui.splitter.setSizes({width, width})

    def addInstruments(self):
        self.source = QDS345Widget()
        self.lockin = QSR830Widget()
        self.ui.controlsLayout.addWidget(self.source)
        self.ui.controlsLayout.addWidget(self.lockin)
        self.source.device.mute = True

    def connectSignals(self):
        self.ui.scan.clicked.connect(self.startScan)
        self.scanner.dataReady.connect(self.readData)
        self.scanner.scanFinished.connect(self.finishScan)

    @pyqtSlot()
    def saveSettings(self):
        self.config.save(self.source)
        self.config.save(self.lockin)
        super().saveSettings()

    @pyqtSlot()
    def restoreSettings(self):
        self.config.restore(self.source)
        self.config.restore(self.lockin)
        super().restoreSettings()

    @pyqtSlot()
    def startScan(self):
        self.source.device.mute = False
        self.data = []

    @pyqtSlot(np.ndarray)
    def readData(self, position):
        freq, amplitude, phase = self.lockin.device.report()
        self.data.append([position, amplitude, phase])
        print(freq, amplitude, phase)

    @pyqtSlot()
    def finishScan(self):
        self.source.device.mute = True
        np.savetxt('data.csv', np.array(self.data), delimiter=',')


def main():
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    camera = QAcousticCamera()
    camera.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
