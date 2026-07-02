# Filterwheel imports
import microscope
from microscope.controllers.zaber import _ZaberFilterWheel, _ZaberConnection

# Laserbox import
import pyvisa

# Scanner import
import ctypes

# Stages import
from pipython import GCSDevice
from pipython import GCSDevice, pitools

# Cameras imports
from pylablib.devices import DCAM

# for connecting without COM ports
import serial
from serial.tools import list_ports

#Logger
import logging
import threading

# Reuse the main application logger configured by logger.py / main.py
logger = logging.getLogger("ALM")


class device_initializations:
    
    def filterwheel_1(self):
        """Connect to the Zaber Filter wheel 1"""

        threading.current_thread().name = "FILTER WHEEL"

        filterwheel1_serial = "A10K5RCPA"

        for p in list_ports.comports():
            if "SER=" in p.hwid:
                serial_filterwheel = p.hwid.split("SER=")[1].split()[0]

                if serial_filterwheel == filterwheel1_serial:

                    time.sleep(0.5)

                    while True:
                        try:
                            filter_conn_1 = _ZaberConnection(port=p.device, baudrate=115200, timeout=0.05)
                            filterwheel_1 = _ZaberFilterWheel(filter_conn_1, 1)
                            
                            logger.info("Filter Wheel 1 connected successfully. Port=%s, serial=%s",
                                        p.device,
                                        filterwheel1_serial)
                            return filterwheel_1
                            
                        except Exception as e:
                            logger.exception("Filter Wheel 1 connection attempt failed. Port=%s, serial=%s",
                            p.device,
                            filterwheel1_serial,)

                            time.sleep(1)
        
        logger.error("Filter Wheel 1 not found. Expected serial=%s",
        filterwheel1_serial,)
        return None

                
    
    def filterwheel_2(self):
        """Connect to the Zaber Filter wheel 2"""

        threading.current_thread().name = "FILTER WHEEL"

        filterwheel2_serial = "AD0JDTC7A"

        for p in list_ports.comports():
            if "SER=" in p.hwid:
                serial_filterwheel = p.hwid.split("SER=")[1].split()[0]

                if serial_filterwheel == filterwheel2_serial:

                    time.sleep(0.5)

                    while True:
                        try:
                            filter_conn_2 = _ZaberConnection(port=p.device, baudrate=115200, timeout=0.05)
                            filterwheel_2 = _ZaberFilterWheel(filter_conn_2, 1)
                            logger.info("Filter Wheel 2 connected successfully. Port=%s, serial=%s",
                                        p.device,
                                        filterwheel2_serial,)
                            return filterwheel_2
                            
                        except Exception as e:
                            logger.exception("Filter Wheel 2 connection attempt failed. Port=%s, serial=%s",
                            p.device,
                            filterwheel2_serial,)
                            time.sleep(1)

        logger.error("Filter Wheel 1 not found. Expected serial=%s",
        filterwheel2_serial,)
        return None


    
    def laserbox(self):
        """Connect to the Coherent OBIS Laser Box"""

        threading.current_thread().name = "LASERS"

        for p in list_ports.comports():
            #print(p.device, "-", p.description, "-", p.hwid)
            if "Coherent OBIS Device" in p.description:
                try:

                    num = int(p.device.replace("COM", ""))

                    rm = pyvisa.ResourceManager()
                    laserbox = rm.open_resource(f'ASRL{num}::INSTR')
                    laserbox.baud_rate = 115200
                    laserbox.read_termination = "\r\n"
                    laserbox.write_termination = "\r\n"

                    logger.info("Laser box connected successfully. Port=%s, VISA resource=ASRL%s::INSTR",
                    p.device,
                    num,)

                    return laserbox
                
                except Exception:
                    logger.exception("Laser box connection failed. Port=%s",
                        p.device,)
                    return None

        logger.error("Laser box not found. No 'Coherent OBIS Device' port was detected.")
        return None

    
    def scanner(self):
        """Load the rtc5_board dll"""

        threading.current_thread().name = "SCANNER"

        dll_path = "RTC5DLLx64"
        try:
            rtc5_board = ctypes.windll.LoadLibrary(dll_path)
            print("Loading DLL from:", dll_path)
            rtc5_board = ctypes.windll.LoadLibrary(dll_path)

            # Initializing the dll
            init_result = rtc5_board.init_rtc5_dll()
            print("Initialization:", init_result)

            # Mode
            mode = rtc5_board.set_rtc4_mode()
            print("Mode:", mode)

            execution = rtc5_board.stop_execution()
            print("Stop Execution:", execution)

            program_files = rtc5_board.load_program_file(0)
            print("Program Files:", program_files)

            load = rtc5_board.load_correction_file(0,1,2)
            print("Correction File Load:", load)

            table = rtc5_board.select_cor_table(1,0)
            print("Correction Table Selection:", table)

            # Set the jump speed
            rtc5_board.set_jump_speed(ctypes.c_double(800000))

            # Set laser control
            rtc5_board.set_laser_control(1)

            # Set Laser Mode 6
            rtc5_board.set_laser_mode(6)

            
            logger.info("Scanner connected successfully. DLL=%s, init_result=%s",
                    dll_path,
                    init_result,)
            return rtc5_board
        
        except Exception:
            logger.exception("Scanner connection failed. The scanner may be powered off or not responding. DLL=%s",
                    dll_path,)
            return None


    def stages(self):
        """Initialize and Reference the Stages"""

        threading.current_thread().name = "STAGES"

        CONTROLLERNAME = 'C-884'
        STAGES = ['M-110.1DG1', 'M-110.1DG1', 'M-112.1DG1']
        controller_serial = "118067518"
        try:
            pidevice = GCSDevice(CONTROLLERNAME)
            pidevice.ConnectUSB(serialnum='118067518')
            pitools.startup(pidevice, stages=STAGES)

            # Set velocities
            velocity_x = 1
            velocity_y = 1
            velocity_z = 1.5
            pidevice.VEL(['1', '2', '3'], [velocity_x, velocity_y, velocity_z])

            # Make sure servos are ON before referencing/moving
            for ax in ['1', '2', '3', '4']:
                try:
                    pidevice.SVO(ax, True)
                except Exception:
                    pass  # axis might not exist

            # reference Z to the maximum position
            try:
                pidevice.SPA('3', 0x70, 6)
                pidevice.SPA('3', 0x16, 25)
            except Exception:
                pass

            # Reference ALL axes
            # (Axes that don't exist will just skip.)
            for ax in ['1', '2', '3', '4']:
                try:
                    pidevice.FRF(ax)
                except Exception:
                    pass
            try:
                pitools.waitontarget(pidevice, axes=['1', '2', '3', '4'])
            except Exception:
                pass

            # Optional: your Z-axis post-referencing steps
            try:
                pidevice.RON('3', 0)
                pidevice.POS('3', 25)
            except Exception:
                pass

            # Now it's safe to move X and Y
            pidevice.MOV(['1', '2'], [2.50000, 2.50000])

            logger.info("Stages connected successfully. Controller=%s, serial=%s",
                CONTROLLERNAME,
                controller_serial,)
            return pidevice
        
        except Exception:
            logger.exception("Stages connection failed. Controller=%s, serial=%s",
                CONTROLLERNAME,
                controller_serial,
            )
            return None

    def camera(self, idx):
        """ Initialize the Camera given by the idx"""

        threading.current_thread().name = "CAMERA"

        camera_map = {
                0: "Camera 2",
                1: "Camera 1",
            }
        
        camera_name = camera_map.get(idx, f"Camera {idx}")
        try:
            camera = DCAM.DCAMCamera(idx)
            
            logger.info(
                "%s connected successfully",
                camera_name,)

            return camera
        
        except Exception:
            logger.exception("%s connection failed",
                camera_name,)
            return None



import time
class device_closings:

    def filterwheel_closing(device):
        device.shutdown()

    def laserbox_closing(device):
        device.close()

    def scanner_closing(device):
        device.release_rtc(1)
        device.free_rtc5_dll()

    def stages_closing(device):
        device.CloseConnection()

    def camera_closing(acq_thread):
        acq_thread.camera.stop_acquisition()
        time.sleep(1)
        acq_thread.camera.clear_acquisition()
        time.sleep(1)
        acq_thread.camera.close()

    



