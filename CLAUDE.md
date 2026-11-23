# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Normal mode (connects to hardware instruments)
python QAcousticCamera.py

# Fake mode (no hardware required, for development/testing)
python QAcousticCamera.py --fake

# Load a data file on startup
python QAcousticCamera.py --read docs/demo.csv

# As a module (equivalent)
python -m QAcousticCamera --fake
```

## Dependencies

Install as an editable package (preferred for development):
```bash
pip install -e ".[dev]"
```

Or install dependencies directly:
```bash
pip install -r requirements.txt
```

Core external packages (not in pyproject.toml, must be installed separately):
- **QPolargraph**: Provides the `QScanner` base class and polargraph scanner control
- **QInstrument**: Provides `QSR830Widget` (lock-in amplifier) and `QDS345Widget` (function generator) UI widgets, plus fake instrument implementations
- **pyqtgraph**: Real-time scientific plotting (used by inherited `QScanner`)
- **PyQt5** or **PyQt6** or **PySide2** or **PySide6**: Any Qt binding supported by `qtpy`

## Running Tests

```bash
pytest tests/
```

Activate the pre-push hook to run tests automatically before every push:
```bash
git config core.hooksPath .githooks
```

## Architecture

The entire application is a single file (`QAcousticCamera.py`) containing one class:

**`QAcousticCamera(QScanner)`** — Inherits the polargraph scanner UI and extends it with:
- Instrument widgets for a DS345 function generator (signal source) and SR830 lock-in amplifier (detector), added to the scanner's controls column in `setupUi()` through `QScanner.controlsLayout`
- Scan lifecycle driven by the QScanner state machine: `toggleScan()` starts a new scan (`_onScanStarting()`: unmute the source, clear data, start the `SR830Worker` thread on real hardware), and `_onStateChanged()` calls `_onScanFinished()` when the state returns to IDLE (stop the worker, mute the source, redraw). Data are recorded only while the state is SCANNING (`_collecting`)
- Acquisition: on real hardware `SR830Worker` runs on its own thread, calling `report()` as fast as the lock-in allows. `_onDataReady()` pushes `(t, x, y)` positions, stamped with `time.monotonic()` by the scan pattern, into a shared deque, and the worker interpolates each reading's position from it and emits `dataReady`; `_onAcousticData()` appends `[x, y, amplitude, phase]`. In fake mode `_onDataReady()` samples a demo acoustic field at each position instead
- Phase-encoded color visualization: phase angles map to hue values and amplitude to saturation
- Data I/O: save/load as CSV or HDF5; `interpolate()` resamples scattered data onto a regular grid via `scipy.griddata`
- Config persistence at `~/.QAcousticCamera/` via the inherited QScanner config system

**Data flow**: Scanner moves microphone → DS345 emits tone → SR830 measures amplitude/phase concurrently → the worker correlates each reading with an interpolated position → `_appendData()` stores and plots each point → `interpolate()` produces gridded surface from scattered measurements.

**Requires** a QPolargraph that provides `QScanner.controlsLayout`, `ScanState` and the `connectSignals`/`_lockedWidgets` hooks (unreleased after 1.5.0). The single file is `QAcousticCamera.py`; the timestamps must stay on `time.monotonic()` to match the scan pattern.

**Fake mode**: Pass `fake=True` to replace hardware widgets with `QFakeDS345`/`QFakeSR830` simulators, enabling full GUI testing without instruments.

## Code Standards

This project follows the conventions of [QInstrument](https://github.com/davidgrier/QInstrument):
- Qt imports via `qtpy` (never direct PyQt5/6 imports)
- Type hints throughout, Python 3.10+ union syntax (`str | None`)
- NumPy-style docstrings on all classes and public methods
- Module-level logger, never `print()`
- Style is the portfolio's (`~/python/STANDARDS.md`): `ruff check .`, configured in `pyproject.toml`, runs in CI as the `Lint` job and as a pre-commit hook; 79 columns, single quotes
