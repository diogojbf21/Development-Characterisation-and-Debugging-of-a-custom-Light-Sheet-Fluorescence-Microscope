import sys
import json
from PySide6.QtCore import Qt, QTimer, QMetaObject, QSignalBlocker
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QLabel, QGridLayout, QComboBox, QHBoxLayout, QVBoxLayout,
    QSizePolicy, QLineEdit, QLayout, QSlider, QCheckBox, QPushButton,
)

# Other imports
from pylablib.devices import DCAM
import numpy as np
import cv2

# Imports from your code
from Extra_Files.ToolTip_Manager import CustomToolTipManager
from Extra_Files.Stylesheet_List import StyleSheets
from Extra_Files.Custom_Line_Edit import CustomLineEdit
from Extra_Files.Acquisition_Thread_Code import Acquisition_Thread
from Extra_Files.Separate_Numbers_Code import separate_numbers

from PySide6.QtCore import QThread, Signal, Slot
import time
from pathlib import Path

import logging
import threading

# Reuse the main application logger configured in main.py / logger.py
logger = logging.getLogger("ALM")

############################################################################################################

class CameraControlThread(QThread):
    """Thread to apply settings to the camera asynchronously."""
    update_signal = Signal(str)  # Signal to notify UI about changes.

    def __init__(self, acquisition_thread):
        super().__init__()
        self.acquisition_thread = acquisition_thread
        self.running = True
        self.task_queue = []  # Store parameter change requests.

    def run(self):
        """Process queued camera commands in a separate thread."""
        while self.running:
            if self.task_queue:
                task_name, params = self.task_queue.pop(0)
                try:
                    if task_name == "change_ROI":
                        self.acquisition_thread.change_ROI(*params)
                    elif task_name == "change_sensor_mode":
                        self.acquisition_thread.change_sensor_mode(params[0])
                    elif task_name == "change_dynamic_range":
                        self.acquisition_thread.change_dynamic_range(params[0])
                    elif task_name == "change_exposure_time":
                        self.acquisition_thread.change_exposure_time(params[0])
                    elif task_name == "change_binning":
                        self.acquisition_thread.change_binning(*params)

                    self.update_signal.emit(f"{task_name} updated successfully.")
                except Exception as e:
                    self.update_signal.emit(f"Error updating {task_name}: {str(e)}")

            self.msleep(50)  # Prevent excessive CPU usage.

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.quit()
        self.wait()

    def update_camera_parameter(self, task_name, *params):
        """Queue a camera setting change request."""
        self.task_queue.append((task_name, params))

############################################################################################################

class CameraFeedbackThread(QThread):
    """Thread to retrieve camera values continuously."""
    fps_signal = Signal(float)   # Updates framerate label.
    exposure_signal = Signal(float)  # Updates exposure time in UI.
    roi_signal = Signal(int, int)  # Updates ROI width and height.

    def __init__(self, acquisition_thread):
        super().__init__()
        self.acquisition_thread = acquisition_thread
        self.running = True

    def run(self):
        """Continuously fetch camera values without blocking the GUI."""
        while self.running:
            try:
                fps = self.acquisition_thread.get_framerate()
                self.fps_signal.emit(fps)

                exposure = self.acquisition_thread.camera.get_attribute_value("EXPOSURE TIME") * 1000  # Convert to ms
                self.exposure_signal.emit(exposure)

                roi_values = self.acquisition_thread.camera.get_roi()
                width = roi_values[1] - roi_values[0]
                height = roi_values[3] - roi_values[2]
                self.roi_signal.emit(width, height)

            except Exception as e:
                print(f"[Camera Feedback Thread] Error: {str(e)}")

            self.msleep(500)  # Update every 500ms.

    def stop(self):
        """Stop the thread."""
        self.running = False
        self.quit()
        self.wait()

############################################################################################################

class Camera_Widget(QWidget):

    # Live button toggled signal
    live_toggled = Signal(bool)
    # Snap button click signal
    snap_clicked = Signal()
    # Restart button click signal
    restart_clicked = Signal()
   
    exposure_changed_by_user = Signal(float, int)
    # float -> exposure in ms
    # int   -> camera index

    ############################################################################################################
    # Initialization

    def __init__(self, idx, label, parent=None, acq_thread=None):
        super().__init__(parent)
    
        # Exposure limits (define valid range)
        self.exposure_min = 1  # Minimum exposure time in milliseconds
        self.exposure_max = 1000  # Maximum exposure time in milliseconds

        # Default Camera Parameters
        self.width_x = 2048  # Default image width
        self.height_y = 2048  # Default image height
        self.sensor_mode = 1  # Default sensor mode
        self.readout_direction = 1  # Default readout direction (e.g., Top-to-bottom)
        self.dynamic_range = 16  # Default dynamic range (bits)
        self.binning = 1
        self.exposure_time = 10.0  # Default exposure time in milliseconds


        # Initialize acquisition thread
        if acq_thread:
            self.acquisition_thread = acq_thread

        # Initialize Camera Control & Feedback Threads
        self.control_thread = CameraControlThread(self.acquisition_thread)
        self.control_thread.update_signal.connect(self.handle_update_signal)  # This line should now work correctly.
        self.control_thread.start()


        self.feedback_thread = CameraFeedbackThread(self.acquisition_thread)
        self.feedback_thread.fps_signal.connect(self.update_framerate)
        self.feedback_thread.exposure_signal.connect(self.update_exposure)
        self.feedback_thread.roi_signal.connect(self.update_roi)
        self.feedback_thread.start()

        self.idx = idx
        self.label = label
        self.setupUi()

        # Timer to update the Framerate in UI every second
        self.framerate_timer = QTimer(self)
        self.framerate_timer.timeout.connect(self.update_framerate_from_feedback)
        self.framerate_timer.start(1000)  # Update every 1 second

        # Timer for debouncing exposure updates from the slider
        self.exposure_update_timer = QTimer(self)
        self.exposure_update_timer.setSingleShot(True)
        self.exposure_update_timer.setInterval(600)  # Debounce time in ms
        self.exposure_update_timer.timeout.connect(self.apply_exposure_update)

        # Timer to ignore exposure feedback for a short period after user input
        self.ignore_exposure_feedback_timer = QTimer(self)
        self.ignore_exposure_feedback_timer.setSingleShot(True)  # Only triggers once per user action
        self.ignore_exposure_feedback_timer.setInterval(1200)  # Ignore feedback for 1.2 seconds

        # True while an acquisition is running and the acquisition thread owns camera configuration.
        self.acquisition_guard = False

        self.mode_change_locked = False




    ############################################################################################################
    # Camera Functions

    def acquisition_thread(self):
        return self.acquisition_thread

    def change_framerate_update(self):
        "Get and insert the Frame Rate"
        self.fps_value = self.acquisition_thread.get_framerate()
        self.framerate.setText(f"{self.fps_value:.1f} /s")

    def change_format(self, text):
        """Change the picture format (ROI) asynchronously when the user inputs a value."""

        # Do not allow ROI changes while an acquisition owns the camera.
        if self.acquisition_guard:
            print("[Camera Widget] ROI change ignored during acquisition.")
            return

        width, height = separate_numbers(text)
        self.control_thread.update_camera_parameter("change_ROI", width, height, self.binning)
        self.format_lineedit.clearFocus()
        self.format_combobox.clearFocus()


    def change_format_selection(self, text):
        """Change the format of the picture when selecting from the dropdown."""
        for i in range(self.format_combobox.count()):
            if text == self.format_combobox.itemText(i):
                width, height = separate_numbers(text)

                # Immediately send the new ROI value to the camera
                self.control_thread.update_camera_parameter("change_ROI", width, height)

                # Force the combobox to lose focus after selection
                self.format_combobox.clearFocus()


    def change_sensor_mode_selection(self, text):
        """
        Change the camera sensor mode asynchronously.
        """
        if self.acquisition_guard:
            logger.warning(
                "Camera mode change ignored during acquisition: requested_mode=%s, camera_index=%s",
                text,
                self.idx,
            )
            return

        if self.mode_change_locked:
            logger.warning(
                "Camera mode change blocked because scanner is active: requested_mode=%s, camera_index=%s",
                text,
                self.idx,
            )
            return

        mode_map = {
            "Internal Trigger": 1,
            "Widefield Mode": 2,
            "Confocal Mode": 3,
        }

        self.sensor_mode = mode_map.get(text, 1)
        self._last_requested_camera_mode_text = text
        self.control_thread.update_camera_parameter("change_sensor_mode", self.sensor_mode)



    def change_binning_selection(self, text):
        """Change the camera binning asynchronously."""

        if self.acquisition_guard:
            print("[Camera Widget] Binning change ignored during acquisition.")
            return

        binning_map = {"1 x 1": 1, "2 x 2": 2, "4 x 4": 4}
        self.binning = binning_map.get(text, 1)
        self.control_thread.update_camera_parameter("change_binning", self.width_x, self.height_y, self.binning)


    def change_dynamicrange_selection(self, text):
        """Change the camera's dynamic range asynchronously."""
        
        if self.acquisition_guard:
            print("[Camera Widget] Dynamic range change ignored during acquisition.")
            return

        range_map = {"16 Bits": 16, "12 Bits": 12, "8 Bits": 8}
        self.dynamic_range = range_map.get(text, 16)  # Store new value

        # Update the camera asynchronously
        self.control_thread.update_camera_parameter("change_dynamic_range", self.dynamic_range)


    def apply_exposure_update(self):
        """Update the camera's exposure time after the debounce timer finishes."""

        if self.acquisition_guard:
            print("[Camera Widget] Exposure update ignored during acquisition.")
            return

        if self.pending_exposure_value is not None:
            self.exposure_time = self.pending_exposure_value  # Store new value
            exposure_seconds = self.exposure_time / 1000.0

            # Update the camera asynchronously
            self.control_thread.update_camera_parameter("change_exposure_time", exposure_seconds)



    def current_exposure(self):
        "returns the current exposure time of the camera in ms"
        return (self.acquisition_thread.camera.get_attribute_value("EXPOSURE TIME") * 1000)

    def checkbox_camera_select(self):
        "returns the selection of the camera and the camera's chosen properties at the selection time"

        if self.camera_checkbox.isChecked():
            # print(self.label + "\n",
            #     f"Format - {self.width_x} x {self.height_y}\n",
            #     f"Sensor Mode - {self.sensor_mode}\n",
            #     f"Dynamic Range - {self.dynamic_range} Bits\n",
            #     f"Binning - {self.binning} x {self.binning}\n",
            #     f"Exposure Time - {self.exposure_time}"
            #     )
            return (self.width_x, self.height_y, self.binning, self.dynamic_range)

        else:
            return None, None, None, None


    @Slot(float)
    def update_framerate(self, fps):
        """Update the displayed framerate."""
        self.framerate.setText(f"{fps:.1f} /s")
        self.fps_value = fps

    @Slot(float)
    def update_exposure(self, exposure):
        """Update the exposure time in the UI, but only if the user is not actively setting a value."""
        if not self.exposuretime_lineedit.hasFocus() and not self.exposure_update_timer.isActive() and not self.ignore_exposure_feedback_timer.isActive():
            self.exposuretime_lineedit.setText(f"{exposure:.6f}")


    @Slot(int, int)
    def update_roi(self, width, height):
        """Update the displayed ROI values and store them for checkbox selection."""
        if not self.format_lineedit.hasFocus():
            self.format_lineedit.setText(f"{width} x {height}")

        # Store the new width & height
        self.width_x = width
        self.height_y = height

        # Convert from pixels to mm using pixel size (0.65 µm = 0.00065 mm)
        width_mm = width * 0.00065
        height_mm = height * 0.00065

        # Update the imagesize QLabel
        self.imagesize.setText(f"{width_mm:.4f} mm × {height_mm:.4f} mm")

    def _camera_name(self) -> str:
        """
        Return the human-readable camera name used in logs.

        Project-specific mapping:
        - camera_index 0 -> Camera 2
        - camera_index 1 -> Camera 1
        """
        camera_map = {
            0: "Camera 2",
            1: "Camera 1",
        }

        return camera_map.get(self.idx, f"Camera index {self.idx}")



    @Slot(str)
    def handle_update_signal(self, message):
        """
        Handle update messages from CameraControlThread.

        Log camera mode changes only when the control thread confirms success.
        """

        threading.current_thread().name = "CAMERA"

        camera_name = self._camera_name()


        if message == "change_sensor_mode updated successfully.":
            logger.info(
                "Camera mode changed successfully: %s, mode=%s",
                camera_name,
                getattr(self, "_last_requested_camera_mode_text", "Unknown"),
            )
        elif message.startswith("Error updating change_sensor_mode"):
            logger.error(
                "Camera mode change failed: %s, requested_mode=%s, error=%s",
                camera_name,
                getattr(self, "_last_requested_camera_mode_text", "Unknown"),
                message,
            )

    
    @Slot()
    def apply_parameters_after_ystack(self):
        """Re-applies all of the Camera parameters to the Camera"""

        if self.camera_checkbox.isChecked():

            format = self.format_lineedit.text()
            width, height = separate_numbers(format)
            binning = self.binning 

            self.control_thread.update_camera_parameter("change_ROI", width, height, binning)
            self.control_thread.update_camera_parameter("change_binning", self.width_x, self.height_y, self.binning)
            self.control_thread.update_camera_parameter("change_sensor_mode", self.sensor_mode)
            self.control_thread.update_camera_parameter("change_dynamic_range", self.dynamic_range)

            
            # Re-apply exposure for the modes where exposure is user-controlled.
            # Internal Trigger = 1
            # Rolling Shutter Mode = 3

            if self.sensor_mode in (1,3):
                exp_ms = float(self.exposuretime_lineedit.text())
                exp_s = exp_ms / 1000
                self.control_thread.update_camera_parameter("change_exposure_time", exp_s)

            self.acquisition_thread.camera.stop_acquisition()
            self.acquisition_thread.camera.clear_acquisition()
            time.sleep(2)

            self.live_button.setChecked(False)
            self.live_button.setText("Live")
            self.snap_button.setEnabled(False)
            self.restart_button.setEnabled(True)

            # In case I want to turn the camera ON after acquisition
            #time.sleep(2)

            # self.live_button.setChecked(True)
            # self.live_button.setText("Stop")
            # self.snap_button.setEnabled(True)
            # self.restart_button.setEnabled(False)

        else: pass

    def set_acquisition_guard(self, enabled: bool):
        """
        Prevent UI-driven camera reconfiguration while an acquisition is running.

        Live preview may continue to read frames, but no parameter-changing command
        should be sent to the camera during acquisition.
        """
        self.acquisition_guard = enabled


    def update_framerate_from_feedback(self):
        """Update the framerate display using the last received FPS value."""
        self.framerate.setText(f"{self.fps_value:.1f} /s")

    def shutdown(self):
        """Clean shutdown of all camera-related threads and timers."""
        self.control_thread.stop()
        self.feedback_thread.stop()

        self.framerate_timer.stop()
        self.exposure_update_timer.stop()
        self.ignore_exposure_feedback_timer.stop()

        try:
            self.acquisition_thread.stop_acquisition()
            time.sleep(0.1)
            self.acquisition_thread.camera.clear_acquisition()
            time.sleep(0.1)
            self.acquisition_thread.camera.close()
        except Exception as e:
            print(f"[Camera Shutdown Error] {e}")


    def closeEvent(self, event):
        self.shutdown()
        event.accept()

    #-------------------------------------------------------------------------------------------
    # Set Exposure in Confocal Mode

    def set_exposure_programmatically(self, exposure_ms: float, apply_to_camera: bool = True) -> None:
        """
        Update the exposure UI from code without creating a feedback loop.
        Optionally apply the value to the physical camera.
        """
        exposure_ms = max(self.exposure_min, min(self.exposure_max, float(exposure_ms)))

        with QSignalBlocker(self.exposuretime_slider):
            slider_value = self.log_to_linear(
                exposure=exposure_ms,
                slider_min=1,
                slider_max=1000,
                exposure_min=self.exposure_min,
                exposure_max=self.exposure_max,
            )
            self.exposuretime_slider.setValue(int(slider_value))

        with QSignalBlocker(self.exposuretime_lineedit):
            self.exposuretime_lineedit.setText(f"{exposure_ms:.6f}")

        self.pending_exposure_value = exposure_ms

        if apply_to_camera and not self.acquisition_guard:
            self.exposure_time = exposure_ms
            exposure_seconds = exposure_ms / 1000.0
            self.control_thread.update_camera_parameter("change_exposure_time", exposure_seconds)



    ############################################################################################################
    # GUI Behaviour Functions

    def enableExpandingLineEdit(self):
        self.exposuretime_lineedit.setMinimumWidth(80)
        self.exposuretime_lineedit.setMaximumWidth(16777215)  # Qt's default maximum width
        self.exposuretime_lineedit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.exposuretime_lineedit.updateGeometry()

    def cameramode_behaviour(self):
        """Determines the behaviour of the remaining UI given the Camera Mode"""

        if self.cameramode_combobox.currentText() == "Internal Trigger":
            self.binning_combobox.setEnabled(True)
            self.exposure_min = 1
            self.exposure_max = 1000
            self.exposuretime_slider.setValue(self.log_to_linear(exposure = self.current_exposure(), slider_min = 1, slider_max = 1000, exposure_min = self.exposure_min, exposure_max = self.exposure_max ))
            self.exposuretime_lineedit.setEnabled(True)
            self.exposuretime_slider.setEnabled(True)

        elif self.cameramode_combobox.currentText() == "Widefield Mode":
            self.binning_combobox.setEnabled(True)
            self.exposure_min = 1
            self.exposure_max = 1000
            self.exposuretime_slider.setValue(self.log_to_linear(exposure = self.current_exposure(), slider_min = 1, slider_max = 1000, exposure_min = self.exposure_min, exposure_max = self.exposure_max ))
            self.exposuretime_lineedit.setDisabled(True)
            self.exposuretime_slider.setDisabled(True)


        elif self.cameramode_combobox.currentText() == "Confocal Mode":
            # Disable binning in rolling shutter mode.
            self.binning_combobox.setEnabled(False)

            # Define the valid exposure range for rolling shutter mode.
            self.exposure_min = 1
            self.exposure_max = 20

            # IMPORTANT:
            # Re-enable the exposure controls explicitly because they may have been
            # disabled previously when the user was in Widefield Mode.
            self.exposuretime_lineedit.setEnabled(True)
            self.exposuretime_slider.setEnabled(True)

            # Update the slider position using the current camera exposure.
            self.exposuretime_slider.setValue(
                self.log_to_linear(
                    exposure=self.current_exposure(),
                    slider_min=1,
                    slider_max=20,
                    exposure_min=self.exposure_min,
                    exposure_max=self.exposure_max
                )
            )

    
    def exposure_lineedit_behaviour(self):
        """Apply exposure time when the user presses Enter in the LineEdit."""
        try:
            value = float(self.exposuretime_lineedit.text())

            # Ensure value is within valid range
            value = max(self.exposure_min, min(self.exposure_max, value))

            slider_value = self.log_to_linear(
                exposure=value,
                slider_min=1, slider_max=1000,
                exposure_min=self.exposure_min, exposure_max=self.exposure_max
            )
            self.exposuretime_slider.setValue(int(slider_value))

            # Apply new exposure to camera (debounced)
            self.pending_exposure_value = value
            self.exposure_update_timer.start()

            self.exposuretime_lineedit.setText(f"{value}")

            # Notify that the user changed exposure manually
            self.exposure_changed_by_user.emit(value, self.idx)

        except ValueError:
            print("[ERROR] Invalid exposure time input")



    def exposure_slider_behaviour(self):
        """Debounce exposure updates when the slider is moved and temporarily ignore camera feedback."""
        value = self.linear_to_log(
            slider_value=self.exposuretime_slider.value(),
            slider_min=1, slider_max=1000,
            exposure_min=self.exposure_min, exposure_max=self.exposure_max
        )

        self.exposuretime_lineedit.setText(f"{value:.6f}")
        self.ignore_exposure_feedback_timer.start()

        self.pending_exposure_value = value
        self.exposure_update_timer.start()

        # Notify that the user changed exposure manually
        self.exposure_changed_by_user.emit(value, self.idx)


    def linear_to_log(self, slider_value, slider_min=1, slider_max=1000, exposure_min=0.0097, exposure_max=0.5):
        # Normalize the slider value between 0 and 1.
        norm = (slider_value - slider_min) / (slider_max - slider_min)
        # Compute the logarithmic bounds for the exposure range.
        log_min = np.log10(exposure_min)
        log_max = np.log10(exposure_max)
        # Map the normalized value to the logarithmic range.
        log_val = norm * (log_max - log_min) + log_min
        # Return the corresponding exposure value.
        return 10 ** log_val

    def log_to_linear(self, exposure, slider_min=1, slider_max=1000, exposure_min=0.0097, exposure_max=0.5):
        # Compute the logarithmic bounds for the exposure range.
        log_min = np.log10(exposure_min)
        log_max = np.log10(exposure_max)
        # Normalize the log of the exposure value.
        norm = (np.log10(exposure) - log_min) / (log_max - log_min)
        # Map the normalized value back to the slider's range.
        slider_value = slider_min + norm * (slider_max - slider_min)
        return slider_value
    
    def live_button_behaviour(self):
        if self.live_button.isChecked():
            self.snap_button.setEnabled(True)
            self.restart_button.setEnabled(False)
            self.live_button.setText("Stop")

        else:
            self.snap_button.setEnabled(False)
            self.restart_button.setEnabled(True)
            self.live_button.setText("Live")

    def _enable_format_once(self, checked):
        if checked:
            self.format_combobox.setEnabled(True)
            # now that it’s on, don’t ever disable it again:
            #self.live_button.toggled.disconnect(self._enable_format_once)


    def restart_button_behaviour(self):
        """Makes all of the remaining UI go back to the default parameters"""
        
        for cb in (
            self.format_combobox,
            self.binning_combobox,
            self.dynamicrange_combobox,
            self.cameramode_combobox,
        ):
            with QSignalBlocker(cb):
                cb.setCurrentIndex(0)

        self.imagesize.setText("1.3312 mm × 1.3312 mm")
        self.format_combobox.setDisabled(True)

    def set_mode_change_locked(self, locked: bool) -> None:
        """
        Lock/unlock the Camera Mode combobox.

        When locked=True the user cannot change the camera acquisition mode.
        This is typically used while the scanner is actively running during Live.
        """
        self.mode_change_locked = locked
        self.cameramode_combobox.setDisabled(locked)



    ############################################################################################################
    # GUI Setup

    def setupUi(self):
        #-----------------------------------------------------------------
        # GUI first steps

        # Initialize the tooltip manager (use self as parent)
        self.tooltip_manager = CustomToolTipManager(self)

        # Create the main layout for this widget
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(0)


        self.grid_widget = QWidget(self)
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_widget.setContentsMargins(0, 0, 0, 0)

        # 0th Line - Camera Label
        self.camera_label = QLabel(self.label)
        self.camera_label.setStyleSheet("QLabel { font-weight: bold; font-size: 16px; }")

        # Get the icon
        script_path = Path(__file__).resolve()
        icon_path   = script_path.parent / "icons" / "check.png"

        self.camera_checkbox = QCheckBox(" Select Camera")
        self.tooltip_manager.attach_tooltip(self.camera_checkbox, f"Selects {self.label[:-1]} with the\nparameters chosen below.")

        self.camera_checkbox.setStyleSheet(f"""
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
                image: url("{icon_path.as_posix()}");  /* Now interpolated */
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
        self.camera_checkbox.toggled.connect(self.checkbox_camera_select)

            
        
        self.grid_layout.addWidget(self.camera_label, 0, 0, alignment=Qt.AlignLeft)
        self.grid_layout.addWidget(self.camera_checkbox, 0, 1, alignment=Qt.AlignRight)

        #-----------------------------------------------------------------
        # 1st Line - Format

        self.format_label = QLabel("Format: ")
        self.format_combobox = QComboBox()
        self.format_combobox.addItems(["2048 x 2048", "1600 x 1600", "1024 x 1024", "512 x 512"])
        self.format_combobox.setEditable(True)
        self.format_combobox.setInsertPolicy(QComboBox.NoInsert)
        self.format_combobox.setEnabled(False)

        self.format_lineedit = self.format_combobox.lineEdit()
        #self.format_combobox.currentTextChanged.connect(lambda text: self.change_format(text))
        self.format_combobox.activated[int].connect(
            lambda index: self.change_format(self.format_combobox.itemText(index))
        )        
        self.format_lineedit.returnPressed.connect(lambda: self.change_format(self.format_lineedit.text()))

        self.grid_layout.addWidget(self.format_label, 1, 0, alignment=Qt.AlignRight)
        self.grid_layout.addWidget(self.format_combobox, 1, 1)

        #-----------------------------------------------------------------
        # 2nd Line - Binning

        self.binning_label = QLabel("Binning: ")
        self.binning_combobox = QComboBox()
        self.binning_combobox.addItems(["1 x 1", "2 x 2", "4 x 4"])
        self.binning_combobox.setEditable(False)
        self.binning_combobox.setEnabled(True)
        self.binning_combobox.currentTextChanged.connect(lambda text: self.change_binning_selection(text))

        self.grid_layout.addWidget(self.binning_label, 2, 0, alignment=Qt.AlignRight)
        self.grid_layout.addWidget(self.binning_combobox, 2, 1)

        #-----------------------------------------------------------------
        # 3rd Line - Dynamic Range

        self.dynamicrange_label = QLabel("Dynamic Range: ")
        self.dynamicrange_combobox = QComboBox()
        self.dynamicrange_combobox.addItems(["16 Bits", "8 Bits"])
        self.dynamicrange_combobox.setEditable(False)
        self.dynamicrange_combobox.currentTextChanged.connect(lambda text: self.change_dynamicrange_selection(text))

        self.grid_layout.addWidget(self.dynamicrange_label, 3, 0, alignment=Qt.AlignRight)
        self.grid_layout.addWidget(self.dynamicrange_combobox, 3, 1)

        #-----------------------------------------------------------------
        # 4th Line - Camera Mode

        self.cameramode_label = QLabel("Camera Mode: ")
        self.cameramode_combobox = QComboBox()
        self.cameramode_combobox.addItems(["Internal Trigger", "Widefield Mode", "Confocal Mode"])
        self.cameramode_combobox.setEditable(False)
        self.cameramode_combobox.currentTextChanged.connect(lambda text: self.change_sensor_mode_selection(text))
        self.cameramode_combobox.currentIndexChanged.connect(self.cameramode_behaviour) 
        # Notify scanner when the camera mode changes
        if self.parent() is not None and hasattr(self.parent(), "scanner_widget"):
            self.cameramode_combobox.currentTextChanged.connect(
                self.parent().scanner_widget._camera_mode_changed
            )
        self.tooltip_manager.attach_tooltip(
            self.cameramode_combobox,
            """Chooses the Camera's acquisition mode:
        Internal Trigger - continuous acquisition
        Widefield Mode - external-trigger global shutter acquisition of the light sheet
        Confocal Mode - external-trigger rolling shutter acquisition of the light sheet"""
        )


        self.grid_layout.addWidget(self.cameramode_label, 4, 0, alignment=Qt.AlignRight)
        self.grid_layout.addWidget(self.cameramode_combobox, 4, 1)

        #-----------------------------------------------------------------
        # 5th Line - Exposure Time

        self.exposuretime_label = QLabel("Exposure Time: ")
        self.exposuretime_widget = QWidget()
        self.exposuretime_layout = QHBoxLayout(self.exposuretime_widget)
        self.exposuretime_layout.setContentsMargins(0, 0, 0, 0)
        self.exposuretime_layout.setSpacing(5)

        self.exposuretime_lineedit = CustomLineEdit()
        self.exposuretime_lineedit.setFixedWidth(80)
        self.exposuretime_lineedit.setFixedHeight(21)
        self.exposuretime_lineedit.editingFinished.connect(self.exposure_lineedit_behaviour)
        self.exposuretime_lineedit.returnPressed.connect(self.exposuretime_lineedit.clearFocus)
        QTimer.singleShot(0, self.enableExpandingLineEdit)

        self.exposuretime_lineedit.setText("10.0000")

        self.exposuretime_lineeditms = QLabel("ms")
        self.exposuretime_lineeditms.setTextFormat(Qt.TextFormat.RichText)
        self.exposuretime_layout.addWidget(self.exposuretime_lineedit)
        self.exposuretime_layout.addWidget(self.exposuretime_lineeditms)

        self.grid_layout.addWidget(self.exposuretime_label, 5, 0, alignment=Qt.AlignRight)
        self.grid_layout.addWidget(self.exposuretime_widget, 5, 1)

        #-----------------------------------------------------------------
        # 6th Line - Exposure Horizontal Slider

        self.exposuretime_slider = QSlider(Qt.Horizontal)
        self.exposuretime_slider.setMinimum(1)
        self.exposuretime_slider.setMaximum(1000)
        self.exposuretime_slider.setValue(self.log_to_linear(exposure = 10, slider_min = 1, slider_max = 1000, exposure_min = 1, exposure_max = 1000 ))
        #h = self.exposuretime_slider.sizeHint().height()
        self.exposuretime_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.exposuretime_slider.setFixedHeight(20)


        self.exposuretime_slider.valueChanged.connect(self.exposure_slider_behaviour)

        self.grid_layout.addWidget(self.exposuretime_slider, 6, 1)

        #-----------------------------------------------------------------
        # 7th Line - Image Size

        self.imagesize_label = QLabel("Image Size: ")
        self.imagesize = QLabel("1.3312 mm × 1.3312 mm")
        self.imagesize.setTextFormat(Qt.TextFormat.RichText)
        self.grid_layout.addWidget(self.imagesize_label, 7, 0, alignment=Qt.AlignRight)
        self.grid_layout.addWidget(self.imagesize, 7, 1, alignment=Qt.AlignRight)

        #-----------------------------------------------------------------
        # 8th Line - Pixel Size

        self.pixelsize_label = QLabel("Pixel Size: ")
        self.pixelsize = QLabel("0.65 μm × 0.65 μm")
        self.pixelsize.setTextFormat(Qt.TextFormat.RichText)
        self.grid_layout.addWidget(self.pixelsize_label, 8, 0, alignment=Qt.AlignRight)
        self.grid_layout.addWidget(self.pixelsize, 8, 1, alignment=Qt.AlignRight)

        #-----------------------------------------------------------------
        # 9th Line - Frame Rate

        self.framerate_label = QLabel("Frame Rate: ")
        self.framerate = QLabel()
        self.grid_layout.addWidget(self.framerate_label, 9, 0, alignment=Qt.AlignRight)
        self.grid_layout.addWidget(self.framerate, 9, 1, alignment=Qt.AlignRight)


        # self.grid_layout.addWidget(self.live_button, 10, 0, alignment=Qt.AlignCenter)
        # self.grid_layout.addWidget(self.snap_button, 10, 1, alignment=Qt.AlignCenter)


        self.main_layout.addWidget(self.grid_widget)

        #-----------------------------------------------------------------
        # 10th Line - Live and Snap Buttons

        self.live_button = QPushButton("Live")
        self.live_button.setFixedHeight(35)
        self.live_button.setFixedWidth(90)
        self.live_button.setCheckable(True)
        self.live_button.clicked.connect(self.live_button_behaviour)
        self.live_button.toggled.connect(self.live_toggled.emit)
        # Notify scanner whenever Live is toggled
        if self.parent() is not None and hasattr(self.parent(), "scanner_widget"):
            self.live_toggled.connect(self.parent().scanner_widget._camera_live_state_changed)
        self.live_button.toggled.connect(self._enable_format_once)
        self.live_button.setStyleSheet("""
                        QPushButton {
                            background-color: #252525;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 8px;
                            padding: 0px 16px;
                            font-size: 15px;
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
        """)

        self.snap_button = QPushButton("Snap")
        self.snap_button.setFixedHeight(35)
        self.snap_button.setFixedWidth(90)
        self.snap_button.setDisabled(True)
        self.snap_button.clicked.connect(self.snap_clicked.emit)
        self.snap_button.setStyleSheet("""
                        QPushButton {
                            background-color: #252525;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 8px;
                            padding: 0px 16px;
                            font-size: 15px;
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
        """)


            # Adding the buttons to the horizontal box layout
        self.buttons_widget = QWidget()
        self.buttons_layout = QHBoxLayout(self.buttons_widget)
        self.buttons_layout.setContentsMargins(0,0,0,0)
        self.buttons_layout.addWidget(self.live_button, alignment=Qt.AlignTop)
        self.buttons_layout.addWidget(self.snap_button, alignment=Qt.AlignTop)
            # Adding the button's widget to the main layout
        self.main_layout.addWidget(self.buttons_widget)

        #-----------------------------------------------------------------
        # 10th Line - Restart Camera Button

        self.restart_button = QPushButton(f"Restart {self.label[:-1]}")
        self.restart_button.setFixedHeight(34)
        self.restart_button.setFixedWidth(205)
        self.restart_button.clicked.connect(self.restart_clicked.emit)
        self.restart_button.clicked.connect(self.restart_button_behaviour)
        self.restart_button.setStyleSheet("""
                        QPushButton {
                            background-color: #252525;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 8px;
                            padding: 0px 16px;
                            font-size: 15px;
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
        """)
        
        self.main_layout.addSpacing(10)
        self.main_layout.addWidget(self.restart_button, alignment=Qt.AlignCenter)

        #-----------------------------------------------------------------
        # Finalizing the Camera Widget

        self.grid_layout.setVerticalSpacing(5)
        #self.setMaximumHeight(400)
        self.setFixedHeight(350)

        # Get the icons
        script_path = Path(__file__).resolve()
        icon_path_1   = script_path.parent / "icons" / "button_down.png"
        icon_path_2   = script_path.parent / "icons" / "button_down_disabled.png"

        self.setStyleSheet(f"""
            QWidget {{ 
                background-color: #303030;  /* Dark background */
            }}
                                                 
            QLabel {{
                color: white;  /* White text */
            }}
            /* ----------- QComboBox ----------- */
                                     
            QComboBox {{
                background-color: #252525;  
                color: white;
                border: 1px solid #444444;
                border-radius: 3px;
            }}

            QComboBox QAbstractItemView {{
                background-color: #272727;
                color: white;
                selection-background-color: #555555;
            }}

            QComboBox::drop-down {{
                width: 20px;
                background-color: #444444;
                border-left: 1px solid #555555;
            }}

            /* Drop-down Arrow */
            QComboBox::down-arrow {{
                image: url("{icon_path_1.as_posix()}");
                width: 12px;
                height: 12px;
            }}

            /* Disabled QComboBox */
            QComboBox:disabled {{
                background-color: #303030;  /* Darker background to indicate it's disabled */
                color: #777777;  /* Dimmed text */
                border: 1px solid #444444;  /* Less prominent border */
            }}

            QComboBox::drop-down:disabled {{
                background-color: #303030;  /* Match the background */
                border-left: 1px solid #333333;  /* Subtler border */
            }}

            QComboBox::down-arrow:disabled {{
                image: url("{icon_path_2.as_posix()}");
                width: 12px;
                height: 12px;
            }}

            /* ----------- QLineEdit ----------- */
            QLineEdit {{
                background-color: #272727;  /* Fix background */
                color: white;  /* Ensure white text */
                border: 1px solid #555555;  /* Darker border */
                padding: 4px;  /* Ensure spacing inside */
                border-radius: 3px;  /* Smooth rounded corners */
                selection-background-color: #0078d7;  /* Fix text selection */
            }}

            QLineEdit:focus {{
                border: 1px solid #888888;  /* Highlight when focused */
                background-color: #444444;  /* Slightly lighter when active */
            }}

            QLineEdit:disabled {{
                background-color: #303030;  /* Darker background to show it's disabled */
                color: #777777;  /* Dimmed text color */
                border: 1px solid #444444;  /* Less prominent border */
            }}

            /* Force disable native styles that Qt might be using */
            QLineEdit, QLineEdit:focus, QLineEdit:disabled {{
                outline: none;
            }}
        """)
        
        QMetaObject.connectSlotsByName(self)