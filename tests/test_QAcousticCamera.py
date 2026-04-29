import collections
import pytest
import numpy as np


@pytest.fixture
def camera(qtbot):
    QPolargraph = pytest.importorskip('QPolargraph')
    from QAcousticCamera.QAcousticCamera import QAcousticCamera
    widget = QAcousticCamera(fake=True)
    qtbot.addWidget(widget)
    return widget


class TestHue:

    def test_zero_phase(self, camera):
        assert camera.hue(0.0) == pytest.approx([0.0])

    def test_phase_360_wraps(self, camera):
        assert camera.hue(360.0) == pytest.approx([0.0])

    def test_phase_90(self, camera):
        assert camera.hue(90.0) == pytest.approx([0.25])

    def test_phase_180(self, camera):
        assert camera.hue(180.0) == pytest.approx([0.5])

    def test_array_input(self, camera):
        result = camera.hue([0.0, 90.0, 180.0, 270.0])
        assert len(result) == 4
        assert result == pytest.approx([0.0, 0.25, 0.5, 0.75])

    def test_negative_phase(self, camera):
        result = camera.hue(-90.0)
        assert result == pytest.approx([0.75])


class TestDataframe:

    def test_empty_columns(self, camera):
        df = camera.dataframe()
        assert list(df.columns) == ['x', 'y', 'amplitude', 'phase']

    def test_empty_has_no_rows(self, camera):
        df = camera.dataframe()
        assert len(df) == 0

    def test_with_data(self, camera):
        camera.data = [[1.0, 2.0, 0.5, 45.0], [3.0, 4.0, 0.8, 90.0]]
        df = camera.dataframe()
        assert len(df) == 2
        assert df['x'].tolist() == pytest.approx([1.0, 3.0])
        assert df['amplitude'].tolist() == pytest.approx([0.5, 0.8])


# ---------------------------------------------------------------------------
# SR830Worker — position interpolation
# ---------------------------------------------------------------------------

class TestSR830WorkerFlush:

    def _make_worker(self):
        from QAcousticCamera.QAcousticCamera import SR830Worker
        buf = collections.deque(maxlen=100)
        worker = SR830Worker(lockin=None, position_buffer=buf)
        return worker, buf

    def test_interpolates_midpoint(self):
        worker, buf = self._make_worker()
        buf.append((0.0, 0.0, 0.0))
        buf.append((1.0, 1.0, 2.0))
        received = []
        worker.dataReady.connect(received.append)
        pending = [(0.5, 0.3, 45.0)]
        worker._flush(pending)
        assert len(received) == 1
        assert received[0]['x'] == pytest.approx(0.5)
        assert received[0]['y'] == pytest.approx(1.0)
        assert received[0]['amplitude'] == pytest.approx(0.3)
        assert received[0]['phase'] == pytest.approx(45.0)
        assert pending == []

    def test_holds_pending_without_trailing_bracket(self):
        worker, buf = self._make_worker()
        buf.append((0.0, 0.0, 0.0))
        received = []
        worker.dataReady.connect(received.append)
        pending = [(0.5, 0.3, 45.0)]
        worker._flush(pending)
        assert received == []
        assert len(pending) == 1

    def test_final_resolves_with_nearest_before(self):
        worker, buf = self._make_worker()
        buf.append((0.0, 3.0, 7.0))
        received = []
        worker.dataReady.connect(received.append)
        pending = [(1.0, 0.5, 90.0)]
        worker._flush(pending, final=True)
        assert len(received) == 1
        assert received[0]['x'] == pytest.approx(3.0)
        assert received[0]['y'] == pytest.approx(7.0)

    def test_final_resolves_with_nearest_after(self):
        worker, buf = self._make_worker()
        buf.append((2.0, 5.0, 6.0))
        received = []
        worker.dataReady.connect(received.append)
        pending = [(1.0, 0.5, 90.0)]
        worker._flush(pending, final=True)
        assert len(received) == 1
        assert received[0]['x'] == pytest.approx(5.0)
        assert received[0]['y'] == pytest.approx(6.0)

    def test_final_drops_reading_with_empty_buffer(self):
        worker, buf = self._make_worker()
        received = []
        worker.dataReady.connect(received.append)
        pending = [(1.0, 0.5, 90.0)]
        worker._flush(pending, final=True)
        assert received == []

    def test_resolves_multiple_readings(self):
        worker, buf = self._make_worker()
        buf.append((0.0, 0.0, 0.0))
        buf.append((2.0, 2.0, 0.0))
        received = []
        worker.dataReady.connect(received.append)
        pending = [(0.5, 0.1, 10.0), (1.5, 0.2, 20.0)]
        worker._flush(pending)
        assert len(received) == 2
        assert received[0]['x'] == pytest.approx(0.5)
        assert received[1]['x'] == pytest.approx(1.5)
        assert pending == []

    def test_reading_exactly_at_first_bracket_gives_first_position(self):
        # t_s == t_before: alpha == 0, result is the first bracket's position
        worker, buf = self._make_worker()
        buf.append((0.0, 3.0, 4.0))
        buf.append((2.0, 9.0, 8.0))
        received = []
        worker.dataReady.connect(received.append)
        pending = [(0.0, 0.5, 45.0)]
        worker._flush(pending)
        assert len(received) == 1
        assert received[0]['x'] == pytest.approx(3.0)
        assert received[0]['y'] == pytest.approx(4.0)
