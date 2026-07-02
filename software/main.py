from concurrent.futures import ThreadPoolExecutor, as_completed
import os, re
os.environ["QT_API"] = "pyside6"
os.environ["NAPARI_QT_API"] = "pyside6"
import vispy.app
vispy.app.use_app('pyside6')

import napari
from napari.layers import Image
import sys
import numpy as np
import ctypes
import cv2

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout, QVBoxLayout, QSplitter, QDialog
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMdiArea, QMdiSubWindow, QLabel, QVBoxLayout, QWidget, QMessageBox
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPalette, QColor, QAction
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PySide6.QtCore import QThread, Signal


from napari.utils.theme import get_theme, register_theme

from Camera_Widget_py import Camera_Widget
from Filterwheels_Widget_py import Filterwheels_Widget
from Lasers_Widget_py import Lasers_Widget
from Scanner_Widget_py import Scanner_Widget
from Stages_Widget_py import Stages_Widget
from YStack_Widget_py import YStack_Widget
from File_Explorer_py import File_Explorer
from Launcher_py import ALM_Launcher

import json
from skimage.transform import pyramid_gaussian

from pylablib.devices import DCAM
from Extra_Files.Acquisition_Thread_Code import Acquisition_Thread
from Extra_Files.Devices_Connections import device_initializations, device_closings
from Extra_Files.Floating_Widget import FloatingWidget


from skimage.transform import resize
import time

import shutil
import numpy as np
import zarr
from ome_zarr.io import parse_url
from ome_zarr.writer import write_multiscales_metadata
from ome_zarr.format import FormatV04
from skimage.transform import downscale_local_mean

from napari_plot_profile import PlotProfile
from quality_control_widget import QualityControl_UI


# --- Quality Control overlays and plot---
from Extra_Files.Quality_Control.qc_overlays import (
    ensure_qc_layers, draw_tilt_line, draw_focus_point, clear_qc_overlays
)
from Extra_Files.Quality_Control.qc_algorithms import fit_focus_hyperbola
from Extra_Files.Quality_Control.qc_plots import FWHMPlotDialog

from Extra_Files.Confocal_Sync import (speed_from_exposure_ms,exposure_ms_from_speed,clamp_confocal_speed,clamp_confocal_exposure_ms)

import os, re, csv
import numpy as np
import cv2
import zarr
from datetime import datetime

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import traceback


def imwrite_unicode(path: str, img: np.ndarray) -> None:
    """
    Write an image to disk using cv2.imencode + Python file I/O.
    This avoids cv2.imwrite issues with Unicode paths on Windows.
    """
    path = str(path)
    ext = os.path.splitext(path)[1]
    if not ext:
        ext = ".png"  # default if extension is missing

    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise IOError(f"cv2.imencode failed for extension {ext}")

    # Ensure the folder exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # Write bytes using Python (handles Unicode paths reliably)
    Path(path).write_bytes(buf.tobytes())


# --- Logger App---
from logger import (setup_logging, update_log_file_dir, install_qt_message_handler, install_excepthook, shutdown_logging)
from pathlib import Path

import logging
import threading
# Create the main application logger
logger = setup_logging(app_name="ALM", level=logging.INFO)

# Redirect Qt internal messages to the Python logger
install_qt_message_handler(logger)

# Catch uncaught exceptions globally
install_excepthook(logger)

MODE_ACQ = "acquisition"
MODE_QC = "quality_control"

####################################################################################################

def set_napari_background(viewer, color="#303030"):
    """Sets only the background color in Napari."""
    theme = get_theme("dark")  # Load the existing dark theme
    theme.background = color   # Change only the background color

    register_theme('custom_dark', theme, 'custom')  # Register the new theme
    viewer.theme = "custom_dark"  # Apply it to Napari



class FrameGrabberThread(QThread):
    """ Continuously grabs frames from a camera on its own thread. """
    frame_ready = Signal(np.ndarray, int)  
    # (frame, camera_id) so you can distinguish Camera 1 vs 2

    def __init__(self, camera, cam_id, interval_ms=50):
        super().__init__()
        self.camera   = camera
        self.cam_id   = cam_id
        self.interval = interval_ms
        self._running = False

    def run(self):
        self._running = True

        while self._running:

            try:
                self.camera.wait_for_frame(timeout=5)
                frame = self.camera.read_newest_image(peek=True)
                
            # Exception that allow the code to progress while the camera is changing parameters when Live
            except Exception as e:
                continue
            
            if frame is not None:
                self.frame_ready.emit(frame, self.cam_id)

            time.sleep(0.03)

    def stop(self):
        self._running = False
        self.wait()


####################################################################################################

from PySide6.QtCore import Slot

class ALM_Lightsheet(QMainWindow):

    # prevent system sleep
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000002)

    #-------------------------------------------------------------------------------------------------
    # Window Functions

    def on_frame_received(self, frame: np.ndarray, cam_id: int):

        name = f"Camera {cam_id}"

        # Mirror the view for Camera 1
        if cam_id == 1:

            # Mirror the frame
            frame = np.fliplr(frame)

            # Ensure it’s C-contiguous so OpenCV can see it as a Mat
            frame = np.ascontiguousarray(frame)

            if "Camera 1" in self.viewer.layers:
                layer = self.viewer.layers["Camera 1"]
                # contrast_limits is a (min, max) tuple
                contrast_val = int(layer.contrast_limits[1])
            else:
                contrast_val = int(frame.max())

            base_org = (10, 85)
            # Current frame dimensions
            cur_width  = self.camera_widget_1.width_x
            cur_height = self.camera_widget_1.height_y
            # Scale factors relative to the 2048×2048 design
            scale_x = cur_width  / 2048
            scale_y = cur_height / 2048

            # Write on the frame
            text       = "Camera 1"
            org        = (int(base_org[0] * scale_x), int(base_org[1] * scale_y))
            font       = cv2.FONT_HERSHEY_DUPLEX
            font_scale = 3.5 * scale_x  # Update font size by the size of the frame
            color = (0, 0, 0)
            thickness  = int(4 * scale_x) # Update font size by the size of the frame
            line_type  = cv2.LINE_AA

            #cv2.putText(frame, text, org, font, font_scale, color, thickness, line_type)

            if name in self.viewer.layers:
                self.viewer.layers[name].data = frame
            else:
                self.viewer.add_image(frame, name=name, colormap="gray")
                QTimer.singleShot(0, lambda: self.viewer.fit_to_view(margin=0.05))

        elif cam_id == 2:

            # Ensure it’s C-contiguous so OpenCV can see it as a Mat
            frame = np.ascontiguousarray(frame)

            if "Camera 2" in self.viewer.layers:
                layer = self.viewer.layers["Camera 2"]
                # contrast_limits is a (min, max) tuple
                contrast_val = int(layer.contrast_limits[1])
            else:
                contrast_val = int(frame.max())

            # Write on the frame
            text       = "Camera 2"
            org        = (10, 85)
            font       = cv2.FONT_HERSHEY_DUPLEX
            font_scale = 3.5 * self.camera_widget_2.width_x / 2048 # Update font size by the size of the frame
            color = (0, 0, 0)
            thickness  = int(4 * self.camera_widget_2.width_x / 2048) # Update font size by the size of the frame
            line_type  = cv2.LINE_AA
        

            #cv2.putText(frame, text, org, font, font_scale, color, thickness, line_type)

            if name in self.viewer.layers:
                self.viewer.layers[name].data = frame
            else:
                self.viewer.add_image(frame, name=name, colormap="gray")
                QTimer.singleShot(0, lambda: self.viewer.fit_to_view(margin=0.05))


    
    @Slot(bool)
    def on_camera1_live_toggled(self, live: bool):
        threading.current_thread().name = "CAMERA"

        # If acquisition is running, do not let live mode reconfigure the camera.
        # The grabber thread may keep running and peeking frames, but acquisition owns setup/start/stop.
        if getattr(self, "acquisition_running", False):
            self.logger.warning("Camera 1 live toggle ignored because acquisition is running")
            return

        # Live ON
        if live:
            try:
                self.camera_1.stop_acquisition()
                self.camera_1.clear_acquisition()

                self.camera_1.setup_acquisition(mode="sequence", nframes=200)
                self.camera_1.start_acquisition()

                # Start grabbing frames
                self.grabber_1.start()

                # Log that live view has started successfully
                self.logger.info("Camera 1 live view started")

                # Fit the viewer
                QTimer.singleShot(0, lambda: self.viewer.fit_to_view(margin=0.05))

                # If the active camera mode is scanner-driven, start the unified scanner button.
                mode = self.camera_widget_1.cameramode_combobox.currentText()
                if mode in ("Widefield Mode", "Confocal Mode"):
                    self.scanner_widget.pushbutton_2.setChecked(True)

                    # Automatic laser activation remains unchanged
                    if self.laser_widget.automatic_laser_activation_checkbox.isChecked():
                        if self.laser_widget.last_laser_on != 0:
                            last_laser = self.laser_widget.last_laser_on
                            self._pending_auto_laser = (last_laser, 1)

            except Exception:
                # Log the full traceback if live view fails to start
                self.logger.exception("Failed to start Camera 1 live view")
                raise

        # Live OFF
        else:
            try:
                self.camera_1.stop_acquisition()
                self.camera_1.clear_acquisition()

                # Stop grabbing frames
                self.grabber_1.stop()

                # Turn lasers off
                self.laser_widget.turn_all_off()

                # Turn scanner off
                self.scanner_widget.ls_stop()

                # Log that live view has stopped
                self.logger.info("Camera 1 live view stopped")

            except Exception:
                # Log the full traceback if live view fails to stop
                self.logger.exception("Failed to stop Camera 1 live view")
                raise



    @Slot(bool)
    def on_camera2_live_toggled(self, live: bool):

        threading.current_thread().name = "CAMERA"

        # If acquisition is running, do not let live mode reconfigure the camera.
        # The grabber thread may keep running and peeking frames, but acquisition owns setup/start/stop.
        if getattr(self, "acquisition_running", False):
            self.logger.warning(
                "Camera 2 live toggle ignored because acquisition is running"
            )
            return

        # Live ON
        if live:
            try:
                self.camera_2.stop_acquisition()
                self.camera_2.clear_acquisition()

                self.camera_2.setup_acquisition(mode="sequence", nframes=200)
                self.camera_2.start_acquisition()

                # Start grabbing frames
                self.grabber_2.start()

                # Log that live view has started
                self.logger.info("Camera 2 live view started")

                # Fit the viewer
                QTimer.singleShot(0, lambda: self.viewer.fit_to_view(margin=0.05))

                # If the active camera mode is scanner-driven, start the unified scanner button.
                mode = self.camera_widget_2.cameramode_combobox.currentText()
                if mode in ("Widefield Mode", "Confocal Mode"):
                    self.scanner_widget.pushbutton_2.setChecked(True)

                    # Automatic laser activation remains unchanged
                    if self.laser_widget.automatic_laser_activation_checkbox.isChecked():
                        if self.laser_widget.last_laser_on != 0:
                            last_laser = self.laser_widget.last_laser_on
                            self._pending_auto_laser = (last_laser, 1)

            except Exception:
                # Log full traceback if live fails to start
                self.logger.exception("Failed to start Camera 2 live view")
                raise

        # Live OFF
        else:
            try:
                self.camera_2.stop_acquisition()
                self.camera_2.clear_acquisition()

                # Stop grabbing frames
                self.grabber_2.stop()

                # Turn lasers off
                self.laser_widget.turn_all_off()

                # Turn scanner off
                self.scanner_widget.ls_stop()

                # Log that live view has stopped
                self.logger.info("Camera 2 live view stopped")

            except Exception:
                # Log full traceback if live fails to stop
                self.logger.exception("Failed to stop Camera 2 live view")
                raise

            

    @Slot(np.ndarray, int)
    def _on_frame_ready(self, frame, cam_id):
        """Keep the newest incoming frame in memory."""
        self.latest_frames[cam_id] = frame.copy()

    @Slot(str)
    def _on_path_changed(self, new_path: str):
        self.current_save_directory = new_path

        if hasattr(self, 'ystack_widget'):
            self.ystack_widget.update_save_directory(new_path)
    
    
    @Slot(bool, bool, int)
    def _on_ls_mode_switch_finished(self, enabled: bool, ok: bool, req_id: int):
        # LS ON
        if not enabled or not ok:
            return

        if self._pending_auto_laser is None:
            return

        laser_hw, power_mw = self._pending_auto_laser
        self._pending_auto_laser = None

        # In LS mode -> laser on
        self.laser_widget.activate_laser_by_number(laser_hw, power_mw)

    #-------------------------------------------------------------------------------------------------
    # For the Floating Widgets

    def add_widget_at_position(self, widget, title, x, y):
        """Adds a widget inside a floating window at a specific position."""
        
        if widget.parent() is not None:
            widget.setParent(None) 

        floating_widget = FloatingWidget(widget, title)
        self.mdi_area.addSubWindow(floating_widget)

        floating_widget.move(x, y)  # Manually position the window
        floating_widget.show()
        return floating_widget

    #-------------------------------------------------------------------------------------------------
    # Snap Capture

    def _get_next_snap_number(self, save_directory, prefix):
        """
        Return the next snap number for the given camera.

        The method supports both:
        1) the legacy flat layout:   CameraX_SnapN.ome.zarr
        2) the new folder layout:    Snap_N_Camera_X/...
        """
        esc = re.escape(prefix)
        legacy_pat = re.compile(rf"^{esc}_Snap(\d+)\.ome\.zarr$")

        cam_match = re.search(r"(\d+)$", prefix)
        camera_id = int(cam_match.group(1)) if cam_match else None
        folder_pat = re.compile(r"^Snap_(\d+)_Camera_(\d+)$")

        nums = []
        for name in os.listdir(save_directory):
            full_path = os.path.join(save_directory, name)

            # New layout: folders named Snap_<N>_Camera_<X>
            if os.path.isdir(full_path):
                m = folder_pat.match(name)
                if m and camera_id is not None and int(m.group(2)) == camera_id:
                    nums.append(int(m.group(1)))
                continue

            # Legacy layout: flat files in the selected directory
            m = legacy_pat.match(name)
            if m:
                nums.append(int(m.group(1)))

        return max(nums) + 1 if nums else 1
        
    def _get_snap_output_paths(self, save_directory, camera_id, file_number):
        """
        Build the output folder and OME-Zarr path for a snap.

        Layout:
            <selected folder>/Snap_<N>_Camera_<X>/Camera<X>_Snap<N>.ome.zarr
        """
        snap_folder = os.path.join(save_directory, f"Snap_{file_number}_Camera_{camera_id}")
        os.makedirs(snap_folder, exist_ok=True)

        output_file = os.path.join(
            snap_folder,
            f"Camera{camera_id}_Snap{file_number}.ome.zarr"
        )
        return snap_folder, output_file
    
        
    def on_camera1_snap(self, save_directory):
        """
        Acquire a single snap from Camera 1 and save it as OME-Zarr
        together with a metadata sidecar file.
        """

        # LOG: snap requested
        self.logger.info("Camera 1 snap requested")

        # ——— load your latest frame ———
        frame: np.ndarray = self.latest_frames.get(1)

        if frame is None:
            # LOG: no frame available
            self.logger.warning(
                "Camera 1 snap failed: no frame available"
            )
            return

        # get the number for the file name
        prefix = "Camera1"
        file_number = self._get_next_snap_number(save_directory, prefix)

        # --- Build the snap folder and the OME-Zarr output path ---
        _, output_file = self._get_snap_output_paths(
            save_directory=save_directory,
            camera_id=1,
            file_number=file_number,
        )

        # LOG: snap file path
        self.logger.info(
            "Camera 1 snap started (file %s)",
            output_file,
        )

        try:
            # --- Open the Zarr store inside the snap folder ---
            store = parse_url(output_file, mode="w").store
            root = zarr.group(store=store, overwrite=True)

            # ——— build an XY-only 3-level pyramid ———
            pyramid = [frame.astype(np.uint16)]
            max_levels = 3
            for level in range(1, max_levels):
                prev = pyramid[-1]
                # downsample by 2× in Y and X only:
                ds = downscale_local_mean(prev, (2, 2)).astype(prev.dtype)
                pyramid.append(ds)

            # ——— write each pyramid level as its own array ———
            for idx, img in enumerate(pyramid):
                chunks = (min(256, img.shape[0]), min(256, img.shape[1]))
                root.create_dataset(
                    str(idx),
                    data=img,
                    chunks=chunks,
                    dtype=img.dtype
                )

            # ——— assemble the multiscale metadata ———
            base_pixel_size = 0.65
            datasets = []
            for idx in range(len(pyramid)):
                scale_factor = 2 ** idx
                datasets.append({
                    "path": str(idx),
                    "coordinateTransformations": [
                        {
                            "type": "scale",
                            "scale": [
                                base_pixel_size * scale_factor,
                                base_pixel_size * scale_factor,
                            ],
                        }
                    ],
                })

            axes = [
                {"name": "y", "type": "space", "unit": "um"},
                {"name": "x", "type": "space", "unit": "um"},
            ]

            write_multiscales_metadata(
                group=root,
                datasets=datasets,
                fmt=FormatV04(),
                axes=axes,
                name="image"
            )

            # Build and save snap metadata as a TXT sidecar file.
            metadata = self._build_snap_metadata(
                camera_id=1,
                frame=frame,
                output_file=output_file,
                file_number=file_number
            )

            if metadata is not None:
                self._write_snap_metadata_txt(metadata, output_file)

            # LOG: snap completed successfully
            self.logger.info(
                "Camera 1 snap saved successfully (file %s)",
                output_file,
            )

        except Exception:
            # LOG: snap failed with traceback
            self.logger.exception(
                "Camera 1 snap failed while writing data"
            )
            raise




    def on_camera2_snap(self, save_directory):
        """
        Acquire a single snap from Camera 2 and save it as OME-Zarr
        together with a metadata sidecar file.
        """

        # LOG: snap requested
        self.logger.info("Camera 2 snap requested")

        # ——— load your latest frame ———
        frame: np.ndarray = self.latest_frames.get(2)

        if frame is None:
            # LOG: no frame available
            self.logger.warning(
                "Camera 2 snap failed: no frame available"
            )
            return

        # get the number for the file name
        prefix = "Camera2"
        file_number = self._get_next_snap_number(save_directory, prefix)

        # --- Build the snap folder and the OME-Zarr output path ---
        _, output_file = self._get_snap_output_paths(
            save_directory=save_directory,
            camera_id=2,
            file_number=file_number,
        )

        # LOG: snap file path
        self.logger.info(
            "Camera 2 snap started (file %s)",
            output_file,
        )

        try:
            # --- Open the Zarr store inside the snap folder ---
            store = parse_url(output_file, mode="w").store
            root = zarr.group(store=store, overwrite=True)

            # ——— build an XY-only 3-level pyramid ———
            pyramid = [frame.astype(np.uint16)]
            max_levels = 3
            for level in range(1, max_levels):
                prev = pyramid[-1]
                # downsample by 2× in Y and X only:
                ds = downscale_local_mean(prev, (2, 2)).astype(prev.dtype)
                pyramid.append(ds)

            # ——— write each pyramid level as its own array ———
            for idx, img in enumerate(pyramid):
                chunks = (min(256, img.shape[0]), min(256, img.shape[1]))
                root.create_dataset(
                    str(idx),
                    data=img,
                    chunks=chunks,
                    dtype=img.dtype
                )

            # ——— assemble the multiscale metadata ———
            base_pixel_size = 0.65
            datasets = []
            for idx in range(len(pyramid)):
                scale_factor = 2 ** idx
                datasets.append({
                    "path": str(idx),
                    "coordinateTransformations": [
                        {
                            "type": "scale",
                            "scale": [
                                base_pixel_size * scale_factor,
                                base_pixel_size * scale_factor,
                            ],
                        }
                    ],
                })

            axes = [
                {"name": "y", "type": "space", "unit": "um"},
                {"name": "x", "type": "space", "unit": "um"},
            ]

            write_multiscales_metadata(
                group=root,
                datasets=datasets,
                fmt=FormatV04(),
                axes=axes,
                name="image"
            )

            # Build and save snap metadata as a TXT sidecar file.
            metadata = self._build_snap_metadata(
                camera_id=2,
                frame=frame,
                output_file=output_file,
                file_number=file_number
            )

            if metadata is not None:
                self._write_snap_metadata_txt(metadata, output_file)

            # LOG: snap completed successfully
            self.logger.info(
                "Camera 2 snap saved successfully (file %s)",
                output_file,
            )

        except Exception:
            # LOG: snap failed with traceback
            self.logger.exception(
                "Camera 2 snap failed while writing data"
            )
            raise



    #-------------------------------------------------------------------------------------------------
    #Snap Metadata

    def _build_snap_metadata(
    self,
    camera_id: int,
    frame: np.ndarray,
    output_file: str,
    file_number: int
) -> dict | None:
        """
        Build a metadata dictionary for a snap.
        Reuse the same fields used during acquisition whenever possible.
        """
        # Guard against missing frames.
        if frame is None:
            print(f"[Snap] No frame available for Camera {camera_id}. Snap metadata was not written.")
            return None

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        camera = self.camera_1 if camera_id == 1 else self.camera_2

        # Build the metadata dictionary using grouped sections.
        metadata = {
            "general": {
                "event": "SNAP",
                "timestamp": timestamp,
                "camera_id": camera_id,
                "camera_name": f"Camera {camera_id}",
                "snap_number": file_number,
                "output_file": output_file,
                "save_directory": self.current_save_directory if hasattr(self, "current_save_directory") else None,
            },
            "camera": {
                "format": f"{frame.shape[1]} x {frame.shape[0]}",
                "binning": None,
                "dynamic_range": f"{frame.dtype.itemsize * 8} bits",
                "mode": None,
                "exposure_time_ms": None,
            },
            "scanner": {
                "speed": None,
                "top": None,
                "bottom": None,
            },
            "laser": {
                "wavelength_nm": None,
                "power_percent": None,
                "power_mw": None,
                "emission_filter": None,
                "active_lasers": [],
            },
        }



        # Try to read the camera mode from the corresponding camera widget.
        try:
            cam_widget = self.camera_widget_1 if camera_id == 1 else self.camera_widget_2
            metadata["camera"]["mode"] = cam_widget.cameramode_combobox.currentText()
        except Exception:
            metadata["camera"]["mode"] = None

        # Try to read the camera exposure time from the corresponding camera widget.

        try:
            exp_ms = getattr(cam_widget, "exposure_time", None)
            metadata["camera"]["exposure_time_ms"] = f"{exp_ms:.6f} ms" if exp_ms is not None else None
        except Exception:
            metadata["camera"]["exposure_time_ms"] = None

         # Try to read camera binning using the same getter used during acquisition.     
        try:
            metadata["camera"]["binning"] = cam_widget.binning_combobox.currentText()
        except Exception:
            try:
                # Fallback to internal numeric value if needed
                b = getattr(cam_widget, "binning", None)
                metadata["camera"]["binning"] = f"{b}" if b is not None else None
            except Exception:
                metadata["camera"]["binning"] = None
    

        # Try to read scanner settings from the UI or controller.
        # Replace these placeholders with your actual attributes.
        try:
            metadata["scanner"]["speed"] = self.scanner_widget.lineedit_1.text()
        except Exception:
            metadata["scanner"]["speed"] = None

        try:
            metadata["scanner"]["top"] = self.scanner_widget.lineedit_2.text()
        except Exception:
            metadata["scanner"]["top"] = None

        try:
            metadata["scanner"]["bottom"] = self.scanner_widget.lineedit_3.text()
        except Exception:
            metadata["scanner"]["bottom"] = None

        # Read all lasers that are currently ON in the laser widget.
        # IMPORTANT: do not use the acquisition checkbox here.
        try:
            metadata["laser"]["active_lasers"] = []

            if hasattr(self.laser_widget, "drag"):
                for i in range(self.laser_widget.drag.blayout.count()):
                    item = self.laser_widget.drag.blayout.itemAt(i).widget()

                    if item is None or not hasattr(item, "button3") or not hasattr(item, "slider"):
                        continue

                    # Laser is ON only if the ON/OFF button is active and power > 0
                    if not item.button3.isChecked():
                        continue
                    if item.slider.value() <= 0:
                        continue

                    label_text = item.label.text() if hasattr(item, "label") else ""
                    match = re.search(r"(\\d+)\\s*nm", label_text)
                    
                    if match:
                        wavelength_nm = match.group(1)   # guarda só "488"
                    else:
                        # fallback: limpa prefixos como "2nd - " e remove "nm" se já existir
                        wavelength_nm = label_text.split("-")[-1].replace("nm", "").strip()


                    power_percent = item.slider.value()

                    # Power in mW from the laser control itself, independent of acquisition checkbox
                    try:
                        power_mw = item.value_lineedit.text().strip() if hasattr(item, "value_lineedit") else ""
                        power_mw = power_mw if power_mw else str(item.slider.value())
                    except Exception:
                        try:
                            power_mw = str(item.slider.value())
                        except Exception:
                            power_mw = None

                    # Get emission filter from Filterwheels Widget (authoritative source)
                    try:
                        filter_key = self.filterwheels_widget.get_selected_filter(camera_id)
                        if filter_key:
                                if camera_id == 1:
                                    filter_info = self.filterwheels_widget.filter_data["Filterwheel_1"].get(filter_key)
                                else:
                                    filter_info = self.filterwheels_widget.filter_data["Filterwheel_2"].get(filter_key)

                                emission_filter = filter_info.get("tooltip") if filter_info else None
                        else:
                            emission_filter = None

                    except Exception:
                        emission_filter = None

                    if emission_filter:
                        emission_filter = emission_filter.replace("\n", " ")


                    metadata["laser"]["active_lasers"].append({
                        "wavelength_nm": wavelength_nm,
                        "power_percent": power_percent,
                        "power_mw": power_mw,
                        "emission_filter": emission_filter,
                    })

        except Exception as e:
            print(f"[Snap metadata] Failed to read laser settings: {e}")

        return metadata
    
    def _format_snap_metadata_txt(self, metadata: dict) -> str:
        """
        Convert the snap metadata dictionary into a human-readable TXT layout.
        """
        camera = metadata.get("camera", {})
        scanner = metadata.get("scanner", {})
        lasers = metadata.get("laser", {}).get("active_lasers",[])

        lines = [
            f"Date: {metadata['general'].get('timestamp')}\n"
            f"Camera: {metadata['general'].get('camera_id')}\n"
            f"Event: {metadata['general'].get('event')}\n"
            "",
            "-----------------------------------------------------------",
            "",
            f"### Camera {metadata['general'].get('camera_id', '?')} Settings:",
            f"  Format:         {camera.get('format', 'N/A')}",
            f"  Binning:        {camera.get('binning', 'N/A')}",
            f"  Dynamic Range:  {camera.get('dynamic_range', 'N/A')}",
            f"  Mode:           {camera.get('mode', 'N/A')}",
            f"  Exposure Time:  {camera.get('exposure_time_ms', 'N/A')}",
            "",
        ]
        
        # Only include scanner settings when the camera is NOT in Internal Trigger mode
        if camera.get("mode") != "Internal Trigger":
            lines.extend([
                "-----------------------------------------------------------",
                "",
                "### Scanner Settings:",
                f"  Speed:   {scanner.get('speed', 'N/A')}",
                f"  Top:     {scanner.get('top', 'N/A')}",
                f"  Bottom:  {scanner.get('bottom', 'N/A')}",
                "",
            ])
        
        lines.extend([
        "-----------------------------------------------------------",
        "",
        "### Laser Settings:",
        "",
    ])

        if not lasers:
            lines.extend([
                "  No active lasers",
                "",
            ])
        else:
            for idx, laser_info in enumerate(lasers, start=1):
                lines.extend([
                    f"  #### Laser {idx}: {laser_info.get('wavelength_nm', 'N/A')} nm",
                    f"      Laser Power:     {laser_info.get('power_percent', 'N/A')}% ({laser_info.get('power_mw', 'N/A')} mW)",
                    f"      Emission Filter: {laser_info.get('emission_filter', 'N/A')}",
                    "",
                ])



        return "\n".join(lines)
        
    def _write_snap_metadata_txt(self, metadata: dict, output_file: str) -> None:
        """
        Write formatted snap metadata to a TXT sidecar file.
        """
        txt_path = output_file.replace(".ome.zarr", "_metadata.txt")
        txt_content = self._format_snap_metadata_txt(metadata)
        Path(txt_path).write_text(txt_content, encoding="utf-8")



    #-------------------------------------------------------------------------------------------------
    # Camera restarts

    def camera1_restart(self):
        """Restart Camera 1 hardware connection."""

        self.logger.info("Camera 1 restart requested")

        try:
            # Close camera connection
            self.camera_1.close()
            self.logger.info("Camera 1 closed successfully")

            # Re-open camera connection
            self.camera_1.open()
            self.logger.info("Camera 1 restarted successfully")

            # Optional: log camera status after restart
            time.sleep(0.5)
            status = self.camera_1.get_status()
            self.logger.info("Camera 1 status after restart: %s", status)

        except Exception:
            self.logger.exception("Camera 1 restart failed")
            raise

    def camera2_restart(self):
        """Restart Camera 2 hardware connection."""

        self.logger.info("Camera 2 restart requested")

        try:
            # Close camera connection
            self.camera_2.close()
            self.logger.info("Camera 2 closed successfully")

            # Re-open camera connection
            self.camera_2.open()
            self.logger.info("Camera 2 restarted successfully")

            # Optional: log camera status after restart
            time.sleep(0.5)
            status = self.camera_2.get_status()
            self.logger.info("Camera 2 status after restart: %s", status)

        except Exception:
            self.logger.exception("Camera 2 restart failed")
            raise

    #-------------------------------------------------------------------------------------------------
    # Device enabling/disabling

    def before_acquisition(self):
        """Prepare the system for acquisition without reconfiguring camera live mode."""

        # Acquisition now owns the camera configuration.
        self.acquisition_running = True

        
        # Stop any interactive scanner mode before acquisition starts
        self.scanner_widget.ls_stop()


        # Then make sure continuous interactive laser output is off.
        self.laser_widget.turn_all_off()


        # IMPORTANT:
        # Do NOT start live here.
        # If live is already running, let the grabber keep peeking frames.
        # If live is OFF, keep it OFF.

        # Freeze camera widgets so the user cannot change ROI / mode / exposure during acquisition.
        if self.camera_widget_1 is not None:
            self.camera_widget_1.set_acquisition_guard(True)

        if self.camera_widget_2 is not None:
            self.camera_widget_2.set_acquisition_guard(True)

        # Disable device widgets during acquisition.
        if self.camera_2 is None:
            self.camera_widget_1.setDisabled(True)
        elif self.camera_1 is None:
            self.camera_widget_2.setDisabled(True)
        else:
            self.camera_widget_1.setDisabled(True)
            self.camera_widget_2.setDisabled(True)

        self.laser_widget.setDisabled(True)
        self.scanner_widget.setDisabled(True)
        self.filterwheels_widget.setDisabled(True)
        self.ystack_widget.start_button.setDisabled(True)
        self.ystack_widget.multipositions_checkbox.setDisabled(True)
        self.stages_widget.setDisabled(True)


    def enable_devices(self):
        # Acquisition no longer owns the camera configuration.
        self.acquisition_running = False

        # Remove camera-side acquisition guard.
        if hasattr(self, "camera_widget_1") and self.camera_widget_1 is not None:
            self.camera_widget_1.set_acquisition_guard(False)

        if hasattr(self, "camera_widget_2") and self.camera_widget_2 is not None:
            self.camera_widget_2.set_acquisition_guard(False)

        if self.camera_2 is None:
            self.camera_widget_1.setEnabled(True)
        elif self.camera_1 is None:
            self.camera_widget_2.setEnabled(True)
        else:
            self.camera_widget_1.setEnabled(True)
            self.camera_widget_2.setEnabled(True)

        self.laser_widget.setEnabled(True)
        self.scanner_widget.setEnabled(True)
        self.filterwheels_widget.setEnabled(True)
        self.ystack_widget.start_button.setEnabled(True)
        self.ystack_widget.multipositions_checkbox.setEnabled(True)
        self.stages_widget.setEnabled(True)

    def _reset_all_image_contrast(self):
        """
        Reset contrast limits on every Image layer
        in the current Napari viewer.
        """
        viewer = napari.current_viewer()
        if viewer is None:
            return

        for layer in viewer.layers:
            if isinstance(layer, Image):
                layer.reset_contrast_limits()
                # layer.reset_contrast_limits_range()
                print(f"Reset contrast on layer: {layer.name!r}")

    #--------------------------------------------------------------------------------------------------
    # For Quality Control and Acquisitions Modes


    
    def open_acquisition_mode(self):
        # Provide a reason string so the log can tell "who" triggered the change.
        self._set_mode(MODE_ACQ, reason="open_acquisition_mode() called")

    
    
    # --------------------------
    # Robust mode switching 
    # --------------------------
    def _mode_xy(self):
        x = 107 + getattr(self, "x_offset", 0)
        y = 677 + getattr(self, "y_offset", 0)
        return x, y

    def _ensure_acq_window(self):
        # garante widget
        if not hasattr(self, "ystack_widget") or self.ystack_widget is None:
            self.ystack_widget = YStack_Widget(
                self.file_manager_widget.current_path,
                self.filterwheel1, self.filterwheel2,
                self.laserbox, self.rtc5_board, self.pidevice,
                self.camera_1, self.camera_2,
                self.laser_widget, self.scanner_widget,
                self.camera_widget_1, self.camera_widget_2
            )

        # garante subwindow (persistente)
        if not hasattr(self, "_acq_subwindow") or self._acq_subwindow is None:
            x, y = self._mode_xy()
            self._acq_subwindow = self.add_widget_at_position(
                self.ystack_widget, "Y-Stack Acquisition", x, y
            )
            # se a subwindow for destruída por alguma razão, limpa a referência
            self._acq_subwindow.destroyed.connect(lambda *_: setattr(self, "_acq_subwindow", None))

    def _ensure_qc_window(self):
        from quality_control_widget import QualityControlWidget

        # garante widget
        if not hasattr(self, "qc_widget") or self.qc_widget is None:
            self.qc_widget = QualityControlWidget(pixel_size_um=0.65,beam_info_provider=self._get_beam_info_snapshot)
            self.qc_widget.save_bundle_ready.connect(self._save_quality_control_bundle)

            # ligações aos grabbers (apenas uma vez)
            if hasattr(self, "grabber_1") and self.grabber_1 is not None:
                self.grabber_1.frame_ready.connect(self.qc_widget.on_new_frame)
            if hasattr(self, "grabber_2") and self.grabber_2 is not None:
                self.grabber_2.frame_ready.connect(self.qc_widget.on_new_frame)

            # overlays e ligações de overlays (apenas uma vez)
            ensure_qc_layers(self.viewer)

            if not getattr(self, "_qc_connections_done", False):
                self.qc_widget.clear_overlays.connect(lambda: clear_qc_overlays(self.viewer))
                self.qc_widget.tilt_ready.connect(lambda angle, coef, shape: draw_tilt_line(self.viewer, coef, shape))
                self.qc_widget.focus_ready.connect(lambda col, row: draw_focus_point(self.viewer, row=row, col=col))
                self._qc_connections_done = True

        # garante subwindow (persistente)
        if not hasattr(self, "_qc_subwindow") or self._qc_subwindow is None:
            x, y = self._mode_xy()
            self._qc_subwindow = self.add_widget_at_position(
                self.qc_widget, "Quality Control Panel", x, y
            )
            self._qc_subwindow.destroyed.connect(lambda *_: setattr(self, "_qc_subwindow", None))

    
    def _set_mode(self, mode: str, *, reason: str = "") -> None:
        """
        Switch between persistent subwindows (Acquisition / Quality Control)
        and record a log entry for traceability.
        """

        threading.current_thread().name = "MainThread"

        # Read previous mode safely (first run may not have current_mode set yet).
        prev_mode = getattr(self, "current_mode", None)

        # Avoid noisy logs if nothing actually changed.
        if prev_mode == mode:
            return

        # Add optional context that helps debugging and auditing.
        save_dir = getattr(self, "current_save_directory", None)
        thread_name = threading.current_thread().name

        # Log intent BEFORE touching UI, so failures are still visible in logs.
        logger.info(
            "UI mode transition: %s -> %s",
            prev_mode,
            mode,
        )

        try:
            # Hide both (do not close) - your existing behaviour.
            if hasattr(self, "_acq_subwindow") and self._acq_subwindow is not None:
                self._acq_subwindow.hide()
            if hasattr(self, "_qc_subwindow") and self._qc_subwindow is not None:
                self._qc_subwindow.hide()

            # Show the requested mode.
            if mode == MODE_ACQ:
                self._ensure_acq_window()
                self._acq_subwindow.show()
                self._acq_subwindow.raise_()
            elif mode == MODE_QC:
                self._ensure_qc_window()
                self._qc_subwindow.show()
                self._qc_subwindow.raise_()
            else:
                # Defensive programming: unknown mode should be explicit in logs.
                logger.warning("Unknown UI mode requested: %r", mode)

            # Commit the state only after UI operations succeeded.
            self.current_mode = mode

        except Exception:
            # Log the stack trace and re-raise so you don't silently swallow UI errors.
            logger.exception("Failed to switch UI mode: %s -> %s", prev_mode, mode)
            raise



    #------------------ Open Quality Control Panel ------------------------------------
    
    def _show_fwhm_dialog(self):
        """Show the dialog modelessly (non-blocking)."""
        if getattr(self, "_fwhm_dialog", None) is None:
            return
        self._fwhm_dialog.show()
        self._fwhm_dialog.raise_()
        self._fwhm_dialog.activateWindow()

    
    def open_quality_control_mode(self):
        from quality_control_widget import QualityControlWidget
        from PySide6.QtWidgets import QWidget, QMessageBox, QInputDialog, QLineEdit

        

        if getattr(self, "_qc_unlocked", False):
            self._set_mode(MODE_QC, reason="QC already unlocked")
            return


        # 1) Ask for password
        pwd, ok = QInputDialog.getText(
            self,
            "Quality Control Mode",
            "Insert Password:",
            QLineEdit.Password
        )
        if not ok:
            return
        if pwd.strip() != "almlightsheet":
            QMessageBox.warning(self, "Quality Control", "Wrong Password.")
            return
        
        self._qc_unlocked = True

        # 2) Create the QC widget once (and wire signals once)
        
        
        if not hasattr(self, "qc_widget") or self.qc_widget is None:
            self.qc_widget = QualityControlWidget(pixel_size_um=0.65)  # use your real pixel size if known
            self.qc_widget.save_bundle_ready.connect(self._save_quality_control_bundle)

            # Connect camera grabbers -> QC widget
            if hasattr(self, "grabber_1") and self.grabber_1 is not None:
                self.grabber_1.frame_ready.connect(self.qc_widget.on_new_frame)
            if hasattr(self, "grabber_2") and self.grabber_2 is not None:
                self.grabber_2.frame_ready.connect(self.qc_widget.on_new_frame)

            # Create the plot dialog once 
            if not hasattr(self, "_fwhm_dialog") or self._fwhm_dialog is None:
                self._fwhm_dialog = FWHMPlotDialog(parent=self)

                # Connect once: update plot and show dialog when new data arrives
                self.qc_widget.fwhm_ready.connect(self._fwhm_dialog.update_data)

                # Show the dialog on the first result (and it's fine if show() is called multiple times)
                self.qc_widget.fwhm_ready.connect(lambda *_: self._show_fwhm_dialog())

            else:
                # Dialog already exists; ensure plot keeps updating (optional safety)
                try:
                    self.qc_widget.fwhm_ready.connect(self._fwhm_dialog.update_data)
                except Exception:
                    pass

            
            # 2.5) Ensure QC overlay layers exist once
            ensure_qc_layers(self.viewer)

            # 2.6) Connect signals only once to avoid duplicates over multiple entries
            if not getattr(self, "_qc_connections_done", False):
                self.qc_widget.clear_overlays.connect(lambda: clear_qc_overlays(self.viewer))
                self.qc_widget.tilt_ready.connect(lambda angle, coef, shape: draw_tilt_line(self.viewer, coef, shape))
                self.qc_widget.focus_ready.connect(lambda col, row: draw_focus_point(self.viewer, row=row, col=col))

                # Plot dialog connections (only once)
                self.qc_widget.fwhm_ready.connect(self._fwhm_dialog.update_data)
                self.qc_widget.fwhm_ready.connect(lambda *_: self._show_fwhm_dialog())

                self._qc_connections_done = True

            
        # 3) Show QC widget in the mode area
        self._set_mode(MODE_QC, reason="QC unlocked by password")

    #--------------------------------------------------------------------------------------------
    #Save Quality Control
        
    def _next_qc_folder(self, base_dir: str, name: str = None) -> str:
        """
        If name is None or empty:
        Create "Quality Control 1", "Quality Control 2", ...

        If name is provided:
        Create "name", "name 2", "name 3", ...
        """
        base = name.strip() if name and name.strip() else "Quality Control"
        pat = re.compile(rf"^{re.escape(base)}(?: (\d+))?$")
        nums = []

        try:
            for d in os.listdir(base_dir):
                full = os.path.join(base_dir, d)
                if not os.path.isdir(full):
                    continue
                m = pat.match(d)
                if not m:
                    continue
                nums.append(int(m.group(1) or 1))
        except Exception:
            pass

        next_idx = max(nums) + 1 if nums else 1

        if base == "Quality Control":
            folder_name = f"{base} {next_idx}"
        else:
            folder_name = base if next_idx == 1 else f"{base} {next_idx}"

        folder = os.path.join(base_dir, folder_name)
        os.makedirs(folder, exist_ok=True)
        return folder


    
    def _get_beam_info(self):
        """
        Devolve info consistente para o PDF:
        - beam_nm: "640 nm"
        - color_hex: "#8B0000"
        - intensity_mw: 0..100 (int)
        - intensity_str: "12 mW"
        """
        lw = getattr(self, "laser_widget", None)
        if lw is None:
            return {"beam_nm": "Unknown", "color_hex": None, "intensity_str": "Unknown"}

        # last_laser_on (hardware): 2..5 (ver Lasers_Widget) 
        beam_hw = getattr(lw, "last_laser_on", None)

        # Mapa: hardware -> (nm, cor) (cores iguais ao teu DragItem color_map)
        hw_to_beam = {
            2: ("640 nm", "#8B0000"),  # dark red
            3: ("561 nm", "#3CB371"),  # green
            4: ("488 nm", "#4682B4"),  # blue
            5: ("405 nm", "#5E018D"),  # purple
        }
        beam_nm, color_hex = hw_to_beam.get(beam_hw, ("Unknown", None))

        intensity_mw = None

        # Ir buscar o valor ao DragItem correspondente ao laser usado
        # Relação: internal = 6 - hardware  (porque worker usa SOURce{6-laser_number}) 
        if beam_hw in hw_to_beam and hasattr(lw, "drag"):
            internal = 6 - int(beam_hw)  # internal 1..4
            try:
                for i in range(lw.drag.blayout.count()):
                    w = lw.drag.blayout.itemAt(i).widget()
                    if getattr(w, "laser_number", None) == internal:
                        # prioridade: line edit (pode ter decimais), senão slider
                        try:
                            intensity_mw = int(float(w.value_lineedit.text()))
                        except Exception:
                            try:
                                intensity_mw = int(w.slider.value())
                            except Exception:
                                intensity_mw = None
                        break
            except Exception:
                intensity_mw = None

        intensity_str = f"{intensity_mw} mW" if intensity_mw is not None else "Unknown"

        return {
            "beam_nm": beam_nm,
            "color_hex": color_hex,
            "intensity_mw": intensity_mw,
            "intensity_str": intensity_str,
            "beam_hw": beam_hw,
        }
    


    def _get_beam_info_snapshot(self):
        """
        Return a consistent snapshot for the PDF:
        - Prefer a laser that is actually ON (power > 0 and button is checked).
        - Fallback to last_laser_on if none is ON.
        """
        lw = getattr(self, "laser_widget", None)
        if lw is None or not hasattr(lw, "drag"):
            return {"beam_nm": "Unknown", "color_hex": None, "intensity_mw": None, "intensity_str": "Unknown", "beam_hw": None}

        # Same colors used in DragItem color_map
        nm_to_color = {
            "405 nm": "#5E018D",
            "488 nm": "#4682B4",
            "561 nm": "#3CB371",
            "640 nm": "#8B0000",
        }

        candidates = []

        for i in range(lw.drag.blayout.count()):
            w = lw.drag.blayout.itemAt(i).widget()
            if w is None:
                continue

            # Heuristic: consider ON if button is checked and slider value > 0
            try:
                is_on = bool(getattr(w, "button3").isChecked()) and int(getattr(w, "slider").value()) > 0
            except Exception:
                is_on = False

            if not is_on:
                continue

            # Determine wavelength string from label text (kept by update_labels)
            try:
                beam_nm = w.label.text().split(" - ", 1)[-1].strip()
            except Exception:
                beam_nm = "Unknown"

            # Read power from lineedit first, fallback to slider
            intensity_mw = None
            try:
                intensity_mw = int(float(w.value_lineedit.text()))
            except Exception:
                try:
                    intensity_mw = int(w.slider.value())
                except Exception:
                    intensity_mw = None

            # Convert internal laser_number -> hardware channel (2..5) if needed
            beam_hw = None
            try:
                # In your code the device channels are derived as (6 - laser_number)
                beam_hw = 6 - int(getattr(w, "laser_number"))
            except Exception:
                beam_hw = None

            candidates.append((intensity_mw or 0, beam_nm, nm_to_color.get(beam_nm), intensity_mw, beam_hw))

        # If multiple lasers are ON, choose the strongest one (or adjust logic if you prefer).
        if candidates:
            candidates.sort(key=lambda t: t[0], reverse=True)
            _, beam_nm, color_hex, intensity_mw, beam_hw = candidates[0]
            intensity_str = f"{intensity_mw} mW" if intensity_mw is not None else "Unknown"
            return {
                "beam_nm": beam_nm,
                "color_hex": color_hex,
                "intensity_mw": intensity_mw,
                "intensity_str": intensity_str,
                "beam_hw": beam_hw,
            }

        # Fallback: use your previous logic based on last_laser_on
        return self._get_beam_info()





    def _save_quality_control_bundle(self, bundle: dict):
        """
        Receive QC results and create outputs.
        Supports:
        - Single camera bundle (existing behavior)
        - Combined 'both' bundle -> single PDF with 2 sections
        """
        # --- andle 'Both' bundle ---
        if isinstance(bundle, dict) and bundle.get("mode") == "both":
            return self._save_quality_control_bundle_both(bundle)

        # --- existing single-camera code below---

        base_dir = getattr(self, "current_save_directory", None) or os.getcwd()
        qc_folder_name = (bundle.get("qc_folder_name") or "").strip()
        out_dir = self._next_qc_folder(base_dir, qc_folder_name if qc_folder_name else None)

        # ---- metadata base ----
        timestamp = bundle.get("timestamp", datetime.now().isoformat(timespec="seconds"))
        cam_id = bundle.get("cam_id", None)
        camera_name = bundle.get("camera_name", f"Camera {cam_id}" if cam_id else "Unknown Camera")

        
        
        beam_info = bundle.get("beam_info") or self._get_beam_info_snapshot()
        beam_used = beam_info.get("beam_nm", "Unknown")
        beam_color = beam_info.get("color_hex")
        intensity = beam_info.get("intensity_str", "Unknown")


        angle_deg = bundle.get("angle_deg", np.nan)
        focus = bundle.get("focus", None)
        coef = bundle.get("coef", None)
        shape = bundle.get("shape", None)
        cols = np.asarray(bundle.get("cols", []))
        peaks = np.asarray(bundle.get("peaks", []))
        fwhms = np.asarray(bundle.get("fwhms", []))
        frame = np.asarray(bundle.get("frame", None))

        # foco + beam waist (fwhm no foco)
        focus_col = None
        focus_row = None
        fwhm_focus = np.nan
        if isinstance(focus, dict):
            focus_col = focus.get("column", None)
            focus_row = focus.get("row", None)
            fwhm_focus = float(focus.get("fwhm", np.nan))

        pixel_um = bundle.get("pixel_size_um", None)
        fwhm_focus_um = (fwhm_focus * float(pixel_um)) if (pixel_um is not None and np.isfinite(fwhm_focus)) else np.nan

        # ---- 1) Guardar imagem raw do feixe ----
        raw_path = os.path.join(out_dir, "beam_raw.png")
        if frame is not None and frame.size:
            # --- Read viewer contrast settings for the active camera layer ---
            # This makes the exported PNG match what the user sees in Napari.
            contrast_limits = None
            gamma = None
            try:
                layer_name = camera_name  # typically "Camera 1" / "Camera 2"
                if layer_name in self.viewer.layers:
                    layer = self.viewer.layers[layer_name]
                    contrast_limits = tuple(layer.contrast_limits)  # (low, high)
                    gamma = float(getattr(layer, "gamma", 1.0))
            except Exception:
                contrast_limits = None
                gamma = None


        #--- 2) Render a "camera snap" image with QC overlays (tilt + focus) ---
        # NOTE: Camera 1 is mirrored in the viewer, so we mirror here too and
        #       adjust overlay coordinates accordingly to match what the user sees.
        
        safe_camera = camera_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        overlay_path = os.path.join(out_dir, f"{safe_camera}_snap_with_overlays.png")

        try: 
            overlay_path = self._render_frame_with_overlays(
                frame=frame,
                coef=coef,
                focus_col=focus_col,
                focus_row=focus_row,
                out_path=overlay_path,
                cam_id=cam_id,
                contrast_limits=contrast_limits,
                gamma=gamma,
            )
        except Exception:
            # --- Do not swallow errors silently; otherwise the PDF will miss the image ---
            overlay_path = None
            print("Failed to generate overlay PNG:")
            print(traceback.format_exc())




        
        # --- 3) Gerar gráfico e guardar PNG (com fit hiperbólico + foco) ---
        graph_path = os.path.join(out_dir, "fwhm_graph.png")
        try:
            plt.figure(figsize=(7, 4))
            plt.title("FWHM vs Column")
            plt.xlabel("Column (px)")
            plt.ylabel("FWHM (px)" if pixel_um is None else "FWHM (µm)")

            x = np.asarray(cols, dtype=float)
            y_px = np.asarray(fwhms, dtype=float)   # <-- assumimos px (ver fix no worker)

            # filtrar finitos
            m = np.isfinite(x) & np.isfinite(y_px)
            x = x[m]
            y_px = y_px[m]

            # dados para plot (converte só para mostrar)
            y_plot = y_px if pixel_um is None else (y_px * float(pixel_um))

            # curva medida
            plt.plot(x, y_plot, "o-", color="tab:blue", linewidth=1.5, markersize=4, label="FWHM (dados)")
            plt.grid(True, alpha=0.3)

            # fit hiperbólico (igual ao qc_plots)
            info = None
            if len(x) >= 3:
                fit = fit_focus_hyperbola(x, y_plot, use_scipy=True)  # fit nas unidades do plot
                if fit.get("ok", False):
                    a, b, c, f = fit["a"], fit["b"], fit["c"], fit["f"]
                    x_fit = np.linspace(float(np.min(x)), float(np.max(x)), 400)
                    y_fit = b * np.sqrt((x_fit - f)**2 + a**2) + c
                    y_min = fit["y_min"]  # = b*a + c

                    plt.plot(x_fit, y_fit, "-", color="tab:red", linewidth=2.0, label="Ajuste hiperbólico")
                    plt.scatter([f], [y_min], s=80, color="tab:green", zorder=5,
                                label=f"Foco: x={f:.2f}, y={y_min:.2f}")

            plt.legend(loc="best", fontsize=8)
            plt.tight_layout()
            plt.savefig(graph_path, dpi=200)
            plt.close()
        except Exception:
            graph_path = None



        # ---- 4) CSV com todos os valores ----
        csv_path = os.path.join(out_dir, "QualityControl_AllValues.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # cabeçalho
            writer.writerow([
                "timestamp", "camera", "beam_used", "intensity",
                "angle_deg", "focus_col", "focus_row",
                "fwhm_focus_px", "fwhm_focus_um",
                "col", "peak_row", "fwhm_px", "fwhm_um"
            ])
            for c, p, w in zip(cols, peaks, fwhms):
                w_um = (float(w) * float(pixel_um)) if pixel_um is not None and np.isfinite(w) else ""
                writer.writerow([
                    timestamp, camera_name, beam_used, intensity,
                    angle_deg, focus_col, focus_row,
                    fwhm_focus, fwhm_focus_um if np.isfinite(fwhm_focus_um) else "",
                    int(c) if np.isfinite(c) else "", float(p) if np.isfinite(p) else "",
                    float(w) if np.isfinite(w) else "", w_um
                ])
        # --- 5) OME-ZARR com frame + overlays ---
        zarr_path = os.path.join(out_dir, "frame_and_overlays.ome.zarr")

        store = parse_url(zarr_path, mode="w").store
        root = zarr.group(store=store, overwrite=True)

        if frame is not None and frame.size:
            # escreve o nível 0 (single-scale)
            chunks = (min(256, frame.shape[0]), min(256, frame.shape[1]))
            root.create_dataset("0", data=frame, chunks=chunks, overwrite=True)

            # metadata OME-Zarr (single scale)
            pixel_um = bundle.get("pixel_size_um", None)
            base = float(pixel_um) if pixel_um is not None else 1.0

            datasets = [{
                "path": "0",
                "coordinateTransformations": [{
                    "type": "scale",
                    "scale": [base, base],  # y, x
                }],
            }]
            axes = [
                {"name": "y", "type": "space", "unit": "um"},
                {"name": "x", "type": "space", "unit": "um"},
            ]

            write_multiscales_metadata(
                group=root,
                datasets=datasets,
                fmt=FormatV04(),
                axes=axes,
                name="image",
            )

        # overlays continuam num subgrupo à parte
        ov = root.require_group("overlays")

        root.attrs.update({
            "timestamp": timestamp,
            "camera": camera_name,
            "beam_used": beam_used,
            "intensity": intensity,
            "angle_deg": float(angle_deg) if np.isfinite(angle_deg) else None,
            "focus_col": int(focus_col) if focus_col is not None else None,
            "focus_row": float(focus_row) if focus_row is not None else None,
            "pixel_size_um": float(pixel_um) if pixel_um is not None else None,
        })

        if coef is not None:
            try:
                ov.create_dataset("tilt_coef", data=np.asarray(coef), overwrite=True)
            except Exception:
                pass

        if focus_col is not None and focus_row is not None:
            ov.create_dataset(
                "focus_point",
                data=np.array([float(focus_row), float(focus_col)], dtype=np.float32),
                overwrite=True
            )

        ov.create_dataset("cols", data=cols.astype(np.int32, copy=False), overwrite=True)
        ov.create_dataset("peaks", data=peaks.astype(np.float32, copy=False), overwrite=True)
        ov.create_dataset("fwhms", data=fwhms.astype(np.float32, copy=False), overwrite=True)

        # ---- 6) PDF report ----
        pdf_path = os.path.join(out_dir, "QualityControl_Report.pdf")
        self._build_qc_pdf(
            pdf_path=pdf_path,
            timestamp=timestamp,
            camera_name=camera_name,
            beam_used=beam_used,
            beam_color_hex=beam_color,
            intensity=intensity,
            angle_deg=angle_deg,
            focus_col=focus_col,
            focus_row=focus_row,
            fwhm_focus_px=fwhm_focus,
            fwhm_focus_um=fwhm_focus_um,
            cols=cols,
            peaks=peaks,
            fwhms=fwhms,
            pixel_um=pixel_um,
            overlay_img_path=overlay_path,
            graph_img_path=graph_path
        )


    def _build_qc_pdf(
        self,
        pdf_path: str,
        timestamp: str,
        camera_name: str,
        beam_used: str,
        beam_color_hex:str,
        intensity: str,
        angle_deg: float,
        focus_col,
        focus_row,
        fwhm_focus_px: float,
        fwhm_focus_um: float,
        cols: np.ndarray,
        peaks: np.ndarray,
        fwhms: np.ndarray,
        pixel_um,
        overlay_img_path: str,
        graph_img_path: str
    ):
        """
        PDF com:
        - valores tilt/focus/waist
        - tabela de FWHM/peaks por coluna
        - imagens: feixe+overlays e gráfico
        """
        from reportlab.lib.colors import HexColor, black
        c = canvas.Canvas(pdf_path, pagesize=A4)
        W, H = A4
        x0 = 2*cm
        y = H - 2*cm

        def line(txt, dy=0.55*cm, size=11):
            nonlocal y
            c.setFont("Helvetica", size)
            c.drawString(x0, y, txt)
            y -= dy
            if y < 2*cm:
                c.showPage()
                y = H - 2*cm

        # Título
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x0, y, "Quality Control Report")
        y -= 0.9*cm

        # Resumo
        line(f"Timestamp: {timestamp}")
        line(f"Camera: {camera_name}")
        
        # Beam usado (texto + swatch da cor)
        c.setFont("Helvetica", 11)
        txt = f"Beam used: {beam_used} "
        c.drawString(x0, y, txt)

        if beam_color_hex:
            sw_x = x0 + c.stringWidth(txt, "Helvetica", 11) + 6
            c.setFillColor(HexColor(beam_color_hex))
            c.rect(sw_x, y - 3, 10, 10, fill=1, stroke=0)  # quadrado cor
            c.setFillColor(black)

        y -= 0.55 * cm

        line(f"Intensity: {intensity}")
        line(f"Angle Tilt (deg): {angle_deg:.3f}" if np.isfinite(angle_deg) else "Angle Tilt (deg): —")
        line(f"Focus (col,row): ({focus_col},{focus_row:.2f})" if focus_col is not None and focus_row is not None else "Focus (col,row): —")
        if pixel_um is None:
            line(f"Beam Waist (FWHM at focus): {fwhm_focus_px:.3f} px" if np.isfinite(fwhm_focus_px) else "Beam Waist: —")
        else:
            line(f"Beam Waist (FWHM at focus): {fwhm_focus_um:.3f} µm" if np.isfinite(fwhm_focus_um) else "Beam Waist: —")

        y -= 0.3*cm

        # Imagens
        def draw_img(path, title):
            nonlocal y
            if not path or not os.path.exists(path):
                return
            line(title, dy=0.6*cm, size=12)
            img = ImageReader(path)
            iw, ih = img.getSize()
            maxw = W - 4*cm
            maxh = 8*cm
            scale = min(maxw/iw, maxh/ih)
            ww, hh = iw*scale, ih*scale
            if y - hh < 2*cm:
                c.showPage()
                y = H - 2*cm
            c.drawImage(img, x0, y - hh, width=ww, height=hh)
            y -= (hh + 0.6*cm)

        draw_img(graph_img_path, "FWHM graph:")
        draw_img(overlay_img_path, f"Camera snapshot + overlays ({camera_name}):")
        

        c.save()

        
    
    
    
    def _render_frame_with_overlays(self, frame, coef, focus_col, focus_row, out_path,
                                    cam_id=None, contrast_limits=None, gamma=1.0):
        """
        Create a PNG snapshot from the camera frame and draw QC overlays.

        IMPORTANT: If contrast_limits is provided (from the Napari layer),
        the exported image will match the viewer contrast (clip + scale).
        """
        if frame is None or frame.size == 0:
            raise ValueError("Empty frame: cannot render overlay image.")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        # --- Mirror Camera 1 to match the viewer appearance ---
        # Viewer code mirrors Camera 1 using np.fliplr(frame). 
        '''
        if cam_id == 1:
            W0 = frame.shape[1]
            frame = np.fliplr(frame)

            # Adjust focus column for horizontal flip: x' = (W-1) - x
            if focus_col is not None:
                try:
                    focus_col = (W0 - 1) - float(focus_col)
                except Exception:
                    pass

            # Adjust tilt line coefficients for horizontal flip:
            # y = m*x + b -> y = (-m)*x' + (m*(W-1) + b)
            if coef is not None and len(coef) >= 2:
                try:
                    m, b = float(coef[0]), float(coef[1])
                    coef = (-m, (m * (W0 - 1) + b))
                except Exception:
                    pass
        
        '''
        # --- CRITICAL: make sure OpenCV sees contiguous memory ---
        frame = np.ascontiguousarray(frame)

        # --- Convert to display-like 8-bit using Napari contrast limits ---
        fr = frame.astype(np.float32)

        if contrast_limits is not None and len(contrast_limits) == 2:
            # Use the exact same low/high as the viewer layer
            low, high = float(contrast_limits[0]), float(contrast_limits[1])
            if high <= low:
                # Fallback if limits are invalid
                low, high = float(np.nanmin(fr)), float(np.nanmax(fr))
        else:
            # Fallback: use robust min/max
            low, high = float(np.nanmin(fr)), float(np.nanmax(fr))

        # Clip + normalize to 0..1
        fr = np.clip(fr, low, high)
        fr = (fr - low) / (high - low + 1e-9)

        # Optional: apply gamma similarly to viewer (best-effort)
        # Napari applies gamma after normalization; this approximates that.
        try:
            g = float(gamma) if gamma is not None else 1.0
            if g > 0 and abs(g - 1.0) > 1e-6:
                fr = np.power(fr, 1.0 / g)
        except Exception:
            pass

        # Convert to 8-bit
        fr8 = (255.0 * fr).astype(np.uint8)
        fr8 = np.ascontiguousarray(fr8)

        # Convert to BGR for colored overlays
        bgr = cv2.cvtColor(fr8, cv2.COLOR_GRAY2BGR)
        H, W = bgr.shape[:2]

        # --- Draw tilt line (if available) ---
        if coef is not None and len(coef) >= 2:
            try:
                m, b = float(coef[0]), float(coef[1])
                x1, x2 = 0, W - 1
                y1 = int(round(m * x1 + b))
                y2 = int(round(m * x2 + b))
                cv2.line(bgr, (x1, y1), (x2, y2), (0, 0, 255), 2, cv2.LINE_AA)  # red
            except Exception:
                pass

        # --- Draw focus point (if available) ---
        if focus_col is not None and focus_row is not None:
            try:
                cx = int(round(float(focus_col)))
                cy = int(round(float(focus_row)))
                cv2.circle(bgr, (cx, cy), 8, (0, 255, 255), -1, cv2.LINE_AA)       # yellow dot
                cv2.circle(bgr, (cx, cy), 14, (0, 255, 255), 2, cv2.LINE_AA)  # yellow ring
            except Exception:
                pass

        # --- Unicode-safe write (Windows) ---
        imwrite_unicode(out_path, bgr)
        if not os.path.exists(out_path):
            raise IOError(f"Image write failed: file was not created: {out_path}")

        return out_path
    
    # Save pdf for "both" cameras when they are enable

    def _save_quality_control_bundle_both(self, combined: dict):
        """
        Save BOTH camera results into the SAME PDF (and same QC folder).
        """
        base_dir = getattr(self, "current_save_directory", None) or os.getcwd()
        qc_folder_name = (combined.get("qc_folder_name") or "").strip()
        out_dir = self._next_qc_folder(base_dir, qc_folder_name if qc_folder_name else None)


        timestamp = combined.get("timestamp", datetime.now().isoformat(timespec="seconds"))
        beam_info = combined.get("beam_info") or self._get_beam_info_snapshot()
        items = combined.get("items", [])

        # --- write a single CSV containing both cameras ---
        csv_path = os.path.join(out_dir, "QualityControl_AllValues.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header (same as single-camera export, plus camera column is already included)
            writer.writerow([
                "timestamp", "camera", "beam_used", "intensity",
                "angle_deg", "focus_col", "focus_row",
                "fwhm_focus_px", "fwhm_focus_um",
                "col", "peak_row", "fwhm_px", "fwhm_um"
            ])

            beam_used = beam_info.get("beam_nm", "Unknown")
            intensity = beam_info.get("intensity_str", "Unknown")

            for item in items:
                cam_id = item.get("cam_id")
                camera_name = item.get("camera_name", f"Camera {cam_id}")

                angle_deg = item.get("angle_deg", np.nan)
                focus = item.get("focus", None)
                pixel_um = item.get("pixel_size_um", None)

                cols = np.asarray(item.get("cols", []))
                peaks = np.asarray(item.get("peaks", []))
                fwhms = np.asarray(item.get("fwhms", []))

                focus_col = focus.get("column") if isinstance(focus, dict) else None
                focus_row = focus.get("row") if isinstance(focus, dict) else None
                fwhm_focus_px = float(focus.get("fwhm", np.nan)) if isinstance(focus, dict) else np.nan
                fwhm_focus_um = (fwhm_focus_px * float(pixel_um)) if (pixel_um is not None and np.isfinite(fwhm_focus_px)) else ""

                # Write one row per (col, peak, fwhm) sample
                for c, p, w in zip(cols, peaks, fwhms):
                    w_um = (float(w) * float(pixel_um)) if (pixel_um is not None and np.isfinite(w)) else ""
                    writer.writerow([
                        timestamp, camera_name, beam_used, intensity,
                        float(angle_deg) if np.isfinite(angle_deg) else "",
                        focus_col if focus_col is not None else "",
                        float(focus_row) if focus_row is not None else "",
                        float(fwhm_focus_px) if np.isfinite(fwhm_focus_px) else "",
                        fwhm_focus_um,
                        int(c) if np.isfinite(c) else "",
                        float(p) if np.isfinite(p) else "",
                        float(w) if np.isfinite(w) else "",
                        w_um
                    ])

        # Build per-camera images/graphs and store paths for PDF
        sections = []
        for item in items:
            cam_id = item.get("cam_id")
            camera_name = item.get("camera_name", f"Camera {cam_id}")
            frame = np.asarray(item.get("frame", None))
            coef = item.get("coef", None)
            focus = item.get("focus", None)
            cols = np.asarray(item.get("cols", []))
            peaks = np.asarray(item.get("peaks", []))
            fwhms = np.asarray(item.get("fwhms", []))
            angle_deg = item.get("angle_deg", np.nan)
            pixel_um = item.get("pixel_size_um", None)

            focus_col = focus.get("column") if isinstance(focus, dict) else None
            focus_row = focus.get("row") if isinstance(focus, dict) else None
            fwhm_focus = float(focus.get("fwhm", np.nan)) if isinstance(focus, dict) else np.nan
            fwhm_focus_um = (fwhm_focus * float(pixel_um)) if (pixel_um is not None and np.isfinite(fwhm_focus)) else np.nan

            # Optional: match viewer contrast if layer exists
            contrast_limits, gamma = None, None
            try:
                if camera_name in self.viewer.layers:
                    layer = self.viewer.layers[camera_name]
                    contrast_limits = tuple(layer.contrast_limits)
                    gamma = float(getattr(layer, "gamma", 1.0))
            except Exception:
                pass

            safe_cam = camera_name.replace(" ", "_")
            overlay_path = os.path.join(out_dir, f"{safe_cam}_snap_with_overlays.png")
            graph_path = os.path.join(out_dir, f"{safe_cam}_fwhm_graph.png")

            # Render overlay PNG
            try:
                overlay_path = self._render_frame_with_overlays(
                    frame=frame,
                    coef=coef,
                    focus_col=focus_col,
                    focus_row=focus_row,
                    out_path=overlay_path,
                    cam_id=cam_id,
                    contrast_limits=contrast_limits,
                    gamma=gamma,
                )
            except Exception:
                overlay_path = None
                print("Failed to generate overlay PNG for", camera_name)
                print(traceback.format_exc())

            # --- generate graph PNG WITH hyperbolic fit and focus marker ---
            try:
                plt.figure(figsize=(7, 4))
                plt.title(f"FWHM vs Column ({camera_name})")
                plt.xlabel("Column (px)")
                plt.ylabel("FWHM (px)" if pixel_um is None else "FWHM (µm)")

                x = np.asarray(cols, dtype=float)
                y_px = np.asarray(fwhms, dtype=float)

                # Keep finite points only
                m = np.isfinite(x) & np.isfinite(y_px)
                x = x[m]
                y_px = y_px[m]

                # Convert only for visualization if pixel calibration exists
                y_plot = y_px if pixel_um is None else (y_px * float(pixel_um))

                # Measured curve
                plt.plot(
                    x, y_plot, "o-",
                    color="tab:blue", linewidth=1.5, markersize=4,
                    label="FWHM (data)"
                )
                plt.grid(True, alpha=0.3)

                # Hyperbolic fit (same approach as single-camera export)
                if len(x) >= 3:
                    fit = fit_focus_hyperbola(x, y_plot, use_scipy=True)  # Fit in plot units
                    if fit.get("ok", False):
                        a, b, c0, f0 = fit["a"], fit["b"], fit["c"], fit["f"]
                        x_fit = np.linspace(float(np.min(x)), float(np.max(x)), 400)
                        y_fit = b * np.sqrt((x_fit - f0) ** 2 + a ** 2) + c0
                        y_min = fit["y_min"]  # = b*a + c

                        plt.plot(
                            x_fit, y_fit, "-",
                            color="tab:red", linewidth=2.0,
                            label="Hyperbolic fit"
                        )
                        plt.scatter(
                            [f0], [y_min],
                            s=80, color="tab:green", zorder=5,
                            label=f"Focus: x={f0:.2f}, y={y_min:.2f}"
                        )

                plt.legend(loc="best", fontsize=8)
                plt.tight_layout()
                plt.savefig(graph_path, dpi=200)
                plt.close()
            except Exception:
                graph_path = None
                print("Failed to generate fitted graph for", camera_name)
                print(traceback.format_exc())

            sections.append({
                "camera_name": camera_name,
                "angle_deg": angle_deg,
                "focus_col": focus_col,
                "focus_row": focus_row,
                "fwhm_focus_px": fwhm_focus,
                "fwhm_focus_um": fwhm_focus_um,
                "pixel_um": pixel_um,
                "overlay_img_path": overlay_path,
                "graph_img_path": graph_path,
            })

        # Build one PDF with both sections
        pdf_path = os.path.join(out_dir, "QualityControl_Report.pdf")
        self._build_qc_pdf_both(
            pdf_path=pdf_path,
            timestamp=timestamp,
            beam_info=beam_info,
            sections=sections
        )


    def _build_qc_pdf_both(self, pdf_path: str, timestamp: str, beam_info: dict, sections: list[dict]):
        """
        Create one PDF containing results for BOTH cameras.
        Each camera gets its own section/page.
        """
        from reportlab.lib.colors import HexColor, black
        c = canvas.Canvas(pdf_path, pagesize=A4)
        W, H = A4
        x0 = 2 * cm
        y = H - 2 * cm

        def line(txt, dy=0.55 * cm, size=11):
            nonlocal y
            c.setFont("Helvetica", size)
            c.drawString(x0, y, txt)
            y -= dy
            if y < 2 * cm:
                c.showPage()
                y = H - 2 * cm

        def draw_img(path, title):
            nonlocal y
            if not path or not os.path.exists(path):
                return
            line(title, dy=0.6 * cm, size=12)
            img = ImageReader(path)
            iw, ih = img.getSize()
            maxw = W - 4 * cm
            maxh = 8 * cm
            scale = min(maxw / iw, maxh / ih)
            ww, hh = iw * scale, ih * scale
            if y - hh < 2 * cm:
                c.showPage()
                y = H - 2 * cm
            c.drawImage(img, x0, y - hh, width=ww, height=hh)
            y -= (hh + 0.6 * cm)

        # --- Cover / Summary ---
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x0, y, "Quality Control Report (Both Cameras)")
        y -= 0.9 * cm
        line(f"Timestamp: {timestamp}")

        beam_used = beam_info.get("beam_nm", "Unknown")
        beam_color_hex = beam_info.get("color_hex", None)
        intensity = beam_info.get("intensity_str", "Unknown")

        c.setFont("Helvetica", 11)
        txt = f"Beam used: {beam_used} "
        c.drawString(x0, y, txt)
        if beam_color_hex:
            sw_x = x0 + c.stringWidth(txt, "Helvetica", 11) + 6
            c.setFillColor(HexColor(beam_color_hex))
            c.rect(sw_x, y - 3, 10, 10, fill=1, stroke=0)
            c.setFillColor(black)
        y -= 0.55 * cm
        line(f"Intensity: {intensity}")
        line("Included cameras: " + ", ".join([s["camera_name"] for s in sections]))

        # --- comparison table on the cover page ---
        # This table summarizes key metrics side-by-side for both cameras.
        y -= 0.3 * cm  # extra spacing before table

        def draw_comparison_table(c, x0, y_top, W, sections):
            """
            Draw a simple grid table using low-level canvas primitives.
            Keeping it self-contained avoids reportlab.platypus dependency changes.
            """
            # Table geometry
            table_width = W - 4 * cm
            col_widths = [0.20, 0.20, 0.30, 0.30]  # fractions of table_width
            col_w = [table_width * f for f in col_widths]
            row_h = 0.75 * cm
            padding_x = 4

            headers = ["Camera", "Angle Tilt (deg)", "Focus (col,row)", "Beam Waist at focus"]

            # Helper: format values
            def fmt_angle(v):
                return f"{v:.3f}" if (v is not None and np.isfinite(v)) else "—"

            def fmt_focus(col, row):
                if col is None or row is None:
                    return "—"
                try:
                    return f"({int(col)},{float(row):.2f})"
                except Exception:
                    return "—"

            def fmt_waist(s):
                """
                Use µm if calibrated; otherwise px.
                """
                px_um = s.get("pixel_um", None)
                if px_um is None:
                    v = s.get("fwhm_focus_px", np.nan)
                    return f"{v:.3f} px" if np.isfinite(v) else "—"
                else:
                    v = s.get("fwhm_focus_um", np.nan)
                    return f"{v:.3f} µm" if np.isfinite(v) else "—"

            # Compute rows
            rows = []
            for s in sections:
                rows.append([
                    s.get("camera_name", "Unknown"),
                    fmt_angle(s.get("angle_deg", np.nan)),
                    fmt_focus(s.get("focus_col", None), s.get("focus_row", None)),
                    fmt_waist(s),
                ])

            # Draw header background (optional but improves readability)
            c.setFillColorRGB(0.90, 0.90, 0.90)
            c.rect(x0, y_top - row_h, table_width, row_h, fill=1, stroke=0)
            c.setFillColorRGB(0, 0, 0)

            # Draw outer border
            c.rect(x0, y_top - row_h * (1 + len(rows)), table_width, row_h * (1 + len(rows)), fill=0, stroke=1)

            # Draw vertical lines
            x = x0
            for w in col_w[:-1]:
                x += w
                c.line(x, y_top, x, y_top - row_h * (1 + len(rows)))

            # Draw horizontal lines
            for i in range(1 + len(rows)):
                y_line = y_top - row_h * i
                c.line(x0, y_line, x0 + table_width, y_line)

            # Write header text
            c.setFont("Helvetica-Bold", 10)
            x = x0
            for j, h in enumerate(headers):
                c.drawString(x + padding_x, y_top - row_h + 0.22 * cm, h)
                x += col_w[j]

            # Write row text
            c.setFont("Helvetica", 10)
            for i, r in enumerate(rows):
                y_row = y_top - row_h * (i + 2) + 0.22 * cm
                x = x0
                for j, cell in enumerate(r):
                    c.drawString(x + padding_x, y_row, str(cell))
                    x += col_w[j]

        # Decide where to place the table (ensure it fits the page)
        table_top_y = y
        min_bottom_y = 2.0 * cm
        needed_height = (1 + len(sections)) * (0.75 * cm)

        if table_top_y - needed_height < min_bottom_y:
            # Not enough space on cover: start a new page for the table
            c.showPage()
            y = H - 2 * cm
            table_top_y = y

        draw_comparison_table(c, x0, table_top_y, W, sections)

        # After the table, go to next page (camera sections)
        c.showPage()

        # --- One section per camera ---
        for s in sections:
            y = H - 2 * cm
            c.setFont("Helvetica-Bold", 15)
            c.drawString(x0, y, f"Results - {s['camera_name']}")
            y -= 0.9 * cm

            angle_deg = s.get("angle_deg", np.nan)
            focus_col = s.get("focus_col", None)
            focus_row = s.get("focus_row", None)
            pixel_um = s.get("pixel_um", None)

            line(f"Angle Tilt (deg): {angle_deg:.3f}" if np.isfinite(angle_deg) else "Angle Tilt (deg): —")
            line(f"Focus (col,row): ({focus_col},{focus_row:.2f})"
                if focus_col is not None and focus_row is not None else "Focus (col,row): —")

            if pixel_um is None:
                fpx = s.get("fwhm_focus_px", np.nan)
                line(f"Beam Waist (FWHM at focus): {fpx:.3f} px" if np.isfinite(fpx) else "Beam Waist: —")
            else:
                fum = s.get("fwhm_focus_um", np.nan)
                line(f"Beam Waist (FWHM at focus): {fum:.3f} µm" if np.isfinite(fum) else "Beam Waist: —")

            y -= 0.3 * cm
            draw_img(s.get("graph_img_path"), "FWHM graph:")
            draw_img(s.get("overlay_img_path"), f"Camera snapshot + overlays ({s['camera_name']}):")

            c.showPage()

        c.save()

    #-----------------------------------------------------------------------------------------------------------
    #Helper for scanner knows camera mode

    def _get_active_scanner_camera_mode(self):
        """
        Return the camera mode that the unified scanner button should use.

        Priority:
            1) Cameras currently in Live mode
            2) Cameras selected for acquisition

        Returns:
            - "Widefield Mode"
            - "Confocal Mode"
            - None  (if no valid active mode or if modes are mixed)
        """
        modes = []

        # First priority: currently live cameras
        for cam_widget in (
            getattr(self, "camera_widget_1", None),
            getattr(self, "camera_widget_2", None),
        ):
            if cam_widget is None:
                continue
            if cam_widget.live_button.isChecked():
                modes.append(cam_widget.cameramode_combobox.currentText())

        # Fallback: selected cameras for acquisition
        if not modes:
            for cam_widget in (
                getattr(self, "camera_widget_1", None),
                getattr(self, "camera_widget_2", None),
            ):
                if cam_widget is None:
                    continue
                if cam_widget.camera_checkbox.isChecked():
                    modes.append(cam_widget.cameramode_combobox.currentText())

        # Keep only valid scanner-driven external modes
        modes = [m for m in modes if m in ("Widefield Mode", "Confocal Mode")]

        # If both active cameras share the same mode, return it
        unique_modes = list(dict.fromkeys(modes))
        if len(unique_modes) == 1:
            return unique_modes[0]

        return None
    
    #-------------------------------------------------------------------------------------------------
    #Helper to change speed and exposure time in Confocal Mode

    def _get_active_confocal_cameras(self):
        """
        Return the list of active camera widgets currently relevant for confocal sync.

        Priority:
            1) Cameras in Live mode
            2) If no camera is live, cameras selected for acquisition

        Only cameras in Confocal Mode are returned.
        """
        camera_widgets = [
            getattr(self, "camera_widget_1", None),
            getattr(self, "camera_widget_2", None),
        ]

        live_cameras = []
        selected_cameras = []

        for cam in camera_widgets:
            if cam is None:
                continue
            if cam.cameramode_combobox.currentText() != "Confocal Mode":
                continue

            if cam.live_button.isChecked():
                live_cameras.append(cam)

            if cam.camera_checkbox.isChecked():
                selected_cameras.append(cam)

        return live_cameras if live_cameras else selected_cameras
    
    def on_camera_exposure_changed_by_user(self, exposure_ms: float, camera_idx: int) -> None:
        """
        When one camera is active in confocal mode, changing its exposure updates scanner speed.
        When two cameras are active, camera exposure editing is ignored and scanner remains the master.
        """
        if self._confocal_sync_in_progress:
            return

        active_cameras = self._get_active_confocal_cameras()
        if not active_cameras:
            return

        # Only enable bidirectional sync when exactly one confocal camera is active
        if len(active_cameras) != 1:
            return

        active_camera = active_cameras[0]
        if active_camera.idx != camera_idx:
            return

        try:
            self._confocal_sync_in_progress = True

            speed = speed_from_exposure_ms(exposure_ms)
            speed = clamp_confocal_speed(speed)

            # Update scanner UI and hardware
            self.scanner_widget.set_scanner_speed_programmatically(speed, apply_to_scanner=True)

        finally:
            self._confocal_sync_in_progress = False

    def on_scanner_speed_changed_by_user(self, speed: float) -> None:
        """
        In confocal mode, scanner speed is always allowed to drive camera exposure.
        With one active camera, only that camera is updated.
        With two active cameras, both active cameras are updated and exposure editing is disabled.
        """
        if self._confocal_sync_in_progress:
            return

        active_cameras = self._get_active_confocal_cameras()
        if not active_cameras:
            return

        try:
            self._confocal_sync_in_progress = True

            exposure_ms = exposure_ms_from_speed(speed)
            exposure_ms = clamp_confocal_exposure_ms(exposure_ms)

            for cam in active_cameras:
                cam.set_exposure_programmatically(exposure_ms, apply_to_camera=True)

        finally:
            self._confocal_sync_in_progress = False

    #--------------------------------------------------------------------------------
    #Block Exposure Edit when there are 2 cameras live in confocal mode

    def update_confocal_exposure_edit_lock(self) -> None:
        """
        Enable or disable manual exposure editing depending on how many confocal cameras are active.

        Rules:
            - 1 active confocal camera  -> exposure can be edited
            - 2 active confocal cameras -> exposure editing is disabled, scanner speed becomes the master
        """
        active_cameras = self._get_active_confocal_cameras()
        two_camera_confocal = len(active_cameras) >= 2

        for cam in [getattr(self, "camera_widget_1", None), getattr(self, "camera_widget_2", None)]:
            if cam is None:
                continue

            is_confocal = cam.cameramode_combobox.currentText() == "Confocal Mode"

            allow_manual_exposure = is_confocal and not two_camera_confocal
            if not is_confocal:
                allow_manual_exposure = True

            cam.exposuretime_lineedit.setEnabled(allow_manual_exposure)
            cam.exposuretime_slider.setEnabled(allow_manual_exposure)




    #-------------------------------------------------------------------------------------------------
    # Initialization

    def center_on_screen(self):
        """Centers the window on the screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())


    def __init__(self, initial_path=None):
        super().__init__()

        
        # Reuse the logger configured at application startup
        self.logger = logging.getLogger("ALM")

        self.logger.info("ALM_Lightsheet initialisation started")

        try:
            # Your existing initialisation code goes here

            self.logger.info("ALM_Lightsheet initialisation completed successfully")

        except Exception:
            # Log the full traceback if something fails during initialisation
            self.logger.exception("Error during ALM_Lightsheet initialisation")
            raise



        self.setWindowTitle("")
        self.setWindowIcon(QIcon("ALM.ico"))

        with open("Extra_Files//Filter_List.json", 'r') as file:
            self.filter_json_data = json.load(file)

        self.latest_frames = {}

        #---------------------------------------------------------------------------
        # Initialize the devices
        # self.filterwheel1 = device_initializations.filterwheel_1(self)
        # self.filterwheel2 = device_initializations.filterwheel_2(self)
        # self.laserbox = device_initializations.laserbox(self)
        # self.rtc5_board = device_initializations.scanner(self)
        # self.pidevice = device_initializations.stages(self)

        # list out each init call as a (name, callable) tuple
        init_tasks = [
            ("filterwheel1",     lambda: device_initializations.filterwheel_1(self)),
            ("filterwheel2",     lambda: device_initializations.filterwheel_2(self)),
            ("laserbox",         lambda: device_initializations.laserbox(self)),
            ("rtc5_board",       lambda: device_initializations.scanner(self)),
            ("pidevice",         lambda: device_initializations.stages(self)),
        ]

        # Submit them all at once
        self._init_results = {}
        with ThreadPoolExecutor(max_workers=len(init_tasks)) as exe:
            futures = { exe.submit(fn): name for name, fn in init_tasks }
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    device_obj = fut.result()
                except Exception as e:
                    # log or re-raise if something goes catastrophically wrong
                    raise RuntimeError(f"Failed to init {name}: {e}")
                self._init_results[name] = device_obj

        # unpack them into attributes
        self.filterwheel1 = self._init_results["filterwheel1"]
        self.filterwheel2 = self._init_results["filterwheel2"]
        self.laserbox     = self._init_results["laserbox"]
        self.rtc5_board   = self._init_results["rtc5_board"]
        self.pidevice     = self._init_results["pidevice"]

        # Global flag: True while a Y-stack acquisition owns the camera configuration.
        self.acquisition_running = False



        # Initialize the cameras
        self.number_of_cameras = DCAM.DCAM.get_cameras_number()

        self.single_camera = None
        # if number_of_cameras == 0:
        if self.number_of_cameras == 1:
            self.camera = device_initializations.camera(self, idx=0)
            self.serial_number = self.camera.get_device_info()[2]

            if self.serial_number == "S/N: 302077":
                self.camera_1 = self.camera
                del self.camera
                self.acquisition_thread_1 = Acquisition_Thread(self.camera_1)
                self.single_camera = 1

                self.camera_2 = None

            elif self.serial_number == "S/N: 302079":
                self.camera_2 = self.camera
                del self.camera
                self.acquisition_thread_2 = Acquisition_Thread(self.camera_2)
                self.single_camera = 2

                self.camera_1 = None


        elif self.number_of_cameras == 2:
            self.camera_1 = device_initializations.camera(self, idx=1)
            self.camera_2 = device_initializations.camera(self, idx=0)

            self.acquisition_thread_1 = Acquisition_Thread(self.camera_1)
            self.acquisition_thread_2 = Acquisition_Thread(self.camera_2)

        
        # Prevent recursive updates between camera exposure and scanner speed
        self._confocal_sync_in_progress = False


        # #---------------------------------------------------------------------------
        # # Create GUI

        # # # Create a central widget with a grid layout.        
        splitter_layout = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter_layout)
        splitter_layout.setContentsMargins(0, 0, 0, 0)


        # _________________________________________
        # Vertical Layout for Cameras

        cameras_container = QWidget()
        cameras_layout = QVBoxLayout(cameras_container)
        cameras_layout.setContentsMargins(0, 0, 0, 0)
        cameras_layout.setSpacing(0)

        
        # if number_of_cameras == 0:
        if self.number_of_cameras == 1:
            
            if self.single_camera == 1:
                    # Create the first camera widget
                self.camera_widget_2 = None
                self.camera_widget_1 = Camera_Widget(idx=0, label="Camera 1:", acq_thread = self.acquisition_thread_1)
                self.camera_widget_1.setMaximumHeight(300)
                cameras_layout.addWidget(self.camera_widget_1, alignment=Qt.AlignTop)

                    # Create the thread
                self.grabber_1 = FrameGrabberThread(camera=self.camera_1, cam_id=1, interval_ms=50)
                self.grabber_1.frame_ready.connect(self.on_frame_received)
                self.grabber_1.frame_ready.connect(self._on_frame_ready)

                self.camera_widget_1.live_toggled.connect(self.on_camera1_live_toggled)
                self.camera_widget_1.snap_clicked.connect(lambda: self.on_camera1_snap(self.current_save_directory))
                self.camera_widget_1.restart_clicked.connect(self.camera1_restart)
                
                
            elif self.single_camera == 2:
                    # Create the first camera widget
                self.camera_widget_1 = None
                self.camera_widget_2 = Camera_Widget(idx=0, label="Camera 2:", acq_thread = self.acquisition_thread_2)
                self.camera_widget_2.setMaximumHeight(300)
                cameras_layout.addWidget(self.camera_widget_2, alignment=Qt.AlignTop)

                    # Create the thread
                self.grabber_2 = FrameGrabberThread(camera=self.camera_2, cam_id=2, interval_ms=50)
                self.grabber_2.frame_ready.connect(self.on_frame_received)
                self.grabber_2.frame_ready.connect(self._on_frame_ready)

                self.camera_widget_2.live_toggled.connect(self.on_camera2_live_toggled)
                self.camera_widget_2.snap_clicked.connect(lambda: self.on_camera2_snap(self.current_save_directory))
                self.camera_widget_2.restart_clicked.connect(self.camera2_restart)


        elif self.number_of_cameras == 2:
                # Create the first camera widget
            self.camera_widget_1 = Camera_Widget(idx=1, label="Camera 1:", parent=self, acq_thread=self.acquisition_thread_1)
            self.camera_widget_1.setMaximumHeight(300)
            cameras_layout.addWidget(self.camera_widget_1, alignment=Qt.AlignTop)

                # Create the second camera widget
            self.camera_widget_2 = Camera_Widget(idx=0, label="Camera 2:", parent=self, acq_thread=self.acquisition_thread_2)
            self.camera_widget_2.setMaximumHeight(300)
            cameras_layout.addWidget(self.camera_widget_2, alignment=Qt.AlignTop)

                # Create the threads
            self.grabber_1 = FrameGrabberThread(camera=self.camera_1, cam_id=1, interval_ms=75)
            self.grabber_2 = FrameGrabberThread(camera=self.camera_2, cam_id=2, interval_ms=75)

                # Connect the received frames
            self.grabber_1.frame_ready.connect(self.on_frame_received)
            self.grabber_1.frame_ready.connect(self._on_frame_ready)
            self.grabber_2.frame_ready.connect(self.on_frame_received)
            self.grabber_2.frame_ready.connect(self._on_frame_ready)

                # Connect the received button signals
            self.camera_widget_1.live_toggled.connect(self.on_camera1_live_toggled)
            self.camera_widget_1.snap_clicked.connect(lambda: self.on_camera1_snap(self.current_save_directory))
            self.camera_widget_1.restart_clicked.connect(self.camera1_restart)
            self.camera_widget_2.live_toggled.connect(self.on_camera2_live_toggled)
            self.camera_widget_2.snap_clicked.connect(lambda: self.on_camera2_snap(self.current_save_directory))
            self.camera_widget_2.restart_clicked.connect(self.camera2_restart)

        # print("Grabber thread is running:", self.grabber_1.isRunning())

        cameras_layout.addStretch()  # Ensure widgets stay at the top

        
        #_________________________________________
        # Mdi Area for Lasers, Filterwheels, Scanner and Stages

        x_offset = 0
        y_offset = 0

        self.mdi_area = QMdiArea()
        self.mdi_area.setMinimumWidth(800)
        self.mdi_area.setBackground(QBrush(QColor(48, 48, 48))) # Color in hex - #303030

        # Create a label for the microscope's name
        viewport = self.mdi_area.viewport()
        self.fixed_label = QLabel(parent=viewport)
        self.fixed_label.setTextFormat(Qt.RichText)
        self.fixed_label.setText("<i>VitaSlice</i> – ALM's Light-Sheet Microscope")
        self.fixed_label.setStyleSheet("""
            QLabel {
                color: white;
                background-color: rgb(48, 48, 48);
                padding: 4px;
                font-size: 18px;
                font: Roboto;
            }
        """)
        self.fixed_label.move(0, 0)  # adjust padding from top-left
        self.fixed_label.show()

        self.stages_widget = Stages_Widget(self.pidevice, parent=self)
        self.stages_widget.setMaximumWidth(600)
        self.stages_widget.setMaximumHeight(600)
        self.add_widget_at_position(self.stages_widget, "Stages", 645 + x_offset, 321 + y_offset)


        self.scanner_widget = Scanner_Widget(self.rtc5_board, parent=self)
        self.scanner_widget.set_camera_mode_provider(self._get_active_scanner_camera_mode)
        self.scanner_widget.setMaximumHeight(600)
        self.add_widget_at_position(self.scanner_widget, "Scanner", 645 + x_offset, 87 + y_offset)

        
        # Ensure the scanner widget keeps a reference to the main window
        # even after being re-parented into a FloatingWidget.
        self.scanner_widget.set_main_window


        # -------------------------------------------------------------------------
        # Connect camera state changes to scanner logic (robust wiring).
        # We do this here because camera widgets are created before scanner_widget,
        # so Camera_Widget.setupUi() cannot reliably find parent().scanner_widget yet.
        # -------------------------------------------------------------------------
        if getattr(self, "camera_widget_1", None) is not None:
            # Update lock when Live toggles
            self.camera_widget_1.live_toggled.connect(self.scanner_widget._camera_live_state_changed)
            # Optional: react to camera mode changes (your scanner already has a handler)
            self.camera_widget_1.cameramode_combobox.currentTextChanged.connect(self.scanner_widget._camera_mode_changed)

        if getattr(self, "camera_widget_2", None) is not None:
            self.camera_widget_2.live_toggled.connect(self.scanner_widget._camera_live_state_changed)
            self.camera_widget_2.cameramode_combobox.currentTextChanged.connect(self.scanner_widget._camera_mode_changed)

        #-----------------------------------------------------------------------------------------------------------------------

        self.filterwheels_widget = Filterwheels_Widget(self.filter_json_data, self.filterwheel1, self.filterwheel2, parent=self)
        self.filterwheels_widget.setMaximumHeight(300)
        self.filterwheels_widget.setMaximumHeight(600)
        self.add_widget_at_position(self.filterwheels_widget, "Filter Wheels", 310 + x_offset, 87 + y_offset)


        self.laser_widget = Lasers_Widget(self.filter_json_data, self.laserbox, parent=self)
        self.laser_widget.setMaximumWidth(600)
        self.laser_widget.setMaximumHeight(350)
        self.add_widget_at_position(self.laser_widget, "Lasers", 29 + x_offset, 300 + y_offset)

        self.scanner_widget.set_laser_widget(self.laser_widget)
        
        self._pending_auto_laser = None  # (laser_hw, power_mW)

        self.laser_widget.lightsheetModeSwitchFinished.connect(self._on_ls_mode_switch_finished)


        self.file_manager_widget = File_Explorer(start_path=initial_path, parent=self)


        #self.file_manager_widget = File_Explorer(parent=self)
        self.add_widget_at_position(self.file_manager_widget, "File Manager", 585 + x_offset, 677 + y_offset)
        # Initiate the save directory
        self.current_save_directory = self.file_manager_widget.current_path
        self.file_manager_widget.currentPathChanged.connect(self._on_path_changed)


        
        # cria o widget (se quiseres manter já criado aqui)
        self.ystack_widget = YStack_Widget(
            self.file_manager_widget.current_path,
            self.filterwheel1, self.filterwheel2,
            self.laserbox, self.rtc5_board, self.pidevice,
            self.camera_1, self.camera_2,
            self.laser_widget, self.scanner_widget,
            self.camera_widget_1, self.camera_widget_2
        )

        # garante subwindow e mostra como modo inicial
        self._set_mode("acquisition")



        # Connect with the Signals
        self.ystack_widget.acquisition_started.connect(self.before_acquisition)
        self.ystack_widget.acquisition_finished.connect(self.enable_devices)
        #self.ystack_widget.frame_acquired.connect(self.on_frame_acquired)

        # Return the remaining devices to their defaults after the Y-Stack
            # Scanner
        self.ystack_widget.acquisition_finished.connect(self.scanner_widget.center_beam_after_ystack)
            # Filter Wheels
        self.ystack_widget.acquisition_finished.connect(self.filterwheels_widget.restore_filters_after_ystack)
            # Lasers
        self.ystack_widget.acquisition_finished.connect(self.laser_widget.turn_all_off)
            # Cameras
        if self.number_of_cameras == 1:
            if self.single_camera == 1:
                self.ystack_widget.acquisition_finished.connect(self.camera_widget_1.apply_parameters_after_ystack)
            elif self.single_camera == 2:
                self.ystack_widget.acquisition_finished.connect(self.camera_widget_2.apply_parameters_after_ystack)
        elif self.number_of_cameras == 2:
            self.ystack_widget.acquisition_finished.connect(self.camera_widget_1.apply_parameters_after_ystack)
            self.ystack_widget.acquisition_finished.connect(self.camera_widget_2.apply_parameters_after_ystack)



        # Route user-driven camera exposure changes to the main sync logic
        self.camera_widget_1.exposure_changed_by_user.connect(
            self.on_camera_exposure_changed_by_user
        )
        self.camera_widget_2.exposure_changed_by_user.connect(
            self.on_camera_exposure_changed_by_user
        )

        # Route user-driven scanner speed changes to the main sync logic
        self.scanner_widget.scanner_speed_changed_by_user.connect(
            self.on_scanner_speed_changed_by_user
        )

        # Recompute manual exposure permissions when camera mode changes
        self.camera_widget_1.cameramode_combobox.currentTextChanged.connect(
            lambda _: self.update_confocal_exposure_edit_lock()
        )
        self.camera_widget_2.cameramode_combobox.currentTextChanged.connect(
            lambda _: self.update_confocal_exposure_edit_lock()
        )

        # Recompute manual exposure permissions when live state changes
        self.camera_widget_1.live_button.toggled.connect(
            lambda _: self.update_confocal_exposure_edit_lock()
        )
        self.camera_widget_2.live_button.toggled.connect(
            lambda _: self.update_confocal_exposure_edit_lock()
        )

        # Recompute manual exposure permissions when acquisition selection changes
        self.camera_widget_1.camera_checkbox.toggled.connect(
            lambda _: self.update_confocal_exposure_edit_lock()
        )
        self.camera_widget_2.camera_checkbox.toggled.connect(
            lambda _: self.update_confocal_exposure_edit_lock()
        )
                
            
        #_________________________________________
        # Napari Viewer

        self.viewer = napari.Viewer(show=False)

        set_napari_background(self.viewer, "#303030")  # Change background

        qt_napari_window = self.viewer.window._qt_window
        qt_napari_window.setWindowFlags(Qt.Widget)
        qt_napari_window.menuBar().setNativeMenuBar(False)
        qt_napari_window.setMinimumWidth(900)
        qt_napari_window.setMinimumHeight(900)



        # # Set the stylesheet
        splitter_layout.setStyleSheet("""           
            /* ----------- QSplitter ----------- */
            QSplitter {
                background-color: #303030;  /* Background color for the entire splitter */
            }
            QSplitter::handle {
                background-color: #555555;  /* Color for the draggable handle */
                width: 10px;                /* Thickness of the handle for horizontal splitter */
            }
        """)

        # Effectively place the widgets
            # Mdi layout for the devices
        splitter_layout.addWidget(self.mdi_area)
            # Add the left container to the grid (column 0)
        splitter_layout.addWidget(cameras_container)
            # Place the Napari widget in the grid (column 1)
        splitter_layout.addWidget(qt_napari_window)
        
        splitter_layout.setStretchFactor(0, 6)  # QMdiArea (equal priority with cameras)
        splitter_layout.setStretchFactor(1, 2)  # Cameras Container (equal priority with QMdiArea)
        splitter_layout.setStretchFactor(2, 10)  # Napari (Expands the most)

        self.profiler = PlotProfile(self.viewer) #Create Plot Profile

        #-------------------------------------------------------------------------------------
        #Quality Control - Menu Bar

        
        # Access napari's menu bar
        menu_bar = qt_napari_window.menuBar()

        # --- NOVO: menu Modes ---
        modes_menu = menu_bar.addMenu("Modes")

        # Ação para Quality Control Mode
        qc_mode_action = QAction("Quality Control Mode", self)
        qc_mode_action.setShortcut("Ctrl+Q")  # opcional
        qc_mode_action.triggered.connect(self.open_quality_control_mode)
        modes_menu.addAction(qc_mode_action)

        # Ação para Acquisition Mode
        acq_mode_action = QAction("Acquisition Mode", self)
        acq_mode_action.setShortcut("Ctrl+A")  # opcional
        acq_mode_action.triggered.connect(self.open_acquisition_mode)
        modes_menu.addAction(acq_mode_action)

        # Apply the correct exposure edit state at startup
        self.update_confocal_exposure_edit_lock()
        

    #----------------------------------------------------------------------------------
    def closeEvent(self, event):

        for sub in self.mdi_area.subWindowList():
            if hasattr(sub, "inner_widget") and hasattr(sub.inner_widget, "shutdown"):
                sub.inner_widget.shutdown()
        
        device_closings.filterwheel_closing(self.filterwheel1)
        device_closings.filterwheel_closing(self.filterwheel2)
        device_closings.scanner_closing(self.rtc5_board)

        self.laserbox.query("SOURce2:AM:STATe OFF")
        self.laserbox.query("SOURce3:AM:STATe OFF")
        self.laserbox.query("SOURce4:AM:STATe OFF")
        self.laserbox.query("SOURce5:AM:STATe OFF")
        device_closings.laserbox_closing(self.laserbox)
        

        device_closings.stages_closing(self.pidevice)
        
        self.pidevice = None

        if self.single_camera == None:
            self.camera_widget_1.shutdown()
            self.camera_widget_2.shutdown()

        elif self.single_camera == 1:
            self.camera_widget_1.shutdown()

        elif self.single_camera == 2:
            self.camera_widget_2.shutdown()

        event.accept()


#######################################################################################

in_path = r"C:\Users\ALM_Light_Sheet\Desktop\testes_acqs"

if __name__ == '__main__':
    logger.info("Application startup requested")

    try:
        app = QApplication(sys.argv)
        app.setWindowIcon(QIcon("ALM.ico"))
        app.setApplicationDisplayName("")

        logger = setup_logging(app_name='ALM')
        install_qt_message_handler(logger)
        install_excepthook(logger)
        logger.info("QApplication created successfully")
        
        # 1. Initialize the software, and choose the path
        dlg = ALM_Launcher()
        if dlg.exec() != QDialog.Accepted:
            sys.exit(0)    
        update_log_file_dir(logger, Path(initial_path=dlg.selected_path) / 'logs')

        
        logger.info("Main window created successfully")
        logger.info("Entering Qt event loop")

        
        # 2. After this open the software
        main_window = ALM_Lightsheet(initial_path=dlg.selected_path)#)
        main_window.showMaximized()
        sys.exit(app.exec())
    
    finally:
        shutdown_logging()
        







