class StyleSheets:

    # Font definition for the whole App

    def main_window(self):
        stylesheet = """
            QMainWindow {
                background-color: #222222;  /* Dark background */
            }
            QLabel, QGroupBox {
                color: white;  /* White text for labels */
            }
        """

        return stylesheet

    def font(self):
        stylesheet = """
            QLabel, QPushButton, QCheckBox, QRadioButton, 
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, 
            QSpinBox, QDoubleSpinBox, QListWidget, QTreeWidget, 
            QTableWidget, QGroupBox, QTabWidget, QToolButton, QMenuBar, 
            QMenu, QStatusBar, QProgressBar, QGroupBox {
                font-family: 'Roboto';
                }
        """

        return stylesheet

    # For the ON/OFF and similar Push Buttons 
    def ON_OFF_PushButton(self):
        stylesheet = """
            QPushButton {
                font-size: 12px;  /* Adjust text size */
                font-weight: bold;  /* Make text bold */
            }
        """

        return stylesheet
