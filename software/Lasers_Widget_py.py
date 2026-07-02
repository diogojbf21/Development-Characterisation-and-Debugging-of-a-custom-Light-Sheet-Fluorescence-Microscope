import os
os.environ["QT_API"] = "pyside6"
os.environ["NAPARI_QT_API"] = "pyside6"

from PySide6.QtCore import QMimeData, Qt, Signal, QSize, QRect, QPoint, QTimer
from PySide6.QtGui import QDrag, QPixmap, QIcon, QPainter, QPainterPath, QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QSlider,
    QWidget,
    QPushButton,
    QSizePolicy,
    QLineEdit,
    QDialog,
    QRadioButton,
    QCheckBox,
    QGraphicsDropShadowEffect
)
from PySide6.QtWidgets import QFrame
import numpy as np

# Imports from my code
from Extra_Files.ToolTip_Manager import CustomToolTipManager
from Extra_Files.Stylesheet_List import StyleSheets
from Extra_Files.Custom_Line_Edit import CustomLineEdit
from Extra_Files.Lasers_EditableLabel import LasersEditableLabel

import re
from pathlib import Path

import logging
# Reuse the main application logger configured in main.py / logger.py
logger = logging.getLogger("ALM")

import threading


class DragTargetIndicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(25, 5, 25, 5)
        self.setStyleSheet("""
            QLabel { background-color: #ccc; 
                    border: 2px solid black; 
                    border-radius: 15px; }    
            """
        )


class DragItem(QWidget):

    powerChanged = Signal(int, int)
    laserSelectedChanged = Signal(int, bool, int)
    filtersChanged = Signal(int, object, object)
    laserTurnedOn = Signal(int)


    # ------------------------------------------------------------------------------------------------------------------------------

    # Initialization

    def __init__(self, label_text, filter_data_file, *args, **kwargs):
        super().__init__(*args, **kwargs)

            # Timer for communication updates
        self.update_timer = QTimer()
        self.update_timer.setInterval(10)  # 100 ms debounce
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.emit_laser_update)

            # Import JSON file's data
        self.filter_data = filter_data_file

            # Extract Laser number from label
        self.laser_number = int(label_text.split(" - ")[0][0])
        self.selected_cam1_filter = None
        self.selected_cam2_filter = None

            # Variables
        self.last_lineedit_input = "1"
        self.lineedit_signal = False

            # Initialize the tooltip manager
        self.tooltip_manager = CustomToolTipManager(self)

        # Container ----------------------------------------------------------------------------------------------------------------

            # Main layout for DragItem
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # No extra margins
        self.main_layout.setSpacing(0)

            # Create a QFrame to act as a container with a border

        
        self.container = QFrame(self)
        self.container.setFrameShape(QFrame.StyledPanel)
        self.container.setFrameShadow(QFrame.Plain)

            # Change the cursor on the container
        self.container.setCursor(Qt.OpenHandCursor)

        laser_name = label_text.split(" - ", 1)[-1]

        color_map = {
            "405 nm": "#5E018D",  # UV Light (Cadet Blue)
            "488 nm": "#4682B4",  # Light Blue
            "561 nm": "#3CB371",  # Green (Medium Sea Green)
            "640 nm": "#8B0000",  # Dark Red
        }

        dark_color_map = {
            "405 nm": "#3E005B",  # Darker Purple for UV Light
            "488 nm": "#2C5476",  # Darker Light Blue
            "561 nm": "#246B4D",  # Darker Green
            "640 nm": "#5A0000",  # Darker Red
        }


        self.wavelength_color = color_map.get(laser_name, "white")  # Default to white if not in map
        self.dark_color = dark_color_map.get(laser_name, "white")

        self.border_color = color_map.get(laser_name, "white")
        self.container.setStyleSheet(f"""
            QFrame {{
                border: 2px solid {self.border_color};
                background-color: #464646;  /* Dark theme background for the box */
                border-radius: 10px;
            }}
        """)


        self.main_layout.addWidget(self.container)

            # Layout for internal widgets inside the container
        self.inner_layout = QVBoxLayout(self.container)
        self.inner_layout.setContentsMargins(10, 10, 10, 10)  # Padding inside the border
        self.inner_layout.setSpacing(5)

        # Label --------------------------------------------------------------------------------------------------------

            # Main label to display the name of the LASER
        self.label = QLabel(label_text, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("border: none; color = white")  # Remove borders from the label
        self.label.setStyleSheet(f"font: {10.5}pt; font-weight: bold; color: white; border: none")
        self.label.setCursor(Qt.OpenHandCursor)

        # Slider Widget --------------------------------------------------------------------------------------------------------

        self.slider_widget = QWidget(self)

            # Vertical slider
        self.slider = QSlider(Qt.Orientation.Vertical, self.slider_widget)
        self.slider.wheelEvent = self.custom_slider_wheel_event
        self.slider.setStyleSheet("")  # Remove any extra styling from slider
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(0)
        self.slider.setFixedSize(25, 150)
        self.slider.setStyleSheet(f"""
                QSlider::groove:vertical {{
                    background: {self.dark_color};  /* Match groove color to wavelength */
                    border: 1px solid white;
                    width: 6px;
                    border-radius: 3px;
                }}
                QSlider::handle:vertical {{
                    background: white;  /* White handle for contrast */
                    border: 1px solid #AAAAAA;
                    height: 20px;
                    width: 20px;
                    border-radius: 10px;
                    margin: -5px; /* Handle overlap for better visuals */
                }}
            """)
            # Cursor on the Slider
        self.slider.setCursor(Qt.ArrowCursor)
            # Connect slider to update the value label
        self.slider.valueChanged.connect(self.update_lineedit)
        self.slider.valueChanged.connect(self.save_lineedit_input_function)
        self.slider.valueChanged.connect(self.notify_laser_update)


            # Line Edit that shows the Laser Power
        self.value_lineedit = QLineEdit(self.slider_widget)
        self.value_lineedit.setGeometry(20, 0, 20, 20)
        self.value_lineedit.setFixedSize(36, 21)
        self.value_lineedit.setText("0")
            # Cursor on the line edit
        self.value_lineedit.setCursor(Qt.ArrowCursor)
        self.value_lineedit.editingFinished.connect(self.update_slider)
        self.value_lineedit.editingFinished.connect(self.update_button_state)
        self.value_lineedit.editingFinished.connect(self.save_lineedit_input_function)
        self.value_lineedit.returnPressed.connect(self.value_lineedit.clearFocus)
        self.value_lineedit.setStyleSheet("""
            QLineEdit {
                background-color: #333333;  /* Fix background */
                color: white;  /* Ensure white text */
                border: 1px solid #555555;  /* Darker border */
                padding: 4px;  /* Ensure spacing inside */
                border-radius: 3px;  /* Smooth rounded corners */
                selection-background-color: #0078d7;  /* Fix text selection */
            }

            QLineEdit:focus {
                border: 1px solid #888888;  /* Highlight when focused */
                background-color: #666666;  /* Slightly lighter when active */
            }

            QLineEdit:disabled {
                background-color: #222222;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                outline: none;
            }
        """)
        self.value_lineedit.setCursor(Qt.IBeamCursor)
        validator = QDoubleValidator()
        self.value_lineedit.setValidator(validator)


        self.value_label = QLabel("mW", self)
        self.value_label.setStyleSheet("border: none;")

            # OFF Button to the right of the Slider and Value Label
        self.button3 = QPushButton(self)
        self.button3.setText("OFF")
        self.button3.setCheckable(True)
        self.button3.setFixedSize(65, 35)
        self.button3.clicked.connect(self.handle_button3_click)
        self.button3.clicked.connect(self.update_slider)
        self.button3.clicked.connect(self.save_lineedit_input_function)
            # Set the cursor for button 3
        self.button3.setCursor(Qt.ArrowCursor)

        self.button3.setStyleSheet("""
            QPushButton {
                background-color: #2E2E2E;
                color: white;
                border: 2px solid #555;
                border-radius: 12px;
                padding: 0px 16px;
                font-size: 12px;
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

            QPushButton:checked:hover {
                background-color: #45A049;
                border: 2px solid #76D275;
            }

            QPushButton:checked:pressed {
                background-color: #388E3C;
                border: 2px solid #60C460;
            }

            QPushButton:checked:disabled {
                background-color: #7CBF7C;  /* Muted green */
                border: 2px solid #A5D6A7;
                font-weight: bold;
                color: black;
            }
        """)

            # Radio Button for the Power Setting
        script_path = Path(__file__).resolve()
        icon_path   = script_path.parent / "icons" / "check.png"
        self.checkbox = QCheckBox("Select Laser")
        self.checkbox.setStyleSheet(f"""
            QCheckBox {{
                spacing: 2px;
                color: white;
                font-size: 12px;
            }}

            QCheckBox::indicator {{
                width: 13px;
                height: 13px;
                border: 2px solid #555;
                border-radius: 4px;
                background-color: #2E2E2E;
            }}

            QCheckBox::indicator:hover {{
                background-color: #3C3C3C;
                border: 2px solid #777;
            }}

            QCheckBox::indicator:pressed {{
                background-color: #1E1E1E;
                border: 2px solid #999;
            }}

            QCheckBox::indicator:checked {{
                background-color: #4CAF50;
                border: 2px solid #80E27E;
                image: url("{icon_path.as_posix()}");
            }}

            QCheckBox::indicator:checked:hover {{
                background-color: #45A049;
                border: 2px solid #76D275;
            }}

            QCheckBox::indicator:checked:pressed {{
                background-color: #388E3C;
                border: 2px solid #60C460;
            }}

            QCheckBox:disabled {{
                color: #B0B0B0;
            }}

            QCheckBox::indicator:disabled {{
                background-color: #5E5E5E;
                border: 2px solid #777;
            }}
        """)

        self.checkbox.setCursor(Qt.ArrowCursor)
        checkbox_rect = QRect(35, 0, 150, 40)
        self.checkbox.setGeometry(checkbox_rect)
            # Move the button to the center of the QRect
        checkbox_size = self.checkbox.size()
        checkbox_x = checkbox_rect.center().x() - checkbox_size.width() // 2
        checkbox_y = checkbox_rect.center().y() - checkbox_size.height() // 2
        self.checkbox.move(checkbox_x, checkbox_y)

        self.tooltip_manager.attach_tooltip(self.checkbox, "Selects this laser for acquisition. When pressed,\nthe selected laser power is shown below.")
        self.checkbox.toggled.connect(self.update_power_label)
        self.checkbox.toggled.connect(self.notify_laser_selection)


        self.power_label = LasersEditableLabel("")
        self.power_label.setStyleSheet("""
                    QLabel {
                    font-size: 12px;
                    color: white;
                    border: none;               
                    }
                """)
        self.power_label.setGeometry(QRect(64, 27, 50, 15))
        self.power_label.setAlignment(Qt.AlignRight)
        self.power_label.textChanged.connect(self.notify_laser_selection)

        # Create the middle widget to place the slider, line edit, label and button
        self.middle_widget = QWidget()
        self.middle_widget.setFixedSize(130-10-10+5, 200 - 30)

            # set the middle_widget as the parent
        self.slider.setParent(self.middle_widget)

        self.checkbox.setParent(self.middle_widget)
        self.power_label.setParent(self.middle_widget)

        self.button3.setParent(self.middle_widget)
        self.value_lineedit.setParent(self.middle_widget)
        self.value_label.setParent(self.middle_widget)

    
        # Move the child widgets inside the parent
        self.slider.move(10-5, 10)

        self.button3.move(55-10-2.5, 120 + 32 - 40 + 10+5)

        self.value_lineedit.move(60-10-5, 168 - 40 - 40 + 10+5)
        self.value_label.move(100-10-5, 170 - 40 - 40 + 10+5)        

        
        # Buttons Widget --------------------------------------------------------------------------------------------------------

        # Create Filter 1 Button
        self.button1 = QPushButton("Cam 1\nFilter", self)

        self.button1.setFixedSize(50, 50)
        self.button1.clicked.connect(self.open_filterwheel1_dialog)
        self.button1.clicked.connect(self.notify_filter_selection)
            # Cursor on the button
        self.button1.setCursor(Qt.ArrowCursor)
        self.tooltip_manager.attach_tooltip(self.button1, "Select a filter for this\nLaser in Camera 1.")
        self.button1.setStyleSheet(f"""
            QPushButton {{
                border: 2px solid #555;
                background-color: #2E2E2E;
                color: white;
                border-radius: 5px;
                padding: 5px;
            }}
            QPushButton:hover {{
                background-color: #3C3C3C;
                border: 2px solid #777;
            }}
            QPushButton:pressed {{
                background-color: #666666;
            }}
        """)


        # Create Filter 2 Button
        self.button2 = QPushButton("Cam 2\nFilter", self)
        self.button2.setFixedSize(50, 50)
        self.button2.clicked.connect(self.open_filterwheel2_dialog)
        self.button2.clicked.connect(self.notify_filter_selection)
            # Cursor on the button
        self.button2.setCursor(Qt.ArrowCursor)
        self.tooltip_manager.attach_tooltip(self.button2, "Select a filter for this\nLaser in Camera 2.")
        self.button2.setStyleSheet(f"""
            QPushButton {{
                border: 2px solid #555;
                background-color: #2E2E2E;
                color: white;
                border-radius: 5px;
                padding: 5px;
            }}
            QPushButton:hover {{
                background-color: #3C3C3C;
                border: 2px solid #777;
            }}
            QPushButton:pressed {{
                background-color: #666666;
            }}
        """)

        # Horizontal layout for two additional buttons
        self.filter_buttons_layout = QHBoxLayout()  

        self.filter_buttons_layout.addWidget(self.button1)
        self.filter_buttons_layout.addWidget(self.button2)

        # Add widgets to the inner layout
        self.inner_layout.addWidget(self.label)
        self.inner_layout.addWidget(self.middle_widget) 
        self.inner_layout.addLayout(self.filter_buttons_layout)

        # Add the container to the main layout
        self.main_layout.addWidget(self.container)

        # Store data separately
        self.data = label_text

    # -------------------------------------------------------------------------------------------------------------
    # Behaviour Functions


    def set_data(self, data):
        self.data = data

    def update_lineedit(self, value):
        " Update the line edit from the slider's value"
        self.value_lineedit.setText(str(value))
        self.update_button_state()

        if self.slider.value() > 0:
            self.container.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {self.border_color};
                    background-color: #606060;
                    border-radius: 25px;
                }}
            """)
        else:
            self.container.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {self.border_color};
                    background-color: #464646;  /* Dark theme background for the box */
                    border-radius: 10px;
                }}
            """)



    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            drag.setMimeData(mime)

            # Create a transparent pixmap of the widget's size
            pixmap = QPixmap(self.size())
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)

            # Clip drawing to a rounded rectangle matching the CSS radius
            path = QPainterPath()
            path.addRoundedRect(self.rect(), 15, 15)
            painter.setClipPath(path)

            # Provide a starting offset (0,0)
            self.render(painter, QPoint(0, 0))
            painter.end()

            drag.setPixmap(pixmap)
            drag.exec(Qt.MoveAction)
            self.show()

    def wheelEvent(self, event):
        """Scroll anywhere on the DragItem to change the slider's value."""
        delta = event.angleDelta().y()

        step = 1  # How much to increment/decrement per wheel 'tick'
        current_value = self.slider.value()

        if delta > 0:
            self.slider.setValue(min(current_value + step, self.slider.maximum()))
        elif delta < 0:
            self.slider.setValue(max(current_value - step, self.slider.minimum()))

        # If the wheel was used to turn ON a Laser, change the last turned ON Laser
        if current_value == 0:
            if self.slider.value() > 0:
                self.laserTurnedOn.emit(6-self.laser_number)

        if self.slider.value() > 0:
            self.container.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {self.border_color};
                    background-color: #606060;
                    border-radius: 25px;
                }}
            """)
        else:
            self.container.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {self.border_color};
                    background-color: #464646;  /* Dark theme background for the box */
                    border-radius: 10px;
                }}
            """)

        event.accept()

    def custom_slider_wheel_event(self, event):
        delta = event.angleDelta().y()
        step = 1
        current = self.slider.value()

        if delta > 0:
            self.slider.setValue(min(current + step, self.slider.maximum()))
        elif delta < 0:
            self.slider.setValue(max(current - step, self.slider.minimum()))

        event.accept()

    def mouseDoubleClickEvent(self, event):
        if self.container.geometry().contains(event.pos()):
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mouseDoubleClickEvent(event)


    def prepare_for_edit(self, event):
        """Set the QLineEdit ready for editing when clicked."""
        self.value_lineedit.setFocus()  # Set focus to the line edit
        self.value_lineedit.selectAll()  # Select all text for easier replacement
        # Call the default mousePressEvent to ensure normal behavior
        super(QLineEdit, self.value_lineedit).mousePressEvent(event)
        

    def update_slider(self):
        """Update the slider value from the QLineEdit."""
        try:
            value = int(self.value_lineedit.text())

            # emit that a laser was turned ON
            if int(self.last_lineedit_input) == 0 and value > 0:
                self.laserTurnedOn.emit(6-self.laser_number)

            if 0 <= value <= 100:
                self.slider.setValue(value)
                self.update_button_state()

                if value > 0:
                    self.container.setStyleSheet(f"""
                        QFrame {{
                            border: 2px solid {self.border_color};
                            background-color: #606060;
                            border-radius: 25px;
                        }}
                    """)
                else:
                    self.container.setStyleSheet(f"""
                        QFrame {{
                            border: 2px solid {self.border_color};
                            background-color: #464646;  /* Dark theme background for the box */
                            border-radius: 10px;
                        }}
                    """)

            else:
                self.value_lineedit.setText(str(self.slider.value()))


        except ValueError:
            self.value_lineedit.setText(str(self.slider.value()))

    def update_button_state(self):
        """Update button3 state based on the value in the line edit."""
        try:
            value = int(self.value_lineedit.text())

            if value > 0:
                self.button3.setChecked(True)
                self.button3.setText("ON")
            else:
                self.button3.setChecked(False)
                self.button3.setText("OFF")

        except ValueError:
            self.value_lineedit.setText("0")
            self.button3.setChecked(False)
            self.button3.setText("OFF")


    def handle_button3_click(self):
        """Control button3 behavior based on its state."""

        if self.button3.isChecked():  # Turning ON
            if self.last_lineedit_input == "0":
                # If the last recorded value was 0, go to 1
                self.value_lineedit.setText("1")
                self.slider.setValue(1)
                self.button3.setChecked(True)
                self.button3.setText("ON")

                self.container.setStyleSheet(f"""
                    QFrame {{
                        border: 2px solid {self.border_color};
                        background-color: #606060;
                        border-radius: 25px;
                    }}
                """)

                # Emit that a laser was turned ON
                self.laserTurnedOn.emit(6-self.laser_number)

            else:
                # Restore the last saved value
                self.value_lineedit.setText(self.last_lineedit_input)
                self.slider.setValue(int(self.last_lineedit_input))
                self.button3.setChecked(True)
                self.button3.setText("ON")

                self.container.setStyleSheet(f"""
                    QFrame {{
                        border: 2px solid {self.border_color};
                        background-color: #606060;
                        border-radius: 25px;
                    }}
                """)

                # Emit that a laser was turned ON
                self.laserTurnedOn.emit(6-self.laser_number)
        
        else:  # Manually turning OFF
            self.last_lineedit_input = self.value_lineedit.text()  # Save the last value before turning OFF
            self.value_lineedit.setText("0")
            self.slider.setValue(0)
            self.button3.setChecked(False)
            self.button3.setText("OFF")

            self.container.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {self.border_color};
                    background-color: #464646;  /* Dark theme background for the box */
                    border-radius: 10px;
                }}
            """)


    def open_filterwheel1_dialog(self):
        """Open the filter wheel dialog for Camera 1 and update the selected filter."""
        dialog = Filterwheel_1_DialogBox(self.button1, self.filter_data)

        if dialog.exec():  
            if dialog.selected_icon:  
                if dialog.selected_icon_file is None:  
                    self.button1.setIcon(QIcon())  
                    self.button1.setText("Cam 1\nFilter")  
                    self.selected_cam1_filter = None  
                else:
                    self.button1.setIcon(dialog.selected_icon)  
                    self.button1.setText("")  
                    self.button1.setIconSize(QSize(40, 40))

                    for filter_key, filter_item in self.filter_data["Filterwheel_1"].items():
                        if f"icons//{filter_item.get('icon_file')}" == dialog.selected_icon_file:
                            self.selected_cam1_filter = filter_key  
                            break  

                self.notify_filter_selection()  

    def open_filterwheel2_dialog(self):
        """Open the filter wheel dialog for Camera 2 and update the selected filter."""
        dialog = Filterwheel_2_DialogBox(self.button2, self.filter_data)

        if dialog.exec():  
            if dialog.selected_icon:  
                if dialog.selected_icon_file is None:
                    self.button2.setIcon(QIcon())  
                    self.button2.setText("Cam 2\nFilter")  
                    self.selected_cam2_filter = None  
                else:
                    self.button2.setIcon(dialog.selected_icon)  
                    self.button2.setText("")  
                    self.button2.setIconSize(QSize(40, 40))


                    for filter_key, filter_item in self.filter_data["Filterwheel_2"].items():
                        if f"icons//{filter_item.get('icon_file')}" == dialog.selected_icon_file:
                            self.selected_cam2_filter = filter_key  
                            break  

                self.notify_filter_selection()

    def update_power_label(self):
        """Updates power label when the radio button is checked, clears it when unchecked."""
        if self.checkbox.isChecked():  # If checked, update label with value
            value = self.value_lineedit.text()
            self.power_label.setText(f"{value} mW")
            font = self.power_label.font()
            font.setBold(True)
            self.power_label.setFont(font)

        else:  # If unchecked, set label to blank
            self.power_label.setText("")



    def save_lineedit_input_function(self):
        """Saves the last valid non-zero input only when turning OFF manually."""
        value = self.value_lineedit.text()
        
        if not self.button3.isChecked():  # Only save the last input when button is turned OFF manually
            if value != "0":  # Prevent overwriting last non-zero value with 0
                self.last_lineedit_input = value


    def notify_laser_update(self):
        """Start/restart the update timer instead of sending immediately."""
        self.update_timer.start()

    def emit_laser_update(self):
        """Emit signal after throttling timeout."""
        try:
            power_value = int(self.slider.value())
        except ValueError:
            power_value = 0

        self.powerChanged.emit(self.laser_number, power_value)


    def notify_laser_selection(self):
        """Emit signal when checkbox is toggled."""
        power_value = self.get_power_value()
        is_selected = self.checkbox.isChecked()

        if self.checkbox.isChecked():
            power_value = int(self.power_label.text().split()[0])

        self.laserSelectedChanged.emit(self.laser_number, is_selected, power_value)

    def notify_filter_selection(self):
        """Emit signal when a filter is selected."""
        self.filtersChanged.emit(self.laser_number, self.selected_cam1_filter, self.selected_cam2_filter)

    def get_power_value(self):
        """Returns the current value of the QLineEdit as an integer."""
        try:
            return int(self.value_lineedit.text())
        except ValueError:
            return 0  # Default to 0 if invalid input



class DragWidget(QWidget):
    """
    Generic list sorting handler with improved placeholder handling.
    """

    orderChanged = Signal(list)

    def __init__(self, filter_data, *args, orientation=Qt.Orientation.Horizontal, **kwargs):
        super().__init__()
        self.setAcceptDrops(True)

        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)

        self.orientation = orientation

        if self.orientation == Qt.Orientation.Horizontal:
            self.blayout = QHBoxLayout()
        else:
            self.blayout = QVBoxLayout()

        self._drag_target_indicator = DragTargetIndicator()
        self.blayout.addWidget(self._drag_target_indicator)
        self._drag_target_indicator.hide()

        self.setLayout(self.blayout)

    def dragEnterEvent(self, e):
        e.accept()

    def dragLeaveEvent(self, e):
        self._drag_target_indicator.hide()
        e.accept()

    def dragMoveEvent(self, e):
        index = self._find_drop_location(e)
        if index is not None:
            # Ensure the placeholder has the correct size
            dragged_widget = e.source()
            if isinstance(dragged_widget, QWidget):
                self._drag_target_indicator.setFixedSize(dragged_widget.size())
            
            self.blayout.insertWidget(index, self._drag_target_indicator)
            e.source().hide()
            self._drag_target_indicator.show()
        e.accept()

    def dropEvent(self, e):
        widget = e.source()
        self._drag_target_indicator.hide()
        index = self.blayout.indexOf(self._drag_target_indicator)

        if index is not None:
            self.blayout.insertWidget(index, widget)
            self.orderChanged.emit(self.get_item_data())
            widget.show()
            self.blayout.activate()

        self.update_labels()
        e.accept()

    def _find_drop_location(self, e):
        pos = e.position()
        spacing = self.blayout.spacing() / 2

        for n in range(self.blayout.count()):
            w = self.blayout.itemAt(n).widget()
            if self.orientation == Qt.Orientation.Horizontal:
                drop_here = (
                    pos.x() >= w.x() - spacing
                    and pos.x() <= w.x() + w.size().width() + spacing
                )
            else:
                drop_here = (
                    pos.y() >= w.y() - spacing
                    and pos.y() <= w.y() + w.size().height() + spacing
                )

            if drop_here:
                break

        return n

    def add_item(self, item):
        self.blayout.addWidget(item)

    def get_item_data(self):
        data = []
        for n in range(self.blayout.count()):
            w = self.blayout.itemAt(n).widget()
            if w != self._drag_target_indicator:
                data.append(w.data)
        return data
    
    def update_labels(self):
        order_labels = ["1st", "2nd", "3rd", "4th"]

        # Find only DragItem widgets
        drag_items = [self.blayout.itemAt(i).widget() for i in range(self.blayout.count())
                    if isinstance(self.blayout.itemAt(i).widget(), DragItem)]

        for i, widget in enumerate(drag_items):
            laser_name = widget.label.text().split(" - ", 1)[-1]
            widget.label.setText(f"{order_labels[i]} - {laser_name}")  # Update text



from Extra_Files.ToolTip_Manager import CustomToolTipManager
from PySide6.QtGui import QDrag, QPixmap, QIcon, QPainter, QPainterPath, QColor, QCursor

class Filterwheel_1_DialogBox(QDialog):
    selected_icon = None  # Property to store the selected icon

    def __init__(self, parent_button, filter_data1):
        super().__init__(parent_button)
        self.setStyleSheet("""
            QDialog {
                background-color: #222222;  /* Dark background */
            }
            QLabel {
                color: white;  /* White text for labels */
            }
        """)  

        self.button_size = QSize(55, 55)
        self.icon_size = QSize(45, 45)
        
        self.setWindowTitle("Filter for Camera 1")

        self.tooltip_manager = CustomToolTipManager(self)
        
        self.selected_icon = None
        self.selected_icon_file = None

        layout = QHBoxLayout()
        # Add the filters present in the JSON file
        for filter_key, filter_item in filter_data1["Filterwheel_1"].items():
            button = QPushButton()
            icon_path = f"icons//{filter_item.get('icon_file')}"
            button.setIcon(QIcon(icon_path))
            button.setFixedSize(self.button_size)
            button.setIconSize(self.icon_size)
            self.tooltip_manager.attach_tooltip(button, f"{filter_item.get('tooltip')}")
            #button.clicked.connect(lambda _, icon_path=icon_path: self.select_filter(QIcon(icon_path)))
            button.clicked.connect(lambda _, path=icon_path: self.select_filter(QIcon(path), path))
            layout.addWidget(button)

        # Add the remove button
        self.button_remove = QPushButton(self)
        self.button_remove.setFixedSize(self.button_size)
        self.icon_remove = QIcon("icons//remove.png")
        self.button_remove.setIcon(self.icon_remove)
        self.button_remove.setIconSize(self.icon_size)
        self.tooltip_manager.attach_tooltip(self.button_remove, "Remove the filter")
        self.button_remove.clicked.connect(lambda: self.select_filter(self.icon_remove, None))
        layout.addWidget(self.button_remove)

        self.setLayout(layout)

    def showEvent(self, event):
        super().showEvent(event)
        # offset by 10px so the dialog doesn’t obscure the pointer
        self.move(QCursor.pos() + QPoint(-60, -120))


    def select_filter(self, icon, icon_file):
            """Set the selected icon and store its file path."""
            self.selected_icon = icon
            self.selected_icon_file = icon_file 
            self.accept()


class Filterwheel_2_DialogBox(QDialog):
    selected_icon = None  # Property to store the selected icon

    def __init__(self, parent_button, filter_data2):
        super().__init__(parent_button)
        self.setStyleSheet("""
            QDialog {
                background-color: #222222;  /* Dark background */
            }
            QLabel {
                color: white;  /* White text for labels */
            }
        """)  

        self.button_size = QSize(55, 55)
        self.icon_size = QSize(45, 45)

        self.setWindowTitle("Filter for Camera 2")

        self.tooltip_manager = CustomToolTipManager(self)

        self.selected_icon = None
        self.selected_icon_file = None

        layout = QHBoxLayout()
        # Add the filters present in the JSON file
        for filter_key, filter_item in filter_data2["Filterwheel_2"].items():
            button = QPushButton()
            icon_path = f"icons//{filter_item.get('icon_file')}"
            button.setIcon(QIcon(icon_path))
            button.setFixedSize(self.button_size)
            button.setIconSize(self.icon_size)
            self.tooltip_manager.attach_tooltip(button, f"{filter_item.get('tooltip')}")
            button.clicked.connect(lambda _, path=icon_path: self.select_filter(QIcon(path), path))
            layout.addWidget(button)

        # Add the remove button
        self.button_remove = QPushButton(self)
        self.button_remove.setFixedSize(self.button_size)
        self.icon_remove = QIcon("icons//remove.png")
        self.button_remove.setIcon(self.icon_remove)
        self.button_remove.setIconSize(self.icon_size)
        self.tooltip_manager.attach_tooltip(self.button_remove, "Remove the filter")
        self.button_remove.clicked.connect(lambda: self.select_filter(self.icon_remove, None))
        layout.addWidget(self.button_remove)

        self.setLayout(layout)

    def select_filter(self, icon, icon_file):
        """Set the selected icon and close the dialog."""
        self.selected_icon = icon
        self.selected_icon_file = icon_file 
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        # offset by 10px so the dialog doesn’t obscure the pointer
        self.move(QCursor.pos() + QPoint(-60, -120))


from PySide6.QtCore import QObject, QThread, Signal, Slot
from datetime import datetime
import time



class LaserWorker(QObject):
    updatePower = Signal(int, float)  # laser_number, power_value
    setLightSheetMode = Signal(bool,int)  # enable/disable Light Sheet mode,request_id
    modeSwitchFinished = Signal(bool, bool, int)  # enabled, ok, request_id 

    def __init__(self, laserbox):
        super().__init__()
        self.laserbox = laserbox
        self.updatePower.connect(self.set_power)
        self.setLightSheetMode.connect(self.set_lightsheet_mode) # connect signal to slot

    
    @Slot()
    def initialise_worker_thread_name_laser_worker(self):
        """
        Rename the Python thread used by the laser worker.

        This changes the value shown by %(threadName)s in the logger output,
        so logs from this worker appear with a readable name instead of Dummy-N.
        """
        threading.current_thread().name = "LASERS"


    
    @Slot(int, float)
    def set_power(self, laser_number, power_value):
        """
        Apply the requested laser power to the hardware.

        Logging policy:
        - Log only when the hardware command is actually sent.
        - Log only the final intended hardware state:
        * OFF when power == 0
        * ON when power > 0
        - Do not log UI requests here.
        """
        # Map UI laser number to human-readable wavelength
        laser_map = {
            1: "405 nm",
            2: "488 nm",
            3: "561 nm",
            4: "640 nm",
        }

        laser_name = laser_map.get(laser_number, f"Unknown laser ({laser_number})")

        # Map UI numbering to hardware channel numbering
        ch = 6 - laser_number

        try:
            # If requested power is zero, turn the laser OFF
            if power_value == 0:
                self.laserbox.write(f"SOURce{ch}:AM:STATe OFF")

                logger.info(
                    "Laser state changed: laser=%s, channel=%s, state=OFF, power=0 mW",
                    laser_name,
                    ch,
                )
                return

            # Convert mW to W if required by the controller
            power_watts = power_value / 1000.0

            # First set the power amplitude
            self.laserbox.write(
                f"SOURce{ch}:POWer:LEVel:IMMediate:AMPLitude {power_watts:.5f}"
            )

            # Then enable the laser output (AM ON)
            self.laserbox.write(f"SOURce{ch}:AM:STATe ON")

            logger.info(
                "Laser state changed: laser=%s, channel=%s, state=ON, power=%s mW",
                laser_name,
                ch,
                power_value,
            )

        except Exception:
            logger.exception(
                "Failed to change laser state: laser=%s, channel=%s, requested power=%s mW",
                laser_name,
                ch,
                power_value,
            )


    


    @Slot(bool, int)
    def set_lightsheet_mode(self, enabled: bool, req_id: int):
        """
        Robust mode switch:
        Many controllers reject AM source/mode changes while AM is enabled.
        So we do:
          1) AM:STATE OFF
          2) Switch AM source (External Digital / Internal CWP)
          3) If enabling LS, arm AM:STATE ON (still gated externally by scanner)
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        mode_cmd = "AM:EXTernal DIGital" if enabled else "AM:INTernal CWP"
        print(f"[{ts}] [Lasers] Request mode switch -> {'LS ON' if enabled else 'LS OFF'}", flush=True)

        ok = True
        for ch in (2, 3, 4, 5):
            try:
                off_cmd = f"SOURce{ch}:AM:STATe OFF"
                print(f"[{ts}] [Lasers]   -> write: {off_cmd}", flush=True)
                self.laserbox.write(off_cmd)
                time.sleep(0.02)

                cmd = f"SOURce{ch}:{mode_cmd}"
                print(f"[{ts}] [Lasers]   -> write: {cmd}", flush=True)
                self.laserbox.write(cmd)
                time.sleep(0.02)
                
                '''
                if enabled:
                    on_cmd = f"SOURce{ch}:AM:STATe ON"
                    print(f"[{ts}] [Lasers]   -> write: {on_cmd}", flush=True)
                    self.laserbox.write(on_cmd)
                    time.sleep(0.02)

                
                # NOTE:
                # Do NOT turn AM:STATE ON during the mode switch.
                # Keep AM OFF here to avoid a one-time flash during transition.
                # The UI will re-apply the intended ON/OFF + power states after the switch completes

                '''

            except Exception as e:
                ok = False
                print(f"[{ts}] [Lasers] !! failed on channel {ch}: {e}", flush=True)

        # Notify UI thread that the switch is complete.
        self.modeSwitchFinished.emit(enabled, ok, req_id)





import pyvisa

class Lasers_Widget(QWidget):
    #-------------------------------------------------------------------------------------
    # Initialization

    lightsheetModeSwitchFinished = Signal(bool, bool, int)  # enabled, ok, request_id

    def __init__(self, filter_data, device, parent=None):
        super().__init__(parent)

        self.filter_data = filter_data

        # Last turned on laser
        self.last_laser_on = 0

        # initialize the laser equipment
        self.laserbox = device

        threading.current_thread().name = "LASERS"

        # Log that the widget received the laser controller object
        if self.laserbox is None:
            logger.error("Laser controller was not provided to Lasers_Widget.")
        else:
            logger.info(
                "Laser controller attached to Lasers_Widget. Device type: %s",
                type(self.laserbox).__name__,)

        
        try:
            # Make sure all laser channels start with AM OFF
            self.laserbox.write("SOURce2:AM:STATe OFF")
            self.laserbox.write("SOURce3:AM:STATe OFF")
            self.laserbox.write("SOURce4:AM:STATe OFF")
            self.laserbox.write("SOURce5:AM:STATe OFF")

            # Start in internal CW mode
            self.laserbox.write("SOURce2:AM:INTernal CWP")
            self.laserbox.write("SOURce3:AM:INTernal CWP")
            self.laserbox.write("SOURce4:AM:INTernal CWP")
            self.laserbox.write("SOURce5:AM:INTernal CWP")

            logger.info(
                "Laser controller initialised successfully: channels 2-5 set to AM OFF and Internal CWP mode."
            )

        except Exception:
            # logger.exception automatically includes the traceback
            logger.exception("Failed to initialise the laser controller in Lasers_Widget.")



        # Setup laser worker in a separate thread
        self.laser_thread = QThread()
        self.laser_worker = LaserWorker(self.laserbox)
        self.laser_worker.moveToThread(self.laser_thread)
        # When the thread starts, rename the Python thread to "LASERS"
        # so that %(threadName)s in the logger becomes "LASERS"
        self.laser_thread.started.connect(self.laser_worker.initialise_worker_thread_name_laser_worker)
        self.laser_thread.start()

        
        self._mode_req_id = 0
        self.laser_worker.modeSwitchFinished.connect(self._on_mode_switch_finished)

        
        self.setupUI()


    def shutdown(self):

        # Stop all QTimers in each DragItem
        for i in range(self.drag.blayout.count()):
            widget = self.drag.blayout.itemAt(i).widget()
            if isinstance(widget, DragItem):
                widget.update_timer.stop()
                
        self.laser_thread.quit()
        self.laser_thread.wait()


    def closeEvent(self, event):
        """Code to run before closing the application"""
        self.shutdown()
        event.accept()

    #-------------------------------------------------------------------------------------
    # Functions for the lasers
    
    def get_laser_settings(self):
        """Gets the power values, checkbox statuses, and selected filters for all lasers."""
        return self.drag.get_all_laser_data()


    def update_laser_power(self, laser_number, power_value):
        # Send command to the worker thread
        self.laser_worker.updatePower.emit(laser_number, power_value)


    def extract_filter_index(self, filter_key, empty_index, filterwheel):
        if filter_key is None:
            return None  # Empty filter case

        # Check in the correct filterwheel (dict from your JSON)
        filter_info = self.filter_data[filterwheel].get(filter_key)
        if filter_info is not None:
            return filter_info.get("position_on_filterwheel", empty_index)
        return empty_index  # Fallback if not found

    def get_selected_lasers(self):
        """
        Returns:
            lasers (list): Laser numbers (2 to 5).
            lasers_power (list): Power values in Watts.
            filters_1 (list): Filter indices for Camera 1 (0 to 5).
            filters_2 (list): Filter indices for Camera 2 (0 to 5).
        """
        EMPTY_INDEX = 5

        lasers = []
        lasers_power = []
        filters_1 = []
        filters_2 = []

        for i in range(self.drag.blayout.count()):
            item = self.drag.blayout.itemAt(i).widget()

            if isinstance(item, DragItem) and item.checkbox.isChecked():
                laser_number = 6 - item.laser_number  # Hardware uses 2–5

                try:
                    txt = item.power_label.text() 
                    mw = int(txt.split()[0])
                    power_value_watts = int(mw) #/ 1000.0
                except ValueError:
                    power_value_watts = 0.0

                key1 = item.selected_cam1_filter
                key2 = item.selected_cam2_filter

                idx1 = self.extract_filter_index(key1, EMPTY_INDEX, "Filterwheel_1")
                idx2 = self.extract_filter_index(key2, EMPTY_INDEX, "Filterwheel_2")

                lasers.append(laser_number)
                lasers_power.append(power_value_watts)
                if idx1 is not None:
                    filters_1.append(idx1)
                if idx2 is not None:
                    filters_2.append(idx2)


        return lasers, lasers_power, filters_1, filters_2
    


    def get_on_lasers(self):
        """
        Return lasers that are currently ON (emitting), regardless of 'Select Laser' checkbox.

        We define "ON" as:
        - The UI ON/OFF button is checked (button3.isChecked() == True)
        - The slider value is > 0 (power > 0)

        Returns:
            lasers (list[int]): Hardware laser channels (2..5)
            lasers_power (list[int]): Power values (mW as int, consistent with your current code)
        """
        lasers = []
        lasers_power = []

        if not hasattr(self, "drag"):
            return lasers, lasers_power

        for i in range(self.drag.blayout.count()):
            item = self.drag.blayout.itemAt(i).widget()

            # Only DragItem has these controls
            if item is None or not hasattr(item, "button3") or not hasattr(item, "slider"):
                continue

            try:
                is_on = bool(item.button3.isChecked()) and int(item.slider.value()) > 0
            except Exception:
                is_on = False

            if not is_on:
                continue

            # Convert internal numbering to hardware numbering (2..5)
            # You already use: hardware = 6 - item.laser_number
            try:
                hw_laser = 6 - int(item.laser_number)
            except Exception:
                continue

            # Prefer lineedit power if valid, else fallback to slider
            power_mw = 0
            try:
                power_mw = int(float(item.value_lineedit.text()))
            except Exception:
                try:
                    power_mw = int(item.slider.value())
                except Exception:
                    power_mw = 0

            lasers.append(hw_laser)
            lasers_power.append(power_mw)

        return lasers, lasers_power
    
    #------------------------------------------------------------------------------------
    # Light Sheet Mode
    
    
    @Slot(bool)
    def set_lightsheet_mode(self, enabled: bool) -> int:
        """
        Request LS/CW mode switch on the laser controller thread and return request_id.
        The caller can use request_id to match the completion event.
        """
        self._mode_req_id = getattr(self, "_mode_req_id", 0) + 1
        req_id = self._mode_req_id
        self.laser_worker.setLightSheetMode.emit(enabled, req_id)
        return req_id


    def _reapply_ui_powers_after_mode_switch(self):
        """
        Re-apply UI power/state to the laser controller AFTER switching AM mode.

        Why:
        - LaserWorker.set_lightsheet_mode() forces AM:STATE OFF to make the controller accept mode changes.
        - Some controllers will not output in External Digital mode unless AM:STATE is turned back ON.
        - Blue/red may be gated elsewhere (analog/AOTF), but green/purple (digital/TTL) often need AM enabled.
        """
        if not hasattr(self, "drag"):
            return

        for i in range(self.drag.blayout.count()):
            item = self.drag.blayout.itemAt(i).widget()

            # Only DragItem widgets have these members
            if item is None or not hasattr(item, "laser_number"):
                continue

            # Internal numbering used by the UI worker (see LaserWorker.set_power usage)
            try:
                ui_laser_number = int(item.laser_number)
            except Exception:
                continue

            # UI power comes from slider/lineedit. Here we use slider as a stable source.
            try:
                power_mw = int(item.slider.value())
            except Exception:
                power_mw = 0

            # Define "ON" as: UI ON button checked AND power > 0
            try:
                is_on = bool(item.button3.isChecked()) and power_mw > 0
            except Exception:
                is_on = False

            # Re-send power command so the controller restores AM state appropriately.
            # LaserWorker.set_power() already turns AM ON if power > 0, OFF if power == 0.
            self.laser_worker.updatePower.emit(ui_laser_number, power_mw if is_on else 0)

    @Slot(bool, bool, int)
    def _on_mode_switch_finished(self, enabled: bool, ok: bool, req_id: int):
        # Ignore stale replies if multiple requests were issued.
        if req_id != getattr(self, "_mode_req_id", req_id):
            return

        # Re-apply UI power/state after the mode switch because mode switching forces AM OFF.
        self._reapply_ui_powers_after_mode_switch()

        # Forward completion to external consumers (Scanner widget).
        self.lightsheetModeSwitchFinished.emit(enabled, ok, req_id)




    #-------------------------------------------------------------------------------------
    # Callable functions

    def turn_all_off(self):
        self.laserbox.write("SOURce2:AM:STATe OFF")
        self.laserbox.write("SOURce3:AM:STATe OFF")
        self.laserbox.write("SOURce4:AM:STATe OFF")
        self.laserbox.write("SOURce5:AM:STATe OFF")

        # iterate every DragItem in the DragWidget
        for i in range(self.drag.blayout.count()):
            w = self.drag.blayout.itemAt(i).widget()
            # only DragItem has .button3
            if hasattr(w, 'button3'):
                # un‑check the button and update its style/text
                w.button3.setChecked(False)
                w.handle_button3_click()

    def set_last_laser_on(self, laser_number):
        self.last_laser_on = laser_number


    def activate_laser_by_number(self, laser_number, power_value):
        """
        Turns on a specific laser by hardware number (2 to 5) and updates the UI.
        Args:
            laser_number (int): 2 to 5 (hardware convention)
            power_value (int): Power in mW (0–100)
        """
        for i in range(self.drag.blayout.count()):
            widget = self.drag.blayout.itemAt(i).widget()
            if isinstance(widget, DragItem):
                internal_number = 6 - laser_number  # Convert 2–5 to internal 0–3
                if widget.laser_number == internal_number:
                    # Simulate setting power and clicking ON
                    widget.last_lineedit_input = str(power_value)
                    widget.value_lineedit.setText(str(power_value))
                    widget.slider.setValue(power_value)
                    widget.button3.setChecked(True)
                    widget.handle_button3_click()
                    break

    #-------------------------------------------------------------------------------------
    # Setting up the UI for the 4 Lasers

    def setupUI(self):

        # Initialize the tooltip manager
        self.tooltip_manager = CustomToolTipManager(self)

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.setObjectName("mainWindow")
        self.setWindowTitle("Lasers Control")

        script_path = Path(__file__).resolve()
        icon_path   = script_path.parent / "icons" / "check.png"
        self.automatic_laser_activation_checkbox = QCheckBox("Automatic laser activation at the camera's Live toggle")
        self.automatic_laser_activation_checkbox.setChecked(True)
        self.tooltip_manager.attach_tooltip(self.automatic_laser_activation_checkbox, "Activate the latest\nused laser when Live")
        self.automatic_laser_activation_checkbox.setStyleSheet(f"""
            QCheckBox {{
                spacing: 2px;
                color: white;
                font-size: 12px;
            }}

            QCheckBox::indicator {{
                width: 13px;
                height: 13px;
                border: 2px solid #555;
                border-radius: 4px;
                background-color: #2E2E2E;
            }}

            QCheckBox::indicator:hover {{
                background-color: #3C3C3C;
                border: 2px solid #777;
            }}

            QCheckBox::indicator:pressed {{
                background-color: #1E1E1E;
                border: 2px solid #999;
            }}

            QCheckBox::indicator:checked {{
                background-color: #4CAF50;
                border: 2px solid #80E27E;
                image: url("{icon_path.as_posix()}");
            }}

            QCheckBox::indicator:checked:hover {{
                background-color: #45A049;
                border: 2px solid #76D275;
            }}

            QCheckBox::indicator:checked:pressed {{
                background-color: #388E3C;
                border: 2px solid #60C460;
            }}

            QCheckBox:disabled {{
                color: #B0B0B0;
            }}

            QCheckBox::indicator:disabled {{
                background-color: #5E5E5E;
                border: 2px solid #777;
            }}
        """)
        layout.addWidget(self.automatic_laser_activation_checkbox)

        self.setStyleSheet("""
            #mainWindow {
                background-color: #222222;  /* Dark background for the main widget */
            }
            QLabel {
                color: white;  /* White text for all labels */
            }
        """)

        self.drag = DragWidget(self.filter_data, orientation=Qt.Orientation.Horizontal)

        self.order = ["1st", "2nd", "3rd", "4th"]
        self.laser_names = ["405 nm", "488 nm", "561 nm", "640 nm"]

        for n, l in enumerate(self.laser_names):
            item = DragItem(self.order[n] + " - " + self.laser_names[n], self.filter_data)
            item.set_data(n)

            # Connect the line edit power
            item.powerChanged.connect(self.update_laser_power)

            # Connect the last laser turned ON
            item.laserTurnedOn.connect(self.set_last_laser_on)

            self.drag.add_item(item)

        #self.drag.orderChanged.connect(print)
        self.drag.orderChanged.connect(self.drag.update_labels)  # Call update_labels on order change


        
        layout.addWidget(self.drag)
        
