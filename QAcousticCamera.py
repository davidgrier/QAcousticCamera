from pathlib import Path
from QPolargraph import QScanner
from QInstrument.instruments import QDS345Widget, QFakeDS345, QSR830Widget, QFakeSR830
from qtpy import QtCore, QtGui, QtWidgets
import numpy as np
import pandas as pd
from scipy.interpolate import griddata, LinearNDInterpolator
import logging


logger = logging.getLogger(__name__)


class QAcousticCamera(QScanner):
    '''Scanning holographic acoustic camera.

    Extends the QScanner polargraph interface with a DS345 function
    generator (tone source) and SR830 lock-in amplifier (detector).
    Each scan position yields amplitude and phase measurements that
    are stored and rendered as a phase-encoded color scatter plot.

    Parameters
    ----------
    fake : bool, optional
        If True, replace hardware widgets with simulated instruments.
        Default: False.
    data : str | None, optional
        Path to a CSV or HDF5 data file to load on startup.
        Default: None.
    '''

    def __init__(self,
                 *args,
                 fake: bool = False,
                 data: str | None = None,
                 **kwargs) -> None:
        configdir = '~/.QAcousticCamera'
        super().__init__(*args, fake=fake, configdir=configdir, **kwargs)
        self._setupUi()
        self._addInstruments(fake)
        self._connectSignals()
        self.adjustSize()
        self.data: list[list[float]] = []
        field = self._loadDemoField() if fake else None
        self._field: LinearNDInterpolator | None = field
        self.readData(data)

    def _setupUi(self) -> None:
        '''Set up the UI layout with a data plot and controls.'''
        self.setWindowTitle('QAcousticCamera')
        icon_path = Path(__file__).parent / 'docs' / 'icon.png'
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))

    def adjustSize(self) -> None:
        '''Resize the window to 80% of the available screen area.'''
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            self.resize(int(geom.width() * 0.8), int(geom.height() * 0.8))
        self.splitter.setSizes([512, 512])

    def _addInstruments(self, fake: bool) -> None:
        '''Create and register instrument widgets.

        Parameters
        ----------
        fake : bool
            If True, use simulated instruments instead of real hardware.
        '''
        source = QFakeDS345() if fake else None
        lockin = QFakeSR830() if fake else None
        self.source = QDS345Widget(device=source)
        self.lockin = QSR830Widget(device=lockin)
        self.controlsLayout.addWidget(self.source)
        self.controlsLayout.addWidget(self.lockin)
        self.config.restore(self.source)
        self.config.restore(self.lockin)

    def _connectSignals(self) -> None:
        '''Connect UI actions and scanner signals to their slots.'''
        super()._connectSignals()
        self.actionSaveData.triggered.connect(self.saveData)
        self.actionSaveDataAs.triggered.connect(self.saveDataAs)
        self.actionLoadData.triggered.connect(self.loadData)
        self.dataReady.connect(self.processData)

    @QtCore.Slot()
    def saveSettings(self) -> None:
        '''Save instrument and scanner settings to config.'''
        self.config.save(self.source)
        self.config.save(self.lockin)
        super().saveSettings()

    @QtCore.Slot()
    def scanStarted(self) -> None:
        '''Unmute the signal source and clear data when a scan begins.'''
        self.source.device.mute = False
        self.data = []
        self.dataPlot.clear()
        super().scanStarted()

    def hue(self, phase: float | np.ndarray) -> list[float]:
        '''Convert phase angle(s) in degrees to hue values in [0, 1).

        Parameters
        ----------
        phase : float | np.ndarray
            Phase angle(s) in degrees.

        Returns
        -------
        list[float]
            Hue values mapped from phase, wrapped to [0, 1).
        '''
        return [(p / 360. + 1.) % 1 for p in np.atleast_1d(phase)]

    def _loadDemoField(self) -> LinearNDInterpolator | None:
        '''Build a complex-signal interpolator from the demo data file.

        Interpolates ``amplitude * exp(i * phase)`` over the (x, y)
        positions in ``docs/demo.csv``.  Returns ``None`` if the file
        is not found.

        Returns
        -------
        LinearNDInterpolator or None
            Interpolator mapping (x, y) → complex signal, or ``None``.
        '''
        path = Path(__file__).parent / 'docs' / 'demo.csv'
        if not path.exists():
            logger.warning(f'Demo field not found: {path}')
            return None
        df = pd.read_csv(path)
        xy = df[['x', 'y']].to_numpy()
        amplitude = df['amp'].to_numpy()
        phase = df['phase'].to_numpy()
        signal = amplitude * np.exp(1j * np.radians(phase))
        return LinearNDInterpolator(xy, signal, fill_value=0.)

    @QtCore.Slot(dict)
    def processData(self, position: dict) -> None:
        '''Record amplitude and phase at the current scan position.

        In fake mode, interpolates amplitude and phase from the demo
        field rather than reading from hardware.  Appends
        ``[x, y, amplitude, phase]`` to ``self.data`` and updates the
        scatter plot.  No-op if the scanner is not actively scanning.

        Parameters
        ----------
        position : dict
            Current position from the scanner with keys ``'x'`` and ``'y'``.
        '''
        if not self.scanner.pattern.scanning():
            return
        x, y = position['x'], position['y']
        if self._field is not None:
            signal = self._field([[x, y]])[0]
            amplitude = float(np.abs(signal))
            phase = float(np.degrees(np.angle(signal)))
        else:
            freq, amplitude, phase = self.lockin.device.report()
        self.data.append([x, y, amplitude, phase])
        self.plotData(x, y, self.hue(phase))
        logger.debug(f'Acquired data: {amplitude} {phase}')

    @QtCore.Slot()
    def scanFinished(self) -> None:
        '''Mute the signal source when the scan completes.'''
        super().scanFinished()
        self.source.device.mute = True

    def dataframe(self) -> pd.DataFrame:
        '''Return the current scan data as a DataFrame.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns ``['x', 'y', 'amplitude', 'phase']``.
        '''
        columns = ['x', 'y', 'amplitude', 'phase']
        if not self.data:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame(np.array(self.data), columns=columns)

    def metadata(self) -> pd.DataFrame:
        '''Return instrument and scanner settings as a DataFrame.

        Returns
        -------
        pd.DataFrame
            DataFrame with keys for polargraph, scanner, source, and
            lockin settings.
        '''
        md = dict(polargraph=self.polargraph.settings,
                  scanner=self.scanner.settings,
                  source=self.source.settings,
                  lockin=self.lockin.settings)
        return pd.DataFrame(md)

    @QtCore.Slot()
    def saveData(self, filename: str | None = None) -> None:
        '''Save scan data to a CSV or HDF5 file.

        Parameters
        ----------
        filename : str | None, optional
            Output path. If None, a default timestamped name is used.
            File format is determined by the ``.csv`` or ``.h5``
            extension.
        '''
        filename = filename or self.config.filename('acam', '.csv')
        if '.csv' in filename:
            self.dataframe().to_csv(filename, index=False)
        else:
            self.dataframe().to_hdf(filename, 'data', 'w', index=False)
            self.metadata().to_hdf(filename, 'metadata', 'a')
        self.showStatus(f'Data saved to {filename}')

    @QtCore.Slot()
    def saveDataAs(self) -> None:
        '''Open a save dialog and save data to the chosen file.'''
        default = self.config.filename('acam', '.csv')
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Data', default, 'CSV (*.csv);;data/metadata (*.h5)')
        if filename:
            self.saveData(filename)
        else:
            self.showStatus('No file selected: Data not saved')

    def readData(self, filename: str | None) -> None:
        '''Load scan data from a CSV or HDF5 file.

        Parameters
        ----------
        filename : str | None
            Path to the data file. Does nothing if None or empty.
        '''
        if not filename:
            return
        self.dataPlot.clear()
        if '.csv' in filename:
            df = pd.read_csv(filename)
        else:
            df = pd.read_hdf(filename, 'data')
        self.data = df[['x', 'y', 'amplitude', 'phase']].to_numpy().tolist()
        x = df.x.to_numpy()
        y = df.y.to_numpy()
        phase = df.phase.to_numpy()
        self.plotData(x, y, self.hue(phase))
        self.showStatus(f'Loaded {filename}')

    @QtCore.Slot()
    def loadData(self) -> None:
        '''Open a file dialog and load scan data from the chosen file.'''
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load Data', self.config.datadir,
            'CSV (*.csv);;data/metadata (*.h5)')
        self.readData(filename)

    @QtCore.Slot()
    def interpolate(self) -> np.ndarray:
        '''Resample scattered scan data onto a regular grid.

        Uses ``scipy.griddata`` (linear interpolation) to resample
        the complex-valued signal (amplitude * exp(i*phase)) from
        the irregular scatter of scan positions onto a rectangular
        grid whose resolution and bounds match the scanner settings.

        Returns
        -------
        np.ndarray
            2D array of complex signal values on the regular grid.
        '''
        df = self.dataframe()
        xy = df[['y', 'x']].to_numpy()
        x0, y0, x1, y1 = self.scanner.pattern.rect
        resolution = self.scanner.pattern.step * 1e-3
        grid = np.mgrid[y0:y1:resolution, x0:x1:resolution].T
        signal = df.amplitude * np.exp(1.j * np.radians(df.phase))
        return griddata(xy, signal, grid, fill_value=np.mean(signal))


def main() -> None:
    '''Launch the QAcousticCamera application.'''
    from argparse import ArgumentParser
    import pyqtgraph as pg

    logging.basicConfig()
    parser = ArgumentParser(description='Scanning acoustic camera')
    parser.add_argument('-f', '--fake',
                        dest='fake', action='store_true',
                        help='Do not connect to instruments')
    parser.add_argument('-r', '--read', dest='data',
                        metavar='FILE', help='Read data file on startup')
    args = parser.parse_args()

    pg.mkQApp('QAcousticCamera')
    camera = QAcousticCamera(fake=args.fake, data=args.data)
    camera.show()
    pg.exec()


if __name__ == '__main__':
    main()


__all__ = ['QAcousticCamera']
