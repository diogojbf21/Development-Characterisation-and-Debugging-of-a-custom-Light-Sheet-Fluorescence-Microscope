class StyleSheets:

    # Font definition for the whole App

    def main_window(self):
        stylesheet = """
            QMainWindow, QWidget {
                background-color: #222222;  /* Dark background */
            }
            QLabel, QGroupBox, QComboBox {
                color: white;  /* White text for labels */
            }

            * PUSH BUTTONS */
            QPushButton {
                background-color: #2E2E2E;
                color: white;
                border: 2px solid #555;
                border-radius: 12px;
                padding: 8px 16px;
                font-size: 10px;
                outline: none;
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

            * LINE EDITS */
            QLineEdit {
                background-color: #333333;  /* Fix background */
                color: white;  /* Ensure white text */
                border: 1px solid #555555;  /* Darker border */
                padding: 4px;  /* Ensure spacing inside */
                border-radius: 3px;  /* Smooth rounded corners */
                selection-background-color: #555555;  /* Fix text selection */
            }

            QLineEdit:focus {
                border: 1px solid #888888;  /* Highlight when focused */
                background-color: #444444;  /* Slightly lighter when active */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                box-shadow: none;
                outline: none;
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
            * PUSH BUTTONS */
            QPushButton {
                background-color: #2E2E2E;
                color: white;
                border: 2px solid #555;
                border-radius: 12px;
                padding: 8px 16px;
                font-size: 10px;
                outline: none;
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
        """

        return stylesheet
