import ctypes
import os
import numpy as np

import sys
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import QThread, Signal, Slot, QObject


class RTC5_Board():

    def __init__(self):
        self.sei_la = 1

    def initialization(self):
        # Load the self.rtc5_board dll
        dll_path = "RTC5DLLx64"
        self.rtc5_board = ctypes.windll.LoadLibrary(dll_path)
        print("Loading DLL from:", dll_path)
        self.rtc5_board = ctypes.windll.LoadLibrary(dll_path)

        # Initializing the dll
        init_result = self.rtc5_board.init_rtc5_dll()
        print("Initialization:", init_result)

        # Mode
        mode = self.rtc5_board.set_rtc4_mode()
        print("Mode:", mode)

        execution = self.rtc5_board.stop_execution()
        print("Stop Execution:", execution)

        program_files = self.rtc5_board.load_program_file(0)
        print("Program Files:", program_files)

        load = self.rtc5_board.load_correction_file(0,1,2)
        print("Correction File Load:", load)

        table = self.rtc5_board.select_cor_table(1,0)
        print("Correction Table Selection:", table)

        # Set the jump speed
        self.rtc5_board.set_jump_speed(ctypes.c_double(800000))


    def move_beam(self, pos):
        "Function to move the beam to a specific X position"
        Xpos = -pos
        Ypos = 0
        self.rtc5_board.goto_xy(ctypes.c_int(Xpos), ctypes.c_int(Ypos))

    
    def mark_toptobottom(self, Xtop, Xbottom, speed):
        """
        Function to form a lightsheet
        It jumps to Xtop, marks from Xtop to Xbottom.
        It's supposed to use in a loop
        """
        self.rtc5_board.set_start_list(1)

        Xi = -Xtop
        Yi = 0
        Xf = -Xbottom
        Yf = 0

        self.rtc5_board.set_jump_speed(ctypes.c_double(800000))
        self.rtc5_board.set_mark_speed(ctypes.c_double(speed))

        self.rtc5_board.jump_abs(ctypes.c_int(Xi), ctypes.c_int(Yi))
        self.rtc5_board.mark_abs(ctypes.c_int(Xf), ctypes.c_int(Yf))

        self.rtc5_board.set_end_of_list()

        self.rtc5_board.execute_list(1)

        self.rtc5_board.execute_list(1)
