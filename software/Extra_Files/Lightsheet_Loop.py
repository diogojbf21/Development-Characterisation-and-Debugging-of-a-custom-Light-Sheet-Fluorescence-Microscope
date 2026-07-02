import sys
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import QThread, Signal, Slot, QObject, QTimer

from PySide6.QtCore import QObject, QTimer, Signal

class lightsheet_loop(QObject):
    finished = Signal()
    update = Signal()

    def __init__(self):
        super().__init__()
        self._stop = False

    def start_loop(self):
        # Create a QTimer that will call do_work at a set interval.
        self.timer = QTimer(self)
        # Set the interval as needed (e.g., 20 ms, 0 ms means “as fast as possible” but yielding control)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self.do_work)
        self.timer.start()

    def do_work(self):
        if self._stop:
            self.timer.stop()
            self.finished.emit()
        else:
            # Do your processing here, then emit the update signal.
            self.update.emit()

    def stop(self):
        self._stop = True

