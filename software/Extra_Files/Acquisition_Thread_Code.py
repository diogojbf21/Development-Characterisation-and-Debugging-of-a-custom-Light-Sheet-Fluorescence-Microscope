import threading
import numpy as np
import time
from collections import deque

from pylablib.devices import DCAM

class Acquisition_Thread:
    def __init__(self, camera, buffer_size=100):

        self.idx = -1

        # Setup the camera object, buffer size, and the thread buffer
        self.camera = camera

        #self.camera = DCAM.DCAMCamera(self.idx)
        self.buffer_size = buffer_size
        

        self.frame_queue = deque(maxlen=buffer_size)
        self.frame_info_queue = deque(maxlen=buffer_size)
        self.stop_event = threading.Event()

        # Camera default parameters
        self.restart = 0
        self.exp_time = 0.1
        self.dynamic_range = 16
        self.binning = 1
        self.roi_x = 2048
        self.roi_y = 2048
        self.acq_mode = 1
        self.readout_direction = 1

    # ------------------------------------------------------------------------

    # Functions to acquire frames

    def _wait_ready(self, timeout=0.1):
        t0 = time.time()
        while self.camera.get_status() == "busy" and (time.time() - t0) < timeout:
            time.sleep(0.001)

    def _acquire_frames(self):
        """Second thread to acquire frames from the acquisition"""
        while not self.stop_event.is_set():
            try:
                self.camera._wait_for_next_frame(timeout=self.exp_time + 0.1)

                frame_buffer, frame_info = self.camera._get_single_frame(0)

                self.frame_queue.appendleft(frame_buffer)
                self.frame_info_queue.appendleft(frame_info)
                
            except TimeoutError:
                # no frame this round… just continue polling
                continue

            except Exception as e:
                print(f"Error acquiring frame: {e}")
                break

    def get_latest_frame(self):
        """Retrieve the latest frame from the deque"""
        if self.frame_queue:
            return self.frame_queue[0] # Most recent frame
        return None, None

    def get_all_frames_from_buffer(self):
        """Retrieve all the frames and frame info available in the buffer in chronological order"""
        return self.frame_queue, self.frame_info_queue
        
    def restart_camera(self):
        """Restarts the camera connections and automatically sets the latest used parameters"""
        self.camera.close()
        self.camera = DCAM.DCAMCamera(self.idx)

        # Set the last used parameters

        self.camera.set_exposure(self.exp_time)

        if self.dynamic_range == 8:
            self.camera.set_attribute_value("IMAGE PIXEL TYPE", 1)
        elif self.dynamic_range == 12:
            self.camera.set_attribute_value("IMAGE PIXEL TYPE", 2)
            self.camera.set_attribute_value("BIT PER CHANNEL", self.dynamic_range)
        elif self.dynamic_range == 16:
            self.camera.set_attribute_value("IMAGE PIXEL TYPE", 2)
            self.camera.set_attribute_value("BIT PER CHANNEL", self.dynamic_range)

        self.camera.set_attribute_value("BINNING", self.binning)

        x_start = (2048 - self.roi_x) // 2
        y_start = (2048 - self.roi_y) // 2

        x_end = x_start + self.roi_x
        y_end = y_start + self.roi_y
        self.camera.set_roi(x_start, x_end, y_start, y_end)

        self.camera.set_attribute_value("SENSOR MODE", self.acq_mode)

    def get_framerate(self):
        """Returns the framerate of the system with the current parameters"""
        return self.camera.get_attribute_value("INTERNAL FRAME RATE")

    #-----------------------------------------------------------------------------------
    #Helper to attribute a right number to mode

    def _set_mode_attribute_by_label(self, attr_name: str, wanted_label: str):
        """
        Resolve a MODE/enum camera attribute label (e.g. 'PROGRESSIVE', 'FORWARD')
        into the internal numeric value expected by pylablib/DCAM, then set it.
        """
        # Try to get an attribute object if the wrapper exposes one
        attr_obj = None
        if hasattr(self.camera, "get_attribute"):
            try:
                attr_obj = self.camera.get_attribute(attr_name)
            except Exception:
                attr_obj = None

        # If we got an attribute object, inspect likely enum maps
        if attr_obj is not None:
            for field_name in ("labels", "values", "ivalues", "enum_values"):
                enum_map = getattr(attr_obj, field_name, None)
                if isinstance(enum_map, dict):
                    # direct label -> code
                    if wanted_label in enum_map:
                        self.camera.set_attribute_value(attr_name, enum_map[wanted_label])
                        return
                    # reverse map (code -> label)
                    for k, v in enum_map.items():
                        if str(v).upper() == wanted_label.upper():
                            self.camera.set_attribute_value(attr_name, k)
                            return

        raise RuntimeError(
            f"Could not resolve enum label '{wanted_label}' for attribute '{attr_name}'."
        )
    #_______________________________________________________________________

    # Functions to update the camera's settings

    def camera(self):
        """Gives access to the camera object"""
        return self.camera

    #_______________________________________________________________________
    def change_exposure_time(self, exp_time):
        """Change the Exposure Time of the Camera"""

        self.exp_time = exp_time

        # 2) apply the new setting
        self.camera.set_exposure(exp_time)
        print(f"Exposure now set to {self.camera.get_exposure()}")


    #_______________________________________________________________________
    def change_dynamic_range(self, bit_value):
        """Change the Dynamic Range of the Camera"""

        self.dynamic_range = bit_value

        # 1) stop & clear acquisition
        self.camera.stop_acquisition()
        self.camera.clear_acquisition()

        # 2) wait for camera to settle
        while self.camera.get_status() in ("busy","unstable"):
            time.sleep(0.005)

        # 3) set the attribute
        if bit_value == 8:
            self.camera.set_attribute_value("IMAGE PIXEL TYPE", 1)
        elif bit_value == 16:
            self.camera.set_attribute_value("IMAGE PIXEL TYPE", 2)

        # 4) restart acqusition
        self.camera.setup_acquisition(mode="sequence", nframes=200)
        self.camera.start_acquisition()


        
    #_______________________________________________________________________    
    def change_binning(self, roi_x, roi_y, binning):
        """Change the Binning of the Camera's Sensor"""

        # self.binning = binning

        # # 1) stop & clear acquisition
        # self.camera.stop_acquisition()
        # self.camera.clear_acquisition()

        # # 2) wait for camera to settle
        # while self.camera.get_status() in ("busy","unstable"):
        #     time.sleep(0.005)

        # # 3) set the attribute
        # self.camera.set_attribute_value("BINNING", self.binning)

        # # 4) restart acqusition
        # self.camera.setup_acquisition(mode="sequence", nframes=200)
        # self.camera.start_acquisition()

        self.roi_x = roi_x
        self.roi_y = roi_y
        self.binning = binning

        # Calculate the coordinates in the sensor for a centered custom ROI
        roi_x_start = (2048 - roi_x) // 2
        roi_y_start = (2048 - roi_y) // 2

        roi_x_end = roi_x_start + roi_x
        roi_y_end = roi_y_start + roi_y

        # 1) stop & clear acquisition
        self.camera.stop_acquisition()
        self.camera.clear_acquisition()

        # 2) wait for camera to settle
        while self.camera.get_status() in ("busy","unstable"):
            time.sleep(0.005)
        

        # 3) set the attribute
        self.camera.set_roi(roi_x_start, roi_x_end, roi_y_start, roi_y_end, binning, binning)

        # 4) restart acqusition
        self.camera.setup_acquisition(mode="sequence", nframes=200)
        self.camera.start_acquisition()

    #----------------------------------------------------------------------------
    #Mode3-Rolling Shutter Functions
    
    #_______________________________________________________________________
    def change_ROI(self, roi_x, roi_y, binning):
        """Change the ROI of the Camera. The ROI is always centered on the sensor"""

        self.roi_x = roi_x
        self.roi_y = roi_y
        self.binning = binning

        # Calculate the coordinates in the sensor for a centered custom ROI
        roi_x_start = (2048 - roi_x) // 2
        roi_y_start = (2048 - roi_y) // 2

        roi_x_end = roi_x_start + roi_x
        roi_y_end = roi_y_start + roi_y

        # 1) stop & clear acquisition
        self.camera.stop_acquisition()
        self.camera.clear_acquisition()

        # 2) wait for camera to settle
        while self.camera.get_status() in ("busy","unstable"):
            time.sleep(0.005)
        

        # 3) set the attribute
        self.camera.set_roi(roi_x_start, roi_x_end, roi_y_start, roi_y_end, binning, binning)

        # 4) restart acqusition
        self.camera.setup_acquisition(mode="sequence", nframes=200)
        self.camera.start_acquisition()


    def change_sensor_mode(self, mode):
        """Change the the Sensor Mode of the Camera"""

        self.acq_mode = mode

        # Internal Trigger - Normal Mode
        if mode == 1:

            # 1) stop & clear acquisition
            self.camera.stop_acquisition()
            self.camera.clear_acquisition()

            # 2) wait for camera to settle
            while self.camera.get_status() in ("busy","unstable"):
                time.sleep(0.005)

            self._set_mode_attribute_by_label("SENSOR MODE", "AREA")

            # 3) arrange the Internal Trigger Mode
            self.camera.set_trigger_mode("int")



            # 4) restart acqusition
            self.camera.setup_acquisition(mode="sequence", nframes=200)
            self.camera.start_acquisition()


        # External Trigger - Widefield Mode
        elif mode == 2:

            # 1) stop & clear acquisition
            self.camera.stop_acquisition()
            self.camera.clear_acquisition()

            # 2) wait for camera to settle
            while self.camera.get_status() in ("busy","unstable"):
                time.sleep(0.005)

            self._set_mode_attribute_by_label("SENSOR MODE", "AREA")


            # 3) arrange the External Trigger Mode
            self.camera.set_trigger_mode("ext")
            self.camera.set_attribute_value("TRIGGER ACTIVE", 2)
            self.camera.set_attribute_value("TRIGGER POLARITY", 2)
            self.camera.set_attribute_value("TRIGGER GLOBAL EXPOSURE", 5)

            # 4) restart acqusition
            self.camera.setup_acquisition(mode="sequence", nframes=200)
            self.camera.start_acquisition()
        
        # External Trigger - Confocal Mode
        elif mode == 3:
            
            # 1) stop & clear acquisition
            self.camera.stop_acquisition()
            self.camera.clear_acquisition()

            # 2) wait for camera to settle
            while self.camera.get_status() in ("busy","unstable"):
                time.sleep(0.005)

            # 3) arrange Top-to-bottom readout direction
            self._set_mode_attribute_by_label("SENSOR MODE", "PROGRESSIVE")

            #4) FORWARD to Top to Bottom direction (mode 1)
            self.camera.set_attribute_value("READOUT DIRECTION", 1) 
            
            # 5) Use external trigger source so the scanner becomes the master
            self.camera.set_trigger_mode("ext")
            self.camera.set_attribute_value("TRIGGER SOURCE", 2)

            # 6) Use normal trigger mode
            #    In scanner-master rolling shutter, one external trigger pulse starts one readout cycle.
            self._set_mode_attribute_by_label("TRIGGER MODE", "NORMAL")

            # 7) Use edge trigger
            #    SYNCREADOUT is not available in PROGRESSIVE mode on this camera.
            self.camera.set_attribute_value("TRIGGER ACTIVE", 1)

            # 8) Set trigger polarity
            #    Use POSITIVE if your scanner trigger pulse is low->high.
            #    Use NEGATIVE if your hardware pulse is high->low.
            self.camera.set_attribute_value("TRIGGER POLARITY", 2)

            # 9) Optional: set trigger delay to zero
            self.camera.set_attribute_value("TRIGGER DELAY", 0.0)

            # 10) Restart acquisition
            self.camera.setup_acquisition(mode="sequence", nframes=200)
            self.camera.start_acquisition()

            print("[Camera] Confocal Mode configured: PROGRESSIVE + FORWARD + EXTERNAL EDGE TRIGGER")
