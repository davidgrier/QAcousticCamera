from QPolargraph import QScanner
from QInstrument.instruments import (QSR830Widget, QDS345Widget)


class QAcousticCamera(QScanner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle('QAcousticCamera')
        self.addInstruments()
        self.adjustSize()

    def addInstruments(self):
        self.source = QDS345Widget()
        self.lockin = QSR830Widget()
        self.ui.controlsLayout.addWidget(self.source)
        self.ui.controlsLayout.addWidget(self.lockin)


def main():
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    camera = QAcousticCamera()
    camera.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
