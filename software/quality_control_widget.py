from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform, QIntValidator)
from PySide6.QtWidgets import (QApplication, QGroupBox, QLabel, QLineEdit,
    QMainWindow, QPushButton, QSizePolicy, QStatusBar,
    QWidget,QVBoxLayout,QSpinBox,QDoubleSpinBox,QHBoxLayout, QComboBox,QGridLayout)
from PySide6.QtCore import Signal, Slot, QObject, QThread,QTimer
from PySide6.QtWidgets import QWidget, QMessageBox
import sys
import numpy as np
import traceback

from pathlib import Path

from Extra_Files.Quality_Control.qc_algorithms import (
    extract_gaussian_profiles,
    calculate_tilt_from_peaks,
    calculate_focus_point,
)

#------------------------------------------------------------------------------
#Quality Control Panel GUI

class QualityControl_UI(object):
    #------------------------------------------------------------------------
    #GUI Construction

    def setupUi(self, parent:QWidget):

        # Main Window
        parent.setObjectName("Beam_Quality")
        parent.setMinimumSize(200, 400)

        # Stylesheet
        parent.setStyleSheet("""
        QWidget {
            background-color: #222222;
        }

        QLabel {
            color: white;
            font-size: 12px;
        }

        /* -------- LINE EDITS (textos que escreves) -------- */
        QLineEdit {
            background-color: #2b2b2b;
            color: #ffffff;              /* cor do texto que escreves */
            border: 1px solid #555555;
            border-radius: 6px;
            padding: 4px 6px;
        }

        QLineEdit:focus {
            border: 1px solid #00aaff;
            background-color: #303030;
        }

        /* placeholder (o “1–2048”, etc.) */
        QLineEdit::placeholder {
            color: #aaaaaa;
        }

        /* seleção de texto */
        QLineEdit::selection {
            background: #0078d7;
            color: #ffffff;
        }

        /* -------- BOTÃO -------- */
        QPushButton {
            background-color: #3a3a3a;   /* cor do botão */
            color: #ffffff;              /* cor do texto do botão */
            border: 1px solid #666666;
            border-radius: 10px;
            padding: 8px 12px;
            font-weight: bold;
        }

        QPushButton:hover {
            background-color: #4a4a4a;
            border: 1px solid #888888;
        }

        QPushButton:pressed {
            background-color: #2a2a2a;
        }

        QPushButton:disabled {
            background-color: #555555;
            color: #bbbbbb;
            border: 1px solid #777777;
        }
        
        /* --------Live Calculations Button-------------------*/
        QPushButton#live_calc_btn:checked {
            background-color: #2ecc71;
            border: 1px solid #27ae60;
            color: #ffffff;
        }
        QPushButton#live_calc_btn:checked:hover {
            background-color: #36d37d;
        }
                             
        """)
  

        #Vertical Layout
        self.main_layout = QVBoxLayout(parent)
        self.main_layout.setContentsMargins(16,16,16,16)
        self.main_layout.setSpacing(12)

        #-------------------------------------------------------------
        #Line 0-Quality Control Pasta Name

        # Experiment Name
        self.exp_name_widget = QWidget()
        self.exp_name_layout = QHBoxLayout()
        self.exp_name_layout.setContentsMargins(0, 0, 5, 5)
        self.exp_name_widget.setLayout(self.exp_name_layout)

        self.exp_name_label = QLabel("QC File Name: ")
        self.exp_name_lineedit = QLineEdit("")
        self.exp_name_lineedit.setFixedHeight(25)
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

        self.main_layout.addWidget(self.exp_name_widget)


        #---------------------------------------------------------------
        # 1st Line - Camera

        self.row_camera = QHBoxLayout()
        self.row_camera.setSpacing(8)

        self.camera_label = QLabel("QC Camera: ")
        self.camera_combobox = QComboBox()
        self.camera_combobox.addItems(["Camera 1", "Camera 2", "Both"])
        #self.camera_combobox.setEditable(True)
        self.camera_combobox.setInsertPolicy(QComboBox.NoInsert)
        self.camera_combobox.setFixedWidth(110)

        
        script_path = Path(__file__).resolve()
        icon_path_enabled = script_path.parent / "icons" / "button_down.png"
        icon_path_disabled = script_path.parent / "icons" / "button_down_disabled.png"

        self.camera_combobox.setStyleSheet(f"""
        /* Match Camera_Widget combobox style */
        QComboBox {{
            background-color: #252525;
            color: white;
            border: 1px solid #444444;
            border-radius: 3px;
            padding-left: 6px;            /* Optional: improve text spacing */
            padding-right: 24px;          /* Make room for the arrow area */
        }}

        QComboBox QAbstractItemView {{
            background-color: #272727;
            color: white;
            selection-background-color: #555555;
        }}

        /* Dropdown button area */
        QComboBox::drop-down {{
            width: 20px;
            background-color: #444444;
            border-left: 1px solid #555555;
        }}

        /* Dropdown arrow image */
        QComboBox::down-arrow {{
            image: url("{icon_path_enabled.as_posix()}");
            width: 12px;
            height: 12px;
        }}

        /* Disabled state */
        QComboBox:disabled {{
            background-color: #303030;
            color: #777777;
            border: 1px solid #444444;
        }}

        QComboBox::drop-down:disabled {{
            background-color: #303030;
            border-left: 1px solid #333333;
        }}

        QComboBox::down-arrow:disabled {{
            image: url("{icon_path_disabled.as_posix()}");
            width: 12px;
            height: 12px;
        }}
        """)

        # add widgets to the row
        self.row_camera.addWidget(self.camera_label)
        self.row_camera.addStretch(1) # pushes the spin to the right
        self.row_camera.addWidget(self.camera_combobox)

        self.main_layout.addLayout(self.row_camera)

        #---------------------------------------------------------------------

        # 2st Row - Number of Points

        self.row_num_points = QHBoxLayout()
        self.row_num_points.setSpacing(8)
        
        self.num_points = QLabel("Number of Points: ")
        self.edit_num_points = QLineEdit()
        self.edit_num_points.setAlignment(Qt.AlignRight)
        self.edit_num_points.setPlaceholderText("1–2048")
        self.edit_num_points.setText("100")  #initial value
        self.edit_num_points.setValidator(QIntValidator(1, 2048, self.edit_num_points))
        self.edit_num_points.setFixedWidth(80)


        # add widgets to the row
        self.row_num_points.addWidget(self.num_points)
        self.row_num_points.addStretch(1) # pushes the spin to the right
        self.row_num_points.addWidget(self.edit_num_points)

        self.main_layout.addLayout(self.row_num_points)
       
        #--------------------------------------------------------------

        # 3nd Row - Points Grouping

        self.row_grouping = QHBoxLayout()
        self.row_grouping.setSpacing(5)
        
        self.points_grouping = QLabel("Points Grouping:")
        self.edit_points_grouping = QLineEdit()
        self.edit_points_grouping.setAlignment(Qt.AlignRight)
        self.edit_points_grouping.setPlaceholderText("1–50")
        self.edit_points_grouping.setText("3")
        self.edit_points_grouping.setValidator(QIntValidator(1, 50, self.edit_points_grouping))
        self.edit_points_grouping.setFixedWidth(80)


        # add widgets to the row
        self.row_grouping.addWidget(self.points_grouping)
        self.row_grouping.addStretch(1) # pushes the spin to the right
        self.row_grouping.addWidget(self.edit_points_grouping)

        self.main_layout.addLayout(self.row_grouping)
       
        #--------------------------------------------------------------

        # 4th Row - Beam Window

        self.row_beam = QHBoxLayout()
        self.row_beam.setSpacing(5)

        self.beam_window = QLabel("Beam Window:")
        self.edit_beam_window = QLineEdit()
        self.edit_beam_window.setAlignment(Qt.AlignRight)
        self.edit_beam_window.setPlaceholderText("1–2000")
        self.edit_beam_window.setText("150")
        self.edit_beam_window.setValidator(QIntValidator(1, 2000, self.edit_beam_window))
        self.edit_beam_window.setFixedWidth(80)

        self.row_beam.addWidget(self.beam_window)
        self.row_beam.addStretch(1)
        self.row_beam.addWidget(self.edit_beam_window)
        
        self.main_layout.addLayout(self.row_beam)

       
        #--------------------------------------------------------------

        # 5th Row - Calculate Tilt

        self.tilt_row = QHBoxLayout()
        self.tilt_row.setSpacing(5)

        self.calculate_tilt = QLabel("Tilt:")
        self.tilt_deg = QLabel("Angle:  \u00B0")
        self.tilt_deg.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # add widgets to the row
        self.tilt_row.addWidget(self.calculate_tilt)
        self.tilt_row.addStretch(1) # pushes the spin to the right
        self.tilt_row.addWidget(self.tilt_deg)

        self.main_layout.addLayout(self.tilt_row)
       
        #--------------------------------------------------------------

        # 6th Row - Calculate Focus

        self.focus_row = QHBoxLayout()
        self.focus_row.setSpacing(5)

        self.calculate_focus = QLabel("Focus:")
        self.focus_pixel = QLabel("Pixel: ")
        self.focus_pixel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # add widgets to the row
        self.focus_row.addWidget(self.calculate_focus)
        self.focus_row.addStretch(1) # pushes the spin to the right
        self.focus_row.addWidget(self.focus_pixel)

        self.main_layout.addLayout(self.focus_row)
       
        #--------------------------------------------------------------

        # 7th Row - Beam Waist

        self.waist_row = QHBoxLayout()
        self.waist_row.setSpacing(5)

        self.calculate_fwhm = QLabel("FWHM:")
        self.fwhm_um = QLabel(" \u03bcm")
        self.fwhm_um.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # add widgets to the row
        self.waist_row.addWidget(self.calculate_fwhm)
        self.waist_row.addStretch(1) # pushes the spin to the right
        self.waist_row.addWidget(self.fwhm_um)

        self.main_layout.addLayout(self.waist_row)

        #-----------------------------------------------------------------

        #8th Row- Live Calculations

        self.live_row = QHBoxLayout()
        self.live_row.setSpacing(5)

        self.live_all = QPushButton("Live Calculation")
        
        self.live_all.setCheckable(True)
        self.live_all.setObjectName("live_calc_btn")

        # add widgets to the row
        self.live_row.addWidget(self.live_all)
        self.main_layout.addLayout(self.live_row)

        #------------------------------------------------------------------
    

        #8th Row- Save All Calculations for 1 frame

        self.all_row = QHBoxLayout()
        self.all_row.setSpacing(5)

        self.calculate_all = QPushButton("Save Calculations")
        # add widgets to the row
        self.all_row.addWidget(self.calculate_all)
        self.main_layout.addLayout(self.all_row)
    
        #----------------------------------------------------------------

        # Expander to push content upwards (optional)
        self.main_layout.addStretch(1)


        QMetaObject.connectSlotsByName(parent)

#-------------------------------------------------------------------------------------------------
# Worker to run calculations


class QCWorker(QObject):
    """
    Worker object that runs Quality Control computations in a background thread.
    It never touches UI elements directly; it only emits signals with results.
    """
    result_ready = Signal(object)  # Emits a dict with all computed outputs
    errored = Signal(str)          # Emits a traceback string
    finished = Signal()            # Emitted when the worker completes (success or failure)

    def __init__(self, frame: np.ndarray, params: dict, pixel_size_um=None):
        super().__init__()
        self.frame = frame
        self.params = params
        self.pixel_size_um = pixel_size_um


    @Slot()
    def run(self):
        """Entry point executed in the worker thread."""
        try:
            # Heavy computation: extract Gaussian profiles from the image
            cols, peaks, fwhms, r2s = extract_gaussian_profiles(
                image=self.frame,
                num_points=self.params["num_points"],
                beam_window=self.params["beam_window"],
                agrupamento=self.params["agrupamento"],
                baseline_mode=self.params["baseline_mode"],
                use_scipy=self.params["use_scipy"],
                min_r2=self.params["min_r2"],
                pixel_size_um=self.pixel_size_um,
            )

            # Compute tilt and focus from extracted measurements
            angle_deg, coef = calculate_tilt_from_peaks(cols, peaks)
            focus = calculate_focus_point(cols, fwhms, peaks,tilt_coef=coef, use_scipy=True)

            # Compute summary statistic for display (median FWHM)
            med = np.nanmedian(fwhms) if len(fwhms) else np.nan

            # Package results into a single dict and emit
            self.result_ready.emit({
                "cols": cols,
                "peaks": peaks,
                "fwhms": fwhms,
                "angle_deg": float(angle_deg) if np.isfinite(angle_deg) else np.nan,
                "coef": coef,
                "shape": self.frame.shape,
                "focus": focus,
                "median_fwhm": float(med) if np.isfinite(med) else np.nan,
            })

        except Exception:
            # Never raise across threads; emit traceback instead
            self.errored.emit(traceback.format_exc())

        finally:
            # Always signal completion so the UI can re-enable controls and clean up
            self.finished.emit()


#------------------------------------------------------------------------------------------------


class QualityControlWidget(QWidget):
    """
    Quality Control panel widget.

    Responsibilities:
    - Receives live camera frames via a Qt Slot (on_new_frame).
    - Stores the latest frame per camera (latest_frames dict).
    - Runs QC analysis when the user clicks the main button.f
    - Updates UI labels (tilt, focus, fwhm).
    - Emits Signals with results so the main app can draw Napari overlays/plots.
    """

    # Signals to be handled by the main window (Napari overlay/plot code lives there)
    clear_overlays = Signal()
    tilt_ready = Signal(float, object, tuple)   # angle_deg, coef, image_shape
    focus_ready = Signal(int, float)            # col, row
    fwhm_ready = Signal(object, object)         # cols, fwhms
    save_bundle_ready = Signal(object)  # frame + results + metadata

    def __init__(self, parent=None, pixel_size_um=None, beam_info_provider=None):
        super().__init__(parent)

        # Build the UI directly onto this QWidget
        self.ui = QualityControl_UI()
        self.ui.setupUi(self)

        # Optional pixel size (um/px). If None, FWHM will effectively be in pixels.
        self.pixel_size_um = pixel_size_um

        
        # Keep a callable that returns a snapshot dict for the currently active laser
        # This is injected by the main window so QC does not depend on laser UI internals.
        self._beam_info_provider = beam_info_provider


        # Buffer: cam_id -> np.ndarray
        self.latest_frames: dict[int, np.ndarray] = {}

        # Connect UI actions
        self.ui.calculate_all.clicked.connect(self._run_qc_from_selection)

        # Optional: reset displayed results when the user changes camera selection
        self.ui.camera_combobox.currentTextChanged.connect(self._on_camera_changed)

        
        # Background QC execution objects (kept as attributes to avoid premature GC)
        self._qc_thread = None
        self._qc_worker = None

        
        # Live mode state + timer
        self._live_enabled = False
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(1500)  # 1500 ms
        self._live_timer.timeout.connect(self._live_tick)

        # Optional: To ignore results when you turn off live streaming.
        self._live_job_id = 0
        self._latest_job_id = 0

        # turn on the live button (toggle)
        self.ui.live_all.toggled.connect(self._toggle_live)

        
        # Warning: avoid repeating popups in Live when there are no frames.
        self._live_warned_no_frame = False

        #Saving Data of Calculations
        self._pending_save = False
        self._pending_save_meta = {}

        
        # --- support for "Both" single-shot save ---
        self._both_pending = False
        self._both_results = []          # list of per-camera bundles
        self._both_queue = []            # list of (cam_id, camera_name, frame_copy)
        self._both_meta_base = {}        # shared metadata (timestamp, beam_info, params, etc.)
        self._both_current_cam = None    # cam_id being processed

    # -----------------------------
    # Frame input (from main thread)
    # -----------------------------
    @Slot(object, int)
    def on_new_frame(self, frame, cam_id: int):
        """
        Receive a live camera frame and store it as the latest for that cam_id.

        This slot will be invoked in the GUI thread when connected to a Qt Signal.
        """
        
        # --- Apply the same camera 1 mirroring used in the Napari viewer ---
        if cam_id == 1:
            # Mirror to match what the user sees in Napari
            frame = np.fliplr(frame)

        # Store the processed frame
        self.latest_frames[cam_id] = np.asarray(frame)

        
        # If this frame belongs to the selected camera, unlock the warning.
        # In 'Both' mode, any incoming frame unlocks the warning.
        selected_id = self._selected_cam_id()
        if selected_id is None:
            # 'Both' mode: accept any camera update
            self._live_warned_no_frame = False
        elif cam_id == selected_id:
            self._live_warned_no_frame = False




    # -----------------------------
    # UI helpers
    # -----------------------------
    def _on_camera_changed(self, _txt: str):
        """Clear result labels when the selected camera changes."""
        self.ui.tilt_deg.setText("Angle: —°")
        self.ui.focus_pixel.setText("Pixel: —")
        self.ui.fwhm_um.setText("— µm")

        # --- NEW: Live is not allowed in 'Both' mode ---
        mode = self._selected_cam_mode()
        if mode == "both":
            # Force Live OFF and disable the toggle
            if self.ui.live_all.isChecked():
                self.ui.live_all.setChecked(False)
            self.ui.live_all.setEnabled(False)
            self.ui.live_all.setToolTip("Live is disabled when 'Both' is selected.")
        else:
            self.ui.live_all.setEnabled(True)
            self.ui.live_all.setToolTip("")

        if self.ui.live_all.isChecked():
            self.ui.live_all.setChecked(False)


    def _selected_cam_mode(self):
        """
        Return the current camera selection mode.
        Expected combobox items: 'Camera 1', 'Camera 2', 'Both'.
        """
        txt = self.ui.camera_combobox.currentText()
        if "Both" in txt:
            return "both"
        if "1" in txt:
            return "cam1"
        if "2" in txt:
            return "cam2"
        return None


    def _selected_cam_id(self):
        """
        Return the numeric camera id for single-camera selection.
        Returns:
            1 for 'Camera 1'
            2 for 'Camera 2'
            None for 'Both' or unknown
        """
        mode = self._selected_cam_mode()
        if mode == "cam1":
            return 1
        if mode == "cam2":
            return 2
        return None

    def _get_selected_camera_frame(self):
        """
        Return (frame, cam_id) for the selected single camera.
        If mode is 'both', returns (None, None).
        """
        mode = self._selected_cam_mode()
        if mode == "cam1":
            return self.latest_frames.get(1), 1
        if mode == "cam2":
            return self.latest_frames.get(2), 2
        return None, None

    def _read_qc_params(self):
        """
        Read and validate QC parameters from UI.

        Returns a dict with validated ints and algorithm flags.
        """
        def _to_int(line_edit, default, min_val=1, max_val=None):
            try:
                v = int(line_edit.text())
            except Exception:
                v = default
            if v < min_val:
                v = min_val
            if max_val is not None and v > max_val:
                v = max_val
            return v

        num_points = _to_int(self.ui.edit_num_points, default=100, min_val=1, max_val=2048)
        agrupamento = _to_int(self.ui.edit_points_grouping, default=3, min_val=1, max_val=50)
        beam_window = _to_int(self.ui.edit_beam_window, default=150, min_val=5, max_val=2000)

        return {
            "num_points": num_points,
            "agrupamento": agrupamento,
            "beam_window": beam_window,
            "baseline_mode": "auto",
            "use_scipy": True,
            "min_r2": 0.7,
        }
    
    @Slot(object)
    def _on_qc_result(self, res: dict):
        """
        Handle QC results on the UI thread:
        - Update labels
        - Emit signals for Napari overlays/plots
        """
        angle_deg = res["angle_deg"]
        coef = res["coef"]
        shape = res["shape"]
        cols = res["cols"]
        fwhms = res["fwhms"]
        focus = res["focus"]
        med = res["median_fwhm"]

        # ---- Tilt ----
        if np.isfinite(angle_deg):
            self.ui.tilt_deg.setText(f"Angle: {angle_deg:.2f}°")
            self.tilt_ready.emit(float(angle_deg), coef, shape)
        else:
            self.ui.tilt_deg.setText("Angle: —°")

        # ---- Focus ----
        if focus is not None:
            self.ui.focus_pixel.setText(f"Pixel: ({focus['column']}, {focus['row']:.1f})")
            self.focus_ready.emit(int(focus["column"]), float(focus["row"]))
        else:
            self.ui.focus_pixel.setText("Pixel: —")

        
        # --- FWHM ---
        self.fwhm_ready.emit(cols, fwhms)  # mantém tudo em px para plots/fit

        # Preferir FWHM no foco (vindo do calculate_focus_point)
        fwhm_focus = np.nan
        if focus is not None:
            fwhm_focus = float(focus.get("fwhm", np.nan))

        if np.isfinite(fwhm_focus):
            if self.pixel_size_um is not None:
                fwhm_focus_um = fwhm_focus * float(self.pixel_size_um)
                self.ui.fwhm_um.setText(f"{fwhm_focus_um:.2f} µm")
            else:
                # se não houver calibração, pelo menos não mentimos na unidade
                self.ui.fwhm_um.setText(f"{fwhm_focus:.2f} px")
        else:
            self.ui.fwhm_um.setText("— µm")




    @Slot(str)
    def _on_qc_error(self, tb: str):
        """Display worker error message on the UI thread."""
        QMessageBox.warning(self, "Quality Control", f"QC failed:\n{tb}")


    @Slot()
    def _on_qc_finished(self):
        """
        Cleanup after QC completes:
        - Re-enable UI
        - Release worker references
        """
        self.ui.calculate_all.setEnabled(True)
        self.ui.calculate_all.setText("Save Calculations")

        # Schedule worker deletion on the UI thread
        if self._qc_worker is not None:
            self._qc_worker.deleteLater()

        self._qc_worker = None
        self._qc_thread = None


    # -----------------------------
    # QC execution
    # -----------------------------
    
    
    def _run_qc_from_selection(self):
        """
        Save button action:
        - If a single camera is selected -> existing behavior
        - If 'Both' is selected -> run QC twice and emit one combined bundle
        """
        if self._selected_cam_mode() == "both":
            self._start_qc_job_both()
        else:
            self._start_qc_job(live=False)



    #---------------------------------------------------------------------------
    #Live Quality Control Calculations
 
    def _toggle_live(self, checked: bool):
        """Turn live calculations on/off."""
        # --- block Live when in 'Both' mode ---
        if checked and self._selected_cam_mode() == "both":
            QMessageBox.information(self, "Live Calculations",
                                    "Live mode is not available when 'Both' is selected.")
            self.ui.live_all.blockSignals(True)
            self.ui.live_all.setChecked(False)
            self.ui.live_all.blockSignals(False)
            return

        self._live_enabled = checked
        self._live_warned_no_frame = False
        if checked:
            self.ui.live_all.setText("Stop Calculations")
            self._live_tick()
            self._live_timer.start()
        else:
            self.ui.live_all.setText("Live Calculation")
            self._live_timer.stop()


    def _live_tick(self):
        """Tick ​​do live: launch QC if there's no job running."""
        if not self._live_enabled:
            return

        # If a calculation is already running, don't launch another one (avoids backlog and freezes).
        if self._qc_thread is not None and self._qc_thread.isRunning():
            return

        self._start_qc_job(live=True)

    
    def _start_qc_job(self, live: bool = False):
        frame, cam_id = self._get_selected_camera_frame()
        if frame is None:
            msg = (
                "No frame available for the selected camera yet.\n"
                "Enable Live mode and wait for a frame."
            )

            if live:
                QMessageBox.information(self, "Live Calculations", msg)
                # Desliga automaticamente o Live (pára timer via toggled)
                self.ui.live_all.setChecked(False)
                return
            else:
                QMessageBox.information(self, "Save Calculations", msg)
                return


        # Se chegou um frame válido, podes voltar a permitir futuros avisos
        self._live_warned_no_frame = False

        # Evita overlap
        if self._qc_thread is not None and self._qc_thread.isRunning():
            return

       
        params = self._read_qc_params()
        frame_for_worker = np.asarray(frame).copy()

        from datetime import datetime
        if not live:
            self._pending_save = True

            # Capture laser snapshot NOW (at click time), not later when PDF is generated.
            beam_info = None
            try:
                if callable(self._beam_info_provider):
                    beam_info = self._beam_info_provider()
            except Exception:
                beam_info = None

            self._pending_save_meta = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "cam_id": cam_id,
                "camera_name": self.ui.camera_combobox.currentText(),
                "params": params,
                "pixel_size_um": self.pixel_size_um,
                "frame": frame_for_worker,

                # Store beam snapshot inside the bundle to guarantee consistency.
                "beam_info": beam_info,
                "qc_folder_name": self.ui.exp_name_lineedit.text().strip(),
            }
        else:
            self._pending_save = False
            self._pending_save_meta = {}



        # job id (para ignorar resultados fora de tempo)
        self._live_job_id += 1
        job_id = self._live_job_id
        self._latest_job_id = job_id

        # Single-shot: limpa overlays + feedback UI
        if not live:
            self.clear_overlays.emit()
            self.ui.calculate_all.setEnabled(False)
            self.ui.calculate_all.setText("Running...")

        # Thread + worker
        self._qc_thread = QThread(self)
        self._qc_worker = QCWorker(frame_for_worker, params, pixel_size_um=self.pixel_size_um)
        self._qc_worker.moveToThread(self._qc_thread)

        self._qc_thread.started.connect(self._qc_worker.run)

        # Resultado com filtro por job_id e estado live
        self._qc_worker.result_ready.connect(lambda res: self._on_qc_result_live_safe(res, job_id, live))
        self._qc_worker.errored.connect(self._on_qc_error)
        self._qc_worker.finished.connect(lambda: self._on_qc_finished_mode(live))

        self._qc_worker.finished.connect(self._qc_thread.quit)
        self._qc_thread.finished.connect(self._qc_thread.deleteLater)

        self._qc_thread.start()
  
    def _on_qc_result_live_safe(self, res: dict, job_id: int, live: bool):
        # se já desligaste live, ignora resultados de jobs live
        if live and not self._live_enabled:
            return
        # ignora jobs antigos
        if job_id != self._latest_job_id:
            return
        self._on_qc_result(res)

        if (not live) and self._pending_save:
            bundle = dict(res)
            bundle.update(self._pending_save_meta)
            self.save_bundle_ready.emit(bundle)

            # garantir que só emite uma vez
            self._pending_save = False
            self._pending_save_meta = {}



    def _on_qc_finished_mode(self, live: bool):
        # faz a limpeza base (o teu método atual)
        self._on_qc_finished()

        # em live, não queremos mexer no botão calculate_all com "Running..."
        if live:
            self.ui.calculate_all.setEnabled(True)
            self.ui.calculate_all.setText("Save Calculations")

    #---------------------------------------------------------------------------------------------------
    # When "both" cameras are enable

    def _start_qc_job_both(self):
        """
        Run QC sequentially for Camera 1 and Camera 2 and emit a single combined bundle.
        Live mode is intentionally NOT supported here.
        """
        # Ensure we have both frames
        f1 = self.latest_frames.get(1)
        f2 = self.latest_frames.get(2)

        if f1 is None or f2 is None:
            QMessageBox.information(
                self, "Save Calculations",
                "Both frames are required.\n"
                "Please enable Camera 1 and Camera 2 Live briefly to populate frames, then stop Live."
            )
            return

        # Avoid overlap if a job is already running
        if self._qc_thread is not None and self._qc_thread.isRunning():
            return

        params = self._read_qc_params()

        # Capture shared metadata ONCE (same click)
        from datetime import datetime
        beam_info = None
        try:
            if callable(self._beam_info_provider):
                beam_info = self._beam_info_provider()
        except Exception:
            beam_info = None

        timestamp = datetime.now().isoformat(timespec="seconds")

        # Prepare queue (copy frames to freeze the data)
        self._both_queue = [
            (1, "Camera 1", np.asarray(f1).copy()),
            (2, "Camera 2", np.asarray(f2).copy()),
        ]
        self._both_results = []
        self._both_meta_base = {
            "mode": "both",
            "timestamp": timestamp,
            "params": params,
            "pixel_size_um": self.pixel_size_um,
            "beam_info": beam_info,
            "qc_folder_name": self.ui.exp_name_lineedit.text().strip(),
        }
        self._both_pending = True

        # UI feedback
        self.clear_overlays.emit()
        self.ui.calculate_all.setEnabled(False)
        self.ui.calculate_all.setText("Running (Both)...")

        # Start first camera job
        self._start_next_both_job()

    def _start_next_both_job(self):
        """
        Start QC for the next camera in the both-queue.
        This keeps only one worker thread running at a time.
        """
        if not self._both_queue:
            # Done: emit a single combined bundle
            combined = dict(self._both_meta_base)
            combined["items"] = self._both_results
            self.save_bundle_ready.emit(combined)

            # Reset UI/state
            self._both_pending = False
            self.ui.calculate_all.setEnabled(True)
            self.ui.calculate_all.setText("Save Calculations")
            return

        cam_id, camera_name, frame_copy = self._both_queue.pop(0)
        self._both_current_cam = cam_id

        # Start worker thread using existing infrastructure
        params = self._both_meta_base["params"]
        self._qc_thread = QThread(self)
        self._qc_worker = QCWorker(frame_copy, params, pixel_size_um=self.pixel_size_um)
        self._qc_worker.moveToThread(self._qc_thread)

        self._qc_thread.started.connect(self._qc_worker.run)

        # Collect result, then move to next camera
        self._qc_worker.result_ready.connect(
            lambda res: self._on_qc_result_both(res, cam_id, camera_name, frame_copy)
        )
        self._qc_worker.errored.connect(self._on_qc_error)
        self._qc_worker.finished.connect(self._qc_thread.quit)
        self._qc_thread.finished.connect(self._qc_thread.deleteLater)
        self._qc_thread.start()

    def _on_qc_result_both(self, res: dict, cam_id: int, camera_name: str, frame_copy: np.ndarray):
        """
        Package a per-camera bundle and store it.
        We can optionally update the UI with the last processed camera.
        """
        # Optional: update UI with last camera results (not required for saving)
        self._on_qc_result(res)

        bundle = dict(res)
        bundle.update({
            "timestamp": self._both_meta_base["timestamp"],
            "cam_id": cam_id,
            "camera_name": camera_name,
            "params": self._both_meta_base["params"],
            "pixel_size_um": self._both_meta_base["pixel_size_um"],
            "frame": frame_copy,
            "beam_info": self._both_meta_base["beam_info"],
        })
        self._both_results.append(bundle)

        # Cleanup worker references and continue
        if self._qc_worker is not None:
            self._qc_worker.deleteLater()
        self._qc_worker = None
        self._qc_thread = None

        self._start_next_both_job()






