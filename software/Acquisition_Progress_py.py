from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtWidgets import (QApplication, QFrame, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QSlider, QStatusBar,
    QTextEdit, QWidget, QLineEdit, QMenu, QVBoxLayout, QButtonGroup, QHBoxLayout, QVBoxLayout, QGridLayout)
from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtCore import QObject, QThread, Signal, Slot

######

from PySide6.QtWidgets import QProgressBar
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QFont
from PySide6.QtCore import Qt, QRectF

class RoundedProgressBar(QProgressBar):
    def __init__(self, *args, radius=4, border_width=2, **kwargs):
        super().__init__(*args, **kwargs)
        self._radius = radius
        self._bw = border_width
        # disable any stylesheet so we’re in full control
        self.setStyleSheet("")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1) Draw the groove (track)
        groove = QRectF(self._bw/2,
                        self._bw/2,
                        self.width()  -   self._bw,
                        self.height() -   self._bw)
        painter.setPen(QColor('grey'))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(groove, self._radius, self._radius)

        # 2) Compute fill rectangle
        span = max(1, self.maximum() - self.minimum())
        frac = (self.value() - self.minimum()) / span
        fill_w = (groove.width()) * frac
        fill = QRectF(groove.x(),
                      groove.y(),
                      fill_w,
                      groove.height())

        # 3) Draw the fill with rounded corners on both ends
        if fill_w > 0:
            # gradient exactly across the fill
            grad = QLinearGradient(fill.topLeft(), fill.topRight())
            grad.setColorAt(0.0, QColor('#80E27E'))
            grad.setColorAt(0.5, QColor('#4CAF50'))
            grad.setColorAt(1.0, QColor('#388E3C'))
            painter.setPen(Qt.NoPen)
            painter.setBrush(grad)
            # radius for fill = groove radius minus half border width
            fr = max(0, self._radius - self._bw/2)
            painter.drawRoundedRect(fill, fr, fr)

        # 4) Draw centered text
        painter.setPen(QColor('white'))
        font = QFont(self.font())
        font.setBold(True)
        painter.setFont(font)
        text = f"{int(frac*100)}%"
        painter.drawText(groove, Qt.AlignCenter, text)




class AcquisitionProgress_Dialog(QDialog):

    #----------------------------------------------------
    # Functions for the Elapsed Time
    
    def format_elapsed(self, ms: int) -> str:
        """
        Turn milliseconds into a string "X days X h. X min. X sec.",
        omitting days/hours/minutes if they are zero.
        """
        total_seconds = ms // 1000
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)

        parts = []
        if days:
            if days == 1:
                parts.append(f"{days} day")
            else:
                parts.append(f"{days} days")

        if hours:
            parts.append(f"{hours} h.")
        if minutes:
            parts.append(f"{minutes} min.")
        parts.append(f"{seconds} sec.")

        return " ".join(parts)
    
    def _tick(self):
        """Called every 1 s to refresh the elapsed‐time label (and bar text)."""
        ms = self._elapsed_clock.elapsed()
        text = self.format_elapsed(ms)
        self.time_label.setText(text)
        # if you also want it inside the bar:
        #self.bar.setFormat(text)

    
    #----------------------------------------------------
    # Slots

    @Slot(int, int)
    def update_slice(self, current, total):
        self.slice_counter_label .setText(f"{current} / {total}")

    @Slot(int, int)
    def update_channel(self, current, total):
        self.channel_counter_label.setText(f"{current} / {total}")

    @Slot(int, int)
    def update_position(self, current, total):
        self.acq_counter_label.setText(f"{current} / {total}")

    @Slot(int, int)
    def update_timepoint(self, current, total):
        self.time_point_counter_label.setText(f"{current} / {total}")



    #----------------------------------------------------
    # GUI setup


    def __init__(self, total_slices, order, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Y-Stack Acquisition Progress")
        self.setWindowModality(Qt.ApplicationModal)


        # layout
        layout = QVBoxLayout(self)

        # grid layout for the counters
        grid_widget = QWidget()
        grid_layout = QGridLayout()
        grid_widget.setLayout(grid_layout)

        # grid layout - 1st Line - Current Slice Label
        self.slice_label     = QLabel(f"Current Slice: ")
        self.slice_counter_label = QLabel("")
        
        # grid layout - 2nd Line - Current Channel Label
        self.channel_label   = QLabel(f"Current Channel: ")
        self.channel_counter_label = QLabel("")

        # grid layout - 3rd line - Current Acqusitin Label
        self.acq_label = QLabel(f"Current Position: ")
        self.acq_counter_label = QLabel("")

        # grid layout - 4th Line - Current time-point label
        self.timepoint_label = QLabel(f"Current Timepoint: ")
        self.time_point_counter_label = QLabel("")

        
        # Elapsed Time Label
        self.elapsed_label   = QLabel("Elapsed Time:")
        self.elapsed_label.setStyleSheet("""
                        font-size: 13px;""")

        # Time and Stop Acquisition Buttons
        self.time_button_widget = QWidget()
        self.time_button_layout = QHBoxLayout()
        self.time_button_widget.setLayout(self.time_button_layout)

        self.time_label = QLabel("0 sec.")
        self.time_label.setStyleSheet("""
                        font-size: 13px;
                        font-weight: bold;""")

        self.discard_button = QPushButton("Discard Acquisition")
        self.discard_button.setFixedSize(200, 35)
        self.discard_button.setStyleSheet("""
                        QPushButton {
                            background-color: #2A1A1A;  /* dark red tint */
                            color: white;
                            border: 2px solid #550000;
                            border-radius: 12px;
                            padding: 0px 16px;
                            font-size: 13px;
                            outline: none;
                            font-weight: bold;
                        }

                        QPushButton:hover {
                            background-color: #3B2323;  /* slightly lighter on hover */
                            border: 2px solid #770000;
                        }

                        QPushButton:pressed {
                            background-color: #1F1212;  /* darker on press */
                            border: 2px solid #990000;
                        }

                        QPushButton:disabled {
                            background-color: #5E2E2E;  /* muted when disabled */
                            border: 2px solid #777;
                            color: #B0B0B0;
                        }

                        QPushButton:checked {
                            background-color: #D32F2F;  /* red highlight when checked */
                            border: 2px solid #E57373;
                            color: black;
                            font-weight: bold;
                        }

                        /* Checked + Hover effect */
                        QPushButton:checked:hover {
                            background-color: #C62828;
                            border: 2px solid #EF9A9A;
                        }

                        /* Checked + Pressed effect */
                        QPushButton:checked:pressed {
                            background-color: #B71C1C;
                            border: 2px solid #FFCDD2;
                        }
                        """)

        self.stop_button = QPushButton("Stop Acquisition")
        self.stop_button.setFixedSize(200, 35)
        self.stop_button.setStyleSheet("""
                        QPushButton {
                            background-color: #252525;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 12px;
                            padding: 0px 16px;
                            font-size: 13px;
                            outline: none;
                            font-weight: bold;
                        }

                        QPushButton:hover {
                            background-color: #3C3C3C;
                            border: 2px solid #777;
                        }

                        QPushButton:pressed {
                            background-color: #1E1E1E;
                            border: 2px solid #999;
                        }

                        QPushButton:disabled {
                            background-color: #5E5E5E;
                            border: 2px solid #777;
                            color: #B0B0B0;
                        }
                        QPushButton:checked {
                            background-color: #4CAF50; /* Green highlight */
                            border: 2px solid #80E27E;
                            color: black;
                            font-weight: bold;
                        }

                        /* Checked + Hover effect */
                        QPushButton:checked:hover {
                            background-color: #45A049;
                            border: 2px solid #76D275;
                        }

                        /* Checked + Pressed effect */
                        QPushButton:checked:pressed {
                            background-color: #388E3C;
                            border: 2px solid #60C460;
                        }
        """)

        self.bar = RoundedProgressBar()#QProgressBar()
        self.bar.setRange(0, total_slices)
        self.bar.setValue(0)
        self.bar.setFixedSize(200, 35)
        self.bar.setStyleSheet("""
            QProgressBar {
                border-style: solid;
                border-color: grey;
                border-radius: 2px;
                border-width: 2px;
                text-align: center;
                padding: 2px 2px; /* Adds 4px padding on left and right */
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0   #80E27E,
                    stop:0.5 #4CAF50,
                    stop:1   #388E3C
                );
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                /* Avoid setting right-side radius to let the groove's border-radius handle it */
                margin: 0px;
                min-width: 0px;
            }
        """)


        
        grid_layout.addWidget(self.slice_label, 0, 0)#, alignment=Qt.AlignRight)
        grid_layout.addWidget(self.slice_counter_label, 0, 1)
        grid_layout.addWidget(self.channel_label, 1, 0)#, alignment=Qt.AlignRight)
        grid_layout.addWidget(self.channel_counter_label, 1, 1)

        # Time-Points first:
        if order == 1:
            grid_layout.addWidget(self.timepoint_label, 2, 0)#, alignment=Qt.AlignRight)
            grid_layout.addWidget(self.time_point_counter_label, 2, 1)
            grid_layout.addWidget(self.acq_label, 3, 0)#, alignment=Qt.AlignRight)
            grid_layout.addWidget(self.acq_counter_label, 3, 1)

        # Positions first:
        elif order == 2:
            grid_layout.addWidget(self.acq_label, 2, 0)#, alignment=Qt.AlignRight)
            grid_layout.addWidget(self.acq_counter_label, 2, 1)
            grid_layout.addWidget(self.timepoint_label, 3, 0)#, alignment=Qt.AlignRight)
            grid_layout.addWidget(self.time_point_counter_label, 3, 1)

        
        grid_layout.setContentsMargins(0,0,0,0)

        layout.addWidget(grid_widget, alignment=Qt.AlignLeft)
        layout.addSpacing(10)
        layout.addWidget(self.elapsed_label)
        layout.addWidget(self.time_label)
        layout.addWidget(self.bar)
        layout.addStretch()
        layout.addWidget(self.discard_button)
        layout.addWidget(self.stop_button)

        # ————————————————
        # Start the timers:

        # master clock
        self._elapsed_clock = QElapsedTimer()
        self._elapsed_clock.start()

        # update the time_label every second
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self.setStyleSheet("""
            QWidget { 
                background-color: #303030;  /* Dark background */
            }
                                                 
            QLabel {
                color: white;  /* White text */
            }
            /* ----------- QComboBox ----------- */
                                     
        """)