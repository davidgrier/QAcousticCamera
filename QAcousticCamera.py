from QPolargraph import QScanner
from QInstrument.instruments import (QSR830Widget, QDS345Widget)
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import (QDesktopWidget, QFileDialog)
import numpy as np
import logging

from QInstrument.instruments import QFakeDS345

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class QAcousticCamera(QScanner):

    def __init__(self, *args, fake=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle('QAcousticCamera')
        self.addInstruments(fake)
        self.connectSignals()
        self.adjustSize()
        self.data = list()

    def adjustSize(self):
        self.resize(QDesktopWidget().availableGeometry(self).size() * 0.8)
        width = 512
        self.ui.splitter.setSizes({width, width})

    def addInstruments(self, fake):
        device = QFakeDS345() if fake else None
        self.source = QDS345Widget(device=device)
        self.lockin = QSR830Widget()
        self.ui.controlsLayout.addWidget(self.source)
        self.ui.controlsLayout.addWidget(self.lockin)
        self.config.restore(self.source)
        self.config.restore(self.lockin)

    def connectSignals(self):
        self.ui.scan.clicked.connect(self.startScan)
        self.ui.actionSaveData.triggered.connect(self.saveData)
        self.ui.actionSaveDataAs.triggered.connect(self.saveDataAs)
        self.scanner.dataReady.connect(self.readData)
        self.scanner.scanFinished.connect(self.finishScan)

    @pyqtSlot()
    def saveSettings(self):
        self.config.save(self.source)
        # self.config.save(self.lockin)
        super().saveSettings()

    @pyqtSlot()
    def startScan(self):
        logger.debug('Starting scan')
        self.source.device.mute = False
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
        self.source.device.mute = True

    @pyqtSlot()
    def saveData(self, filename=None):
        filename = filename or self.config.filename('acam', 'csv')
        np.savetxt(filename, np.array(self.data), delimiter=',')
        self.statusBar().showMessage(f'Data saved to {filename}')

    @pyqtSlot()
    def saveDataAs(self):
        dialog = QFileDialog.getSaveFileName
        default = self.config.filename('acam', '.csv')
        filename, _ = dialog(self, 'Save Data', default, 'CSV (*.csv)')
        if filename:
            self.saveData(filename)
        else:
            self.statusBar().showMessage('No file selected: Data not saved')


def main():
    from PyQt5.QtWidgets import QApplication
    import sys
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-f', '--fake',
                        dest='fake', action='store_true',
                        help='Do not connect to instruments')
    args, unparsed = parser.parse_known_args()
    qt_args = sys.argv[:1] + unparsed

    app = QApplication(qt_args)
    camera = QAcousticCamera(fake=args.fake)
    camera.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
