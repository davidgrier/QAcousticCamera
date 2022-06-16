from QPolargraph import QScanner
from QInstrument.instruments import (QSR830Widget, QDS345Widget)
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import (QDesktopWidget, QFileDialog)
import numpy as np
import logging


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class QAcousticCamera(QScanner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle('QAcousticCamera')
        self.addInstruments()
        self.connectSignals()
        self.adjustSize()
        self.data = list()

    def adjustSize(self):
        self.resize(QDesktopWidget().availableGeometry(self).size() * 0.8)
        width = 512
        self.ui.splitter.setSizes({width, width})

    def addInstruments(self):
        self.source = QDS345Widget()
        self.lockin = QSR830Widget()
        self.ui.controlsLayout.addWidget(self.source)
        self.ui.controlsLayout.addWidget(self.lockin)
        #self.source.device.mute = True

    def connectSignals(self):
        self.ui.scan.clicked.connect(self.startScan)
        self.ui.actionSaveData.triggered.connect(self.saveData)
        self.ui.actionSaveDataAs.triggered.connect(self.saveDataAs)
        self.scanner.dataReady.connect(self.readData)
        self.scanner.scanFinished.connect(self.finishScan)

    @pyqtSlot()
    def saveSettings(self):
        #self.config.save(self.source)
        #self.config.save(self.lockin)
        super().saveSettings()

    @pyqtSlot()
    def restoreSettings(self):
        #self.config.restore(self.source)
        #self.config.restore(self.lockin)
        super().restoreSettings()

    @pyqtSlot()
    def startScan(self):
        logger.debug('Starting scan')
        #self.source.device.mute = False
        self.data = list()

    @pyqtSlot(np.ndarray)
    def readData(self, position):
        logger.debug('Reading data')
        freq, amplitude, phase = self.lockin.device.report()
        self.data.append([position, amplitude, phase])
        print(freq, amplitude, phase)

    @pyqtSlot()
    def finishScan(self):
        logger.debug('Finishing scan')
        #self.source.device.mute = True

    @pyqtSlot()
    @pyqtSlot(str)
    def saveData(self, filename=None):
        filename = filename or self.config.filename('acam', 'csv')
        logger.debug(f'Saving data: {filename}')
        np.savetxt(filename, np.array(self.data), delimiter=',')
        self.statusBar().showMessage(f'Saving data: {filename}')

    @pyqtSlot()
    def saveDataAs(self):
        dialog = QFileDialog.getSaveFileName
        default = self.config.filename('acam', 'csv')
        filename = dialog(self, 'Save Data', default, 'CSV (*.csv)')
        if filename:
            self.saveData(filename)
        else:
            logger.debug('Data not saved')
            self.statusBar().showMessage('Data not saved')


def main():
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    camera = QAcousticCamera()
    camera.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
