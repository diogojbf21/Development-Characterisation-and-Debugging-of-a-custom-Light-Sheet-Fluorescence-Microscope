#######################################################################################
# Software Launcher to choose the path
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog
)
import sys, os

class ALM_Launcher(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VitaSlice")
        self.resize(300, 100)

        self.selected_path = None

        lbl = QLabel("Please select your save directory:")
        btn = QPushButton("Choose Folder…")
        btn.clicked.connect(self.on_choose)

        layout = QVBoxLayout(self)
        layout.addWidget(lbl)
        layout.addStretch()
        layout.addWidget(btn)
        layout.addStretch()

        self.setStyleSheet("""
            /* ————————————— Root dialog ————————————— */
            QDialog {
                background-color: #303030;    /* same deep charcoal as your progress dialog */
            }

            /* ————————————— Labels ————————————— */
            QLabel {
                color: #FFFFFF;               /* crisp white text */
                font-size: 13px;
            }

            /* ————————————— Buttons ————————————— */
            QPushButton {
                background-color: #388E3C;    /* emerald green base */
                color: white;
                border: 2px solid #2E7D32;    /* darker green outline */
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4CAF50;    /* brighter on hover */
                border-color: #80E27E;
            }
            QPushButton:pressed {
                background-color: #2E7D32;    /* darker on press */
                border-color: #1B5E20;
            }
            QPushButton:disabled {
                background-color: #555555;    /* muted */
                border-color: #777777;
                color: #B0B0B0;
            }

            /* ————————————— QFileDialog panels ————————————— */
            QFileDialog QWidget {
                background: #383838;
                color: #FFFFFF;
            }
            QFileDialog QPushButton {
                background-color: #252525;
                border: 1px solid #555555;
            }
            QFileDialog QPushButton:hover {
                background-color: #3C3C3C;
            }
        """)


    def on_choose(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Save Directory",
            os.getcwd(),
            QFileDialog.ShowDirsOnly
        )
        if path:
            self.selected_path = path
            self.accept()     # close dialog with QDialog.Accepted