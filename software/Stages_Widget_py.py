from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt, QTimer)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter, QDoubleValidator,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QGroupBox, QLabel, QLineEdit,
    QMainWindow, QPushButton, QSizePolicy, QStatusBar,
    QWidget, QButtonGroup, QVBoxLayout)
import sys

from pipython import GCSDevice
from pipython import GCSDevice, pitools

import numpy as np
import os
import json
from datetime import datetime


# Imports from my code
from Extra_Files.ToolTip_Manager import CustomToolTipManager
from Extra_Files.Stylesheet_List import StyleSheets
from Extra_Files.Custom_Line_Edit import CustomLineEdit

from PySide6.QtWidgets import QGroupBox, QApplication, QWidget, QVBoxLayout, QStyleOptionFrame, QStyle
from PySide6.QtGui import QPainter, QTextDocument
from PySide6.QtCore import QRectF



class ItalicTitleGroupBox(QGroupBox):
    def __init__(self, title="", parent=None):
        super().__init__("", parent)  # No native title
        self._rich_title = title

    def paintEvent(self, event):
        painter = QPainter(self)

        # Render title as rich text
        doc = QTextDocument()
        doc.setHtml(self._rich_title)
        text_height = doc.size().height()
        text_width = doc.idealWidth()
        title_rect = QRectF(10, 0, text_width + 4, text_height)

        # Draw background behind title
        painter.setBrush(self.palette().window())
        painter.setPen(self.palette().window().color())
        painter.drawRect(title_rect)

        # Draw the rich text title
        painter.save()
        painter.translate(title_rect.topLeft())
        doc.drawContents(painter)
        painter.restore()

        # Draw the frame manually (since we're skipping super().paintEvent)
        opt = QStyleOptionFrame()
        opt.initFrom(self)
        opt.rect = self.rect()
        opt.lineWidth = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth, opt, self)
        opt.midLineWidth = 0
        opt.features = QStyleOptionFrame.None_

        self.style().drawPrimitive(QStyle.PE_FrameGroupBox, opt, painter, self)

        painter.end()





class Stages_Widget(QWidget):

    def closeEvent(self, event):
        self.shutdown()
        event.accept()
        
    def shutdown(self):
        print("stages shutdown")
        if self.timer.isActive():
            self.timer.stop()
        if self.save_timer.isActive():
            self.save_timer.stop()
        self.save_positions_to_json()


    def __init__(self, device, parent=None):
        super().__init__(parent)

        # Value to change grop box 2's widgets position
        self.two = 3

        #--------------------------------------------------------

        # Initiate the position saving
        base = os.path.dirname(__file__)
        self.json_path = os.path.join(base, "Extra_Files", "Stage_Positions.json")
        # ensure folder exists
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        # create a default when missing:
        if not os.path.isfile(self.json_path):
            with open(self.json_path, "w") as f:
                json.dump({"X": 0, "Y": 0, "Z": 0, "theta": 0}, f, indent=4)

        #--------------------------------------------------------

        # Initialize and Reference the Stages
        self.pidevice = device

            # set the default increments
        self.increment_xz = 0.005      # in mm, coarse movement for default
        self.y_increment = 0.05       # 50 um by default
        self.angular_increment = 3 # in degrees, coarse movement by default

            # set the default fine, coarse and FOV movements
        self.fine_increment = 0.0001
        self.coarse_increment = 0.005
        self.fov_increment = 1.3312
        

            # set the limits of operation of the stages
        self.x_max = self.pidevice.qTMX('1')['1']
        self.x_min = self.pidevice.qTMN('1')['1']

        self.y_max = self.pidevice.qTMX('2')['2']
        self.y_min = self.pidevice.qTMN('2')['2']

        self.z_max = self.pidevice.qTMX('3')['3']
        self.z_min = 1
        

        #--------------------------------------------------------

        # Icons Import and sizes
        self.icon_button_right = QIcon("icons//button_right.png")
        self.icon_button_up = QIcon("icons//button_up.png")
        self.icon_button_left = QIcon("icons//button_left.png")
        self.icon_button_down = QIcon("icons//button_down.png")
        self.icon_button_d2 = QIcon("icons//button_d2.png")
        self.icon_button_d1 = QIcon("icons//button_d1.png")
        self.icon_button_d3 = QIcon("icons//button_d3.png")
        self.icon_button_d4 = QIcon("icons//button_d4.png")
        self.icon_button_counterclock_rotation = QIcon("icons//button_counterclock_rotation.png")
        self.icon_button_clock_rotation = QIcon("icons//button_clock_rotation.png")

        # set up the GUI
        self.setupUi()

        # initialize the timer
        self.timer_update()

        # timer for JSON save
        self.save_timer = QTimer(self)
        self.save_timer.timeout.connect(self.save_positions_to_json)
        self.save_timer.start(5000) 

    #################################################################################

    # Functions for XYZ

    def get_inverted_x_position(self, input_position):
        """Function that inverts in software the positive direction of the X axis"""
        # Invert input position relative to midpoint
        mid = (self.x_max + self.x_min) / 2
        inverted = 2 * mid - input_position

        # Clamp to limits
        inverted = min(max(inverted, self.x_min), self.x_max)
        return inverted

    def move_joystick(self, axis, direction, increment=None):
        """
        Function to move a stage incremently in the positive way of the axis
        axis - ['1', '2', '3'] = ['X', 'Y', 'Z']
        direction - 0: negative, 1: positive
        increment - step size for the stage movement (in milimeters)
        """

        if increment is None:
            increment = self.increment_xz

        current_position = self.pidevice.qPOS(axis)[axis]

        # Invert the X axis
        if axis == '1':
            direction = 1 - direction

        # Calculate the new position
        if direction == 0:
            new_position = current_position - increment
        elif direction == 1:
            new_position = current_position + increment
        else: 
            return

        # Calculate the new position based on the stage's limits
        if axis == '1':
            new_position = min(new_position, self.x_max)
            new_position = max(new_position, self.x_min)
        elif axis == '2':
            new_position = min(new_position, self.y_max)
            new_position = max(new_position, self.y_min)
        elif axis == '3':
            new_position = min(new_position, self.z_max)
            new_position = max(new_position, self.z_min)

        # Move the stage
        self.pidevice.MOV(axis, new_position)

    def move_y_increment(self, direction):

        increment = self.y_increment

        current_position = self.pidevice.qPOS('2')['2']

        # Calculate the new position
        if direction == 0:
            new_position = current_position - increment
        elif direction == 1:
            new_position = current_position + increment
        else: 
            return

        new_position = min(new_position, self.y_max)
        new_position = max(new_position, self.y_min)

        self.pidevice.MOV('2', new_position)



    def diag_movement(self, n):
        """
        Function to move a stage incremently in a diagonal way in the visualization
        """
        increment = np.round( np.sqrt(2)*self.increment_xz , 6)
        if n == 1:
            self.move_joystick('1', 1, increment)
            self.move_joystick('3', 1, increment)
        elif n == 2:
            self.move_joystick('1', 0, increment)
            self.move_joystick('3', 1, increment)
        elif n == 3:
            self.move_joystick('1', 0, increment)
            self.move_joystick('3', 0, increment)
        elif n == 4:
            self.move_joystick('1', 1, increment)
            self.move_joystick('3', 0, increment)


    def fine_movement(self):
        """
        Function that defines the step size as Fine, 1 um
        """
        # Enable the Auto Repeat function of the XZ buttons
        self.AutoRepeat(1)

        # Enable the exclusivity of the Fine and Coarse Buttons
        self.button_group_1.setExclusive(True)

        self.increment_xz = self.fine_increment   # increment of 0.1 um

        self.lineEdit.setText(f"{self.increment_xz * 1000}")

    def coarse_movement(self):
        """
        Function that defines the step size as Coarse, 50 um
        """
        # Enable the Auto Repeat function of the XZ buttons
        self.AutoRepeat(1)

        # Enable the exclusivity of the Fine and Coarse Buttons
        self.button_group_1.setExclusive(True)

        self.increment_xz = self.coarse_increment   # increment of 5 um

        self.lineEdit.setText(f"{self.increment_xz * 1000}")

    def XZ_step_size(self, step):
        """
        Function that allows the user to define the step size
        step - in um, micrometers
        """
        # Enable the Auto Repeat function of the XZ buttons
        self.AutoRepeat(1)

        # Disable the exclusivity of the Fine and Coarse Buttons
        self.button_group_1.setExclusive(False)

        if float(step) == self.fine_increment*1000:
            self.pushButton_9.setChecked(True)
            self.pushButton_10.setChecked(False)
            self.pushButton_11.setChecked(False)
        elif float(step) == self.coarse_increment*1000:
            self.pushButton_9.setChecked(False)
            self.pushButton_10.setChecked(True)
            self.pushButton_11.setChecked(False)
        elif float(step) == self.fov_increment*1000:
            self.pushButton_9.setChecked(False)
            self.pushButton_10.setChecked(False)
            self.pushButton_11.setChecked(True)
        else:
            self.pushButton_9.setChecked(False)
            self.pushButton_10.setChecked(False)
            self.pushButton_11.setChecked(False)
        
        self.increment_xz = float(step) / 1000

    def Y_step_size(self, step):
        """
        Function that allows the user to define the Y step size
        step - in um, micrometers
        """
        self.y_increment = float(step) / 1000

    def move_pos(self, axis, pos):
        """
        Function that moves the stage to a determined position
        """

        text = pos.strip()
        if not text:
            return
        try:
            position = float(pos) / 1000
        except ValueError:
            return

        if axis == '1':
            

            if position > self.x_max:
                self.lineEdit_4.clear()
            elif position < self.x_min:
                self.lineEdit_4.clear()
            else:
                position = self.get_inverted_x_position(position)
                go_position = min(position, self.x_max)
                go_position = max(go_position, self.x_min)
                self.lineEdit_4.clear()

                self.pidevice.MOV(axis, go_position)

        if axis == '2':
            if position > self.y_max:
                self.lineEdit_4.clear()
            elif position < self.y_min:
                self.lineEdit_4.clear()
            else:
                go_position = min(position, self.y_max)
                go_position = max(go_position, self.y_min)
                self.lineEdit_5.clear()

                self.pidevice.MOV(axis, go_position)

        if axis == '3':
            if position > self.z_max:
                self.lineEdit_4.clear()
            elif position < self.z_min:
                self.lineEdit_4.clear()
            else:
                go_position = min(position, self.z_max)
                go_position = max(go_position, self.z_min)
                self.lineEdit_6.clear()

                self.pidevice.MOV(axis, go_position)

        

        

    #--------------------------------------------------------

    # Functions for Theta Rotation

    def angular_incremental_movement(self, direction, increment=None):
        """
        Function to move the Theta stage incrementally 
        axis - '4' - Theta
        direction - 0: counter clockwise, 1: clockwise
        increment - is going to be either a preset or defined by the user
        """

        if increment == None:
            increment = self.angular_increment

        # In this function I'm just working with the XY plane rotation - Theta
        axis = '4'

        # Determine the current Z position
        current_position = self.pidevice.qPOS(axis)[axis]

        # Calculate the new position to move to
        if direction == 0:         # negative direction
            new_position = current_position - increment
        elif direction == 1:       # positive direction
            new_position = current_position + increment
        else:
            return

        # Move the stage
        self.pidevice.MOV(axis, new_position)

    def move_theta_pos(self, angle):
        """
        Functions that adapts the angle that the user inputs to the real angle
        in which the stage is
        """
        axis = '4'

        text = angle.strip()
        if not text:
            return
        try:
            angle = float(angle)
        except ValueError:
            return

        # Determine the rotation stage's current position
        real_angle = self.pidevice.qPOS(axis)[axis]

        # Adapt the user's input angle to the current angular position
        #nr_revolutions = real_angle // 360
        nr_revolutions = int(round((real_angle - angle) / 360.0))
        pretended_angle = nr_revolutions*360 + angle

        # Move the stage
        self.pidevice.MOV(axis, pretended_angle)
        self.lineEdit_7.clear()

    def theta_fine_movement(self):
        """
        Function that defines the step size as Fine, 1 um
        """
        self.button_group_3.setExclusive(True)
        self.angular_increment = 0.5  # increment of 0.5 degrees
        self.lineEdit_3.setText(f"{self.angular_increment}")

    def theta_coarse_movement(self):
        """
        Function that defines the step size as Coarse, 50 um
        """
        self.button_group_3.setExclusive(True)
        self.angular_increment = 3   # increment of 3 degrees
        self.lineEdit_3.setText(f"{self.angular_increment}")

    def theta_step_size(self, step):
        """
        Function that allows the user to define the angular step size
        step - in degrees
        """

        self.button_group_3.setExclusive(False)
        self.pushButton_22.setChecked(False)
        self.pushButton_23.setChecked(False)

        self.angular_increment = float(step)

    #--------------------------------------------------------

    # Functions for Position Update

    def timer_update(self):
        # QTimer to periodically update positions
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(10)  # Update every 500ms

    def update(self):
        
        # Get the positions
        x = self.pidevice.qPOS('1')['1']
        y = self.pidevice.qPOS('2')['2']
        z = self.pidevice.qPOS('3')['3']
        theta = self.pidevice.qPOS('4')['4']

        # Update the Labels
        self.label_13.setText(f"<i>X</i>: {(self.get_inverted_x_position(x) * 1000):.2f} \u03bcm")
        self.label_14.setText(f"<i>Y</i>: {(y * 1000):.2f} \u03bcm")
        self.label_15.setText(f"<i>Z</i>: {(z * 1000):.2f} \u03bcm")   # esta precisa de mudar para que a referenciação fique em 25
        self.label_16.setText(f"<i>\u03b8</i>: {(theta % 360):.2f}º ({(theta):.2f}º)")


    #--------------------------------------------------------

    # FOV Function

    def AutoRepeat(self, enabling):
        """
        Function that either enables or disables the Auto Repeat function of the XZ plane control buttons
        """
        if enabling == 0:
            # Disable the Auto Repeat function that is denabled by default
            self.pushButton.setAutoRepeat(False)
            self.pushButton_2.setAutoRepeat(False)
            self.pushButton_3.setAutoRepeat(False)
            self.pushButton_4.setAutoRepeat(False)
            self.pushButton_5.setAutoRepeat(False)
            self.pushButton_6.setAutoRepeat(False)
            self.pushButton_7.setAutoRepeat(False)
            self.pushButton_8.setAutoRepeat(False)

        elif enabling == 1:
            # Enable the Auto Repeat function that is denabled by default
            self.pushButton.setAutoRepeat(True)
            self.pushButton_2.setAutoRepeat(True)
            self.pushButton_3.setAutoRepeat(True)
            self.pushButton_4.setAutoRepeat(True)
            self.pushButton_5.setAutoRepeat(True)
            self.pushButton_6.setAutoRepeat(True)
            self.pushButton_7.setAutoRepeat(True)
            self.pushButton_8.setAutoRepeat(True)



    def FOV(self):
        """
        Function that changes the XY step size to move a full FOV frame
        """
        # Disable the Auto Repeat of the XY buttons
        self.AutoRepeat(0)
        self.increment_xz = self.fov_increment # um for 2048x2048
        self.lineEdit.setText("")

    #--------------------------------------------------------

    # Function to save the positions

    def save_positions_to_json(self):
        # query raw positions
        raw_x = self.pidevice.qPOS('1')['1']
        raw_y = self.pidevice.qPOS('2')['2']
        raw_z = self.pidevice.qPOS('3')['3']
        raw_theta = self.pidevice.qPOS('4')['4']

        # convert to your display units (µm, degrees)
        x = self.get_inverted_x_position(raw_x) * 1000
        y = raw_y * 1000
        z = raw_z * 1000
        theta = raw_theta % 360

        data = {
            "X": round(x, 4),
            "Y": round(y, 4),
            "Z": round(z, 4),
            "theta": round(theta, 3)
        }
        with open(self.json_path, "w") as f:
            json.dump(data, f, indent=4)

    
    #################################################################################

    # GUI Construction

    def setupUi(self):

        # Main Window
        self.setWindowTitle("Stages Control")
        self.setFixedSize(440, 310)

        #main_layout = QVBoxLayout(self)
        #--------------------------------------------------------

        # Group Boxes
            # Group Box 1 - YZ Plane
        self.groupBox = ItalicTitleGroupBox('<span style="color:white; "><i>XZ</i> [\u03bcm]</span>', self)
        # self.groupBox.setTitle("<i>XY</i> [\u03bcm]")
        self.groupBox.setGeometry(QRect(10, 10, 231, 181))


            # Group Box 2 - X Axis
        self.groupBox_2 = ItalicTitleGroupBox('<span style="color:white; "><i>Y</i> [\u03bcm]</span>', self)
        self.groupBox_2.setGeometry(QRect(250, 10, 181, 101))


            # Group Box 3 - Rotation
        self.groupBox_3 = ItalicTitleGroupBox('<span style="color:white; ">Rotation (degrees)</span>', self)
        self.groupBox_3.setGeometry(QRect(250, 110, 181, 81))


            # Group Box 4 - Set XYZT Position
        self.groupBox_4 = ItalicTitleGroupBox('<span style="color:white; ">Set <i>XYZ\u03b8</i> Position</span>', self)
        self.groupBox_4.setGeometry(QRect(10, 190, 231, 110))


            # Group Box 5 - XYZT Position
        self.groupBox_5 = ItalicTitleGroupBox('<span style="color:white; "><i>XYZ\u03b8</i> Position</span>', self)
        self.groupBox_5.setGeometry(QRect(250, 190, 181, 110))


        #--------------------------------------------------------

        # Push Buttons

            # Group Box 1 - XZ Plane
        self.pushButton = QPushButton(self.groupBox)
        self.pushButton.setIcon(self.icon_button_right)
        self.pushButton.setGeometry(QRect(110, 50+5, 30, 80))
        self.pushButton.setAutoRepeat(True)
        self.pushButton.setAutoRepeatInterval(5)
        self.pushButton.setAutoRepeatDelay(0)
        self.pushButton.pressed.connect(lambda: self.move_joystick('1', 1) )

        self.pushButton_2 = QPushButton(self.groupBox)
        self.pushButton_2.setIcon(self.icon_button_up)
        self.pushButton_2.setGeometry(QRect(40, 20+5, 70, 30))
        self.pushButton_2.setAutoRepeat(True)
        self.pushButton_2.setAutoRepeatInterval(5)
        self.pushButton_2.setAutoRepeatDelay(0)
        self.pushButton_2.pressed.connect(lambda: self.move_joystick('3', 1) )

        self.pushButton_3 = QPushButton(self.groupBox)
        self.pushButton_3.setIcon(self.icon_button_left)
        self.pushButton_3.setGeometry(QRect(10, 50+5, 30, 80))
        self.pushButton_3.setAutoRepeat(True)
        self.pushButton_3.setAutoRepeatInterval(5)
        self.pushButton_3.setAutoRepeatDelay(0)
        self.pushButton_3.pressed.connect(lambda: self.move_joystick('1', 0) )

        self.pushButton_4 = QPushButton(self.groupBox)
        self.pushButton_4.setIcon(self.icon_button_down)
        self.pushButton_4.setGeometry(QRect(40, 130+5, 70, 30))
        self.pushButton_4.setAutoRepeat(True)
        self.pushButton_4.setAutoRepeatInterval(5)
        self.pushButton_4.setAutoRepeatDelay(0)
        self.pushButton_4.pressed.connect(lambda: self.move_joystick('3', 0) )

        self.pushButton_5 = QPushButton(self.groupBox)
        self.pushButton_5.setIcon(self.icon_button_d2)
        self.pushButton_5.setGeometry(QRect(110, 20+5, 30, 30))
        self.pushButton_5.setAutoRepeat(True)
        self.pushButton_5.setAutoRepeatInterval(5)
        self.pushButton_5.setAutoRepeatDelay(0)
        self.pushButton_5.pressed.connect(lambda n=1: self.diag_movement(n))

        self.pushButton_6 = QPushButton(self.groupBox)
        self.pushButton_6.setIcon(self.icon_button_d1)
        self.pushButton_6.setGeometry(QRect(10, 20+5, 30, 30))
        self.pushButton_6.setAutoRepeat(True)
        self.pushButton_6.setAutoRepeatInterval(5)
        self.pushButton_6.setAutoRepeatDelay(0)
        self.pushButton_6.pressed.connect(lambda n=2: self.diag_movement(n))

        self.pushButton_7 = QPushButton(self.groupBox)
        self.pushButton_7.setIcon(self.icon_button_d3)
        self.pushButton_7.setGeometry(QRect(10, 130+5, 30, 30))
        self.pushButton_7.setAutoRepeat(True)
        self.pushButton_7.setAutoRepeatInterval(5)
        self.pushButton_7.setAutoRepeatDelay(0)
        self.pushButton_7.pressed.connect(lambda n=3: self.diag_movement(n))

        self.pushButton_8 = QPushButton(self.groupBox)
        self.pushButton_8.setIcon(self.icon_button_d4)
        self.pushButton_8.setGeometry(QRect(110, 130+5, 30, 30))
        self.pushButton_8.setAutoRepeat(True)
        self.pushButton_8.setAutoRepeatInterval(5)
        self.pushButton_8.setAutoRepeatDelay(0)
        self.pushButton_8.pressed.connect(lambda n=4: self.diag_movement(n))

        self.pushButton_9 = QPushButton(self.groupBox)
        self.pushButton_9.setText("Fine")
        self.pushButton_9.setGeometry(QRect(150, 20+5, 75, 24))
        self.pushButton_9.setCheckable(True)
        self.pushButton_9.pressed.connect(lambda: self.fine_movement())

        self.pushButton_10 = QPushButton(self.groupBox)
        self.pushButton_10.setText("Coarse")
        self.pushButton_10.setGeometry(QRect(150, 50+5, 75, 24))
        self.pushButton_10.setCheckable(True)
        self.pushButton_10.pressed.connect(lambda: self.coarse_movement())
        self.pushButton_10.setChecked(True)

        self.pushButton_11 = QPushButton(self.groupBox)
        self.pushButton_11.setText("FOV")
        self.pushButton_11.setGeometry(QRect(150, 80+5, 75, 24))
        self.pushButton_11.setCheckable(True)
        self.pushButton_11.pressed.connect(lambda: self.FOV())

            # Button Group for GroupBox 1
        self.button_group_1 = QButtonGroup(self.groupBox)
        self.button_group_1.addButton(self.pushButton_9)
        self.button_group_1.addButton(self.pushButton_10)
        self.button_group_1.addButton(self.pushButton_11)
        self.button_group_1.setExclusive(True)



        #--------------------------------------------------------

            # Group Box 2 - Y Axis
        self.pushButton_12 = QPushButton(self.groupBox_2)
        self.pushButton_12.setIcon(self.icon_button_up)
        self.pushButton_12.setGeometry(QRect(10, 20+self.two, 40, 24))
        self.pushButton_12.setAutoRepeat(True)
        self.pushButton_12.setAutoRepeatInterval(5)
        self.pushButton_12.setAutoRepeatDelay(0)
        self.pushButton_12.pressed.connect(lambda: self.move_joystick('2', 1, 0.0001) )

        self.pushButton_13 = QPushButton(self.groupBox_2)
        self.pushButton_13.setIcon(self.icon_button_down)
        self.pushButton_13.setGeometry(QRect(10, 70+self.two, 40, 24))
        self.pushButton_13.setAutoRepeat(True)
        self.pushButton_13.setAutoRepeatInterval(5)
        self.pushButton_13.setAutoRepeatDelay(0)
        self.pushButton_13.pressed.connect(lambda: self.move_joystick('2', 0, 0.0001) )

        self.pushButton_14 = QPushButton(self.groupBox_2)
        self.pushButton_14.setIcon(self.icon_button_up)
        self.pushButton_14.setGeometry(QRect(50, 20+self.two, 40, 24))
        self.pushButton_14.setAutoRepeat(True)
        self.pushButton_14.setAutoRepeatInterval(5)
        self.pushButton_14.setAutoRepeatDelay(0)
        self.pushButton_14.pressed.connect(lambda: self.move_joystick('2', 1, 0.001) )

        self.pushButton_15 = QPushButton(self.groupBox_2)
        self.pushButton_15.setIcon(self.icon_button_down)
        self.pushButton_15.setGeometry(QRect(50, 70+self.two, 40, 24))
        self.pushButton_15.setAutoRepeat(True)
        self.pushButton_15.setAutoRepeatInterval(5)
        self.pushButton_15.setAutoRepeatDelay(0)
        self.pushButton_15.pressed.connect(lambda: self.move_joystick('2', 0, 0.001) )

        self.pushButton_16 = QPushButton(self.groupBox_2)
        self.pushButton_16.setIcon(self.icon_button_up)
        self.pushButton_16.setGeometry(QRect(90, 20+self.two, 40, 24))
        self.pushButton_16.setAutoRepeat(True)
        self.pushButton_16.setAutoRepeatInterval(5)
        self.pushButton_16.setAutoRepeatDelay(0)
        self.pushButton_16.pressed.connect(lambda: self.move_joystick('2', 1, 0.01) )

        self.pushButton_17 = QPushButton(self.groupBox_2)
        self.pushButton_17.setIcon(self.icon_button_down)
        self.pushButton_17.setGeometry(QRect(90, 70+self.two, 40, 24))
        self.pushButton_17.setAutoRepeat(True)
        self.pushButton_17.setAutoRepeatInterval(5)
        self.pushButton_17.setAutoRepeatDelay(0)
        self.pushButton_17.pressed.connect(lambda: self.move_joystick('2', 0, 0.01) )

        self.pushButton_18 = QPushButton(self.groupBox_2)
        self.pushButton_18.setIcon(self.icon_button_up)
        self.pushButton_18.setGeometry(QRect(130, 20+self.two, 40, 24))
        self.pushButton_18.setAutoRepeat(True)
        self.pushButton_18.setAutoRepeatInterval(5)
        self.pushButton_18.setAutoRepeatDelay(0)
        self.pushButton_18.pressed.connect(lambda: self.move_y_increment(1) )

        self.pushButton_19 = QPushButton(self.groupBox_2)
        self.pushButton_19.setIcon(self.icon_button_down)
        self.pushButton_19.setGeometry(QRect(130, 70+self.two, 40, 24))
        self.pushButton_19.setAutoRepeat(True)
        self.pushButton_19.setAutoRepeatInterval(5)
        self.pushButton_19.setAutoRepeatDelay(0)
        self.pushButton_19.pressed.connect(lambda: self.move_y_increment(0) )


            # Group Box 3 - Rotation
        self.pushButton_20 = QPushButton(self.groupBox_3)
        self.pushButton_20.setIcon(self.icon_button_counterclock_rotation)
        self.pushButton_20.setGeometry(QRect(110, 20+5, 31, 50))
        self.pushButton_20.setIconSize(QSize(25, 38))
        self.pushButton_20.setAutoRepeat(True)
        self.pushButton_20.setAutoRepeatInterval(5)
        self.pushButton_20.setAutoRepeatDelay(0)
        self.pushButton_20.pressed.connect(lambda: self.angular_incremental_movement(0))

        self.pushButton_21 = QPushButton(self.groupBox_3)
        self.pushButton_21.setIcon(self.icon_button_clock_rotation)
        self.pushButton_21.setGeometry(QRect(140, 20+5, 31, 50))
        self.pushButton_21.setIconSize(QSize(25, 38))
        self.pushButton_21.setAutoRepeat(True)
        self.pushButton_21.setAutoRepeatInterval(5)
        self.pushButton_21.setAutoRepeatDelay(0)
        self.pushButton_21.pressed.connect(lambda: self.angular_incremental_movement(1) )

        self.pushButton_22 = QPushButton(self.groupBox_3)
        self.pushButton_22.setText("Fine")
        self.pushButton_22.setGeometry(QRect(5, 20+5, 55, 25))
        self.pushButton_22.setCheckable(True)
        self.pushButton_22.pressed.connect(lambda: self.theta_fine_movement())

        self.pushButton_23 = QPushButton(self.groupBox_3)
        self.pushButton_23.setText("Coarse")
        self.pushButton_23.setGeometry(QRect(5, 45+5, 55, 25))
        self.pushButton_23.setCheckable(True)
        self.pushButton_23.pressed.connect(lambda: self.theta_coarse_movement())
        self.pushButton_23.setChecked(True)



            # Button Group for GroupBox 3
        self.button_group_3 = QButtonGroup(self.groupBox_3)
        self.button_group_3.addButton(self.pushButton_22)
        self.button_group_3.addButton(self.pushButton_23)
        self.button_group_3.setExclusive(True)

        #--------------------------------------------------------

        # Labels

            # Group Box 1 - XZ Plane
        self.label = QLabel(self.groupBox)
        self.label.setText(u"Step:")
        self.label.setGeometry(QRect(57, 70+5, 27, 15))

            # Group Box 2 - Y Axis
        self.label_2 = QLabel(self.groupBox_2)
        self.label_2.setText("0.1")
        self.label_2.setGeometry(QRect(23, 50+self.two, 20, 16))

        self.label_3 = QLabel(self.groupBox_2)
        self.label_3.setText("1.0")
        self.label_3.setGeometry(QRect(63, 50+self.two, 20, 16))

        self.label_4 = QLabel(self.groupBox_2)
        self.label_4.setText("10")
        self.label_4.setGeometry(QRect(103, 50+self.two, 20, 16))

            # Group Box 3 - Rotation
        self.label_17 = QLabel(self.groupBox_3)
        self.label_17.setText("Step:")
        self.label_17.setGeometry(QRect(69, 27+5, 30, 25))

            # Group Box 4 - Set XYZT Position
        self.label_6 = QLabel(self.groupBox_4)
        self.label_6.setText("<i>X</i>:")
        self.label_6.setTextFormat(Qt.TextFormat.RichText)
        self.label_6.setGeometry(QRect(10, 20+5, 16, 16))

        self.label_7 = QLabel(self.groupBox_4)
        self.label_7.setText("<i>Y</i>:")
        self.label_7.setTextFormat(Qt.TextFormat.RichText)
        self.label_7.setGeometry(QRect(10, 40+5, 16, 16))

        self.label_8 = QLabel(self.groupBox_4)
        self.label_8.setText("<i>Z</i>:")
        self.label_8.setTextFormat(Qt.TextFormat.RichText)
        self.label_8.setGeometry(QRect(10, 60+5, 16, 16))

        self.label_9 = QLabel(self.groupBox_4)
        self.label_9.setText("<i>\u03b8</i>:")
        self.label_9.setTextFormat(Qt.TextFormat.RichText)
        self.label_9.setGeometry(QRect(10, 80+5, 16, 16))

        self.label_9 = QLabel(self.groupBox_4)
        self.label_9.setText("[0, 5000] \u03bcm")
        self.label_9.setTextFormat(Qt.TextFormat.RichText)
        self.label_9.setGeometry(QRect(115, 20+5, 100, 16))

        self.label_10 = QLabel(self.groupBox_4)
        self.label_10.setText("[0, 5000] \u03bcm")
        self.label_10.setTextFormat(Qt.TextFormat.RichText)
        self.label_10.setGeometry(QRect(115, 40+5, 100, 16))

        self.label_11 = QLabel(self.groupBox_4)
        self.label_11.setText(f"[{(self.z_min * 1000):.0f}, 25000] \u03bcm")
        self.label_11.setTextFormat(Qt.TextFormat.RichText)
        self.label_11.setGeometry(QRect(115, 60+5, 100, 16))

        self.label_12 = QLabel(self.groupBox_4)
        self.label_12.setText("[0, 360]º")
        self.label_12.setGeometry(QRect(115, 80+5, 100, 16))

            # Group 5 - XYZT Positions
        self.label_13 = QLabel(self.groupBox_5)
        self.label_13.setText("<i>X</i>: ")
        self.label_13.setTextFormat(Qt.TextFormat.RichText)
        self.label_13.setGeometry(QRect(10, 20+5, 150, 16))

        self.label_14 = QLabel(self.groupBox_5)
        self.label_14.setText("<i>Y</i>: ")
        self.label_14.setTextFormat(Qt.TextFormat.RichText)
        self.label_14.setGeometry(QRect(10, 40+5, 150, 16))

        self.label_15 = QLabel(self.groupBox_5)
        self.label_15.setText("<i>Z</i>: ")
        self.label_15.setTextFormat(Qt.TextFormat.RichText)
        self.label_15.setGeometry(QRect(10, 60+5, 150, 16))

        self.label_16 = QLabel(self.groupBox_5)
        self.label_16.setText("<i>\u03b8</i>: ")
        self.label_16.setTextFormat(Qt.TextFormat.RichText)
        self.label_16.setGeometry(QRect(10, 80+5, 150, 16))

        #--------------------------------------------------------

        # Line Edits

        validator = QDoubleValidator()
        validator.setLocale(QLocale(QLocale.English))

            # Group Box 1 - XZ Plane
        self.lineEdit = QLineEdit(self.groupBox)
        self.lineEdit.setGeometry(QRect(56, 88+4, 38, 22))
        self.lineEdit.returnPressed.connect(lambda: self.XZ_step_size(self.lineEdit.text()) )
        self.lineEdit.editingFinished.connect(lambda: self.XZ_step_size(self.lineEdit.text()) )
        self.lineEdit.returnPressed.connect(self.lineEdit.clearFocus)
        self.lineEdit.setText(f"{self.increment_xz * 1000}")
        self.lineEdit.setValidator(validator)
        self.lineEdit.setStyleSheet("""
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
                background-color: #444444;  /* Slightly lighter when active */
            }

            QLineEdit:disabled {
                background-color: #222222;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                outline: none;
            }""")

            # Group Box 2 - Y Axis
        self.lineEdit_2 = QLineEdit(self.groupBox_2)
        self.lineEdit_2.setText(f"{self.y_increment * 1000:g}")
        self.lineEdit_2.setGeometry(QRect(133, 48+self.two-1, 33, 22))
        self.lineEdit_2.returnPressed.connect(lambda: self.Y_step_size(self.lineEdit_2.text()) )
        self.lineEdit_2.editingFinished.connect(lambda: self.Y_step_size(self.lineEdit_2.text()) )
        self.lineEdit_2.returnPressed.connect(self.lineEdit_2.clearFocus)
        self.lineEdit_2.setValidator(validator)
        self.lineEdit_2.setStyleSheet("""
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
                background-color: #444444;  /* Slightly lighter when active */
            }

            QLineEdit:disabled {
                background-color: #222222;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                outline: none;
            }""")


            # Group Box 3 - Rotation
        self.lineEdit_3 = QLineEdit(self.groupBox_3)
        self.lineEdit_3.setGeometry(QRect(68, 49+4, 35, 22))
        self.lineEdit_3.returnPressed.connect(lambda: self.theta_step_size(self.lineEdit_3.text()) )
        self.lineEdit_3.editingFinished.connect(lambda: self.theta_step_size(self.lineEdit_3.text()) )
        self.lineEdit_3.returnPressed.connect(self.lineEdit_3.clearFocus)
        self.lineEdit_3.setText(f"{self.angular_increment}")
        self.lineEdit_3.setValidator(validator)
        self.lineEdit_3.setStyleSheet("""
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
                background-color: #444444;  /* Slightly lighter when active */
            }

            QLineEdit:disabled {
                background-color: #222222;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                outline: none;
            }""")

            # Group Box 4 - Set XYZT Position
        self.lineEdit_4 = QLineEdit(self.groupBox_4)
        self.lineEdit_4.setGeometry(QRect(30, 18+5, 70, 19))
        self.lineEdit_4.returnPressed.connect(lambda: self.move_pos('1', self.lineEdit_4.text()))
        self.lineEdit_4.editingFinished.connect(lambda: self.move_pos('1', self.lineEdit_4.text()))
        self.lineEdit_4.returnPressed.connect(self.lineEdit_4.clearFocus)
        self.lineEdit_4.setValidator(validator)
        self.lineEdit_4.setStyleSheet("""
            QLineEdit {
                background-color: #333333;  /* Fix background */
                color: white;  /* Ensure white text */
                border: 1px solid #555555;  /* Darker border */
                padding: 4px;  /* Ensure spacing inside */
                border-radius: 3px;  /* Smooth rounded corners */
                selection-background-color: #0078d7;  /* Fix text selection */
                font-size: 10px;
            }

            QLineEdit:focus {
                border: 1px solid #888888;  /* Highlight when focused */
                background-color: #444444;  /* Slightly lighter when active */
            }

            QLineEdit:disabled {
                background-color: #222222;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                outline: none;
            }""")


        self.lineEdit_5 = QLineEdit(self.groupBox_4)
        self.lineEdit_5.setGeometry(QRect(30, 38+5, 70, 19))
        self.lineEdit_5.returnPressed.connect(lambda: self.move_pos('2', self.lineEdit_5.text()) )
        self.lineEdit_5.editingFinished.connect(lambda: self.move_pos('2', self.lineEdit_5.text()) )
        self.lineEdit_5.returnPressed.connect(self.lineEdit_5.clearFocus)
        self.lineEdit_5.setValidator(validator)
        self.lineEdit_5.setStyleSheet("""
            QLineEdit {
                background-color: #333333;  /* Fix background */
                color: white;  /* Ensure white text */
                border: 1px solid #555555;  /* Darker border */
                padding: 4px;  /* Ensure spacing inside */
                border-radius: 3px;  /* Smooth rounded corners */
                selection-background-color: #0078d7;  /* Fix text selection */
                font-size: 10px;
            }

            QLineEdit:focus {
                border: 1px solid #888888;  /* Highlight when focused */
                background-color: #444444;  /* Slightly lighter when active */
            }

            QLineEdit:disabled {
                background-color: #222222;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                outline: none;
            }""")


        self.lineEdit_6 = QLineEdit(self.groupBox_4)
        self.lineEdit_6.setGeometry(QRect(30, 58+5, 70, 19))
        self.lineEdit_6.returnPressed.connect(lambda: self.move_pos('3', self.lineEdit_6.text()) )
        self.lineEdit_6.editingFinished.connect(lambda: self.move_pos('3', self.lineEdit_6.text()) )
        self.lineEdit_6.returnPressed.connect(self.lineEdit_6.clearFocus)
        self.lineEdit_6.setValidator(validator)
        self.lineEdit_6.setStyleSheet("""
            QLineEdit {
                background-color: #333333;  /* Fix background */
                color: white;  /* Ensure white text */
                border: 1px solid #555555;  /* Darker border */
                padding: 4px;  /* Ensure spacing inside */
                border-radius: 3px;  /* Smooth rounded corners */
                selection-background-color: #0078d7;  /* Fix text selection */
                font-size: 10px;
            }

            QLineEdit:focus {
                border: 1px solid #888888;  /* Highlight when focused */
                background-color: #444444;  /* Slightly lighter when active */
            }

            QLineEdit:disabled {
                background-color: #222222;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                outline: none;
            }""")


        self.lineEdit_7 = QLineEdit(self.groupBox_4)
        self.lineEdit_7.setGeometry(QRect(30, 78+5, 70, 19))
        self.lineEdit_7.returnPressed.connect(lambda: self.move_theta_pos(self.lineEdit_7.text()) )
        self.lineEdit_7.editingFinished.connect(lambda: self.move_theta_pos(self.lineEdit_7.text()) )
        self.lineEdit_7.returnPressed.connect(self.lineEdit_7.clearFocus)
        self.lineEdit_7.setValidator(validator)
        self.lineEdit_7.setStyleSheet("""
            QLineEdit {
                background-color: #333333;  /* Fix background */
                color: white;  /* Ensure white text */
                border: 1px solid #555555;  /* Darker border */
                padding: 4px;  /* Ensure spacing inside */
                border-radius: 3px;  /* Smooth rounded corners */
                selection-background-color: #0078d7;  /* Fix text selection */
                font-size: 10px;
            }

            QLineEdit:focus {
                border: 1px solid #888888;  /* Highlight when focused */
                background-color: #444444;  /* Slightly lighter when active */
            }

            QLineEdit:disabled {
                background-color: #222222;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {
                outline: none;
            }""")


        #--------------------------------------------------------

        self.setStyleSheet("""
            QWidget {
                background-color: #222222;
            }

            QLabel{
                color: white;
            }
                           
            QGroupBox {
                border: 1px solid #444444;
                border-radius: 5px; /* Optional, for smooth corners */
                padding: 5px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 5px;
                color: white;
                background: transparent;
            }
                        
            QPushButton {
                background-color: #2E2E2E;
                color: white;
                border: 2px solid #555;
                border-radius: 12px;
                padding: 2px 6px;
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

            QPushButton:checked:disabled {
                background-color: #7CBF7C;  /* Muted green */
                border: 2px solid #A5D6A7;
                font-weight: bold;
                color: black;
            }

        """
        )



# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     window = Stages_Widget()
#     window.show()
#     sys.exit(app.exec_())