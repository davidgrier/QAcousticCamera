from QPolargraph import QScanner
from QInstrument.instruments import (QSR830Widget, QDS345Widget)
from QInstrument.instruments import (QFakeDS345, QFakeSR830)
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import (QDesktopWidget, QFileDialog)
import numpy as np
import pandas as pd
import logging


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class QAcousticCamera(QScanner):

    def __init__(self, *args, fake=False, data=None, **kwargs):
        configdir = '~/.QAcousticCamera'
        super().__init__(*args, configdir=configdir, **kwargs)
        self.setWindowTitle('QAcousticCamera')
        self.addInstruments(fake)
        self.connectSignals()
        self.adjustSize()
        self.data = list()
        self.readData(data)

    def adjustSize(self):
        self.resize(QDesktopWidget().availableGeometry(self).size() * 0.8)
        width = 512
        self.ui.splitter.setSizes({width, width})

    def addInstruments(self, fake):
        source = QFakeDS345() if fake else None
        lockin = QFakeSR830() if fake else None
        self.source = QDS345Widget(device=source)
        self.lockin = QSR830Widget(device=lockin)
        self.ui.controlsLayout.addWidget(self.source)
        self.ui.controlsLayout.addWidget(self.lockin)
        self.config.restore(self.source)
        self.config.restore(self.lockin)

    def connectSignals(self):
        self.ui.actionSaveData.triggered.connect(self.saveData)
        self.ui.actionSaveDataAs.triggered.connect(self.saveDataAs)
        self.ui.actionLoadData.triggered.connect(self.loadData)
        self.scanner.dataReady.connect(self.processData)

    @pyqtSlot()
    def saveSettings(self):
        self.config.save(self.source)
        self.config.save(self.lockin)
        super().saveSettings()

    @pyqtSlot()
    def scanStarted(self):
        self.source.device.mute = False
        self.data = list()
        self.dataPlot.clear()
        super().scanStarted()

    def hue(self, phase):
        return [(p/360. + 1.) % 1 for p in np.atleast_1d(phase)]

    @pyqtSlot(np.ndarray)
    def processData(self, position):
        if not self.scanner.scanning():
            return
        freq, amplitude, phase = self.lockin.device.report()
        self.data.append([*position, amplitude, phase])
        self.plotData(*position, self.hue(phase))
        logger.debug(f'Acquired data: {amplitude} {phase}')

    @pyqtSlot()
    def scanFinished(self):
        super().scanFinished()
        self.source.device.mute = True

    def metadata(self):
        md = dict(polargraph=self.ui.polargraph.settings,
                  scanner=self.ui.scanner.settings,
                  source=self.source.settings,
                  lockin=self.lockin.settings)
        return pd.DataFrame(md)

    @pyqtSlot()
    def saveData(self, filename=None):
        columns = ['x', 'y', 'amplitude', 'phase']
        df = pd.DataFrame(np.array(self.data), columns=columns)
        filename = filename or self.config.filename('acam', '.csv')
        if '.csv' in filename:
            df.to_csv(filename, index=False)
        else:
            df.to_hdf(filename, 'data', 'w', index=False)
            self.metadata().to_hdf(filename, 'metadata', 'a')
        self.showStatus(f'Data saved to {filename}')

    @pyqtSlot()
    def saveDataAs(self):
        dialog = QFileDialog.getSaveFileName
        default = self.config.filename('acam', '.csv')
        filename, _ = dialog(self, 'Save Data', default,
                             'CSV (*.csv);;data/metadata (*.h5)')
        if filename:
            self.saveData(filename)
        else:
            self.showStatus('No file selected: Data not saved')

    def readData(self, filename):
        if filename is None:
            return
        self.dataPlot.clear()
        if '.csv' in filename:
            df = pd.read_csv(filename)
        else:
            df = pd.read_hdf(filename, 'data')
        x = df.x.to_numpy()
        y = df.y.to_numpy()
        phase = df.phase.to_numpy()
        self.plotData(x, y, self.hue(phase))
        self.showStatus(f'Loaded {filename}')

    @pyqtSlot()
    def loadData(self):
        dialog = QFileDialog.getOpenFileName
        filename, _ = dialog(self, 'Load Data', self.config.datadir,
                             'CSV (*.csv);;data/metadata (*.h5)')
        self.readData(filename)


def main():
    from PyQt5.QtWidgets import QApplication
    import sys
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-f', '--fake',
                        dest='fake', action='store_true',
                        help='Do not connect to instruments')
    parser.add_argument('-r', '--read', dest='data', help='Read data file')
    args, unparsed = parser.parse_known_args()
    qt_args = sys.argv[:1] + unparsed

    app = QApplication(qt_args)
    camera = QAcousticCamera(fake=args.fake, data=args.data)
    camera.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
