Changelog
=========

1.2.0 (2026-11-23)
------------------

- Requires QInstrument 3.1 and QPolargraph 1.6, and Python 3.11 or later
  (CI tests 3.11 to 3.14).
- The camera follows the ``QScanner`` state machine of QPolargraph, and the
  lock-in amplifier is read on a worker thread on monotonic time, with the
  position of each reading interpolated from the scan.
- The amplitude of an image is encoded as brightness, and as saturation
  (loud is color, quiet is white), after a scan and when data are loaded.
- Fixed: saving scan data raised ``TypeError`` with pandas 3, whose
  ``to_hdf`` takes keyword arguments only.
- Fixed: loading data restores ``self.data``; the file dialog is given a
  ``str`` directory.
- Code style is enforced with ``ruff`` (CI ``Lint`` job and a pre-commit
  hook) and types with ``pyright`` (CI ``Types`` job).
