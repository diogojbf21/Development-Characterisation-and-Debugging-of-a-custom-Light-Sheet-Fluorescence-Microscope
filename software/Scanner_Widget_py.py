# Imports from libraries
from PySide6.QtCore import Qt, QMetaObject, QTimer, QRect, QThread, QEventLoop, QSignalBlocker, QLocale
from PySide6.QtGui import QIntValidator, QColor, QDoubleValidator
from PySide6.QtWidgets import (QApplication, QLabel, QLineEdit, QMainWindow,
    QPushButton, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGraphicsDropShadowEffect, QSlider, QCheckBox)
from PySide6.QtCore import Slot
from superqt import QRangeSlider
import sys

# Imports from my code
from Extra_Files.ToolTip_Manager import CustomToolTipManager
from Extra_Files.Scanner_Stylesheet import StyleSheets
from Extra_Files.Custom_Line_Edit import CustomLineEdit


import ctypes
import os
import csv
from datetime import datetime
import numpy as np
import time
from pathlib import Path

import sys
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import QThread, Signal, Slot, QObject

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import QThread, Signal, Slot, QObject, QTimer

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtCore import QThread, Signal, QObject, QTimer

#Logger
import logging
import threading
# Reuse the main application logger
logger = logging.getLogger("ALM")



class BeamWorker(QThread):
    beam_moved = Signal(int)  # Signal emitted when beam movement is complete
    finished = Signal()  # Signal emitted when the thread should stop

    def __init__(self, rtc5_board, ui):
        super().__init__()
        self.rtc5_board = rtc5_board
        self.ui = ui
        self._stop = False

    def move_beam(self, pos):
        """ Moves the beam to the specified position. """
        self.stop()  # Ensure no interference from the lightsheet process
        self.ui.move_beam_to(pos)
        self.beam_moved.emit(pos)

    def run(self):
        self._stop = False
        first_loop = True

        while not self._stop:
            Xtop = int(self.ui.lineedit_2.text())
            Xbottom = int(self.ui.lineedit_3.text())
            speed = float(self.ui.lineedit_1.text())

            if first_loop:
                self.ui.jump_top(Xtop)
                first_loop = False
            else:
                self.ui.mark_toptobottom(Xtop, Xbottom, speed)

        #loop that checks if the Scanner is marking, and only then emits the signal
        status = ctypes.c_uint()
        position = ctypes.c_int()
        while True:
            self.rtc5_board.get_status(ctypes.byref(status), ctypes.byref(position))
            busy         = bool(status.value & 0x00000001)  # BUSY bit
            internalBusy = bool(status.value & 0x00008000)  # INTERNAL-BUSY bit
            if not (busy or internalBusy):
                break
            time.sleep(0.001)

        self.finished.emit()

    def stop(self):
        """ Stops the marking process immediately. """
        self._stop = True


class LightsheetWorker(QThread):
    """
    Dedicated worker that continuously executes the light-sheet list.
    """

    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self._stop_requested = False

    def request_stop(self):
        """Ask the loop to stop. The worker will stop after the current list finishes."""
        self._stop_requested = True

    def run(self):
        """
        Start the Widefield LightSheet worker.

        Logging policy:
        - Log once when the worker really starts the LightSheet.
        - Do not log every sweep inside the continuous loop.
        """

        threading.current_thread().name = "SCANNER"

        self._stop_requested = False

        try:
            # Read the initial scanner parameters from the UI
            xtop = int(self.ui.lineedit_2.text())
            xbottom = int(self.ui.lineedit_3.text())
            speed = float(self.ui.lineedit_1.text())
        except Exception:
            logger.error("Failed to start Widefield LightSheet: invalid top/bottom/speed values.")
            return

        # Log the real LightSheet start only once
        logger.info(
            "Make LightSheet started (Widefield): top=%s, bottom=%s, speed=%s",
            xtop,
            xbottom,
            speed,
        )

        while not self._stop_requested:
            # Re-read UI parameters each cycle if live updates are allowed
            try:
                xtop = int(self.ui.lineedit_2.text())
                xbottom = int(self.ui.lineedit_3.text())
                speed = float(self.ui.lineedit_1.text())
            except Exception:
                # Invalid UI values -> stop safely
                break

            self.ui.mark_toptobottom(
                Xtop=xtop,
                Xbottom=xbottom,
                speed=speed,
                dwell_ms=self.ui._ls_dwell_ms,
            )

            while self.ui._scanner_is_busy():
                if self._stop_requested:
                    continue
                time.sleep(0.001)

        
        # Log only when the worker has actually stopped
        logger.info("LightSheet stopped (Widefield).")



class RollingShutterWorker(QThread):
    """
    Dedicated worker that continuously executes the rolling shutter sweep.
    """

    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self._stop_requested = False

    def request_stop(self):
        """Ask the worker to stop after the current RTC list finishes."""
        self._stop_requested = True

    def run(self):
        """
        Start the Confocal / Rolling Shutter LightSheet worker.

        Logging policy:
        - Log once when the worker really starts the rolling-shutter LightSheet.
        - Do not log every sweep inside the continuous loop.
        """

        threading.current_thread().name = "SCANNER"

        self._stop_requested = False

        try:
            # Read the initial scanner parameters from the UI
            xtop = int(self.ui.lineedit_2.text())
            xbottom = int(self.ui.lineedit_3.text())
            speed = float(self.ui.lineedit_1.text())
        except Exception:
            logger.error("Failed to start Confocal LightSheet: invalid top/bottom/speed values.")
            return

        # Log the real LightSheet start only once
        logger.info(
            "Make LightSheet started (Confocal): top=%s, bottom=%s, speed=%s",
            xtop,
            xbottom,
            speed,
        )

        while not self._stop_requested:
            try:
                xtop = int(self.ui.lineedit_2.text())
                xbottom = int(self.ui.lineedit_3.text())
                speed = float(self.ui.lineedit_1.text())
            except Exception:
                break

            self.ui.mark_toptobottom_rs(
                Xtop=xtop,
                Xbottom=xbottom,
                speed=speed,
            )

            while self.ui._scanner_is_busy():
                if self._stop_requested:
                    continue
                time.sleep(0.001)


        # Log only when the worker has actually stopped
        logger.info("LightSheet stopped (Confocal).")


class Scanner_Widget(QWidget):

    scanner_speed_changed_by_user = Signal(float)

    #-------------------------------------------------------------------------------------
    # Initialization

    def __init__(self, device, parent=None):
        super().__init__(parent)

        try:
            # Keep a stable reference to the main window.
            # IMPORTANT: this widget will be re-parented into a FloatingWidget,
            # so self.parent() will no longer be the main window later.
            self._main_window = parent


            self._update_in_progress = False
            self.lightsheet_running = False

            # Global Variables
            self.z_top = 2950
            self.z_bottom = -2500
            self.range_top = 4000
            self.range_bottom = -4000
            self.lightsheet_speed = 100
            self.center_beam_position = 0

            self.rtc5_board = device

            # Go to the reference
            self.rtc5_board.goto_xy(ctypes.c_int(self.center_beam_position), ctypes.c_int(0))

            self.worker = BeamWorker(self.rtc5_board, self)

            # send the position into the real mover
            #self.worker.beam_moved.connect(self.move_beam_to)
            #self.worker.finished.connect(self.on_lightsheet_stopped)

            #-----Light Sheet state----------------
            
            self._ls_running = False
            self._ls_state = "stopped"  # "need_jump_top" | "ready_to_sweep" | "at_bottom" | "stopped"
            self._ls_next_allowed_ns = 0  # monotonic time gate for dwell at bottom
            self._ls_dwell_ms = 10       # time to stay at Xbottom after each swipe (tune)
            self._ls_stop_requested = False

            
            # --- Rolling shutter state ---
            self.rolling_shutter_running = False
            self._rs_start_pending = False
            self._rs_pending_req_id = None
            self._rs_worker = None

            #----Camera Mode Provider--------

            self._camera_mode_provider = None

            # Track which camera mode the scanner is currently running with.
            # This prevents unnecessary stop/restart cycles when multiple cameras toggle Live.
            self._running_mode = None
                    
            # --- Laser gate mapping (hardware convention) ---
            # Laser 2 -> analog out 2 (DA2)
            # Laser 4 -> analog out 1 (DA1)
            self._laser_gate_on_level = 512  # "ON" value for DA outputs (adjust if needed)

            # --- Digital laser gate mapping (consistent with your comments) ---
            # Laser 3 -> Digital Out 1 -> bit0
            # Laser 5 -> Digital Out 2 -> bit1
            self._laser3_bit = 0x01
            self._laser5_bit = 0x02
            self._digital_mask_bits = self._laser3_bit | self._laser5_bit  # 0x03

            # Safety: ensure digital outputs start OFF
            if hasattr(self.rtc5_board, "set_laser_pin_out"):
                self.rtc5_board.set_laser_pin_out(0)

            self._laser_widget = None  # will be injected by main.py via set_laser_widget()


            self.setupUi()

            threading.current_thread().name = "SCANNER"

            # Log only after the scanner widget finished its initial setup successfully
            logger.info(
                "Scanner initialised successfully. Device type: %s",
                type(self.rtc5_board).__name__,
            )

        except Exception:
            logger.warning("Scanner initialisation failed.")
            raise



    def closeEvent(self, event):
        """Code to run before closing the application"""
        # Check if the thread and worker are running
        self.shutdown()
        if hasattr(self, 'thread') and self.thread.isRunning():
            if hasattr(self, 'loop'):
                self.loop.stop()  # Signal the worker to stop
            self.thread.quit()    # Ask the thread to exit
            self.thread.wait()    # Wait for the thread to finish
        event.accept()  # Accept the close event

    def shutdown(self):
        print("scanner shutdown")

    #-----------------------------------------------------------------------
    #Helpers to block change camera mode during scanner button is on

    def _iter_camera_widgets(self):
        """
        Yield available camera widgets from the main window.

        NOTE:
        The scanner widget is placed inside a FloatingWidget (QMdiSubWindow),
        so self.parent() will not reliably point to the ALM_Lightsheet main window.
        We therefore use self._main_window and also fall back to walking up the
        parent chain as a safety net.
        """
        # 1) Prefer the stored main window reference
        mw = getattr(self, "_main_window", None)

        # 2) Fallback: walk up the Qt parent chain until we find a container
        #    that has camera_widget_1 / camera_widget_2 attributes.
        if mw is None:
            p = self.parent()
            while p is not None and not hasattr(p, "camera_widget_1") and not hasattr(p, "camera_widget_2"):
                p = p.parent()
            mw = p

        if mw is None:
            return

        for attr in ("camera_widget_1", "camera_widget_2"):
            cam_widget = getattr(mw, attr, None)
            if cam_widget is not None:
                yield cam_widget


    def _update_camera_mode_lock(self) -> None:
        """
        Disable Camera Mode combobox in ALL cameras when:
        1) the scanner unified button (pushbutton_2) is checked, AND
        2) ANY camera is currently in Live mode.

        If no camera is in Live, Camera Mode remains available even if
        pushbutton_2 is checked.
        """
        scanner_button_active = self.pushbutton_2.isChecked()

        cams = list(self._iter_camera_widgets() or [])
        any_camera_live = any(cam.live_button.isChecked() for cam in cams)

        # Global lock condition requested by user:
        lock_all_camera_modes = scanner_button_active and any_camera_live

        for cam in cams:
            cam.set_mode_change_locked(lock_all_camera_modes)

        #print("[Scanner] pushbutton_2:", scanner_button_active)
        #print("[Scanner] cameras found:", len(cams))
        #print("[Scanner] any live:", any_camera_live)
        #print("[Scanner] lock_all:", lock_all_camera_modes)

    def set_main_window(self, main_window) -> None:
        """
        Store/overwrite the reference to the main application window.
        This is useful because this widget is later re-parented into a FloatingWidget.
        """
        self._main_window = main_window
    #-------------------------------------------------------------------------------------
    # Behaviour Functions

    def check_lineedit0_input(self):
        "Create the glow effect on lineedit_0 if its input is missing"
        print("signal emitted")
        if not self.lineedit_0.text():
            self.glow = QGraphicsDropShadowEffect(self.lineedit_0)
            self.glow.setColor(QColor("red"))
            self.glow.setBlurRadius(20)
            self.glow.setOffset(0)
            self.lineedit_0.setGraphicsEffect(self.glow)
        else:
            self.lineedit_0.setGraphicsEffect(None)

    def check_button2_input(self, checked):
        "Create a glow effect on the line edits if the input is missing"
        #if checked:
        if not self.lineedit_1.text():
            # Create the self.glow effect
            self.glow = QGraphicsDropShadowEffect(self.lineedit_1)
            self.glow.setColor(QColor("red"))
            self.glow.setBlurRadius(20)
            self.glow.setOffset(0)
            self.lineedit_1.setGraphicsEffect(self.glow)
            self.pushbutton_2.setChecked(False)
        else:
            self.lineedit_1.setGraphicsEffect(None)

        if not self.lineedit_2.text():
            # Create the self.glow effect
            self.glow = QGraphicsDropShadowEffect(self.lineedit_2)
            self.glow.setColor(QColor("red"))
            self.glow.setBlurRadius(20)
            self.glow.setOffset(0)
            self.lineedit_2.setGraphicsEffect(self.glow)
            self.pushbutton_2.setChecked(False)
        else:
            self.lineedit_2.setGraphicsEffect(None)

        if not self.lineedit_3.text():
                # Create the self.glow effect
            self.glow = QGraphicsDropShadowEffect(self.lineedit_3)
            self.glow.setColor(QColor("red"))
            self.glow.setBlurRadius(20)
            self.glow.setOffset(0)
            self.lineedit_3.setGraphicsEffect(self.glow)
            self.pushbutton_2.setChecked(False)
        else:
            self.lineedit_3.setGraphicsEffect(None)

            
    def lineedit_behaviour(self):
        if (self.lineedit_2.text() == str(self.z_top)) and (self.lineedit_3.text() == str(self.z_bottom)):
            self.pushbutton_1.setChecked(True)
        else:
            self.pushbutton_1.setChecked(False)
        self.doubleslider.setValue((int(float(self.lineedit_3.text())), int(float(self.lineedit_2.text()))))

    def button1_behaviour(self):
        self.pushbutton_1.setChecked(True)
        self.lineedit_2.setText(str(self.z_top))
        self.lineedit_3.setText(str(self.z_bottom))
        self.doubleslider.setValue((self.z_bottom, self.z_top))
        self.lineedit_2.repaint()
        self.lineedit_3.repaint()

    def slider_behaviour(self):
        bottom, top = self.doubleslider.sliderPosition()
        self.lineedit_2.setText(str(int(top)))
        self.lineedit_3.setText(str(int(bottom)))
        if (self.lineedit_2.text() == str(self.z_top)) and (self.lineedit_3.text() == str(self.z_bottom)):
            self.pushbutton_1.setChecked(True)
        else:
            self.pushbutton_1.setChecked(False)

    def move_beam_slider_behaviour(self):
        self.move_beam_slider.setEnabled(True)
        self.move_beam_to(self.move_beam_slider.value())
        self.lineedit_0.setText(str(self.move_beam_slider.value()))


    def lineedit0_behaviour(self):
        self.move_beam_slider.setValue(int(self.lineedit_0.text()))

    def lineedit1_speed_behaviour(self) -> None:
        """
        Handle manual scanner speed edits made by the user.

        This method validates the speed value entered in lineedit_1 and emits
        a signal so the main window can synchronize the confocal camera exposure.
        """
        try:
            speed = float(self.lineedit_1.text())

            # Reject invalid or non-positive values
            if speed <= 0:
                print("[Scanner] Invalid scanner speed value.")
                return

            # Normalize the displayed value
            self.lineedit_1.setText(f"{speed:g}")

            # Notify the main window that the user changed the scanner speed
            self.scanner_speed_changed_by_user.emit(speed)

        except ValueError:
            print("[Scanner] Invalid scanner speed input.")


    def button2_behaviour(self):
        """
        Update the UI when the Light Sheet button changes state.
        """
        if self.pushbutton_2.isChecked():
            # Light Sheet started -> disable manual beam controls
            self.lineedit_1.setEnabled(False)
            self.move_beam_slider.setEnabled(False)
            self.lineedit_0.setEnabled(False)
            self.pushbutton_2.setText("Stop\nLight Sheet")
        else:
            # Light Sheet stopped -> re-enable manual beam controls
            self.lineedit_1.setEnabled(True)
            self.move_beam_slider.setEnabled(True)
            self.lineedit_0.setEnabled(True)
            self.pushbutton_2.setText("Make\nLight Sheet")

        # Camera Mode must only be locked while the scanner button is ON
        # AND the respective camera is currently in Live mode.
        self._update_camera_mode_lock()



    def checkbox_scanner_select(self):
        """returns the scanner's parameters for the Y-Stack Acquisition"""

        # Read the text
        top_text = self.lineedit_2.text().strip()
        bottom_text = self.lineedit_3.text().strip()
        speed_text = self.lineedit_1.text().strip()

        # If the line edit is blank, return nothing
        if not top_text or not bottom_text or not speed_text:
            return {
                'scan_top': None,
                'scan_bottom': None,
                'mark_speed': None,
            }
        
        # Safeguard the value reading as well
        try:
            y_top = int(top_text)
            y_bottom = int(bottom_text)
            speed = float(speed_text)
        except ValueError:
            return {
                'scan_top': None,
                'scan_bottom': None,
                'mark_speed': None,
            }
        
        return {
            'scan_top': y_top,
            'scan_bottom': y_bottom,
            'mark_speed': speed,
        }
    


    
    #-------------------------------------------------------------------------------------
    # Slots

    @Slot()
    def center_beam_after_ystack(self):
        """Function that moves the mirror to the center after the end of the Y-Stack"""
        
        # Move the mirror
        self.move_beam_to(self.center_beam_position)

        # Set the GUI parameters
        self.move_beam_slider.setValue(self.center_beam_position)
        self.lineedit_0.setText(str(self.center_beam_position))

    @Slot()
    def on_lightsheet_stopped(self):
        """Only once the worker thread has fully exited do we
           read lineedit_0 and move the beam there."""
        pos = int(self.lineedit_0.text())
        self.move_beam_to(pos)
        self.move_beam_slider.setValue(pos)



    #-------------------------------------------------------------------------------------
    # Functions for the Scanner

    def move_beam_to(self, pos):
        "Function to move the beam to a specific X position"
        Xpos = pos
        Ypos = 0
        self.rtc5_board.goto_xy(ctypes.c_int(Xpos), ctypes.c_int(Ypos))


    def jump_top(self, Xtop):
        self.rtc5_board.set_start_list(1)
        self.rtc5_board.set_jump_speed(ctypes.c_double(800000))

        # Ensure beam is OFF during this reposition list
        self._laser_gate_off_in_list()

        self.rtc5_board.jump_abs(ctypes.c_int(Xtop), ctypes.c_int(0))
        self.rtc5_board.set_end_of_list()
        self.rtc5_board.execute_list(1)


    def _append_dwell_in_list(self, dwell_ms: float) -> None:
        """
        Append an in-list delay/dwell so the beam stays at the current position
        (bottom) for dwell_ms. This must be encoded in the RTC list.

        IMPORTANT:
        - This depends on your rtc5_board wrapper exposing a delay primitive
        (e.g., long_delay / time_delay / wait).
        - If your wrapper does not expose it yet, you must add it in the device layer.
        """
        if dwell_ms is None or dwell_ms <= 0:
            return

        # Try common RTC delay method names. Adjust to your actual wrapper.
        # Typical Scanlab RTC: long_delay(n) where n is in 10us ticks (depends on config).
        if hasattr(self.rtc5_board, "long_delay"):
            # --- Assumption: argument is in microseconds (or 10us ticks). ---
            # If your API expects 10us ticks, use: ticks = int(dwell_ms * 100)  # 1ms = 100 * 10us
            # If your API expects microseconds, use: us = int(dwell_ms * 1000)
            ticks_or_us = int(dwell_ms * 1000)  # <-- adjust to your hardware API
            self.rtc5_board.long_delay(ctypes.c_uint(ticks_or_us))
            return

        if hasattr(self.rtc5_board, "time_delay"):
            us = int(dwell_ms * 1000)
            self.rtc5_board.time_delay(ctypes.c_uint(us))
            return

        # If we reach here, no in-list delay is available from the wrapper.
        # Without it, you cannot do a true "beam parked at bottom" inside the RTC list.
        # You must implement a delay primitive in the RTC wrapper.
        print("[WARN] No in-list delay primitive found on rtc5_board. "
            "Add long_delay/time_delay to the RTC5 wrapper to park the beam at bottom.")

    def _set_da_in_list(self, da_channel: int, value: int) -> None:
        """
        Set an analog output inside the RTC list.
        This function tries common wrapper names. Adjust to your actual API.

        da_channel: 1 or 2
        value: typically 0..some DAC range (you are using 512 for ON)
        """
        # Prefer explicit list-methods if your wrapper has them
        if da_channel == 1:
            if hasattr(self.rtc5_board, "write_da_1_list"):
                self.rtc5_board.write_da_1_list(int(value))
                return
            if hasattr(self.rtc5_board, "write_da_1"):
                # Many wrappers record this into the list when called between set_start_list/set_end_of_list
                self.rtc5_board.write_da_1(int(value))
                return
        elif da_channel == 2:
            if hasattr(self.rtc5_board, "write_da_2_list"):
                self.rtc5_board.write_da_2_list(int(value))
                return
            if hasattr(self.rtc5_board, "write_da_2"):
                self.rtc5_board.write_da_2(int(value))
                return

        print(f"[WARN] No DA{da_channel} in-list method found on rtc5_board.")


    def _set_digital_mask_in_list(self, mask_value: int) -> None:
        # Preferir o comando LIST quando estamos entre set_start_list e set_end_of_list
        if hasattr(self.rtc5_board, "set_laser_pin_out_list"):
            self.rtc5_board.set_laser_pin_out_list(int(mask_value))
            return
        if hasattr(self.rtc5_board, "set_laser_pin_out"):
            # fallback (menos ideal): control command
            self.rtc5_board.set_laser_pin_out(int(mask_value))
            return
        print("[WARN] rtc5_board has no set_laser_pin_out/_list")


    def mark_toptobottom(self, Xtop: int, Xbottom: int, speed: float, dwell_ms: float = 10.0) -> None:
        """
        Build ONE RTC list with proper blanking:
        1) Laser gates OFF (jump/reposition)
        2) jump_abs to top
        3) Laser gates ON (only selected lasers)
        4) mark_abs to bottom (the swipe)
        5) Laser gates OFF immediately after the swipe
        6) dwell at bottom with laser OFF (in-list delay)
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        selected = self._get_selected_hw_lasers()
        print(f"[{ts}] [Scanner] LightSheet running? {getattr(self, 'lightsheet_running', False)}", flush=True)

        print(f"[{ts}] [Scanner] mark_toptobottom: Xtop={Xtop}, Xbottom={Xbottom}, speed={speed}, dwell_ms={dwell_ms}", flush=True)
        print(f"[{ts}] [Scanner] Selected HW lasers for gating: {selected}", flush=True)

        Xi, Yi = int(Xtop), 0
        Xf, Yf = int(Xbottom), 0

        self.rtc5_board.set_start_list(1)
        self.rtc5_board.set_jump_speed(ctypes.c_double(800000))
        self.rtc5_board.set_mark_speed(ctypes.c_double(speed))

        # --- 1) OFF during reposition ---
        print(f"[{ts}] [Scanner] Laser gates -> OFF (reposition/jump)", flush=True)
        self._laser_gate_off_in_list()

        # --- 2) jump to top ---
        self.rtc5_board.jump_abs(ctypes.c_int(Xi), ctypes.c_int(Yi))

        # --- 3) ON only for the sweep ---
        print(f"[{ts}] [Scanner] Laser gates -> ON (sweep only)", flush=True)
        self._laser_gate_on_in_list()

        # --- 4) swipe ---
        self.rtc5_board.mark_abs(ctypes.c_int(Xf), ctypes.c_int(Yf))

        # --- 5) OFF right after the sweep ---
        print(f"[{ts}] [Scanner] Laser gates -> OFF (post-sweep + dwell)", flush=True)
        self._laser_gate_off_in_list()

        # --- 6) dwell at bottom with beam OFF ---
        self._append_dwell_in_list(dwell_ms)

        self.rtc5_board.set_end_of_list()
        self.rtc5_board.execute_list(1)


    def lightsheet_thread(self, checked):
        if checked:
            self.thread = QThread()
            self.loop = lightsheet_loop()
            self.loop.moveToThread(self.thread)
            
            self.thread.started.connect(self.loop.start_loop)
            self.loop.finished.connect(self.thread.quit)
            self.loop.finished.connect(self.loop.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.loop.update.connect(self.handle_update)
            
            self.thread.start()
            print("Light Sheet thread started.")
        else:
            if self.loop:
                self.loop.stop()
                # Let the thread finish naturally instead of blocking with wait().
                self.thread.quit()
                print("Light Sheet thread stopping...")


    def handle_update(self):
        # If an update is already in progress, ignore this one
        if self._update_in_progress:
            return
        self._update_in_progress = True
        QTimer.singleShot(0, self.process_update)

    def process_update(self):
        # Call the board function
        self.mark_toptobottom(
            int(self.lineedit_2.text()),
            int(self.lineedit_3.text()),
            float(self.lineedit_1.text())
        )
        # Allow new updates once processing is done
        self._update_in_progress = False


    def move_beam(self):
        """ Stops lightsheet marking before moving the beam. """
        if self.lightsheet_running:
            self.toggle_lightsheet(False)  # Ensure lightsheet stops first
        new_position = int(self.lineedit_0.text())
        self.worker.move_beam(new_position)

    def on_beam_moved(self):
        """ Callback when beam movement is done. """
        print("Beam moved successfully!")


    def toggle_lightsheet(self, checked: bool) -> None:
        """
        Start/stop LightSheet. Start is delayed until lasers confirm LS mode is active.
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        if checked:
            print(f"[{ts}] [Scanner] LightSheet START requested.", flush=True)

            # Start is pending until lasers confirm mode switch is complete.
            self.lightsheet_running = False
            self._ls_start_pending = True

            lw = getattr(self, "_laser_widget", None)
            if lw is None:
                print(f"[{ts}] [Scanner] Laser widget not set -> cannot start LightSheet.", flush=True)
                self.pushbutton_2.setChecked(False)
                return

            print(f"[{ts}] [Scanner] Request lasers LightSheet mode -> ON", flush=True)

            # Request mode switch and store request id.
            self._ls_pending_req_id = lw.set_lightsheet_mode(True)

            # Do NOT start the LightSheet worker here.
            # It will start inside _on_laser_mode_switch_finished().
            return

        # ---- STOP ----
        print(f"[{ts}] [Scanner] LightSheet STOP requested (will stop after current list).", flush=True)
        self._ls_start_pending = False
        self.lightsheet_running = False

        if getattr(self, "_ls_worker", None) is not None and self._ls_worker.isRunning():
            self._ls_worker.request_stop()
        else:
            print(f"[{ts}] [Scanner] LightSheet worker not running.", flush=True)

        # Switch lasers back to CW mode (no need to block on completion for STOP).
        self._notify_lasers_lightsheet_mode(False)
        print(f"[{ts}] [Scanner] LightSheet STOP command issued.", flush=True)


    def lightsheet_stop(self) -> None:
        """
        Stop the lightsheet thread and restore UI controls.
        """
        # Request stop
        self.toggle_lightsheet(False)

        # Restore UI state (same intent as your current code)
        self.pushbutton_2.setChecked(False)
        self.pushbutton_2.setText("Make\nLight Sheet")
        self.lineedit_0.setEnabled(True)
        self.lineedit_1.setEnabled(True)
        self.move_beam_slider.setEnabled(True)

    #------------------------Functions for Acquistion Control-------------------------------------------------
    
    def set_lightsheet_mode_blocking(self, enabled: bool, timeout_ms: int = 5000) -> bool:
        """
        Switch the laser system mode and wait until the laser widget confirms it.
        """
        lw = getattr(self, "_laser_widget", None)
        if lw is None:
            print("[Scanner] Laser widget is not available.")
            return False

        result = {"ok": False}
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)

        req_id = lw.set_lightsheet_mode(enabled)

        def _handler(signal_enabled: bool, ok: bool, signal_req_id: int):
            # Ignore unrelated requests.
            if signal_req_id != req_id:
                return

            # Ignore the opposite transition.
            if signal_enabled != enabled:
                return

            result["ok"] = ok

            # Stop the timeout timer if it is still active.
            if timer.isActive():
                timer.stop()

            # Leave the local event loop.
            loop.quit()

        lw.lightsheetModeSwitchFinished.connect(_handler)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        loop.exec()

        # Safe disconnect: avoid warning if the handler was already disconnected implicitly.
        try:
            lw.lightsheetModeSwitchFinished.disconnect(_handler)
        except (TypeError, RuntimeError):
            pass

        return result["ok"]


    def prepare_lightsheet_mode_for_acquisition(self, timeout_ms: int = 5000) -> bool:
        """
        Put the lasers into Light Sheet mode before starting a full acquisition.
        """
        return self.set_lightsheet_mode_blocking(True, timeout_ms=timeout_ms)


    def restore_normal_mode_after_acquisition(self, timeout_ms: int = 5000) -> bool:
        """
        Restore the lasers to their normal/CW mode after acquisition ends.
        """
        return self.set_lightsheet_mode_blocking(False, timeout_ms=timeout_ms)

    #------------------Change Light Sheet Mode----------------------------------------------
    def _scanner_is_busy(self) -> bool:
        """Return True if the RTC5 board is busy executing a list."""
        status = ctypes.c_uint()
        position = ctypes.c_int()
        self.rtc5_board.get_status(ctypes.byref(status), ctypes.byref(position))

        busy = bool(status.value & 0x00000001)        # BUSY bit
        internal_busy = bool(status.value & 0x00008000)  # INTERNAL-BUSY bit
        return busy or internal_busy
    
    def set_laser_widget(self, laser_widget) -> None:
        """
        Store a reference to the laser widget and connect to its mode-switch completion signal.
        """
        self._laser_widget = laser_widget

        if not getattr(self, "_ls_mode_signal_connected", False):
            try:
                laser_widget.lightsheetModeSwitchFinished.connect(self._on_laser_mode_switch_finished)
                self._ls_mode_signal_connected = True
            except Exception as e:
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"[{ts}] [Scanner] Could not connect lightsheetModeSwitchFinished: {e}", flush=True)



    @Slot(bool, bool, int)
    def _on_laser_mode_switch_finished(self, enabled: bool, ok: bool, req_id: int):
        """
        Called when lasers finish switching between CW and Light Sheet modulation mode.
        """

        # First, let the rolling shutter handler inspect the event.
        if self._handle_rolling_shutter_mode_switch_finished(enabled, ok, req_id):
            return

        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Existing Light Sheet logic continues below...
        if req_id != getattr(self, "_ls_pending_req_id", None):
            return

        if not enabled:
            return

        if not ok:
            print(f"[{ts}] [Scanner] Laser LS mode switch FAILED -> abort LightSheet start.", flush=True)
            self._ls_start_pending = False
            self.lightsheet_running = False
            self.pushbutton_2.blockSignals(True)
            self.pushbutton_2.setChecked(False)
            self.pushbutton_2.blockSignals(False)
            self.button2_behaviour()
            return

        if not self.pushbutton_2.isChecked() or not getattr(self, "_ls_start_pending", False):
            print(f"[{ts}] [Scanner] Laser LS mode ready but start was cancelled.", flush=True)
            return

        print(f"[{ts}] [Scanner] Lasers ready in LS mode -> starting LightSheet worker.", flush=True)
        self.lightsheet_running = True
        self._ls_start_pending = False

        if getattr(self, "_ls_worker", None) is None or not self._ls_worker.isRunning():
            self._ls_worker = LightsheetWorker(ui=self)
            self._ls_worker.finished.connect(
                lambda: print(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [Scanner] LightSheet WORKER finished.",
                    flush=True
                )
            )
            self._ls_worker.start()
            print(f"[{ts}] [Scanner] LightSheet WORKER started.", flush=True)

    
    def _notify_lasers_lightsheet_mode(self, enabled: bool) -> None:
        """
        Ask laser widget to switch modulation mode and store request_id.
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        lw = getattr(self, "_laser_widget", None)
        if lw is None:
            print(f"[{ts}] [Scanner] Laser widget reference not set -> cannot switch laser mode.", flush=True)
            return

        print(f"[{ts}] [Scanner] Request lasers LightSheet mode -> {'ON' if enabled else 'OFF'}", flush=True)
        self._ls_pending_req_id = lw.set_lightsheet_mode(enabled)


    def _laser_gate_on_in_list(self) -> None:
        selected = set(self._get_selected_hw_lasers())

        mask = 0
        if 3 in selected:
            mask |= self._laser3_bit
        if 5 in selected:
            mask |= self._laser5_bit

        # Analog gating 
        self._set_da_in_list(2, self._laser_gate_on_level if 2 in selected else 0)  # Laser 2 -> DA2
        self._set_da_in_list(1, self._laser_gate_on_level if 4 in selected else 0)  # Laser 4 -> DA1

        # Digital gating 
        self._set_digital_mask_in_list(mask)


    def _laser_gate_off_in_list(self) -> None:
        """
        Turn OFF all laser gate outputs inside the RTC list.
        """
        # Analog OFF
        self._set_da_in_list(1, 0)
        self._set_da_in_list(2, 0)

        # Digital OFF (clear bits 0 and 1)
        self._set_digital_mask_in_list(0)

    # Scanner_Widget_py.py
    def _get_selected_hw_lasers(self):
        """
        Return lasers as hardware channel numbers (2..5).

        Behaviour:
        - During Light Sheet or Rolling Shutter mode:
        prefer lasers that are actually ON.
        - Otherwise:
        fall back to the currently selected lasers.
        """
        lw = getattr(self, "_laser_widget", None)
        if lw is None:
            return []

        if getattr(self, "lightsheet_running", False) or getattr(self, "rolling_shutter_running", False):
            try:
                lasers_on, _powers_on = lw.get_on_lasers()
                if lasers_on:
                    return lasers_on
            except Exception:
                pass

        try:
            lasers_selected, _lasers_power, _filters_1, _filters_2 = lw.get_selected_lasers()
            return lasers_selected
        except Exception:
            return []
        
    #-------------------------------------------------------------------------------------
    #Rolling Shutter

    def _start_rolling_shutter_worker(self) -> None:
        """
        Start the rolling shutter worker if it is not already running.
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        if self._rs_worker is None or not self._rs_worker.isRunning():
            self._rs_worker = RollingShutterWorker(ui=self)
            self._rs_worker.finished.connect(
                lambda: print(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                    f"[Scanner] Rolling Shutter WORKER finished.",
                    flush=True
                )
            )
            self._rs_worker.start()
            print(f"[{ts}] [Scanner] Rolling Shutter WORKER started.", flush=True)

    def _abort_rolling_shutter_start(self, reason: str = "") -> None:
        """
        Abort a pending rolling shutter start and restore the unified button state.
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if reason:
            print(f"[{ts}] [Scanner] Rolling Shutter start aborted: {reason}", flush=True)

        self._rs_start_pending = False
        self.rolling_shutter_running = False

        # Revert the unified button state without re-emitting signals
        self.pushbutton_2.blockSignals(True)
        self.pushbutton_2.setChecked(False)
        self.pushbutton_2.blockSignals(False)
        self.button2_behaviour()

    def toggle_rolling_shutter(self, checked: bool) -> None:
        """
        Start or stop rolling shutter mode.

        The start is delayed until the laser modulation mode switch is confirmed
        by the laser widget. This mirrors the same logic already used for
        Light Sheet mode.
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        if checked:
            print(f"[{ts}] [Scanner] Rolling Shutter START requested.", flush=True)

            # The scanner is not truly running yet. It becomes active only after
            # the laser widget confirms the mode switch.
            self.rolling_shutter_running = False
            self._rs_start_pending = True

            lw = getattr(self, "_laser_widget", None)
            if lw is None:
                self._abort_rolling_shutter_start("laser widget is not set")
                return

            # Reuse the same laser modulation switch used by Light Sheet mode.
            self._rs_pending_req_id = lw.set_lightsheet_mode(True)
            return

        # ---- STOP ----
        print(f"[{ts}] [Scanner] Rolling Shutter STOP requested.", flush=True)

        self._rs_start_pending = False
        self.rolling_shutter_running = False

        # Ask the worker to stop after the current RTC list finishes.
        if self._rs_worker is not None and self._rs_worker.isRunning():
            self._rs_worker.request_stop()
        else:
            print(f"[{ts}] [Scanner] Rolling Shutter worker not running.", flush=True)

        # Restore the laser system to normal mode.
        self._notify_lasers_lightsheet_mode(False)

        print(f"[{ts}] [Scanner] Rolling Shutter STOP command issued.", flush=True)


    def _handle_rolling_shutter_mode_switch_finished(self, enabled: bool, ok: bool, req_id: int) -> bool:
        """
        Handle the delayed start of Rolling Shutter after the laser mode switch.
        Returns True if the event belonged to Rolling Shutter and was handled.
        Returns False if the event was unrelated to Rolling Shutter.
        """
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Ignore unrelated requests
        if req_id != getattr(self, "_rs_pending_req_id", None):
            return False

        # We only care about the "enabled=True" completion event
        if not enabled:
            return False

        if not ok:
            self._abort_rolling_shutter_start("laser mode switch failed")
            return True

        # If the user cancelled the action while the lasers were switching,
        # do not start the worker anymore.
        if not self.pushbutton_2.isChecked() or not getattr(self, "_rs_start_pending", False):
            print(
                f"[{ts}] [Scanner] Laser mode ready but Rolling Shutter start was cancelled.",
                flush=True
            )
            return True

        print(f"[{ts}] [Scanner] Lasers ready -> starting Rolling Shutter worker.", flush=True)
        self.rolling_shutter_running = True
        self._rs_start_pending = False
        self._start_rolling_shutter_worker()
        return True
    
    def rolling_shutter_stop(self) -> None:
        """
        Stop rolling shutter mode and restore the scanner UI state.
        """
        # Request a clean stop.
        self.toggle_rolling_shutter(False)

        # Restore the button state without emitting signals again.
        self.pushbutton_2.blockSignals(True)
        self.pushbutton_2.setChecked(False)
        self.pushbutton_2.blockSignals(False)

        # Restore the original button text and manual controls.
        self.pushbutton_2.setText("Make\nRolling Shutter")
        self.lineedit_0.setEnabled(True)
        self.lineedit_1.setEnabled(True)
        self.move_beam_slider.setEnabled(True)

    def mark_toptobottom_rs(self, Xtop: int, Xbottom: int, speed: float) -> None:
        Xi, Yi = int(Xtop), 0
        Xf, Yf = int(Xbottom), 0

        self.rtc5_board.set_start_list(1)
        self.rtc5_board.set_jump_speed(ctypes.c_double(800000))
        self.rtc5_board.set_mark_speed(ctypes.c_double(speed))

        # OFF during reposition
        self._laser_gate_off_in_list()

        # Jump to top
        self.rtc5_board.jump_abs(ctypes.c_int(Xi), ctypes.c_int(Yi))

        # ON only during sweep
        self._laser_gate_on_in_list()

        # Sweep
        self.rtc5_board.mark_abs(ctypes.c_int(Xf), ctypes.c_int(Yf))

        # OFF immediately after sweep
        self._laser_gate_off_in_list()

        # No dwell for RS
        self.rtc5_board.set_end_of_list()
        self.rtc5_board.execute_list(1)

    # Acquisition with Rolling Shutter

    def set_rolling_shutter_mode_blocking(self, enabled: bool, timeout_ms: int = 5000) -> bool:
        """
        Switch the lasers between normal/CW mode and the modulation mode required
        for Rolling Shutter acquisition, then wait until the change is confirmed.

        IMPORTANT:
        At the moment, Rolling Shutter reuses the same laser modulation path as
        Light Sheet mode. This wrapper exists for semantic clarity and future
        extensibility.
        """
        return self.set_lightsheet_mode_blocking(enabled, timeout_ms=timeout_ms)

    def prepare_rolling_shutter_mode_for_acquisition(self, timeout_ms: int = 5000) -> bool:
        """
        Put the lasers into the modulation mode required for Rolling Shutter
        acquisition before starting a full Y-stack acquisition.
        """
        return self.set_rolling_shutter_mode_blocking(True, timeout_ms=timeout_ms)
    
    def restore_rolling_shutter_normal_mode_after_acquisition(self, timeout_ms: int = 5000) -> bool:
        """
        Restore the lasers to normal/CW mode after Rolling Shutter acquisition.
        """
        return self.set_rolling_shutter_mode_blocking(False, timeout_ms=timeout_ms)
    
    #-----------------------------------------------------------------------------------
    #Know which mode is on in camera

    def set_camera_mode_provider(self, provider) -> None:
        """
        provider: callable sem argumentos que devolve:
            - "Widefield Mode"
            - "Confocal Mode"
            - None
        """
        self._camera_mode_provider = provider

    def _get_active_camera_mode(self):
        if callable(self._camera_mode_provider):
            try:
                return self._camera_mode_provider()
            except Exception:
                return None
        return None
    
    
    def toggle_ls_mode(self, checked: bool) -> None:
        """
        Unified scanner button logic.

        Improvement:
        - Latch the mode at the moment the scanner is started.
        - This makes behaviour stable when both cameras are Live.
        """
        mode = self._get_active_camera_mode()

        if checked:
            # If the mode is invalid/unknown, revert safely.
            if mode not in ("Widefield Mode", "Confocal Mode"):
                self._running_mode = None  # Not running
                self.pushbutton_2.blockSignals(True)
                self.pushbutton_2.setChecked(False)
                self.pushbutton_2.blockSignals(False)
                self.button2_behaviour()
                print("[Scanner] Cannot start: no valid active camera mode (LS/RS).")
                return

            # Latch the mode we are about to run with.
            self._running_mode = mode

            if mode == "Widefield Mode":
                self.toggle_lightsheet(True)
                return

            if mode == "Confocal Mode":
                self.toggle_rolling_shutter(True)
                return

        # ---- STOP path ----
        self._running_mode = None  # Not running anymore

        if (
            self.lightsheet_running
            or getattr(self, "_ls_start_pending", False)
            or (getattr(self, "_ls_worker", None) is not None and self._ls_worker.isRunning())
        ):
            self.toggle_lightsheet(False)

        if (
            self.rolling_shutter_running
            or getattr(self, "_rs_start_pending", False)
            or (getattr(self, "_rs_worker", None) is not None and self._rs_worker.isRunning())
        ):
            self.toggle_rolling_shutter(False)


    def ls_stop(self) -> None:
        """
        Unified stop function for the single scanner button.
        This is the method main.py should call when Live is stopped
        or before acquisition starts.
        """
        if (
            self.lightsheet_running
            or getattr(self, "_ls_start_pending", False)
            or (getattr(self, "_ls_worker", None) is not None and self._ls_worker.isRunning())
        ):
            self.toggle_lightsheet(False)

        if (
            self.rolling_shutter_running
            or getattr(self, "_rs_start_pending", False)
            or (getattr(self, "_rs_worker", None) is not None and self._rs_worker.isRunning())
        ):
            self.toggle_rolling_shutter(False)

        self.pushbutton_2.blockSignals(True)
        self.pushbutton_2.setChecked(False)
        self.pushbutton_2.blockSignals(False)
        self.button2_behaviour()
        self._update_camera_mode_lock()


    def _camera_mode_changed(self):
        """
        If the camera mode changes while a camera is in Live and the scanner button
        is active, stop the scanner and uncheck pushbutton_2.
        """
        mode = self._get_active_camera_mode()

        # Check if any camera is currently in Live
        live_active = False
        parent = self.parent()
        if parent is not None:
            for attr in ("camera_widget_1", "camera_widget_2"):
                cam_widget = getattr(parent, attr, None)
                if cam_widget is not None and cam_widget.live_button.isChecked():
                    live_active = True
                    break

        # Update the button label according to the current mode
        if mode == "Widefield Mode":
            next_text = "Make\nLight Sheet"
        elif mode == "Confocal Mode":
            next_text = "Make\nLight Sheet"
        else:
            next_text = "Make\nLight Sheet"

        # If we are in Live and the scanner button is active, turn it OFF
        if live_active and self.pushbutton_2.isChecked():
            self.ls_stop()   # stops LS/RS, unchecks button, restores UI
            self.pushbutton_2.setText(next_text)
            return

        # If the button is already OFF, just keep the correct label
        if not self.pushbutton_2.isChecked():
            self.pushbutton_2.setText(next_text)

    def _camera_live_state_changed(self, live: bool):
        """
        Called when any camera Live mode is toggled.

        Fix:
        - Do NOT blindly stop and restart the scanner on every Live toggle.
        - Only restart if the effective camera mode changes (LS <-> RS).
        - If the effective mode becomes invalid, stop safely.
        """
        # Always keep the Camera Mode lock in sync
        self._update_camera_mode_lock()

        # If the scanner button is OFF, nothing else to do
        if not self.pushbutton_2.isChecked():
            return

        # Determine what the scanner *should* run with right now
        mode_now = self._get_active_camera_mode()

        # If we can no longer determine a valid mode, stop safely
        if mode_now not in ("Widefield Mode", "Confocal Mode"):
            print("[Scanner] Live state changed but no valid LS/RS mode is active -> stopping scanner.")
            self.ls_stop()
            self._running_mode = None
            self._update_camera_mode_lock()
            return

        # If we were not running (should not happen if button is checked), latch mode
        if self._running_mode is None:
            self._running_mode = mode_now
            self._update_camera_mode_lock()
            return

        # If mode is unchanged, keep running (CRITICAL for 2 cameras Live)
        if mode_now == self._running_mode:
            self._update_camera_mode_lock()
            return

        # Mode changed (e.g., LS -> RS). Restart to apply correct worker.
        print(f"[Scanner] Mode changed while running ({self._running_mode} -> {mode_now}) -> restarting.")
        self.ls_stop()
        self._running_mode = None

        # Restart scanner cleanly
        self.pushbutton_2.setChecked(True)
        self._running_mode = mode_now
        self._update_camera_mode_lock()

    #-----------------------------------------------------------------------------------
    #Set speed in Confocal Mode

    def set_scanner_speed_programmatically(self, speed: float, apply_to_scanner: bool = False) -> None:
        """
        Update the scanner speed field from code without emitting user-change signals.
        Optionally apply the new speed to the scanner logic.
        """
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            return

        if speed <= 0:
            return

        with QSignalBlocker(self.lineedit_1):
            self.lineedit_1.setText(f"{speed:.3f}")

        if apply_to_scanner:
            # Call your existing scanner update path here if needed
            pass



    #-------------------------------------------------------------------------------------
    # UI

    def setupUi(self):
        # Initialize the tooltip manager
        self.tooltip_manager = CustomToolTipManager(self)

        self.setWindowTitle("Scanner Control")
        
        center_widget = QWidget(self)
        center_layout = QHBoxLayout(center_widget)
        
        # Left Widget (Slider)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.doubleslider = QRangeSlider(Qt.Vertical)
        self.doubleslider.setRange(self.range_bottom, self.range_top)
        self.doubleslider.setValue((self.z_bottom, self.z_top))
        self.doubleslider.setFixedSize(25, 150)
        self.doubleslider.valueChanged.connect(self.slider_behaviour)
        self.doubleslider.setGeometry(QRect(10, 10, 30, 160))

        self.doubleslider.setObjectName("mySlider")
        left_layout.addWidget(self.doubleslider)


        # Move Beam Slider
        self.move_beam_slider = QSlider()
        self.move_beam_slider.setMinimum(self.range_bottom)
        self.move_beam_slider.setMaximum(self.range_top)
        self.move_beam_slider.setValue(self.center_beam_position)
        self.move_beam_slider.setFixedSize(25, 150)
        self.move_beam_slider.valueChanged.connect(self.move_beam_slider_behaviour)


        
        # Middle Widget (Labels and LineEdits with Grid Layout)
        middle_widget = QWidget()
        middle_layout = QGridLayout(middle_widget)

        self.label_0 = QLabel("Move Beam:")

        self.lineedit_0 = CustomLineEdit()
        self.lineedit_0.setFixedWidth(50)
        self.lineedit_0.setValidator(QIntValidator())
        self.lineedit_0.editingFinished.connect(self.lineedit0_behaviour)
        self.lineedit_0.editingFinished.connect(self.move_beam)
        self.lineedit_0.returnPressed.connect(self.lineedit_0.clearFocus)
        self.lineedit_0.setText(f"{self.center_beam_position}")
        self.tooltip_manager.attach_tooltip(self.lineedit_0, "<html>Moves the beam to a specific<br>coordinate in <i>Z</i>.</html>")
        self.lineedit_0.setStyleSheet("""
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
            }
        """)

        self.label_1 = QLabel("Light Sheet\nSpeed:")
        self.lineedit_1 = CustomLineEdit()
        self.lineedit_1.setFixedWidth(50)
        self.lineedit_1.setText(str(self.lightsheet_speed))
        validator = QDoubleValidator(2.0, 2**31 - 1, 3, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        validator.setLocale(QLocale(QLocale.C))
        self.lineedit_1.setValidator(validator)
        
        # Keep the existing focus handling
        self.lineedit_1.returnPressed.connect(self.lineedit_1.clearFocus)

        # Emit scanner speed changes when the user finishes editing
        self.lineedit_1.editingFinished.connect(self.lineedit1_speed_behaviour)

        self.lineedit_1.returnPressed.connect(self.lineedit_1.clearFocus)
        self.tooltip_manager.attach_tooltip(self.lineedit_1, "Sets the speed at which the mirror\nthat forms the Light Sheet moves.") 
        self.lineedit_1.setStyleSheet("""
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
            }
        """)        

        self.label_2 = QLabel("Top <i>Z</i>:")
        self.label_2.setTextFormat(Qt.TextFormat.RichText)
        self.lineedit_2 = CustomLineEdit(f"{self.z_top}")
        self.lineedit_2.setFixedWidth(50)
        self.lineedit_2.setValidator(QIntValidator())
        self.lineedit_2.editingFinished.connect(self.lineedit_behaviour)
        self.lineedit_2.returnPressed.connect(self.lineedit_2.clearFocus)
        self.lineedit_2.setStyleSheet("""
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
            }
        """)
        
        self.label_3 = QLabel("Bottom <i>Z</i>:")
        self.label_3.setTextFormat(Qt.TextFormat.RichText)
        self.lineedit_3 = CustomLineEdit(f"{self.z_bottom}")
        self.lineedit_3.setFixedWidth(50)
        self.lineedit_3.setValidator(QIntValidator())
        self.lineedit_3.editingFinished.connect(self.lineedit_behaviour)
        self.lineedit_3.returnPressed.connect(self.lineedit_3.clearFocus)
        self.lineedit_3.setStyleSheet("""
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
            }
        """)
        
        middle_layout.addWidget(self.label_0, 0, 0)
        middle_layout.addWidget(self.lineedit_0, 0, 1)
        middle_layout.addWidget(self.label_1, 1, 0)
        middle_layout.addWidget(self.lineedit_1, 1, 1)
        middle_layout.addWidget(self.label_2, 2, 0)
        middle_layout.addWidget(self.lineedit_2, 2, 1)
        middle_layout.addWidget(self.label_3, 3, 0)
        middle_layout.addWidget(self.lineedit_3, 3, 1)
            # Add a margin to the right for the glowing effect
        middle_layout.setContentsMargins(0, 0, 9, 0)  # left, top, right, bottom

        
        # Right Widget (Buttons)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        self.pushbutton_1 = QPushButton("Current FOV")
        self.pushbutton_1.setCheckable(True)
        self.pushbutton_1.setChecked(True)
        self.pushbutton_1.clicked.connect(self.button1_behaviour)
        self.pushbutton_1.setFixedSize(100, 65)  # Set a fixed size (width, height)
        self.pushbutton_1.setStyleSheet("""
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

        
        self.pushbutton_2 = QPushButton("Make\nLight Sheet")
        self.pushbutton_2.setCheckable(True)
        self.pushbutton_2.toggled.connect(self.check_button2_input)
        self.pushbutton_2.clicked.connect(self.button2_behaviour)
        self.pushbutton_2.toggled.connect(self._update_camera_mode_lock)
        self.pushbutton_2.toggled.connect(self.toggle_ls_mode)
        self.pushbutton_2.setFixedSize(100, 65)
        self.pushbutton_2.setStyleSheet("""
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

        self.setStyleSheet("""
            QWidget {
                background-color: #222222;  /* Dark background */
            }
                       
            QLabel, QGroupBox {
                color: white;  /* White text for labels */
            }
                       
            /* Override for the custom slider */
            QRangeSlider#mySlider {
                background-color: transparent; /* or specify the desired color for your slider */
            }

        """)

        
        right_layout.addWidget(self.pushbutton_1)
        right_layout.addWidget(self.pushbutton_2)


        
        # Add widgets to main layout
        center_layout.addWidget(left_widget)
        center_layout.addWidget(self.move_beam_slider)
        center_layout.addWidget(middle_widget)
        center_layout.addWidget(right_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)


        main_layout = QVBoxLayout()
        main_layout.addWidget(center_widget)
        self.setLayout(main_layout)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Scanner_Widget()  # Your QWidget subclass
    window.show()
    sys.exit(app.exec())
