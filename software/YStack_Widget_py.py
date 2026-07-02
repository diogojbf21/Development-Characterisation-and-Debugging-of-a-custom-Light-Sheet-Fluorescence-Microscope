from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTabBar, QGridLayout,
    QLineEdit, QFrame, QComboBox, QSizePolicy, QButtonGroup, QCheckBox
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QIcon, QPixmap, QIntValidator, QDoubleValidator, QFont
from PySide6.QtCore import Qt, QSize, QTimer, QLocale
import sys
import numpy as np
import os, re
import threading
import shutil
from pathlib import Path

import importlib
from itertools import zip_longest

# Imports from my code
from Extra_Files.ToolTip_Manager import CustomToolTipManager
from Extra_Files.Custom_Line_Edit import CustomLineEdit
from Extra_Files.Z_Plane import ZUpStageWidget
from Extra_Files.Y_Stack_Algorithms import y_stack
from Acquisition_Progress_py import AcquisitionProgress_Dialog

#Logger
import logging
import threading
# Reuse the main application logger
logger = logging.getLogger("ALM")
import time

class CustomTabBar(QTabBar):
    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        if self.tabText(index) == "" and self.tabIcon(index):
            return QSize(37, size.height())  # Smaller width for the "+" tab
        return size

class CustomTabWidget(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setTabBar(CustomTabBar())

from PySide6.QtGui import QDoubleValidator, QValidator

class ClampingDoubleValidator(QDoubleValidator):
    def __init__(self, bottom: float, top: float, decimals: int, parent=None):
        # ←— make sure you call *this* overload, not the 1-arg version!
        super().__init__(bottom, top, decimals, parent)
        # optional: force '.' as decimal separator
        self.setLocale(QLocale(QLocale.C))

    def validate(self, input_str: str, pos: int):
        if input_str in ("", "-", "+", ".", "-.", "+."):
            return (QValidator.Intermediate, input_str, pos)
        state, text, p = super().validate(input_str, pos)
        if state == QValidator.Invalid:
            return (QValidator.Invalid, input_str, pos)
        try:
            v = float(input_str)
        except ValueError:
            return (QValidator.Invalid, input_str, pos)
        if v < self.bottom() or v > self.top():
            return (QValidator.Invalid, input_str, pos)
        return (QValidator.Acceptable, input_str, pos)

    def fixup(self, input_str: str) -> str:
        try:
            v = float(input_str)
        except ValueError:
            v = self.bottom()
        v = max(self.bottom(), min(v, self.top()))
        return str(v)

from PySide6.QtWidgets import QProxyStyle, QStyle

# OpenGL imports
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QSlider
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt
from OpenGL.GL import *
from OpenGL.GLU import *

from Extra_Files.Devices_Connections import device_initializations
from Extra_Files.Acquisition_Thread_Code import Acquisition_Thread


from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QWidget, QPushButton, QMessageBox
# … your other imports (QVBoxLayout, QLabel, etc.) …

class YStackWorker(QObject):
    finished = Signal()         # signal that emits if the acquisition is finished
    error    = Signal(str)
    cancelled = Signal(str)

    slice_changed       = Signal(int, int)   # current_slice, total_slices
    channel_changed     = Signal(int, int)   # current_channel, total_channels
    timepoint_changed   = Signal(int, int)   # current_timepoint, total_timepoints
    position_changed    = Signal(int, int)   # current_acq, total_acqs
    frame_acquired = Signal(np.ndarray, int, int, int, int) # signal that emits the newest frame and the Camera ID

    def get_inverted_x_position(self, input_position):
        """Function that inverts in software the positive direction of the X axis"""

        x_max = self.pidevice.qTMX('1')['1']
        x_min = self.pidevice.qTMN('1')['1']

        # Invert input position relative to midpoint
        mid = (x_max + x_min) / 2
        inverted = 2 * mid - input_position

        # Clamp to limits
        inverted = min(max(inverted, x_min), x_max)
        return inverted

    def make_next_experiment_dir(self, base_dir, name=None):
        """
        If name is None:
        • scan for "Experiment N"
        • next_idx = max(N)+1 (or 1 if none)
        • new_name = "Experiment {next_idx}"

        If name is given:
        • scan for "{name}" or "{name} M"
        • next_idx = max(M)+1 (or 1 if none)
        • new_name = "{name}"       (if next_idx==1)
                    or "{name} {next_idx}" (if next_idx>1)

        Returns (new_path, next_idx).
        """
        # 1) decide the “base” prefix
        base = name or "Experiment"

        # 2) match either "base" or "base <digits>"
        pat = re.compile(rf'^{re.escape(base)}(?: (\d+))?$')

        # 3) collect all existing indices
        nums = []
        for d in os.listdir(base_dir):
            full = os.path.join(base_dir, d)
            if not os.path.isdir(full):
                continue
            m = pat.match(d)
            if not m:
                continue
            # if there's no digit suffix, count it as 1
            nums.append(int(m.group(1) or 1))

        # 4) pick the next index
        next_idx = max(nums) + 1 if nums else 1

        # 5) build the new folder name
        if name:
            # first instance gets the bare name
            new_name = base if next_idx == 1 else f"{base} {next_idx}"
        else:
            # always number the default "Experiment"
            new_name = f"{base} {next_idx}"

        # 6) make it and return
        new_path = os.path.join(base_dir, new_name)
        os.makedirs(new_path, exist_ok=True)
        return new_path, next_idx


    def __init__(self, multipositions_check, zstackwidget_parameters, save_directory,
    filterwheel1, filterwheel2, laserbox, rtc5_board, pidevice, 
    camera1=None, camera2=None, selected_camera1=None, selected_camera2=None,
    camera_widget1=None, camera_widget2=None, lasers_widget=None, scanner_widget=None, ystack_widget=None, acq_camera_mode="Widefield Mode"):

        super().__init__()

        self.multipositions_check = multipositions_check

        self._stop_event = threading.Event()
        self._delete_data = False

        self.experiment_counter = 1

        self.selected_camera1 = selected_camera1
        self.selected_camera2 = selected_camera2

        self.zstackwidget_parameters  = zstackwidget_parameters
        self.save_directory = save_directory

        self.filterwheel1 = filterwheel1
        self.filterwheel2 = filterwheel2
        self.laserbox = laserbox
        self.rtc5_board = rtc5_board
        self.pidevice = pidevice
        self.camera1 = camera1
        self.camera2 = camera2
        self.ystack_widget=ystack_widget

        
        # Store the exact combobox camera mode text used for acquisition
        self.acq_camera_mode = acq_camera_mode


        # Get the laser's parameters
        self.lasers, self.laser_powers_mW, self.filters1, self.filters2 = lasers_widget.get_selected_lasers()
        self.laser_powers_W = np.array(self.laser_powers_mW) / 1000

        # Get the Scanner's parameters
        scan = scanner_widget.checkbox_scanner_select()
        self.scan_top    = scan['scan_top']
        self.scan_bottom = scan['scan_bottom']
        self.mark_speed  = scan['mark_speed']

        # print(self.scan_top, self.scan_bottom, self.mark_speed)
        #print(f"[DEBUG][YStackWorker] lasers={self.lasers}")
        #print(f"[DEBUG][YStackWorker] scan_top={self.scan_top}, scan_bottom={self.scan_bottom}, mark_speed={self.mark_speed}")
        #print(f"[DEBUG][YStackWorker] acq_camera_mode={self.acq_camera_mode}")

        # Get the camera's parameters
            # Only Camera 1
        if self.selected_camera1 and not self.selected_camera2:
            self.camera1_width_x, self.camera1_height_y, self.camera1_binning, self.camera1_dynamic_range = camera_widget1.checkbox_camera_select()
            # Only Camera 2
        if self.selected_camera2 and not self.selected_camera1:
            self.camera2_width_x, self.camera2_height_y, self.camera2_binning, self.camera2_dynamic_range = camera_widget2.checkbox_camera_select()
            # Both
        if self.selected_camera1 and self.selected_camera2:
            self.camera1_width_x, self.camera1_height_y, self.camera1_binning, self.camera1_dynamic_range = camera_widget1.checkbox_camera_select()
            self.camera2_width_x, self.camera2_height_y, self.camera2_binning, self.camera2_dynamic_range = camera_widget2.checkbox_camera_select()


    @Slot()
    def stop(self):
        """Just stop acquisition, but keep the data."""
        logger.warning("Acquisition stop requested by user.")
        self._stop_event.set()

    @Slot()
    def discard(self):
        """Stop acquisition and delete whatever’s been written so far."""
        logger.warning("Acquisition discard requested by user.")
        self._delete_data = True
        self._stop_event.set()

    def _maybe_emit(self, sig, *args):
        """Only emit if no stop_event is set."""
        # self._stop_event is a threading.Event()
        if not self._stop_event.is_set():
            sig.emit(*args)

    def _laser_hw_to_wavelength(self, hw_channel: int) -> str:
        """
        Convert hardware laser channel (2..5) into a wavelength label.
        Based on your current mapping:
            hw=5 -> 405nm
            hw=4 -> 488nm
            hw=3 -> 561nm
            hw=2 -> 640nm
        """
        mapping = {5: "405nm", 4: "488nm", 3: "561nm", 2: "640nm"}
        return mapping.get(int(hw_channel), f"HW{hw_channel}")


    def _filter_name_from_position(self, wheel_number: int, position: int) -> str:
        """
        Resolve a human-readable filter name from filter_data given wheel number and position index.
        We reuse the same structure used in the filter widgets: Filterwheel_1 / Filterwheel_2.
        """
        try:
            # Lasers_Widget stores filter_data; worker received lasers_widget and stored it in __init__.
            filter_data = getattr(self.lasers_widget, "filter_data", None)
            if not filter_data:
                return str(position)

            wheel_key = f"Filterwheel_{int(wheel_number)}"
            wheel_dict = filter_data.get(wheel_key, {})

            for _, item in wheel_dict.items():
                if item.get("position_on_filterwheel") == int(position):
                    return item.get("name") or "Unknown"

            return "Unknown"
        except Exception:
            # Never crash acquisition because of logging metadata
            return "Unknown"
        
    def _log_channel_plan(self) -> None:
        """
        Log the channel plan once before acquisition starts.
        Format matches the user's desired log style.
        """
        # Number of channels (selected lasers)
        logger.info("Number of channels (lasers): %d", len(self.lasers))

        # Choose which filterwheel label to show depending on selected camera(s)
        cam1_only = bool(self.selected_camera1) and not bool(self.selected_camera2)
        cam2_only = bool(self.selected_camera2) and not bool(self.selected_camera1)

        for idx, (hw_laser, power_mw) in enumerate(zip(self.lasers, self.laser_powers_mW), start=1):
            wavelength = self._laser_hw_to_wavelength(hw_laser)

            # Resolve filter label (example output wants only one filter name like "DAPI")
            if cam1_only:
                fpos = self.filters1[idx - 1] if (idx - 1) < len(self.filters1) else None
                fname = self._filter_name_from_position(1, fpos) if fpos is not None else "Unknown"
            elif cam2_only:
                fpos = self.filters2[idx - 1] if (idx - 1) < len(self.filters2) else None
                fname = self._filter_name_from_position(2, fpos) if fpos is not None else "Unknown"
            else:
                # Both cameras selected: show both
                fpos1 = self.filters1[idx - 1] if (idx - 1) < len(self.filters1) else None
                fpos2 = self.filters2[idx - 1] if (idx - 1) < len(self.filters2) else None
                fn1 = self._filter_name_from_position(1, fpos1) if fpos1 is not None else "Unknown"
                fn2 = self._filter_name_from_position(2, fpos2) if fpos2 is not None else "Unknown"
                fname = f"cam1={fn1}, cam2={fn2}"

            # Match your target format exactly:
            # "Laser/Power/Filters channel 1:488nm, 1mW,DAPI"
            logger.info(
                "Laser/Power/Filters channel %d:%s, %smW,%s",
                idx, wavelength, str(power_mw), fname
            )

    @Slot()
    def run(self):

        threading.current_thread().name = "ACQUISITION"
        t0 = time.perf_counter()

        try:
            ystack_alg = y_stack()

            # Create the Experiment folder
            exp_name = self.ystack_widget.exp_name_lineedit.text()
            experiment_dir, exp_idx = self.make_next_experiment_dir(self.save_directory, exp_name)

            os.makedirs(experiment_dir, exist_ok=True)

            
            logger.info(
            "Acquisition run started. Experiment folder created at %s",
            str(experiment_dir),
            )

            
            logger.info(
            "Acquisition configuration: cameras selected -> cam1=%s, cam2=%s; mode=%s",
            bool(self.selected_camera1),
            bool(self.selected_camera2),
            str(self.acq_camera_mode),
            )

            
            
            # Log selected channels plan before acquisition starts iterating channels
            self._log_channel_plan()



            total_acqs = len(self.zstackwidget_parameters)

            Yis_um    = [tab['yi']        for tab in self.zstackwidget_parameters]
            Yfs_um    = [tab['yf']        for tab in self.zstackwidget_parameters]
            Ysteps_um = [tab['Ystep']     for tab in self.zstackwidget_parameters]
            Xs_um     = [tab['x']         for tab in self.zstackwidget_parameters]
            print(Xs_um)
            Xs_mm     = [x / 1000 for x in Xs_um]
            print(Xs_mm)
            Zs_um     = [tab['z']         for tab in self.zstackwidget_parameters]
            Thetas    = [tab['theta']     for tab in self.zstackwidget_parameters]
            Tpoints   = [tab['Tpoints']   for tab in self.zstackwidget_parameters]
            Tstep     = [tab['Tstep']     for tab in self.zstackwidget_parameters]
            Tstep_unit= [tab['Tstep_unit']for tab in self.zstackwidget_parameters]
            mode_yl   = [tab['mode_yl']   for tab in self.zstackwidget_parameters]
            mode_ly   = [tab['mode_ly']   for tab in self.zstackwidget_parameters]

            Yis_mm = [y / 1000 for y in Yis_um]
            Yfs_mm = [y / 1000 for y in Yfs_um]
            Ysteps_mm = [y / 1000 for y in Ysteps_um]
            Xs_mm = [self.get_inverted_x_position(x) for x in Xs_mm]
            Zs_mm = [z / 1000 for z in Zs_um]

            # Check the Mode of Acquisition
            mode_yl   = [tab['mode_yl']   for tab in self.zstackwidget_parameters]
            mode_ly   = [tab['mode_ly']   for tab in self.zstackwidget_parameters]

            # Get a single value
            mode_yl = mode_yl[0]
            mode_ly = mode_ly[0]



            print()
            print(Yis_mm,
                Yfs_mm,
                Ysteps_mm,
                Xs_mm,
                Zs_mm,
                Thetas,
                Tpoints,
                Tstep,
                Tstep_unit
                )
            print()

            print(
                self.lasers, 
                self.laser_powers_W, 
                self.filters1, 
                self.filters2,
                )
            print()

            print(self.scan_top,
                self.scan_bottom,
                self.mark_speed
                )
            print()


            print(self.selected_camera1)
            print(self.selected_camera2)
            print()

            print()

            print(Tpoints, Tstep, Tstep_unit)

            # In this mode, all time spacings are the same
            Tpoints = Tpoints[0]
            Tstep = Tstep[0]
            Tstep_unit = Tstep_unit[0]

            tstep = Tstep
            tstep_unit = Tstep_unit

            print(Tpoints, Tstep, Tstep_unit)
            
            result = None
                
            # Mode in which the whole volume is acquired with one channel at a time
            if mode_ly:
                    
                # Both Cameras
                if self.selected_camera1 and self.selected_camera2:
                    print(self.camera1_width_x, self.camera1_height_y, self.camera1_binning, self.camera1_dynamic_range)
                    print(self.camera2_width_x, self.camera2_height_y, self.camera2_binning, self.camera2_dynamic_range)
                    both = 0
                    _ = 0
                    result = ystack_alg.lY_stack_sametimepoints(Yis=Yis_mm, Yfs=Yfs_mm, Y_spacings=Ysteps_mm,
                                                        Xs=Xs_mm, Zs=Zs_mm, Thetas=Thetas,
                                                        time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                                        filterwheel1=self.filterwheel1, filterwheel2=self.filterwheel2, laserbox=self.laserbox, rtc5_board=self.rtc5_board, pidevice=self.pidevice, camera1=self.camera1, camera2=self.camera2, selected_cameras=both,
                                                        lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                                        filters1=self.filters1, filters2=self.filters2,
                                                        camera1_format_x=self.camera1_width_x, camera1_format_y=self.camera1_height_y, camera1_binning=self.camera1_binning, camera1_dynamic_range=self.camera1_dynamic_range,
                                                        camera2_format_x=self.camera2_width_x, camera2_format_y=self.camera2_height_y, camera2_binning=self.camera2_binning, camera2_dynamic_range=self.camera2_dynamic_range,
                                                        scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                                        save_dir=experiment_dir,
                                                        slice_callback     = lambda cur, tot: self._maybe_emit(self.slice_changed, cur, tot),
                                                        channel_callback   = lambda cur, tot: self._maybe_emit(self.channel_changed, cur, tot),
                                                        timepoint_callback = lambda cur, tot: self._maybe_emit(self.timepoint_changed, cur, tot),
                                                        position_callback = lambda cur, tot: self._maybe_emit(self.position_changed, cur, tot),
                                                        stop_event=self._stop_event,
                                                        acq_camera_mode=self.acq_camera_mode)


                    # Save the meta-data in the OME-Zarr file
                    try:
                        for pos_idx in range(len(Yis_mm)):
                            acq_name = f"Position {pos_idx+1}"
                            acq_dir = os.path.join(experiment_dir, acq_name)

                            z1 = os.path.join(acq_dir, f"Position{pos_idx+1}_Camera1.ome.zarr")
                            ystack_alg.write_metadata(
                                z1,
                                self.filters1,
                                self.camera1_dynamic_range,
                                self.camera1_binning,
                                t_spacing=tstep,
                                t_spacing_unit=tstep_unit,
                                z_step=Ysteps_um[pos_idx],
                                pixel_size_x=0.65,
                                pixel_size_y=0.65,
                            )

                            z2 = os.path.join(acq_dir, f"Position{pos_idx+1}_Camera2.ome.zarr")
                            ystack_alg.write_metadata(
                                z2,
                                self.filters2,
                                self.camera2_dynamic_range,
                                self.camera2_binning,
                                t_spacing=tstep,
                                t_spacing_unit=tstep_unit,
                                z_step=Ysteps_um[pos_idx],
                                pixel_size_x=0.65,
                                pixel_size_y=0.65,
                            )

                            ystack_alg.write_txt_settings(
                                Yi=Yis_um[pos_idx], Yf=Yfs_um[pos_idx], Y_spacing=Ysteps_um[pos_idx],
                                X=Xs_um[pos_idx], Z=Zs_um[pos_idx], Theta=Thetas[pos_idx],
                                time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                filters1=self.filters1, filters2=self.filters2,
                                camera1_format_x=self.camera1_width_x, camera1_format_y=self.camera1_height_y, camera1_binning=self.camera1_binning, camera1_dynamic_range=self.camera1_dynamic_range,
                                camera2_format_x=self.camera2_width_x, camera2_format_y=self.camera2_height_y, camera2_binning=self.camera2_binning, camera2_dynamic_range=self.camera2_dynamic_range,
                                pixel_size_x=0.65, pixel_size_y=0.65,
                                scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                experiment_dir=acq_dir, exp_name=acq_name,camera_mode=self.acq_camera_mode)

                    except Exception as e: print(e)#pass

                # Only Camera 1
                elif self.selected_camera1 and not self.selected_camera2:
                    print(self.camera1_width_x, self.camera1_height_y, self.camera1_binning, self.camera1_dynamic_range)
                    both = 1
                    _ = 0
                    result = ystack_alg.lY_stack_sametimepoints(Yis=Yis_mm, Yfs=Yfs_mm, Y_spacings=Ysteps_mm,
                                                        Xs=Xs_mm, Zs=Zs_mm, Thetas=Thetas,
                                                        time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                                        filterwheel1=self.filterwheel1, filterwheel2=self.filterwheel2, laserbox=self.laserbox, rtc5_board=self.rtc5_board, pidevice=self.pidevice, camera1=self.camera1, camera2=self.camera2, selected_cameras=both,
                                                        lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                                        filters1=self.filters1, filters2=self.filters2,
                                                        camera1_format_x=self.camera1_width_x, camera1_format_y=self.camera1_height_y, camera1_binning=self.camera1_binning, camera1_dynamic_range=self.camera1_dynamic_range,
                                                        camera2_format_x=_, camera2_format_y=_, camera2_binning=_, camera2_dynamic_range=_,
                                                        scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                                        save_dir=experiment_dir,
                                                        slice_callback     = lambda cur, tot: self._maybe_emit(self.slice_changed, cur, tot),
                                                        channel_callback   = lambda cur, tot: self._maybe_emit(self.channel_changed, cur, tot),
                                                        timepoint_callback = lambda cur, tot: self._maybe_emit(self.timepoint_changed, cur, tot),
                                                        position_callback = lambda cur, tot: self._maybe_emit(self.position_changed, cur, tot),
                                                        stop_event=self._stop_event,
                                                        acq_camera_mode=self.acq_camera_mode)

                    # Save the meta-data in the OME-Zarr file
                    try:
                        for pos_idx in range(len(Yis_mm)):
                            acq_name = f"Position {pos_idx+1}"
                            acq_dir = os.path.join(experiment_dir, acq_name)

                            z1 = os.path.join(acq_dir, f"Position{pos_idx+1}_Camera1.ome.zarr")
                            ystack_alg.write_metadata(
                                z1,
                                self.filters1,
                                self.camera1_dynamic_range,
                                self.camera1_binning,
                                t_spacing=tstep,
                                t_spacing_unit=tstep_unit,
                                z_step=Ysteps_um[pos_idx],
                                pixel_size_x=0.65,
                                pixel_size_y=0.65,
                            )

                            ystack_alg.write_txt_settings(
                                Yi=Yis_um[pos_idx], Yf=Yfs_um[pos_idx], Y_spacing=Ysteps_um[pos_idx],
                                X=Xs_um[pos_idx], Z=Zs_um[pos_idx], Theta=Thetas[pos_idx],
                                time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                filters1=self.filters1, filters2=self.filters2,
                                camera1_format_x=self.camera1_width_x, camera1_format_y=self.camera1_height_y, camera1_binning=self.camera1_binning, camera1_dynamic_range=self.camera1_dynamic_range,
                                camera2_format_x=_, camera2_format_y=_, camera2_binning=_, camera2_dynamic_range=_,
                                pixel_size_x=0.65, pixel_size_y=0.65,
                                scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                experiment_dir=acq_dir, exp_name=acq_name,camera_mode=self.acq_camera_mode)

                    except Exception as e: print(e)#pass

                # Only Camera 2
                elif self.selected_camera2 and not self.selected_camera1:
                    print(self.camera2_width_x, self.camera2_height_y, self.camera2_binning, self.camera2_dynamic_range)
                    both = 2
                    _ = 0
                    result = ystack_alg.lY_stack_sametimepoints(Yis=Yis_mm, Yfs=Yfs_mm, Y_spacings=Ysteps_mm,
                                                        Xs=Xs_mm, Zs=Zs_mm, Thetas=Thetas,
                                                        time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                                        filterwheel1=self.filterwheel1, filterwheel2=self.filterwheel2, laserbox=self.laserbox, rtc5_board=self.rtc5_board, pidevice=self.pidevice, camera1=self.camera1, camera2=self.camera2, selected_cameras=both,
                                                        lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                                        filters1=self.filters1, filters2=self.filters2,
                                                        camera1_format_x=_, camera1_format_y=_, camera1_binning=_, camera1_dynamic_range=_,
                                                        camera2_format_x=self.camera2_width_x, camera2_format_y=self.camera2_height_y, camera2_binning=self.camera2_binning, camera2_dynamic_range=self.camera2_dynamic_range,
                                                        scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                                        save_dir=experiment_dir,
                                                        slice_callback     = lambda cur, tot: self._maybe_emit(self.slice_changed, cur, tot),
                                                        channel_callback   = lambda cur, tot: self._maybe_emit(self.channel_changed, cur, tot),
                                                        timepoint_callback = lambda cur, tot: self._maybe_emit(self.timepoint_changed, cur, tot),
                                                        position_callback = lambda cur, tot: self._maybe_emit(self.position_changed, cur, tot),
                                                        stop_event=self._stop_event,
                                                        acq_camera_mode=self.acq_camera_mode)

                    # Save the meta-data in the OME-Zarr file
                    # if result != 0:
                    try:
                        for pos_idx in range(len(Yis_mm)):
                            acq_name = f"Position {pos_idx+1}"
                            acq_dir = os.path.join(experiment_dir, acq_name)

                            z2 = os.path.join(acq_dir, f"Position{pos_idx+1}_Camera2.ome.zarr")
                            ystack_alg.write_metadata(
                                z2,
                                self.filters2,
                                self.camera2_dynamic_range,
                                self.camera2_binning,
                                t_spacing=tstep,
                                t_spacing_unit=tstep_unit,
                                z_step=Ysteps_um[pos_idx],
                                pixel_size_x=0.65,
                                pixel_size_y=0.65,
                            )

                            ystack_alg.write_txt_settings(
                                Yi=Yis_um[pos_idx], Yf=Yfs_um[pos_idx], Y_spacing=Ysteps_um[pos_idx],
                                X=Xs_um[pos_idx], Z=Zs_um[pos_idx], Theta=Thetas[pos_idx],
                                time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                filters1=self.filters1, filters2=self.filters2,
                                camera1_format_x=_, camera1_format_y=_, camera1_binning=_, camera1_dynamic_range=_,
                                camera2_format_x=self.camera2_width_x, camera2_format_y=self.camera2_height_y, camera2_binning=self.camera2_binning, camera2_dynamic_range=self.camera2_dynamic_range,
                                pixel_size_x=0.65, pixel_size_y=0.65,
                                scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                experiment_dir=acq_dir, exp_name=acq_name,camera_mode=self.acq_camera_mode)

                    except Exception as e: print(e)#pass

            # else:

            #     # In this mode, time spacings can be different
            #     Tpoints = Tpoints
            #     Tstep = Tstep
            #     Tstep_unit = Tstep_unit

            # Mode in which every channel is acquired at each position
            elif mode_yl:
                    
                # Both Cameras
                if self.selected_camera1 and self.selected_camera2:
                    print(self.camera1_width_x, self.camera1_height_y, self.camera1_binning, self.camera1_dynamic_range)
                    print(self.camera2_width_x, self.camera2_height_y, self.camera2_binning, self.camera2_dynamic_range)
                    both = 0
                    _ = 0
                    result = ystack_alg.YL_stack_sametimepoints(Yis=Yis_mm, Yfs=Yfs_mm, Y_spacings=Ysteps_mm,
                                                        Xs=Xs_mm, Zs=Zs_mm, Thetas=Thetas,
                                                        time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                                        filterwheel1=self.filterwheel1, filterwheel2=self.filterwheel2, laserbox=self.laserbox, rtc5_board=self.rtc5_board, pidevice=self.pidevice, camera1=self.camera1, camera2=self.camera2, selected_cameras=both,
                                                        lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                                        filters1=self.filters1, filters2=self.filters2,
                                                        camera1_format_x=self.camera1_width_x, camera1_format_y=self.camera1_height_y, camera1_binning=self.camera1_binning, camera1_dynamic_range=self.camera1_dynamic_range,
                                                        camera2_format_x=self.camera2_width_x, camera2_format_y=self.camera2_height_y, camera2_binning=self.camera2_binning, camera2_dynamic_range=self.camera2_dynamic_range,
                                                        scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                                        save_dir=experiment_dir,
                                                        slice_callback     = lambda cur, tot: self._maybe_emit(self.slice_changed, cur, tot),
                                                        channel_callback   = lambda cur, tot: self._maybe_emit(self.channel_changed, cur, tot),
                                                        timepoint_callback = lambda cur, tot: self._maybe_emit(self.timepoint_changed, cur, tot),
                                                        position_callback = lambda cur, tot: self._maybe_emit(self.position_changed, cur, tot),
                                                        stop_event=self._stop_event,
                                                        acq_camera_mode=self.acq_camera_mode)


                    # Save the meta-data in the OME-Zarr file
                    try:
                        for pos_idx in range(len(Yis_mm)):
                            acq_name = f"Position {pos_idx+1}"
                            acq_dir = os.path.join(experiment_dir, acq_name)

                            z1 = os.path.join(acq_dir, f"Position{pos_idx+1}_Camera1.ome.zarr")
                            ystack_alg.write_metadata(
                                z1,
                                self.filters1,
                                self.camera1_dynamic_range,
                                self.camera1_binning,
                                t_spacing=tstep,
                                t_spacing_unit=tstep_unit,
                                z_step=Ysteps_um[pos_idx],
                                pixel_size_x=0.65,
                                pixel_size_y=0.65,
                            )

                            z2 = os.path.join(acq_dir, f"Position{pos_idx+1}_Camera2.ome.zarr")
                            ystack_alg.write_metadata(
                                z2,
                                self.filters2,
                                self.camera2_dynamic_range,
                                self.camera2_binning,
                                t_spacing=tstep,
                                t_spacing_unit=tstep_unit,
                                z_step=Ysteps_um[pos_idx],
                                pixel_size_x=0.65,
                                pixel_size_y=0.65,
                            )

                            ystack_alg.write_txt_settings(
                                Yi=Yis_um[pos_idx], Yf=Yfs_um[pos_idx], Y_spacing=Ysteps_um[pos_idx],
                                X=Xs_um[pos_idx], Z=Zs_um[pos_idx], Theta=Thetas[pos_idx],
                                time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                filters1=self.filters1, filters2=self.filters2,
                                camera1_format_x=self.camera1_width_x, camera1_format_y=self.camera1_height_y, camera1_binning=self.camera1_binning, camera1_dynamic_range=self.camera1_dynamic_range,
                                camera2_format_x=self.camera2_width_x, camera2_format_y=self.camera2_height_y, camera2_binning=self.camera2_binning, camera2_dynamic_range=self.camera2_dynamic_range,
                                pixel_size_x=0.65, pixel_size_y=0.65,
                                scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                experiment_dir=acq_dir, exp_name=acq_name,camera_mode=self.acq_camera_mode)

                    except Exception:
                         logger.exception("Failed to write YLambda metadata/settings for both cameras")

                # Only Camera 1
                elif self.selected_camera1 and not self.selected_camera2:
                    print(self.camera1_width_x, self.camera1_height_y, self.camera1_binning, self.camera1_dynamic_range)
                    both = 1
                    _ = 0
                    result = ystack_alg.YL_stack_sametimepoints(Yis=Yis_mm, Yfs=Yfs_mm, Y_spacings=Ysteps_mm,
                                                        Xs=Xs_mm, Zs=Zs_mm, Thetas=Thetas,
                                                        time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                                        filterwheel1=self.filterwheel1, filterwheel2=self.filterwheel2, laserbox=self.laserbox, rtc5_board=self.rtc5_board, pidevice=self.pidevice, camera1=self.camera1, camera2=self.camera2, selected_cameras=both,
                                                        lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                                        filters1=self.filters1, filters2=self.filters2,
                                                        camera1_format_x=self.camera1_width_x, camera1_format_y=self.camera1_height_y, camera1_binning=self.camera1_binning, camera1_dynamic_range=self.camera1_dynamic_range,
                                                        camera2_format_x=_, camera2_format_y=_, camera2_binning=_, camera2_dynamic_range=_,
                                                        scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                                        save_dir=experiment_dir,
                                                        slice_callback     = lambda cur, tot: self._maybe_emit(self.slice_changed, cur, tot),
                                                        channel_callback   = lambda cur, tot: self._maybe_emit(self.channel_changed, cur, tot),
                                                        timepoint_callback = lambda cur, tot: self._maybe_emit(self.timepoint_changed, cur, tot),
                                                        position_callback = lambda cur, tot: self._maybe_emit(self.position_changed, cur, tot),
                                                        stop_event=self._stop_event,
                                                        acq_camera_mode=self.acq_camera_mode)

                    # Save the meta-data in the OME-Zarr file
                    try:
                        for pos_idx in range(len(Yis_mm)):
                            acq_name = f"Position {pos_idx+1}"
                            acq_dir = os.path.join(experiment_dir, acq_name)

                            z1 = os.path.join(acq_dir, f"Position{pos_idx+1}_Camera1.ome.zarr")
                            ystack_alg.write_metadata(
                                z1,
                                self.filters1,
                                self.camera1_dynamic_range,
                                self.camera1_binning,
                                t_spacing=tstep,
                                t_spacing_unit=tstep_unit,
                                z_step=Ysteps_um[pos_idx],
                                pixel_size_x=0.65,
                                pixel_size_y=0.65,
                            )

                            ystack_alg.write_txt_settings(
                                Yi=Yis_um[pos_idx], Yf=Yfs_um[pos_idx], Y_spacing=Ysteps_um[pos_idx],
                                X=Xs_um[pos_idx], Z=Zs_um[pos_idx], Theta=Thetas[pos_idx],
                                time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                filters1=self.filters1, filters2=self.filters2,
                                camera1_format_x=self.camera1_width_x, camera1_format_y=self.camera1_height_y, camera1_binning=self.camera1_binning, camera1_dynamic_range=self.camera1_dynamic_range,
                                camera2_format_x=_, camera2_format_y=_, camera2_binning=_, camera2_dynamic_range=_,
                                pixel_size_x=0.65, pixel_size_y=0.65,
                                scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                experiment_dir=acq_dir, exp_name=acq_name,camera_mode=self.acq_camera_mode)

                    except Exception as e:
                         logger.exception("Failed to write YLambda metadata/settings for Camera 1")

                # Only Camera 2
                elif self.selected_camera2 and not self.selected_camera1:
                    print(self.camera2_width_x, self.camera2_height_y, self.camera2_binning, self.camera2_dynamic_range)
                    both = 2
                    _ = 0
                    result = ystack_alg.YL_stack_sametimepoints(Yis=Yis_mm, Yfs=Yfs_mm, Y_spacings=Ysteps_mm,
                                                        Xs=Xs_mm, Zs=Zs_mm, Thetas=Thetas,
                                                        time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                                        filterwheel1=self.filterwheel1, filterwheel2=self.filterwheel2, laserbox=self.laserbox, rtc5_board=self.rtc5_board, pidevice=self.pidevice, camera1=self.camera1, camera2=self.camera2, selected_cameras=both,
                                                        lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                                        filters1=self.filters1, filters2=self.filters2,
                                                        camera1_format_x=_, camera1_format_y=_, camera1_binning=_, camera1_dynamic_range=_,
                                                        camera2_format_x=self.camera2_width_x, camera2_format_y=self.camera2_height_y, camera2_binning=self.camera2_binning, camera2_dynamic_range=self.camera2_dynamic_range,
                                                        scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                                        save_dir=experiment_dir,
                                                        slice_callback     = lambda cur, tot: self._maybe_emit(self.slice_changed, cur, tot),
                                                        channel_callback   = lambda cur, tot: self._maybe_emit(self.channel_changed, cur, tot),
                                                        timepoint_callback = lambda cur, tot: self._maybe_emit(self.timepoint_changed, cur, tot),
                                                        position_callback = lambda cur, tot: self._maybe_emit(self.position_changed, cur, tot),
                                                        stop_event=self._stop_event,
                                                        acq_camera_mode=self.acq_camera_mode)

                    # Save the meta-data in the OME-Zarr file
                    try:
                        for pos_idx in range(len(Yis_mm)):
                            acq_name = f"Position {pos_idx+1}"
                            acq_dir = os.path.join(experiment_dir, acq_name)

                            z2 = os.path.join(acq_dir, f"Position{pos_idx+1}_Camera2.ome.zarr")
                            ystack_alg.write_metadata(
                                z2,
                                self.filters2,
                                self.camera2_dynamic_range,
                                self.camera2_binning,
                                t_spacing=tstep,
                                t_spacing_unit=tstep_unit,
                                z_step=Ysteps_um[pos_idx],
                                pixel_size_x=0.65,
                                pixel_size_y=0.65,
                            )

                            ystack_alg.write_txt_settings(
                                Yi=Yis_um[pos_idx], Yf=Yfs_um[pos_idx], Y_spacing=Ysteps_um[pos_idx],
                                X=Xs_um[pos_idx], Z=Zs_um[pos_idx], Theta=Thetas[pos_idx],
                                time_points=Tpoints, time_spacing=Tstep, time_step_unit=Tstep_unit,
                                lasers=self.lasers, laser_powers_W=self.laser_powers_W,
                                filters1=self.filters1, filters2=self.filters2,
                                camera1_format_x=_, camera1_format_y=_, camera1_binning=_, camera1_dynamic_range=_,
                                camera2_format_x=self.camera2_width_x, camera2_format_y=self.camera2_height_y, camera2_binning=self.camera2_binning, camera2_dynamic_range=self.camera2_dynamic_range,
                                pixel_size_x=0.65, pixel_size_y=0.65,
                                scan_top=self.scan_top, scan_bottom=self.scan_bottom, mark_speed=self.mark_speed,
                                experiment_dir=acq_dir, exp_name=acq_name,camera_mode=self.acq_camera_mode)
                            
                    except Exception:
                         logger.exception("Failed to write YLambda metadata/settings for Camera 2")

            else:
                raise RuntimeError("No Y-stack acquisition mode selected.")

                        
            self.experiment_counter += 1

            dt = time.perf_counter() - t0

            if self._stop_event.is_set():
                logger.warning(
                    "Acquisition stopped early after %.3f s. result=%s discard=%s data_dir=%s",
                    dt,
                    result,
                    self._delete_data,
                    str(experiment_dir),
                )
                self.cancelled.emit("Acquisition was stopped before completion.")
                return

            logger.info(
                "Acquisition run finished successfully in %.3f s. Data saved in %s",
                dt,
                str(experiment_dir),
            )


            self.finished.emit()

        except Exception as e:
            logger.exception("Acquisition run failed due to an unexpected exception")
            self.error.emit(str(e))

        finally:
            if self._stop_event.is_set() and self._delete_data:
                try:
                    shutil.rmtree(experiment_dir)
                except Exception:
                    pass
            

from PySide6.QtCore import QObject, QThread, Signal, QTimer

class UpdateWorker(QObject):
    update_signal = Signal(float)  # This will emit the current Y position

    def __init__(self, pidevice, parent=None):
        super().__init__(parent)
        self.pidevice = pidevice
        self._running = True

    def stop(self):
        self._running = False

    def start_updates(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.perform_update)
        self.timer.start(50)  # 50 ms interval

    def perform_update(self):
        if not self._running:
            self.timer.stop()
            return

        try:
            current_y = self.pidevice.qPOS('2')['2']
            self.update_signal.emit(current_y)
        except Exception as e:
            print(f"UpdateWorker Error: {e}")

from PySide6.QtCore import Signal

class YStack_Widget(QWidget):

    ##########################################################################
    # Singals and Slots

    acquisition_started = Signal()
    acquisition_finished = Signal()
    # Acquired frame to emit for visualization
    frame_acquired = Signal(np.ndarray, int, int, int, int)

    @Slot(int, int)
    def _on_any_slice(self, slice_idx, slice_total):
        # every time *any* slice fires, increment the bar by one
        self._progress_counter += 1
        self.progress_dialog.bar.setValue(self._progress_counter)

        
        # Log only every N steps to keep logs readable.
        if (self._progress_counter % 1) == 0:
            logger.info(
                "Acquisition progress: %d of %d steps completed.",
                self._progress_counter,
                self._grand_total,
            )


    @Slot()
    def on_acq_finished(self):

        threading.current_thread().name = "ACQUISITION"

        logger.info("Acquisition completed successfully.")

        
        if hasattr(self, "_acq_t0"):
            dt = time.perf_counter() - self._acq_t0
            logger.info("Total acquisition duration was %.3f s.", dt)


        self.is_acquiring = False
        self.start_button.setEnabled(True)

        # Restore the laser system to normal/CW mode after the full acquisition.
        if self.scanner_widget is not None:
            self.scanner_widget.restore_normal_mode_after_acquisition(timeout_ms=5000)

        self.acquisition_finished.emit()
        QMessageBox.information(self, "Done", "Acquisition completed.")


    @Slot(str)
    def on_acq_cancelled(self, msg: str):

        threading.current_thread().name = "ACQUISITION"

        logger.warning("Acquisition cancelled: %s", msg)

        self.start_button.setEnabled(True)
        self.is_acquiring = False

        if self.scanner_widget is not None:
            self.scanner_widget.restore_normal_mode_after_acquisition(timeout_ms=5000)

        self.acquisition_finished.emit()
        QMessageBox.information(self, "Stopped", msg)


    @Slot(int)
    def on_acq_progress(self, step):
        # e.g. show “slice 3 of 7” in a QLabel or a QProgressBar
        total = len(self.content_tabs)
        #self.estimated_time_label.setText(f"Slice {step}/{total}")

    @Slot(str)
    def on_acq_error(self, msg: str):

        threading.current_thread().name = "ACQUISITION"

        logger.error("Acquisition failed: %s", msg)

        self.start_button.setEnabled(True)
        self.is_acquiring = False

        # Always try to restore normal/CW mode after an acquisition error.
        if self.scanner_widget is not None:
            self.scanner_widget.restore_normal_mode_after_acquisition(timeout_ms=5000)

        self.acquisition_finished.emit()
        QMessageBox.critical(self, "Y-Stack Error", f"Acquisition failed:\n\n{msg}")

    ################################################################################
    #Get camera mode to do the acquisition

    def _get_selected_acquisition_camera_mode(self):
        """
        Return the exact camera mode text selected on the checked camera(s).

        Possible return values:
            - "Widefield Mode"
            - "Confocal Mode"
            - "Internal Trigger"

        Return None if:
            - no camera is selected, or
            - selected cameras do not share the same mode.
        """
        selected_modes = []

        # Read Camera 1 mode if Camera 1 is selected for acquisition
        if self.camera_widget_1 is not None and self.camera_widget_1.camera_checkbox.isChecked():
            selected_modes.append(self.camera_widget_1.cameramode_combobox.currentText())

        # Read Camera 2 mode if Camera 2 is selected for acquisition
        if self.camera_widget_2 is not None and self.camera_widget_2.camera_checkbox.isChecked():
            selected_modes.append(self.camera_widget_2.cameramode_combobox.currentText())

        # No selected cameras
        if not selected_modes:
            return None

        # Mixed camera modes are not allowed in one acquisition
        if len(set(selected_modes)) != 1:
            return None

        # Return the exact combobox text
        return selected_modes[0]

    ##########################################################################
    # GUI Behaviour Functions

    def remove_tab(self, tab_widget):
        """Function that is linked to the Remove Tab button"""
        real_tabs = self.tab_widget.count() - 1
        if real_tabs <= 1:
            return

        index = self.tab_widget.indexOf(tab_widget)
        if index != -1:
            self.block_tab_changed = True
            self.tab_widget.removeTab(index)
            self.block_tab_changed = False

            self.update_tab_labels()

            for entry in self.content_tabs:
                if entry.get('tab') is tab_widget:
                    self.content_tabs.remove(entry)
                    break

            # Decide which tab to select next
            new_count = self.tab_widget.count()
            if new_count > 1:  # Still has real tabs + "+"
                # Try to select the tab at the same index,
                # or the one to the left if we deleted the last real tab
                next_index = min(index, new_count - 2)
                self.tab_widget.setCurrentIndex(next_index)


    def add_plus_tab(self):
        """Function to create the tab to Add a new tab"""
        plus_tab = QWidget()
        pixmap = QPixmap("icons//plus.png").scaled(13, 13, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon = QIcon(pixmap)
        self.tab_widget.addTab(plus_tab, icon, "")  # Only icon, no text
        self.tab_widget.setIconSize(QSize(13, 13))


    def handle_tab_changed(self, index):
        """Function that handles the changing of the tabs"""
        if self.initializing or self.block_tab_changed:
            return

        if index == self.tab_widget.count() - 1:
            self.add_content_tab()


    def update_tab_labels(self):
        """Function that updates the labels of the tabs"""
        for i in range(self.tab_widget.count() - 1):  # Exclude "+" tab
            self.tab_widget.setTabText(i, f"Pos. {i + 1}")

            # Also update the label *inside* the tab
            tab = self.tab_widget.widget(i)
            if tab:
                label = tab.findChild(QLabel)
                # if label:
                #     label.setText(f"This is tab {i + 1}")

    def update_save_directory(self, new_path):
        """Update the current save directory."""
        self.current_save_directory = new_path

    def time_points_lineedit_behaviour(self):
        """Function that gives out the behaviour for each tab"""

        sender = self.sender()
        for tab in self.content_tabs:
            if tab['Tpoints'] is sender:
                tp = sender.text()


    def get_inverted_x_position(self, input_position):
        """Function that inverts in software the positive direction of the X axis"""

        x_max = self.pidevice.qTMX('1')['1']
        x_min = self.pidevice.qTMN('1')['1']

        # Invert input position relative to midpoint
        mid = (x_max + x_min) / 2
        inverted = 2 * mid - input_position

        # Clamp to limits
        inverted = min(max(inverted, x_min), x_max)
        return inverted

    def begin_button_behaviour(self):
        """Fills the initial position parameters or moves the Stage"""

        # First check the correct tab to fill
        sender = self.sender()
        for tab in self.content_tabs:
            if tab['Begin'] is sender:

                # If at least one is empty, fill them up
                if tab['Yi'].text() == "" or tab['Yf'].text() == "" or tab['X'].text() == "" or tab['Theta'].text() == "":
                    self.x_real = np.round(self.pidevice.qPOS('1')['1'], 3)
                    yi = f"{np.round( self.pidevice.qPOS('2')['2'] * 1000, 3):.2f}"
                    z = f"{np.round(self.pidevice.qPOS('3')['3'] * 1000, 3 ):.2f}"
                    theta = f"{self.pidevice.qPOS('4')['4'] % 360:.2f}"   # Get the equivalent angle in the [0, 360]º range

                    tab['Yi'].setText(yi)
                    tab['Yi'].setAlignment(Qt.AlignLeft)
                    QTimer.singleShot(0, lambda: tab['Yi'].setCursorPosition(0))

                    # Display the inverted position of X
                    tab['X'].setText(f"{self.get_inverted_x_position(self.x_real) * 1000:.2f}")
                    tab['X'].setAlignment(Qt.AlignLeft)
                    QTimer.singleShot(0, lambda: tab['X'].setCursorPosition(0))

                    tab['Z'].setText(z)
                    tab['Z'].setAlignment(Qt.AlignLeft)
                    QTimer.singleShot(0, lambda: tab['Z'].setCursorPosition(0))

                    tab['Theta'].setText(theta)
                    tab['Theta'].setAlignment(Qt.AlignLeft)
                    QTimer.singleShot(0, lambda: tab['Theta'].setCursorPosition(0))
                
                # If they are all filled, take the stage to that position
                else: # tab['Yi'].text() and tab['Yf'].text() and tab['X'].text() and tab['Z'].text() and tab['Theta'].text() != "":
                    self.pidevice.MOV('1', self.get_inverted_x_position(float( tab['X'].text() ) / 1000 ) )
                    self.pidevice.MOV('2', float( tab['Yi'].text() ) / 1000 )
                    self.pidevice.MOV('3', float( tab['Z'].text() ) / 1000 )
                    self.pidevice.MOV('4', float( tab['Theta'].text() ) )

    def end_button_behaviour(self):
        """Fills the initial position parameters or moves the Stage"""
        
        # First check the correct tab to fill
        sender = self.sender()
        for tab in self.content_tabs:
            if tab['End'] is sender:

                # If at least one is empty, fill them up
                if tab['Yi'].text() == "" or tab['Yf'].text() == "" or tab['X'].text() == "" or tab['Theta'].text() == "":

                    yf = f"{np.round(self.pidevice.qPOS('2')['2']*1000, 3):.2f}"
                    tab['Yf'].setText(yf)

                # If they are all filled, take the stage to that position
                else: # tab['Yi'].text() and tab['Yf'].text() and tab['X'].text() and tab['Z'].text() and tab['Theta'].text() != "":
                    self.pidevice.MOV('1', self.get_inverted_x_position(float( tab['X'].text() ) / 1000 ) )
                    self.pidevice.MOV('2', float( tab['Yf'].text() ) / 1000 )
                    self.pidevice.MOV('3', float( tab['Z'].text() ) / 1000 )
                    self.pidevice.MOV('4', float( tab['Theta'].text() ) )

    def center_button_behaviour(self):
        """Moves the Stage to the Center position"""
        sender = self.sender()
        for tab in self.content_tabs:
            if tab['Center'] is sender:

                center_y = ( float(tab['Yi'].text()) + float(tab['Yf'].text()) ) / 2
                self.pidevice.MOV('1', self.get_inverted_x_position(float( tab['X'].text() ) / 1000 ) )
                self.pidevice.MOV('2', center_y / 1000 )
                self.pidevice.MOV('3', float( tab['Z'].text() ) / 1000 )
                self.pidevice.MOV('4', float( tab['Theta'].text() ) )


    def clear_button_behaviour(self):
        """Clears all of the line edits in a tab"""

        # First check the correct tab to fill
        sender = self.sender()
        for tab in self.content_tabs:
            if tab['Clear'] is sender:

                tab['Yi'].setText("")
                tab['Yf'].setText("")
                tab['X'].setText("")
                tab['Z'].setText("")
                tab['Theta'].setText("")
                tab['Ystep'].setText("")
                tab['Tpoints'].setText("1")
                tab['Tstep'].setText("")
                tab['Ttotal'].setText("")



    def on_frame_acquired(self, frame, camera_id, time_point, laser, z_position):
        self.frame_acquired.emit(frame, camera_id, time_point, laser, z_position)

    ##########################################################################################################
    # Time management function

    def _unit_to_seconds(self, unit: str) -> float:
        return {'seconds':1.0,'minutes':60.0,'hours':3600.0,'days':86400.0}[unit]

    def _best_unit(self, seconds: float) -> tuple[float,str]:
        for name,factor in (
            ('days',86400),('hours',3600),('minutes',60),('seconds',1)
        ):
            v = seconds/factor
            if v >= 1:
                return round(v,3), name
        return round(seconds,3), 'seconds'

    def _parse_int(self, le: QLineEdit) -> int|None:
        try: return int(le.text())
        except: return None

    def _parse_float(self, le: QLineEdit, unit: str) -> float|None:
        try: val = float(le.text())
        except: return None
        return val * self._unit_to_seconds(unit)

    def _on_time_change(self,
                        tp_le: QLineEdit,
                        ts_le: QLineEdit,
                        ts_cb: QComboBox,
                        tt_le: QLineEdit,
                        tt_cb: QComboBox,
                        changed: str):
        """
        Only when the user has touched two *different* controls in succession
        (e.g. edited 'points' then 'step'), calculate the 3rd.
        """
        if self._time_updating:
            return
        self._time_updating = True
        try:
            # 1) update your last/two‐ago tracker (ignore repeated same-changed)
            if changed != self._last_time_changed:
                self._prev_time_changed = self._last_time_changed
                self._last_time_changed = changed

            # 2) if we don't yet have two distinct fields, bail
            if self._prev_time_changed is None:
                return

            # 3) figure out which field to compute
            fields = {'points','step','total'}
            touched = {self._prev_time_changed, self._last_time_changed}
            missing = (fields - touched).pop()

            # 4) parse all current values
            tp = self._parse_int(tp_le)
            ts = self._parse_float(ts_le, ts_cb.currentText())
            tt = self._parse_float(tt_le, tt_cb.currentText())

            # 5) compute exactly that missing field:
            if missing == 'points':
                # need step + total
                if ts is None or tt is None or ts <= 0: return
                pt = int(tt/ts + 1)
                tp_le.blockSignals(True); tp_le.setText(str(pt)); tp_le.blockSignals(False)

            elif missing == 'step':
                # need points + total
                if tp is None or tp <= 1 or tt is None: return
                step_sec = tt/(tp - 1)
                val, unit = self._best_unit(step_sec)
                ts_cb.blockSignals(True); ts_le.blockSignals(True)
                ts_cb.setCurrentText(unit); ts_le.setText(str(val))
                ts_le.blockSignals(False); ts_cb.blockSignals(False)

            elif missing == 'total':
                # need points + step
                if tp is None or tp <= 1 or ts is None: return
                total_sec = (tp - 1)*ts
                val, unit = self._best_unit(total_sec)
                tt_cb.blockSignals(True); tt_le.blockSignals(True)
                tt_cb.setCurrentText(unit); tt_le.setText(str(val))
                tt_le.blockSignals(False); tt_cb.blockSignals(False)

        finally:
            self._time_updating = False


    #########################################################################################################################################
    # Updates function

    def updates(self):

        if self.is_acquiring:
            return
        


        # Update tab parameters
        for tab in self.content_tabs:
            yi_text = tab['Yi'].text().strip()
            yf_text = tab['Yf'].text().strip()
            # Update Y-size
            if yi_text and yf_text:
                try:
                    diff = abs(float(yf_text) - float(yi_text))
                    tab['Ysize'].setText(f"{diff:.3f}")
                except ValueError:
                    tab['Ysize'].setText("")
            else:
                tab['Ysize'].setText("")

            # Update Nsteps
            ystep_text = tab['Ystep'].text().strip()
            if yi_text and yf_text and ystep_text:
                try:
                    yi, yf, step = map(float, (yi_text, yf_text, ystep_text))
                    count = 1 if step == 0 else ( int( np.floor( np.round( abs(yf - yi) / step) ) ) + 1 ) or 1
                    tab['Nsteps'].setText(str(count))
                except ValueError:
                    tab['Nsteps'].setText("")
            else:
                tab['Nsteps'].setText("")

            # Update the Center Button
            if tab['Yi'].text() != "" and tab['Yf'].text() != "" and tab['X'].text() != "" and tab['Z'].text() != "" and tab['Theta'].text() != "":
                tab['Center'].setEnabled(True)
            else:
                tab['Center'].setEnabled(False)

        # Check if all tabs are complete
        all_tabs_complete = True
        self.tooltip_manager.attach_tooltip(self.start_button, "Starts the Acquisition.\nBecomes enabled when:\n- All of the coordinates are set.\n- The scanner's settings are selected.\n- The intented lasers are selected.\n- The Camera's filters are selected.\n- The intended Camera's are selected.")
        for tab in self.content_tabs:
            tp = tab['Tpoints'].text().strip()
            required = (
                tab['Yi'].text().strip() and
                tab['Yf'].text().strip() and
                tab['X'].text().strip() and
                tab['Z'].text().strip() and
                tab['Theta'].text().strip() and
                tab['Ystep'].text().strip() and
                tp
            )
            # If T-points >1, T-step must also be filled
            if not required or (tp not in ("0", "1") and not tab['Tstep'].text().strip()):
                all_tabs_complete = False
                break

            # Check if all of the devices parameters are set
                
                # Scanner

            self.selected_scan = self.scanner_widget.checkbox_scanner_select()
            self.selected_scan_top    = self.selected_scan['scan_top']
            self.selected_scan_bottom = self.selected_scan['scan_bottom']
            self.selected_mark_speed  = self.selected_scan['mark_speed']
            if self.selected_scan_top is None:
                all_tabs_complete = False
                break

                # Cameras
            self.camera_1_selected = False
            self.camera_2_selected = False

            if self.camera_widget_1 is not None:
                self.width_x_1, self.height_y_1, self.binning_1, self.dynamic_range_1 = self.camera_widget_1.checkbox_camera_select()
                if self.width_x_1 is not None:
                    self.camera_1_selected = True

            if self.camera_widget_2 is not None:
                self.width_x_2, self.height_y_2, self.binning_2, self.dynamic_range_2 = self.camera_widget_2.checkbox_camera_select()
                if self.width_x_2 is not None:
                    self.camera_2_selected = True

            if not (self.camera_1_selected or self.camera_2_selected):
                all_tabs_complete = False

                # Lasers
            self.selected_lasers, self.selected_laser_powers_mW, self.selected_filters1, self.selected_filters2 = self.lasers_widget.get_selected_lasers()
            self.selected_laser_powers_W = np.array(self.selected_laser_powers_mW) / 1000

            n_lasers = len(self.selected_lasers)

            # 1) Must pick at least one laser
            if n_lasers == 0:
                all_tabs_complete = False
                break

            # 2) Now enforce one filter per laser
            if self.camera_1_selected and not self.camera_2_selected:
                # wheel 1 must have n_lasers filters
                if len(self.selected_filters1) != n_lasers:
                    all_tabs_complete = False
                    break

            elif self.camera_2_selected and not self.camera_1_selected:
                # wheel 2 must have n_lasers filters
                if len(self.selected_filters2) != n_lasers:
                    all_tabs_complete = False
                    break

            elif self.camera_1_selected and self.camera_2_selected:
                # both wheels must have n_lasers filters
                if (len(self.selected_filters1)  != n_lasers or
                    len(self.selected_filters2)  != n_lasers):
                    all_tabs_complete = False
                    break

        # Finally, update the start button state based on all tabs' completeness
        self.start_button.setEnabled(all_tabs_complete)

        if all_tabs_complete:
            # 1) detach any old tooltip
            self.tooltip_manager.detach_tooltip(self.start_button)

            # 2) scanner parameters
            scan   = self.scanner_widget.checkbox_scanner_select()
            top    = scan['scan_top']
            bottom = scan['scan_bottom']
            speed  = scan['mark_speed']

            # 3) laser + filter lists
            lasers = self.selected_lasers
            powers = self.selected_laser_powers_mW
            f1s    = self.selected_filters1
            f2s    = self.selected_filters2

            # 4) lookup tables
            LASER_WL = {2: "640 nm", 3: "561 nm", 4: "488 nm", 5: "405 nm"}
            FILTER_N = {
                0: "DAPI", 1: "GFP", 2: "YFP",
                3: "Alexa568", 4: "Alexa647", 5: "Empty"
            }

            # 5) build the “- …” laser lines (preserve original order)
            lines = []
            for idx, power, f1, f2 in zip_longest(lasers, powers, f1s, f2s, fillvalue=None):
                wl = LASER_WL.get(idx, f"{idx} nm")

                slots  = [f for f in (f1, f2) if f is not None]
                chosen = [FILTER_N[f] for f in slots if FILTER_N[f] != "Empty"]

                if chosen:
                    if len(chosen) == 1:
                        suffix = f", and {chosen[0]} filter"
                    else:
                        suffix = ", and " + ", ".join(chosen) + " filters"
                else:
                    if   len(slots) == 1: suffix = ", and no filter"
                    elif len(slots) >= 2: suffix = ", and no filters"
                    else:                 suffix = ""

                lines.append(f"- {wl} with {power} mW{suffix}")

            # 6) assemble header + lasers block
            header = (
                "The selected parameters are:\n\n"
                f"Scanner:\n- Top: {top}\n- Bottom: {bottom}\n- Speed: {speed}\n\n"
                "Lasers:\n"
            )
            tooltip_text = header + "\n".join(lines)

            # 7) Camera 1 parameters

            if self.camera_widget_1 is not None:
                w1, h1, bin1, dr1 = self.camera_widget_1.checkbox_camera_select()
                if None not in (w1, h1, bin1, dr1):
                    cam1_lines = [
                        f"- Format: {w1} x {h1};",
                        f"- Binning: {bin1} x {bin1};",
                        f"- Dynamic Range: {dr1} bits"
                    ]
                    tooltip_text += "\n\nCamera 1:\n" + "\n".join(cam1_lines)

            # 8) Camera 2 parameters

            if self.camera_widget_2 is not None:
                w2, h2, bin2, dr2 = self.camera_widget_2.checkbox_camera_select()
                if None not in (w2, h2, bin2, dr2):
                    cam2_lines = [
                        f"- Format: {w2} x {h2};",
                        f"- Binning: {bin2} x {bin2};",
                        f"- Dynamic Range: {dr2} bits"
                    ]
                    tooltip_text += "\n\nCamera 2:\n" + "\n".join(cam2_lines)

            # 9) attach the fully rendered tooltip
            self.tooltip_manager.attach_tooltip(
                self.start_button,
                tooltip_text
            )

    #########################################################################################################################################

    def get_zstackwidget_parameters(self):
        """Function that gives all of the parameters in all of the available tabs"""

        zstackwidget_parameters = []

        for widgets in self.content_tabs:
            parameters = {
                'mode_yl': widgets['Mode Yl'].isChecked(),
                'mode_ly': widgets['Mode lY'].isChecked(),
                'yi': float(widgets['Yi'].text()),
                'yf': float(widgets['Yf'].text()),
                'x': float(widgets['X'].text()),
                'z': float(widgets['Z'].text()),
                'theta': float(widgets['Theta'].text()),
                'Ystep': float(widgets['Ystep'].text()),
                'Nsteps': int(widgets['Nsteps'].text()),
                'Tpoints': int(widgets['Tpoints'].text()),
                'Tstep': float(widgets['Tstep'].text() or "0"),
                'Tstep_unit': widgets['Tstep unit'].currentText()
            }

            zstackwidget_parameters.append(parameters)

        return zstackwidget_parameters
    
    def start_acquisition(self):

        threading.current_thread().name = "ACQUISITION"

        logger.info(
        "Acquisition starts and will be saved in %s",
        str(self.current_save_directory),
        )

        self.is_acquiring = True

        # Step 1: read the exact camera mode selected for acquisition.
        acq_camera_mode = self._get_selected_acquisition_camera_mode()
        if acq_camera_mode is None:
            self.is_acquiring = False
            QMessageBox.warning(
                self,
                "Acquisition Mode",
                "Please select at least one camera and make sure all selected cameras use the same mode."
            )
            return

        # Step 2: reject unsupported acquisition modes.
        if acq_camera_mode == "Internal Trigger":
            self.is_acquiring = False
            QMessageBox.warning(
                self,
                "Acquisition Mode",
                "Y-stack acquisition is only available with 'Widefield Mode' or 'Confocal Mode'."
            )
            return

        # Step 3: freeze all stack parameters BEFORE the main window starts shutting things down.
        zstackwidget_parameters = self.get_zstackwidget_parameters()

        # Step 4: define acquisition order now.
        # Hard-code order 2 - the dif.timepoints function will not be usable through GUI
        order = 2

        # Step 5: create the worker BEFORE emitting acquisition_started.
        # This is critical because the worker constructor reads:
        # - selected lasers
        # - scanner parameters
        # - selected camera parameters
        # and we want that snapshot before before_acquisition() turns outputs off.
        self.thread = QThread(self)
        self.worker = YStackWorker(
            True,
            zstackwidget_parameters,
            self.current_save_directory,
            self.filterwheel1, self.filterwheel2, self.laserbox, self.rtc5_board, self.pidevice,
            self.camera1, self.camera2, self.camera_1_selected, self.camera_2_selected,
            self.camera_widget_1, self.camera_widget_2,
            self.lasers_widget, self.scanner_widget, self,
            acq_camera_mode=acq_camera_mode,
        )
        self.worker.moveToThread(self.thread)

        # Step 6: now let the main window disable UI / stop interactive scanner mode.
        self.acquisition_started.emit()

        # Step 7: prepare the scanner / laser system AFTER before_acquisition().
        # This ensures the LS/RS mode is not immediately undone by pushbutton stop logic.
        if self.scanner_widget is not None:
            if acq_camera_mode == "Widefield Mode":
                ok = self.scanner_widget.prepare_lightsheet_mode_for_acquisition(timeout_ms=5000)
                if not ok:
                    self.is_acquiring = False
                    QMessageBox.warning(
                        self,
                        "Widefield Mode",
                        "Failed to switch the lasers into Widefield mode. Acquisition was aborted."
                    )
                    return

            elif acq_camera_mode == "Confocal Mode":
                ok = self.scanner_widget.prepare_rolling_shutter_mode_for_acquisition(timeout_ms=5000)
                if not ok:
                    self.is_acquiring = False
                    QMessageBox.warning(
                        self,
                        "Confocal Mode",
                        "Failed to switch the lasers into Confocal Mode. Acquisition was aborted."
                    )
                    return

        # Step 8: connect the thread after the system is fully ready.
        self.thread.started.connect(self.worker.run)
        self.worker.frame_acquired.connect(self.on_frame_acquired)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.on_acq_finished)

        self.worker.cancelled.connect(self.thread.quit)
        self.worker.cancelled.connect(self.on_acq_cancelled)

        self.worker.error.connect(self.thread.quit)
        self.worker.error.connect(self.on_acq_error)

        # Step 9: progress dialog.
        self._grand_total = 0
        for p in zstackwidget_parameters:
            total_slices = p['Nsteps']
            total_timep = p['Tpoints']
            lasers, _, _, _ = self.lasers_widget.get_selected_lasers()
            total_ch = len(lasers)
            self._grand_total += total_timep * total_ch * total_slices

        self._progress_counter = 0
        self.progress_dialog = AcquisitionProgress_Dialog(self._grand_total, order, self)
        self.progress_dialog.setModal(False)
        self.progress_dialog.setWindowModality(Qt.NonModal)

        self.worker.slice_changed.connect(self.progress_dialog.update_slice)
        self.worker.slice_changed.connect(self._on_any_slice)
        self.worker.channel_changed.connect(self.progress_dialog.update_channel)
        self.worker.timepoint_changed.connect(self.progress_dialog.update_timepoint)
        self.worker.position_changed.connect(self.progress_dialog.update_position)
        self.worker.finished.connect(self.progress_dialog.accept)
        self.worker.cancelled.connect(self.progress_dialog.accept)
        self.worker.error.connect(self.progress_dialog.accept)

        self.progress_dialog.stop_button.clicked.connect(lambda: self.worker.stop())
        self.progress_dialog.discard_button.clicked.connect(lambda: self.worker.discard())
        self.progress_dialog.show()

        # Step 10: start acquisition only after everything is stable.
        self.thread.start()


    ###########################################################################################
    # Widget Construction

    def __init__(self, save_directory,
                filterwheel1, filterwheel2, laserbox, rtc5_board, pidevice, camera1=None, camera2=None,
                lasers_widget=None, scanner_widget=None, camera_widget_1=None, camera_widget_2=None):
        super().__init__()
        self.setWindowTitle("Y-Stack Acquisition")

        # For the time handling logic
        self._prev_time_changed = None
        self._last_time_changed = None
        self._time_updating = False

        # Initialize the tooltip manager
        self.tooltip_manager = CustomToolTipManager(self)

        # Initialize the devices as global variables
        self.filterwheel1 = filterwheel1
        self.filterwheel2 = filterwheel2
        self.laserbox = laserbox
        self.rtc5_board = rtc5_board
        self.pidevice = pidevice
        self.camera1 = camera1
        self.camera2 = camera2

        self.lasers_widget = lasers_widget
        self.scanner_widget = scanner_widget
        self.camera_widget_1 = camera_widget_1
        self.camera_widget_2 = camera_widget_2

        # set the limits of operation of the stages
        self.x_max = self.pidevice.qTMX('1')['1'] * 1000
        self.x_min = self.pidevice.qTMN('1')['1'] * 1000

        self.y_max = self.pidevice.qTMX('2')['2'] * 1000
        self.y_min = self.pidevice.qTMN('2')['2'] * 1000

        self.z_max = self.pidevice.qTMX('3')['3'] * 1000
        self.z_min = 1

        self.current_save_directory = save_directory

        self.setStyleSheet("""
            QWidget {
                background-color: #222222;
                color: white;
            }

            QLabel {
                color: white;
            }

        """)

        # Initialize the tabs dictionary
        self.content_tabs = []

        self.curent_save_directory = save_directory

        # Flags
        self.initializing = True
        self.block_tab_changed = False
        self.is_acquiring = False

        # Global variable to save the X real position
        self.x_real = 0

        # Create main layout
        self.layout = QVBoxLayout(self)

        #-------------------------------------------------------------------------------------
        # Multi-Positions Checkbox

        self.multipositions_checkbox = QCheckBox(" Acquire all positions at each time point")
        self.multipositions_checkbox.setChecked(True)
        # Do not add this widget.
        # self.layout.addWidget(self.multipositions_checkbox)
        self.layout.addSpacing(10)
            # Propagator for the multi-positions in the same time-point
        self.multipositions_checkbox.toggled.connect(self.on_multipositions_toggled)

        script_path = Path(__file__).resolve()
        check_icon  = script_path.parent / "icons" / "check.png"
        self.multipositions_checkbox.setStyleSheet(f"""
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
                image: url("{check_icon.as_posix()}");
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

        # Experiment Name
        self.exp_name_widget = QWidget()
        self.exp_name_layout = QHBoxLayout()
        self.exp_name_layout.setContentsMargins(0, 0, 5, 5)
        self.exp_name_widget.setLayout(self.exp_name_layout)

        self.exp_name_label = QLabel("Experiment Name :  ")
        self.exp_name_lineedit = QLineEdit("")
        self.exp_name_lineedit.setFixedHeight(26)
        #self.exp_name_lineedit.setFixedWidth(200)
        self.exp_name_lineedit.returnPressed.connect(self.exp_name_lineedit.clearFocus)
        self.exp_name_lineedit.setStyleSheet("""
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

        self.exp_name_layout.addWidget(self.exp_name_label)
        self.exp_name_layout.addWidget(self.exp_name_lineedit)
        #self.exp_name_layout.addStretch(1)

        self.layout.addWidget(self.exp_name_widget)

        #-------------------------------------------------------------------------------------
        # Create the Tab Widget

        # Remove the checkbox and make this value True
        self.acquire_all_positions_at_each_timepoint = True

        self.tab_widget = CustomTabWidget()
            # Function to change the tab
        self.tab_widget.currentChanged.connect(self.handle_tab_changed)

        self.tab_widget.setStyleSheet("""
 
            QTabWidget::pane {
                border: 2px solid #777777;  /* lighter border */
                background: #444444;        /* optional: darker background if you want it */
                border-radius: 10px;        /* make it nicely rounded */
            }

            QTabWidget::tab-bar:top {
                top: -1px;
            }

            QTabWidget::tab-bar:bottom {
                bottom: 1px;
            }

            QTabWidget::tab-bar:left {
                right: 1px;
            }

            QTabWidget::tab-bar:right {
                left: 1px;
            }

            QTabBar::tab {
                border: 1px solid #777777;
            }

            QTabBar::tab:selected {
                background: #464646;
            }

            QTabBar::tab:!selected {
                background: #303030;
            }

            QTabBar::tab:!selected:hover {
                background: #464646;
            }

            QTabBar::tab:top:!selected {
                margin-top: 3px;
                border-top: none;
            }

            QTabBar::tab:bottom:!selected {
                margin-bottom: 3px;
            }

            QTabBar::tab:top, QTabBar::tab:bottom {
                min-width: 8ex;
                margin-right: -1px;
                padding: 5px 10px 5px 10px;
            }

            QTabBar::tab:top:selected {
                border-bottom-color: none;
            }

            QTabBar::tab:bottom:selected {
                border-top-color: none;
            }

            QTabBar::tab:top:last, QTabBar::tab:bottom:last,
            QTabBar::tab:top:only-one, QTabBar::tab:bottom:only-one {
                margin-right: 0;
            }

            QTabBar::tab:left:!selected {
                margin-right: 3px;
            }

            QTabBar::tab:right:!selected {
                margin-left: 3px;
            }

            QTabBar::tab:left, QTabBar::tab:right {
                min-height: 8ex;
                margin-bottom: -1px;
                padding: 10px 5px 10px 5px;
            }

            QTabBar::tab:left:selected {
                border-left-color: none;
            }

            QTabBar::tab:right:selected {
                border-right-color: none;
            }

            QTabBar::tab:left:last, QTabBar::tab:right:last,
            QTabBar::tab:left:only-one, QTabBar::tab:right:only-one {
                margin-bottom: 0;
            }
                                      
            QTabWidget::pane {
                border: 2px solid #777777;     /* lighter border */
                background: #444444;           /* dark background */
                border-radius: 10px;           /* rounded corners */
            }

            /* This removes the ugly inner square */
            QTabWidget > QWidget {
                background-color: transparent; /* match outer background */
                border: none;                  /* no internal frame */
            }
        """)


            # Add the tab widget to the main layout
        self.layout.addWidget(self.tab_widget)

        # Create the Update thread
        self.update_thread = QThread()
        self.update_worker = UpdateWorker(self.pidevice)
        self.update_worker.moveToThread(self.update_thread)
        self.update_thread.started.connect(self.update_worker.start_updates)
        #self.update_worker.update_signal.connect(self.opengl_widget.set_z_position)
        self.update_thread.start()

            # Add tabs in the Tab Widget
        self.add_content_tab()
        self.add_plus_tab()
        self.update_tab_labels()

        #-------------------------------------------------------------------------------------
        # Bottom layout
        self.bottom_layout = QHBoxLayout()

            # Estimated Time Label
        self.estimated_time_label = QLabel(
            "<b>Estimated Time:</b> XX h, XX min. and XX sec."
        )
        self.estimated_time_label.setStyleSheet("font-size: 13px;")
            # Start Button
        self.start_button = QPushButton("Start Acquisition")
        self.tooltip_manager.attach_tooltip(self.start_button, "Starts the Acquisition. Becomes enabled when:\n- All of the coordinates are set.\n- The scanner's settings are selected.\n- The intented lasers are selected.\n- The Camera's filters are selected.\n- The intended Camera's are selected.")
        self.start_button.clicked.connect(self.get_zstackwidget_parameters)
        self.start_button.clicked.connect(self.start_acquisition)
        self.start_button.setFixedSize(140, 30)
        self.start_button.setDisabled(True)
        self.start_button.setStyleSheet("""
                QPushButton {
                    background-color: #2E2E2E;
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

            # Add widgets to the Bottom Layout
        #self.bottom_layout.addWidget(self.estimated_time_label)
        self.bottom_layout.addStretch()
        self.bottom_layout.addWidget(self.start_button)

            # Add bottom layout to the main layout
        self.layout.addLayout(self.bottom_layout)

        self.initializing = False

        # Timer to update the GUI
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updates)
        
        # Start the timer with an interval of 50 milliseconds (0.05 second)
        self.timer.start(50)


    def on_multipositions_toggled(self, checked: bool):
        """When checked==True, copy tab-0’s time settings into every tab."""

        if not checked or not self.content_tabs:
            return

        # Pull the “master” values from the first tab…
        first = self.content_tabs[0]
        for key in ('Tpoints', 'Tstep', 'Ttotal'):
            val = first[key].text()
            self.propagate_field(key, val)
        for key in ('Tstep unit', 'Ttotal unit'):
            txt = first[key].currentText()
            self.propagate_field(key, txt)

    def propagate_field(self, field_key, new_value):
        """Copy new_value into every tab’s widget (line‐edit or combo‐box) except where it came from."""

        if not self.acquire_all_positions_at_each_timepoint:
            return
        
        for tab in self.content_tabs:
            widget = tab[field_key]
            if isinstance(widget, QLineEdit):
                if widget.text() != new_value:
                    widget.blockSignals(True)
                    widget.setText(new_value)
                    widget.blockSignals(False)
            elif isinstance(widget, QComboBox):
                if widget.currentText() != new_value:
                    widget.blockSignals(True)
                    widget.setCurrentText(new_value)
                    widget.blockSignals(False)

    def propagate_acquisition_mode(self, mode_key):
        """Copy selected acquisition mode to every tab."""
        other_key = 'Mode lY' if mode_key == 'Mode Yl' else 'Mode Yl'

        for tab in self.content_tabs:
            selected_button = tab[mode_key]
            other_button = tab[other_key]

            selected_button.blockSignals(True)
            other_button.blockSignals(True)

            selected_button.setChecked(True)
            other_button.setChecked(False)

            selected_button.blockSignals(False)
            other_button.blockSignals(False)


    def add_content_tab(self):
        """Function that is linked to the "Add new Tab" Tab"""

        # Double Float Validator
        validator = QDoubleValidator()
        validator.setLocale(QLocale(QLocale.English))

        # 0. Main layout
        self.main_layout = QVBoxLayout()

        new_tab = QWidget()
        new_tab.setStyleSheet("""
            background-color: transparent;
            border: none;
        """)

        new_tab.setLayout(self.main_layout)

        #--------------------------------------------------------------------------------

        # 1.0. Mode Widget

        self.mode_widget = QWidget()
        self.mode_widget_layout = QHBoxLayout()
        self.mode_widget.setLayout(self.mode_widget_layout)

        # 1.0.1. Mode Label
        self.mode_label = QLabel("Mode: ")
        self.mode_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
            }
        """)

        # 1.0.2. Yl Mode Button
        mode_yl_button = QPushButton("Y λ")
        mode_yl_button.setCheckable(True)
        mode_yl_button.setAutoExclusive(True)
        mode_yl_button.setStyleSheet("""
                        QPushButton {
                            background-color: #2E2E2E;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 12px;
                            padding: 4px 16px;
                            font-size: 13px;
                            outline: none;
                            font-weight: bold;
                            font-style: italic;
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



        # 1.0.2. lY Mode Button
        mode_ly_button = QPushButton("λ Y")
        mode_ly_button.setCheckable(True)
        mode_ly_button.setChecked(True)
        mode_ly_button.setAutoExclusive(True)
        mode_ly_button.setStyleSheet("""
                        QPushButton {
                            background-color: #2E2E2E;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 12px;
                            padding: 4px 16px;
                            font-size: 13px;
                            outline: none;
                            font-weight: bold;
                            font-style: italic;
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

        # 1.0.4. Button Group
        mode_button_group = QButtonGroup()
        mode_button_group.setExclusive(True)
        mode_button_group.addButton(mode_ly_button)
        mode_button_group.addButton(mode_yl_button)
        

        # 1.0.5. Remove_Tab Button
        remove_button = QPushButton()
        remove_button.setFixedSize(20, 20)
        remove_button.setIcon(QIcon("icons//close.png"))
        remove_button.setIconSize(QSize(12, 12))
        remove_button.clicked.connect(lambda _, tab=new_tab: self.remove_tab(tab))
        remove_button.setStyleSheet("""
            QPushButton {
                background-color: #8B2222;   /* Dark red */
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #A30000;
            }
            QPushButton:pressed {
                background-color: #5C0000;
            }
        """)

        self.mode_widget_layout.setSpacing(1)
        self.mode_widget_layout.addWidget(self.mode_label)
        self.mode_widget_layout.addWidget(mode_ly_button)
        self.mode_widget_layout.addWidget(mode_yl_button)
        self.mode_widget_layout.addSpacing(222)
        self.mode_widget_layout.addWidget(remove_button)


        #--------------------------------------------------------------------------------

        # 2. OpenGL Widget
        self.opengl_widget = ZUpStageWidget(width=1.25, depth=1.25, height=5)
        self.opengl_widget.setMinimumSize(300, 180)
        self.update_worker.update_signal.connect(self.opengl_widget.set_z_position)
        

        #-------------------------------------------------------------------------------

        # 2.1. Buttons Widget

        self.buttons_widget = QWidget()
        self.buttons_widget_layout = QHBoxLayout()
        self.buttons_widget.setLayout(self.buttons_widget_layout)

        # 2.1.1. Begin Button
        begin_button = QPushButton("Begin")
        begin_button.setFixedSize(70, 30)
        begin_button.clicked.connect(self.begin_button_behaviour)
        begin_button.setStyleSheet("""
                        QPushButton {
                            background-color: #2E2E2E;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 12px;
                            padding: 0px 16px;
                            font-size: 13px;
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
        

        # 2.1.2 End Button
        end_button = QPushButton("End")
        end_button.setStyleSheet("font-size: 13px;")
        end_button.setFixedSize(70, 30)
        end_button.clicked.connect(self.end_button_behaviour)
        end_button.setStyleSheet("""
                        QPushButton {
                            background-color: #2E2E2E;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 12px;
                            padding: 0px 16px;
                            font-size: 13px;
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

        # 2.1.3 Center Button
        center_button = QPushButton("Center")
        center_button.setStyleSheet("font-size: 13px;")
        center_button.setFixedHeight(30)
        center_button.clicked.connect(self.center_button_behaviour)
        center_button.setDisabled(True)
        center_button.setStyleSheet("""
                        QPushButton {
                            background-color: #2E2E2E;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 12px;
                            padding: 0px 16px;
                            font-size: 13px;
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

        # 2.1.4. Clear Button
        clear_button = QPushButton("Clear")
        clear_button.setFixedSize(70, 30)
        clear_button.clicked.connect(self.clear_button_behaviour)
        clear_button.setStyleSheet("""
                        QPushButton {
                            background-color: #2E2E2E;
                            color: white;
                            border: 2px solid #555;
                            border-radius: 12px;
                            padding: 0px 16px;
                            font-size: 13px;
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
        


        self.buttons_widget_layout.addWidget(begin_button)
        self.buttons_widget_layout.addWidget(end_button)
        self.buttons_widget_layout.addWidget(center_button)
        self.buttons_widget_layout.addSpacing(118)
        self.buttons_widget_layout.addWidget(clear_button)

        #--------------------------------------------------------------------------------

        # 2.2. Ys Widget

        self.Y_parameters_widget = QWidget()
        self.Y_parameters_widget_layout = QGridLayout()
        self.Y_parameters_widget.setLayout(self.Y_parameters_widget_layout)
        self.Y_parameters_widget.setSizePolicy(
            QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        )
        self.Y_parameters_widget_layout.setContentsMargins(9,0,0,0)
        self.Y_parameters_widget_layout.setSpacing(7)

        # 2.2.1. Initial Y

        self.font = QFont("Segoe UI", 9)

        Yi_label = QLabel("<i>Y<sub>i</sub></i> :")
        Yi_label.setTextFormat(Qt.TextFormat.RichText)
        Yi_label.setFont(self.font)

        y_validator = ClampingDoubleValidator(self.y_min, self.y_max, 3, parent=self)

        Yi_lineedit = CustomLineEdit()
        Yi_lineedit.setFixedWidth(80)
        Yi_lineedit.setFixedHeight(21)
        Yi_lineedit.setAlignment(Qt.AlignLeft)
        Yi_lineedit.setValidator(y_validator)
        Yi_lineedit.returnPressed.connect(Yi_lineedit.clearFocus)
        Yi_lineedit.setStyleSheet("""
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

        Yi_unit_label = QLabel("μm")
        Yi_unit_label.setTextFormat(Qt.TextFormat.RichText)
        Yi_unit_label.setFont(self.font)

        self.Y_parameters_widget_layout.addWidget(Yi_label, 0, 0)
        self.Y_parameters_widget_layout.addWidget(Yi_lineedit, 0, 1)
        self.Y_parameters_widget_layout.addWidget(Yi_unit_label, 0, 2, alignment=Qt.AlignLeft)

        # 2.2.2. Final Y

        Yf_label = QLabel("<i>Y<sub>f</sub></i> :")
        Yf_label.setTextFormat(Qt.TextFormat.RichText)
        Yf_label.setFont(self.font)

        Yf_lineedit = CustomLineEdit()
        Yf_lineedit.setFixedWidth(80)
        Yf_lineedit.setFixedHeight(21)
        Yf_lineedit.setAlignment(Qt.AlignLeft)
        Yf_lineedit.setValidator(y_validator)
        Yf_lineedit.returnPressed.connect(Yf_lineedit.clearFocus)
        Yf_lineedit.setStyleSheet("""
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

        Yf_unit_label = QLabel("μm")
        Yf_unit_label.setTextFormat(Qt.TextFormat.RichText)
        Yf_unit_label.setFont(self.font)

        self.Y_parameters_widget_layout.addWidget(Yf_label, 1, 0)
        self.Y_parameters_widget_layout.addWidget(Yf_lineedit, 1, 1)
        self.Y_parameters_widget_layout.addWidget(Yf_unit_label, 1, 2, alignment=Qt.AlignLeft)

        # 2.2.3. Y size

        Ysize_widget = QWidget()
        Ysize_widget_layout = QHBoxLayout()
        Ysize_widget_layout.setContentsMargins(9,0,0,0)
        Ysize_widget.setLayout(Ysize_widget_layout)
        Ysize_widget_layout.setSpacing(3)


            #2.2.3.1 Y size Label
        Ysize_label = QLabel("<i>Y</i> size : ")
        Ysize_label.setTextFormat(Qt.TextFormat.RichText)
        Ysize_label.setFont(self.font)

            #2.2.3.1 Y size
        Ysize = QLabel("")
        Ysize.setFixedWidth(50)
        Ysize.setAlignment(Qt.AlignRight)
        Ysize_unit_label = QLabel("μm")
        Ysize_unit_label.setTextFormat(Qt.TextFormat.RichText)

            # add the widgets to the layout
        Ysize_widget_layout.addWidget(Ysize_label)
        Ysize_widget_layout.addSpacing(46)
        Ysize_widget_layout.addWidget(Ysize)
        Ysize_widget_layout.addSpacing(5)
        Ysize_widget_layout.addWidget(Ysize_unit_label)

        # 2.3 XZTheta Widget

        self.XZTheta_parameters_widget = QWidget()
        self.XZTheta_parameters_widget_layout = QGridLayout()
        self.XZTheta_parameters_widget.setLayout(self.XZTheta_parameters_widget_layout)
        self.XZTheta_parameters_widget.setSizePolicy(
            QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        )
        self.XZTheta_parameters_widget_layout.setSpacing(7)
        self.XZTheta_parameters_widget_layout.setContentsMargins(9,0,0,9)

        # 2.3.3. X

        X_label = QLabel("<i>X</i> :")
        X_label.setTextFormat(Qt.TextFormat.RichText)
        X_label.setFont(self.font)

        x_validator = ClampingDoubleValidator(0, self.x_max, 3, parent=self)

        X_lineedit = CustomLineEdit()
        X_lineedit.setFixedWidth(80)
        X_lineedit.setFixedHeight(21)
        X_lineedit.setValidator(x_validator)
        X_lineedit.setAlignment(Qt.AlignLeft)
        X_lineedit.returnPressed.connect(X_lineedit.clearFocus)
        X_lineedit.setStyleSheet("""
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

        X_unit_label = QLabel("μm")
        X_unit_label.setTextFormat(Qt.TextFormat.RichText)
        X_unit_label.setFont(self.font)

        self.XZTheta_parameters_widget_layout.addWidget(X_label, 0, 0)
        self.XZTheta_parameters_widget_layout.addWidget(X_lineedit, 0, 1)
        self.XZTheta_parameters_widget_layout.addWidget(X_unit_label, 0, 2, alignment=Qt.AlignLeft)

        # 2.2.4. Z

        Z_label = QLabel("<i>Z</i> :")
        Z_label.setTextFormat(Qt.TextFormat.RichText)
        Z_label.setFont(self.font)

        z_validator = ClampingDoubleValidator(self.z_min, self.z_max, 3, parent=self)

        Z_lineedit = CustomLineEdit()
        Z_lineedit.setFixedWidth(80)
        Z_lineedit.setFixedHeight(21)
        Z_lineedit.setValidator(z_validator)
        Z_lineedit.returnPressed.connect(Z_lineedit.clearFocus)
        Z_lineedit.setStyleSheet("""
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

        Z_unit_label = QLabel("μm")
        Z_unit_label.setTextFormat(Qt.TextFormat.RichText)
        Z_unit_label.setFont(self.font)

        self.XZTheta_parameters_widget_layout.addWidget(Z_label, 1, 0)
        self.XZTheta_parameters_widget_layout.addWidget(Z_lineedit, 1, 1)
        self.XZTheta_parameters_widget_layout.addWidget(Z_unit_label, 1, 2, alignment=Qt.AlignLeft)

        # 2.2.5. Theta
        theta_label = QLabel("<i>θ</i> :")
        theta_label.setTextFormat(Qt.TextFormat.RichText)
        theta_label.setFont(self.font)

        theta_lineedit = CustomLineEdit()
        theta_lineedit.setFixedWidth(80)
        theta_lineedit.setFixedHeight(21)
        theta_lineedit.setValidator(validator)
        theta_lineedit.setAlignment(Qt.AlignLeft)
        theta_lineedit.returnPressed.connect(theta_lineedit.clearFocus)
        theta_lineedit.setStyleSheet("""
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

        theta_unit_label = QLabel("degrees")
        theta_unit_label.setTextFormat(Qt.TextFormat.RichText)

        self.XZTheta_parameters_widget_layout.addWidget(theta_label, 2, 0)
        self.XZTheta_parameters_widget_layout.addWidget(theta_lineedit, 2, 1)
        self.XZTheta_parameters_widget_layout.addWidget(theta_unit_label, 2, 2, alignment=Qt.AlignLeft)

        #--------------------------------------------------------------------------------

        # 2.3. Parameters Widget

        self.parameters_widget = QWidget()
        self.parameters_widget_layout = QGridLayout()
        self.parameters_widget.setLayout(self.parameters_widget_layout)
        self.parameters_widget.setSizePolicy(
            QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        )
        self.parameters_widget_layout.setSpacing(7)

        # 2.3.1. Y step

        Ystep_label = QLabel("<i>Y</i> step : ")
        Ystep_label.setTextFormat(Qt.TextFormat.RichText)
        Ystep_label.setFont(self.font)

        Ystep_lineedit = CustomLineEdit()
        Ystep_lineedit.setFixedWidth(80)
        Ystep_lineedit.setFixedHeight(21)
        Ystep_lineedit.setValidator(validator)
        Ystep_lineedit.returnPressed.connect(Ystep_lineedit.clearFocus)
        Ystep_lineedit.setStyleSheet("""
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

        Ystep_unit_label = QLabel("μm")
        Ystep_unit_label.setTextFormat(Qt.TextFormat.RichText)
        Ystep_unit_label.setFont(self.font)

        self.parameters_widget_layout.addWidget(Ystep_label, 0, 0)
        self.parameters_widget_layout.addWidget(Ystep_lineedit, 0, 1)
        self.parameters_widget_layout.addWidget(Ystep_unit_label, 0, 2, alignment=Qt.AlignLeft)

        # 2.3.2 Number of Steps

        N_steps_label = QLabel("Nº steps : ")

        number_of_steps = QLabel("")

        self.parameters_widget_layout.addWidget(N_steps_label, 1, 0)
        self.parameters_widget_layout.addWidget(number_of_steps, 1, 1)
        
        # 2.3.3. Time Points

        time_points_label = QLabel("<i>t</i> points : ")
        time_points_label.setTextFormat(Qt.TextFormat.RichText)

        time_points_lineedit = CustomLineEdit()
        time_points_lineedit.setFixedWidth(80)
        time_points_lineedit.setFixedHeight(21)
        time_points_lineedit.setText("1")
        time_points_lineedit.setValidator(QIntValidator(1, 2147483647))
        time_points_lineedit.textChanged.connect(self.time_points_lineedit_behaviour)
        time_points_lineedit.returnPressed.connect(time_points_lineedit.clearFocus)
        time_points_lineedit.setStyleSheet("""
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

        self.parameters_widget_layout.addWidget(time_points_label, 2, 0)
        self.parameters_widget_layout.addWidget(time_points_lineedit, 2, 1)

        # 2.3.4. Time Step

        time_step_label = QLabel("<i>t</i> frame : ")
        time_step_label.setTextFormat(Qt.TextFormat.RichText)

        time_step_lineedit = CustomLineEdit()
        time_step_lineedit.setFixedWidth(80)
        time_step_lineedit.setFixedHeight(21)
        time_step_lineedit.setValidator(validator)
        time_step_lineedit.returnPressed.connect(time_step_lineedit.clearFocus)
        time_step_lineedit.setStyleSheet("""
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

        time_step_unit_combobox = QComboBox()
        time_step_unit_combobox.addItem("seconds")
        time_step_unit_combobox.addItem("minutes")
        time_step_unit_combobox.addItem("hours")
        time_step_unit_combobox.addItem("days")
        time_step_unit_combobox.setFixedWidth(75)
        time_step_unit_combobox.setFixedHeight(22)

        script_path        = Path(__file__).resolve()
        btn_down_fp        = script_path.parent / "icons" / "button_down.png"
        btn_down_disabled_fp = script_path.parent / "icons" / "button_down_disabled.png"
        time_step_unit_combobox.setStyleSheet(f"""
            QComboBox {{
                background-color: #333333;  
                color: white;
                border: 1px solid #555555;
                border-radius: 3px;
            }}

            QComboBox QAbstractItemView {{
                background-color: #383838;
                color: white;
                selection-background-color: #555555;
            }}

            QComboBox::drop-down {{
                width: 20px;
                background-color: #505050;
                border-left: 1px solid #555555;
            }}

            /* Drop-down Arrow */
            QComboBox::down-arrow {{
                image: url("{btn_down_fp.as_posix()}");
                width: 12px;
                height: 12px;
            }}

            /* Disabled QComboBox */
            QComboBox:disabled {{
                background-color: #303030;  /* Darker background to indicate it's disabled */
                color: #777777;              /* Dimmed text */
                border: 1px solid #444444;   /* Less prominent border */
                border-radius: 3px;
            }}

            QComboBox::drop-down:disabled {{
                background-color: #303030;  /* Match the background */
                border-left: 1px solid #333333;  /* Subtler border */
                border-radius: 3px;
            }}

            QComboBox::down-arrow:disabled {{
                image: url("{btn_down_disabled_fp.as_posix()}");
                width: 12px;
                height: 12px;
            }}
        """)

        self.parameters_widget_layout.addWidget(time_step_label, 3, 0)
        self.parameters_widget_layout.addWidget(time_step_lineedit, 3, 1)
        self.parameters_widget_layout.addWidget(time_step_unit_combobox, 3, 2, alignment=Qt.AlignLeft)


        # 2.3.4. Total Time

        total_time_label = QLabel("total <i>t</i> :")#<i>t</i> total: ")
        total_time_label.setTextFormat(Qt.TextFormat.RichText)

        total_time_lineedit = CustomLineEdit()
        total_time_lineedit.setFixedWidth(80)
        total_time_lineedit.setFixedHeight(21)
        total_time_lineedit.setValidator(validator)
        total_time_lineedit.returnPressed.connect(total_time_lineedit.clearFocus)
        total_time_lineedit.setStyleSheet("""
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

        total_time_unit_combobox = QComboBox()
        total_time_unit_combobox.addItem("seconds")
        total_time_unit_combobox.addItem("minutes")
        total_time_unit_combobox.addItem("hours")
        total_time_unit_combobox.addItem("days")
        total_time_unit_combobox.setFixedWidth(75)
        total_time_unit_combobox.setFixedHeight(22)
        
        script_path = Path(__file__).resolve()
        btn_down_fp = script_path.parent / "icons" / "button_down.png"
        btn_down_disabled_fp = script_path.parent / "icons" / "button_down_disabled.png"
        total_time_unit_combobox.setStyleSheet(f"""
            QComboBox {{
                background-color: #333333;
                color: white;
                border: 1px solid #555555;
                border-radius: 3px;
            }}

            QComboBox QAbstractItemView {{
                background-color: #383838;
                color: white;
                selection-background-color: #555555;
            }}

            QComboBox::drop-down {{
                width: 20px;
                background-color: #505050;
                border-left: 1px solid #555555;
            }}

            /* Drop-down Arrow */
            QComboBox::down-arrow {{
                image: url("{btn_down_fp.as_posix()}");
                width: 12px;
                height: 12px;
            }}

            /* Disabled QComboBox */
            QComboBox:disabled {{
                background-color: #303030;
                color: #777777;
                border: 1px solid #444444;
                border-radius: 3px;
            }}

            QComboBox::drop-down:disabled {{
                background-color: #303030;
                border-left: 1px solid #333333;
                border-radius: 3px;
            }}

            QComboBox::down-arrow:disabled {{
                image: url("{btn_down_disabled_fp.as_posix()}");
                width: 12px;
                height: 12px;
            }}
        """)

        # Propagate the time parameters across positions
        time_points_lineedit.textEdited.connect(
            lambda txt, key='Tpoints': self.propagate_field(key, txt)
        )
        time_step_lineedit.textEdited.connect(
            lambda txt, key='Tstep': self.propagate_field(key, txt)
        )
        total_time_lineedit.textEdited.connect(
            lambda txt, key='Ttotal': self.propagate_field(key, txt)
        )
        time_step_unit_combobox.currentTextChanged.connect(
            lambda txt, key='Tstep unit': self.propagate_field(key, txt)
        )
        total_time_unit_combobox.currentTextChanged.connect(
            lambda txt, key='Ttotal unit': self.propagate_field(key, txt)
        )

        self.parameters_widget_layout.addWidget(total_time_label, 4, 0)
        self.parameters_widget_layout.addWidget(total_time_lineedit, 4, 1)
        self.parameters_widget_layout.addWidget(total_time_unit_combobox, 4, 2, alignment=Qt.AlignLeft)

        # Time management functions connections

        # Line edits
        time_points_lineedit.textEdited.connect(
            lambda _text,
                tp_le=time_points_lineedit,
                ts_le=time_step_lineedit,
                ts_cb=time_step_unit_combobox,
                tt_le=total_time_lineedit,
                tt_cb=total_time_unit_combobox:
                self._on_time_change(tp_le, ts_le, ts_cb, tt_le, tt_cb, changed='points')
        )
        time_step_lineedit.textEdited.connect(
            lambda _text,
                tp_le=time_points_lineedit,
                ts_le=time_step_lineedit,
                ts_cb=time_step_unit_combobox,
                tt_le=total_time_lineedit,
                tt_cb=total_time_unit_combobox:
                self._on_time_change(tp_le, ts_le, ts_cb, tt_le, tt_cb, changed='step')
        )
        total_time_lineedit.textEdited.connect(
            lambda _text,
                tp_le=time_points_lineedit,
                ts_le=time_step_lineedit,
                ts_cb=time_step_unit_combobox,
                tt_le=total_time_lineedit,
                tt_cb=total_time_unit_combobox:
                self._on_time_change(tp_le, ts_le, ts_cb, tt_le, tt_cb, changed='total')
        )

        # Units comboboxes
        time_step_unit_combobox.currentIndexChanged.connect(
            lambda _idx,
                tp_le=time_points_lineedit,
                ts_le=time_step_lineedit,
                ts_cb=time_step_unit_combobox,
                tt_le=total_time_lineedit,
                tt_cb=total_time_unit_combobox:
                self._on_time_change(tp_le, ts_le, ts_cb, tt_le, tt_cb, changed='step')
        )
        total_time_unit_combobox.currentIndexChanged.connect(
            lambda _idx,
                tp_le=time_points_lineedit,
                ts_le=time_step_lineedit,
                ts_cb=time_step_unit_combobox,
                tt_le=total_time_lineedit,
                tt_cb=total_time_unit_combobox:
                self._on_time_change(tp_le, ts_le, ts_cb, tt_le, tt_cb, changed='total')
        )



    
        #--------------------------------------------------------------------------------
        # Insert the widgets onto the Right Widget's layout
        
        self.separator1 = QFrame()
        self.separator1.setFrameShape(QFrame.HLine)
        self.separator1.setFrameShadow(QFrame.Sunken)
        self.separator1.setFixedHeight(2)
        self.separator1.setStyleSheet("""
            QFrame {
                /* Remove any default frames so we can fully control appearance */
                border: none;
                background-color: none;
                border-top: 1px solid #444;   /* Slightly lighter gray for the top edge */
                border-bottom: 1px solid #222; /* Darker gray for the bottom edge */
            }
        """)
        

        self.separator2 = QFrame()
        self.separator2.setFrameShape(QFrame.VLine)
        self.separator2.setFrameShadow(QFrame.Sunken)
        self.separator2.setFixedWidth(2)
        self.separator2.setStyleSheet("""
            QFrame {
                border: none;
                background-color: none;
                border-left: 1px solid #444;  /* slightly lighter gray on the left */
                border-right: 1px solid #222; /* darker gray on the right */
            }
        """)


        # 2. Left Dow nWidget
        self.left_down_widget = QWidget()
        self.left_down_widget_layout = QVBoxLayout()
        self.left_down_widget_layout.setContentsMargins(0, 0, 0, 0)
        self.left_down_widget_layout.setSpacing(0)
        self.left_down_widget.setLayout(self.left_down_widget_layout)

        # 2. Right Down nWidget
        self.right_down_widget = QWidget()
        self.right_down_widget_layout = QVBoxLayout()
        self.right_down_widget_layout.setContentsMargins(0, 0, 0, 0)
        self.right_down_widget_layout.setSpacing(0)
        self.right_down_widget.setLayout(self.right_down_widget_layout)
        

        
        self.left_down_widget_layout.addWidget(self.Y_parameters_widget, alignment=Qt.AlignLeft)
        self.left_down_widget_layout.addSpacing(10)
        self.left_down_widget_layout.addWidget(self.XZTheta_parameters_widget, alignment=Qt.AlignLeft)

        self.right_down_widget_layout.addSpacing(12)
        self.right_down_widget_layout.addWidget(Ysize_widget, alignment=Qt.AlignLeft)
        self.right_down_widget_layout.addWidget(self.parameters_widget, alignment=Qt.AlignLeft)

        self.down_widget = QWidget()
        self.down_widget_layout = QHBoxLayout()
        self.down_widget_layout.setContentsMargins(0,0,0,0)
        self.down_widget.setLayout(self.down_widget_layout)
        self.down_widget_layout.addWidget(self.left_down_widget)
        self.down_widget_layout.addWidget(self.separator2)
        self.down_widget_layout.addWidget(self.right_down_widget)

        self.line3 = QFrame()
        self.line3.setFrameShape(QFrame.HLine)
        self.line3.setFrameShadow(QFrame.Sunken)  # Optional: Raised, Sunken, Plain

        #--------------------------------------------------------------------------------
        # Insert the widgets onto the Main Widget's layout

        self.main_layout.addWidget(self.mode_widget, alignment=Qt.AlignLeft)
        self.main_layout.addWidget(self.separator1)
        self.main_layout.addWidget(self.opengl_widget)
        self.main_layout.addWidget(self.buttons_widget, alignment=Qt.AlignLeft)
        self.buttons_widget_layout.setContentsMargins(0,0,0,0)
        self.main_layout.addWidget(self.down_widget)


        self.tab_widget.insertTab(self.tab_widget.count() - 1, new_tab, "")  # Empty label for now
        self.tab_widget.setCurrentWidget(new_tab)

        tab_widgets = {
            'tab': new_tab,
            'Mode Yl': mode_yl_button,
            'Mode lY': mode_ly_button,
            'Begin': begin_button,
            'End': end_button,
            'Center': center_button,
            'Clear': clear_button,
            'Yi': Yi_lineedit,
            'Yf': Yf_lineedit,
            'Ysize': Ysize,
            'X': X_lineedit,
            'Z': Z_lineedit,
            'Theta': theta_lineedit,
            'Ystep': Ystep_lineedit,
            'Nsteps': number_of_steps,
            'Tpoints': time_points_lineedit,
            'Tstep': time_step_lineedit,
            'Tstep unit': time_step_unit_combobox,
            'Ttotal': total_time_lineedit,
            'Ttotal unit': total_time_unit_combobox
        }

        self.content_tabs.append(tab_widgets)

        # Force the sync of the acquisition mode buttons
        mode_yl_button.toggled.connect(
            lambda checked, key='Mode Yl': self.propagate_acquisition_mode(key) if checked else None
        )

        mode_ly_button.toggled.connect(
            lambda checked, key='Mode lY': self.propagate_acquisition_mode(key) if checked else None
        )

        self.update_tab_labels()

        # Force the sync of the time lineedits
        self.on_multipositions_toggled(True)



    def closeEvent(self, event):
        self.timer.stop()
        self.update_worker.stop()
        self.update_thread.quit()
        self.update_thread.wait()
        super().closeEvent(event)




# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     widget = YStack_Widget(filterwheel1, filterwheel2, laserbox, rtc5_board, pidevice, camera1, camera2)
#     widget.resize(500, 350)
#     widget.show()
#     sys.exit(app.exec())
