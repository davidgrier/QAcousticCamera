from __future__ import annotations

import collections
import time
from pathlib import Path
from QPolargraph import QScanner
from QPolargraph.patterns.QScanPattern import ScanState
from QInstrument.instruments import QDS345Widget, QFakeDS345, QSR830Widget, QFakeSR830
from qtpy import QtCore, QtGui, QtWidgets
import numpy as np
import pandas as pd
from scipy.interpolate import griddata, LinearNDInterpolator
import logging


logger = logging.getLogger(__name__)


class SR830Worker(QtCore.QObject):
    '''Background worker that reads SR830 and correlates readings with position.

    Runs ``report()`` in a tight loop on a dedicated thread. Each reading is
    time-stamped and paired with a linearly-interpolated position from a
    shared position buffer maintained by the main-thread scan loop.

    The position buffer holds ``(timestamp, x, y)`` tuples written by the
    main thread each time the polargraph emits a position update.  For each
    SR830 reading at time ``t_s``, the worker finds the nearest buffer entries
    before and after ``t_s`` and interpolates:

    .. code-block:: text

        α = (t_s − t_before) / (t_after − t_before)
        x = x_before + α · (x_after − x_before)
        y = y_before + α · (y_after − y_before)

    Readings that arrive before any trailing bracket is available are held in
    a pending list and resolved on the next iteration.  Any still-pending
    readings are flushed using the nearest available position when ``stop()``
    is called.

    Parameters
    ----------
    lockin : QSR830
        SR830 instrument instance.  ``report()`` is called directly; the
        caller must ensure no other thread accesses the device concurrently.
    position_buffer : collections.deque
        Shared deque of ``(timestamp, x, y)`` tuples.  Written by the main
        thread, read here.  Python's deque is safe for single-writer /
        single-reader access under the GIL.

    Notes
    -----
    Timestamps use :func:`time.monotonic` to match the timestamps embedded
    in :class:`~QPolargraph.QScanPattern.QScanPattern` position data.

    Signals
    -------
    dataReady(dict)
        Emitted for each resolved SR830 reading.
        Keys: ``'x'``, ``'y'``, ``'amplitude'``, ``'phase'``.
    '''

    dataReady = QtCore.Signal(dict)

    def __init__(self, lockin: object,
                 position_buffer: collections.deque) -> None:
        super().__init__()
        self._lockin = lockin
        self._buffer = position_buffer
        self._running = False

    @QtCore.Slot()
    def run(self) -> None:
        '''Read SR830 continuously and emit interpolated measurements.

        Blocks until :meth:`stop` is called.  Pending readings that are
        still waiting for a trailing position bracket are flushed at the
        end of the run using the nearest available position.
        '''
        self._running = True
        pending: list[tuple[float, float, float]] = []
        while self._running:
            try:
                t_s = time.monotonic()
                _, amplitude, phase = self._lockin.report()
            except Exception:
                logger.exception('SR830 read failed; stopping acquisition')
                break
            pending.append((t_s, amplitude, phase))
            self._flush(pending)
        self._flush(pending, final=True)

    @QtCore.Slot()
    def stop(self) -> None:
        '''Signal the run loop to exit after the current report() completes.'''
        self._running = False

    def _flush(self, pending: list[tuple[float, float, float]],
               final: bool = False) -> None:
        '''Resolve pending SR830 readings against the position buffer.

        For each pending reading, searches the position buffer for a sample
        before and after the SR830 timestamp.  If both are found, the
        position is linearly interpolated and :attr:`dataReady` is emitted.
        Readings without a trailing bracket remain pending unless
        ``final=True``, in which case the nearest available position is used.

        Parameters
        ----------
        pending : list of (float, float, float)
            ``(timestamp, amplitude, phase)`` tuples, modified in place.
            Resolved entries are removed.
        final : bool, optional
            If ``True``, resolve all remaining readings using the nearest
            available position rather than waiting for a trailing bracket.
            Default: ``False``.
        '''
        snapshot = list(self._buffer)
        resolved = []
        for t_s, amplitude, phase in pending:
            before = [(t, x, y) for t, x, y in snapshot if t <= t_s]
            after  = [(t, x, y) for t, x, y in snapshot if t  > t_s]
            if before and after:
                t0, x0, y0 = before[-1]
                t1, x1, y1 = after[0]
                alpha = (t_s - t0) / (t1 - t0) if t1 > t0 else 0.0
                x = x0 + alpha * (x1 - x0)
                y = y0 + alpha * (y1 - y0)
            elif final:
                candidates = before or after
                if not candidates:
                    continue
                _, x, y = candidates[-1] if before else candidates[0]
            else:
                continue
            resolved.append((t_s, amplitude, phase))
            self.dataReady.emit({'x': x, 'y': y,
                                 'amplitude': amplitude, 'phase': phase})
        for item in resolved:
            pending.remove(item)


class QAcousticCamera(QScanner):
    '''Scanning holographic acoustic camera.

    Extends the QScanner polargraph interface with a DS345 function
    generator (tone source) and SR830 lock-in amplifier (detector).
    Each scan position yields amplitude and phase measurements that
    are stored and rendered as a phase-encoded color scatter plot.

    During a scan with real hardware, an :class:`SR830Worker` runs on a
    dedicated thread, calling ``report()`` as fast as the instrument
    allows and correlating each reading with an interpolated polargraph
    position from the shared position buffer.  In fake mode the demo
    acoustic field is sampled directly at each polargraph position update
    instead.

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
        # Initialise all instance attrs before super().__init__() so that
        # connectSignals() (called inside super) never sees unset attributes.
        self._fake = fake
        self.data: list[list[float]] = []
        self._field: LinearNDInterpolator | None = (
            self._loadDemoField() if fake else None)
        self._scan_active: bool = False
        self._collecting: bool = False
        self._position_buffer: collections.deque | None = None
        self._sr830_worker: SR830Worker | None = None
        self._sr830_thread: QtCore.QThread | None = None
        configdir = '~/.QAcousticCamera'
        super().__init__(*args, fake=fake, configdir=configdir, **kwargs)
        self.readData(data)

    def setupUi(self) -> None:
        '''Extend the scanner UI with instrument widgets and a window icon.'''
        super().setupUi()
        self.setWindowTitle('QAcousticCamera')
        icon_path = Path(__file__).parent / 'docs' / 'icon.png'
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))
        self._addInstruments(self._fake)
        geom = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.resize(int(geom.width() * 0.8), int(geom.height() * 0.8))

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

    def connectSignals(self) -> None:
        '''Connect UI actions and scanner signals to their slots.'''
        super().connectSignals()
        self.actionSaveData.triggered.connect(self.saveData)
        self.actionSaveDataAs.triggered.connect(self.saveDataAs)
        self.actionLoadData.triggered.connect(self.loadData)

    def _lockedWidgets(self) -> list:
        '''Include instrument widgets in the set locked during scans.'''
        return super()._lockedWidgets() + [self.source, self.lockin]

    @QtCore.Slot()
    def saveSettings(self) -> None:
        '''Save instrument and scanner settings to config.'''
        self.config.save(self.source)
        self.config.save(self.lockin)
        super().saveSettings()

    @QtCore.Slot()
    def toggleScan(self) -> None:
        '''Start SR830 acquisition when initiating a new scan.

        Extends :meth:`~QPolargraph.QScanner.QScanner.toggleScan` to
        call :meth:`_onScanStarting` when the scan state machine is IDLE
        (i.e. a new scan is being initiated, not a pause or resume).
        '''
        if not self.scanner.pattern.active() and not self._scan_active:
            self._onScanStarting()
        super().toggleScan()

    def _onStateChanged(self, state: ScanState) -> None:
        '''Handle scan state transitions.

        Extends :meth:`~QPolargraph.QScanner.QScanner._onStateChanged`
        to call :meth:`_onScanFinished` when the state machine returns
        to IDLE after a scan — whether it completed normally, was
        abandoned, or was interrupted.

        Parameters
        ----------
        state : ScanState
            New state of the scan pattern.
        '''
        super()._onStateChanged(state)
        self._collecting = (state == ScanState.SCANNING)
        if state == ScanState.IDLE and self._scan_active:
            self._onScanFinished()

    def _onScanStarting(self) -> None:
        '''Prepare for a new scan: unmute source, clear data, start worker.

        Called by :meth:`toggleScan` when a new scan is being initiated.
        Starts the :class:`SR830Worker` thread for real-hardware mode so
        that acquisition is already running when the polargraph begins
        moving to the scan start position.
        '''
        self._scan_active = True
        self.source.device.mute = False
        self.data = []
        self.dataPlot.clear()
        if not self._fake and self.lockin.device.isOpen():
            self._position_buffer = collections.deque(maxlen=100)
            self._sr830_worker = SR830Worker(
                self.lockin.device, self._position_buffer)
            self._sr830_thread = QtCore.QThread()
            self._sr830_worker.moveToThread(self._sr830_thread)
            self._sr830_thread.started.connect(self._sr830_worker.run)
            self._sr830_worker.dataReady.connect(self._onAcousticData)
            self._sr830_thread.start()

    def _onScanFinished(self) -> None:
        '''Clean up after a scan: stop worker, mute source, redraw.

        Called by :meth:`_onStateChanged` whenever the state returns to
        IDLE — whether the scan completed normally, was paused then
        abandoned, or was interrupted.  Waits up to 2 s for the SR830
        thread to exit so no in-flight readings are lost.
        '''
        self._scan_active = False
        if self._sr830_worker is not None:
            self._sr830_worker.stop()
        if self._sr830_thread is not None:
            self._sr830_thread.quit()
            self._sr830_thread.wait(2000)
            self._sr830_thread = None
        self._sr830_worker = None
        self._position_buffer = None
        self.source.device.mute = True
        self.redrawData()

    @QtCore.Slot(object)
    def _onDataReady(self, pos: np.ndarray) -> None:
        '''Handle a position update from the scan loop.

        In fake mode, samples the demo acoustic field at ``pos`` during
        SCANNING only.  In real-hardware mode, pushes a timestamped
        position entry to the shared buffer throughout all motion so that
        the :class:`SR830Worker` has position brackets available as soon
        as SCANNING begins.

        Parameters
        ----------
        pos : np.ndarray
            Position data ``[x, y, t]`` from the scan pattern, where
            ``t`` is a :func:`time.monotonic` timestamp [s].
        '''
        x, y = float(pos[0]), float(pos[1])
        if self._field is not None:
            if self._collecting:
                signal = self._field([[x, y]])[0]
                self._appendData(x, y,
                                 float(np.abs(signal)),
                                 float(np.degrees(np.angle(signal))))
        elif self._position_buffer is not None:
            self._position_buffer.append((float(pos[2]), x, y))

    @QtCore.Slot(dict)
    def _onAcousticData(self, data: dict) -> None:
        '''Receive an interpolated measurement from the SR830 worker.

        Guards against recording during positioning moves: readings
        whose position was resolved against MOVING-phase positions
        are discarded here by checking the current scan state.

        Parameters
        ----------
        data : dict
            Keys: ``'x'``, ``'y'``, ``'amplitude'``, ``'phase'``.
        '''
        if self._collecting:
            self._appendData(data['x'], data['y'],
                             data['amplitude'], data['phase'])

    def _appendData(self, x: float, y: float,
                    amplitude: float, phase: float) -> None:
        '''Record one measurement and update the live plot.

        Parameters
        ----------
        x, y : float
            Position [m].
        amplitude : float
            Lock-in amplitude [V].
        phase : float
            Lock-in phase [degrees].
        '''
        self.data.append([x, y, amplitude, phase])
        self.plotData(x, y, self.hue(phase))
        logger.debug(f'data: x={x:.4f} y={y:.4f} amp={amplitude:.4f} '
                     f'phase={phase:.2f}')
        self.dataReady.emit({'x': x, 'y': y,
                             'amplitude': amplitude, 'phase': phase})

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

    def redrawData(self) -> None:
        '''Redraw the scatter plot with amplitude encoded as saturation.

        Normalizes amplitude across all accumulated data points and
        repaints using HSV color: hue encodes phase, saturation encodes
        relative amplitude.  Loud areas appear as pure hue; quiet areas
        appear white.  No-op if no data has been collected.
        '''
        df = self.dataframe()
        if df.empty:
            return
        amplitude = df.amplitude.to_numpy()
        amax = amplitude.max()
        saturation = amplitude / amax if amax > 0 else np.ones_like(amplitude)
        self.dataPlot.clear()
        self.plotData(df.x.to_numpy(), df.y.to_numpy(),
                      self.hue(df.phase.to_numpy()), saturation)

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
        self.redrawData()
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
