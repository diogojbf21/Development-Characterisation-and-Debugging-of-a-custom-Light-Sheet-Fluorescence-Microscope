
# Extra_Files/Quality_Control/fwhm_plot_dialog.py

import numpy as np
from PySide6.QtWidgets import QDialog, QVBoxLayout
from PySide6.QtCore import Slot

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from Extra_Files.Quality_Control.qc_algorithms import fit_focus_hyperbola  

class FWHMPlotDialog(QDialog):
    """
    Modeless QDialog embedding a Matplotlib canvas.

    This dialog reproduces the behavior of the original `plot_fwhm(...)` function:
    - filters non-finite values
    - clears and redraws the figure each call (like plt.figure(title); plt.clf())
    - plots data (blue "o-")
    - optionally fits a hyperbola and plots fit + focus point
    - adds legend and tight layout
    - does NOT call plt.show() (non-blocking)
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("FWHM vs Pixel")
        self.setMinimumSize(520, 420)

        # Create Matplotlib Figure/Canvas (no pyplot)
        self._fig = Figure(figsize=(5, 4))
        self._canvas = FigureCanvas(self._fig)
        self._ax = self._fig.add_subplot(111)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas)

        # Store the last returned info dict (mimics return_info behavior)
        self.last_info = None

    def plot_fwhm(
        self,
        columns,
        fwhms,
        *,
        title="FWHM vs Pixel",
        xlabel="Pixel (X)",
        ylabel="FWHM (pixels)",
        show_fit=True,
        use_scipy=True,
        return_info=False,
    ):
        """
        Same semantics as the original `plot_fwhm(...)`:
        returns `info` if return_info=True, else returns None.
        Also stores the info dict in `self.last_info`.
        """
        x = np.asarray(columns, dtype=float)
        y = np.asarray(fwhms, dtype=float)

        # Filter non-finite values (same as original)
        m = np.isfinite(x) & np.isfinite(y)
        x, y = x[m], y[m]

        # Equivalent to: plt.figure(title); plt.clf()
        self.setWindowTitle(title)
        self._ax.cla()

        # Draw data
        self._ax.plot(
            x, y,
            "o-",
            color="tab:blue",
            linewidth=1.5,
            markersize=5,
            label="FWHM (dados)",
        )
        self._ax.set_xlabel(xlabel)
        self._ax.set_ylabel(ylabel)
        self._ax.grid(True, alpha=0.3)

        info = None

        # Optional hyperbola fit (same logic as original)
        if show_fit and fit_focus_hyperbola is not None and len(x) >= 3:
            fit = fit_focus_hyperbola(x, y, use_scipy=use_scipy)  #
            if fit.get("ok", False):
                a, b, c, f = fit["a"], fit["b"], fit["c"], fit["f"]
                x_fit = np.linspace(float(np.min(x)), float(np.max(x)), 400)
                y_fit = b * np.sqrt((x_fit - f) ** 2 + a ** 2) + c
                y_min = fit["y_min"]  # = b*a + c 
                self._ax.plot(
                    x_fit, y_fit,
                    "-",
                    color="tab:red",
                    linewidth=2.0,
                    label="Ajuste hiperbólico",
                )
                self._ax.scatter(
                    [f], [y_min],
                    s=80,
                    color="tab:green",
                    zorder=5,
                    label=f"Foco: x={f:.2f}, y={y_min:.2f}",
                )
                info = {"ok": True, "a": a, "b": b, "c": c, "f": f, "y_min": y_min}
            else:
                info = {"ok": False}

        elif show_fit and fit_focus_hyperbola is None:
            info = {"ok": False, "reason": "fit_focus_hyperbola not available"}

        # Legend + tight layout equivalent
        self._ax.legend()
        try:
            self._fig.tight_layout()
        except Exception:
            pass

        # Redraw without blocking
        self._canvas.draw_idle()

        # Store last info for later inspection
        self.last_info = info

        return info if return_info else None

    @Slot(object, object)
    def update_data(self, columns, fwhms):
        """
        Qt slot for signal connection: keeps the default behavior and updates the plot.
        This matches the typical QC signal signature: fwhm_ready(cols, fwhms). 
        """
        self.plot_fwhm(columns, fwhms, return_info=False)