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
