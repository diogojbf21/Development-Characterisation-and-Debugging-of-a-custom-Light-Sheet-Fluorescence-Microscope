
import numpy as np

QC_TILT_NAME = "QC Tilt"
QC_FOCUS_NAME = "QC Focus"

def ensure_qc_layers(viewer):
    """
    Create QC overlay layers once (if missing) and keep them hidden.
    This implements the 'zero-freeze' strategy: never remove/re-add layers.
    """
    # Shapes layer (line)
    if QC_TILT_NAME not in viewer.layers:
        viewer.add_shapes(
            data=[],                    # empty list of shapes
            shape_type="line",
            edge_color="red",
            edge_width=2,
            name=QC_TILT_NAME,
        )
        viewer.layers[QC_TILT_NAME].visible = False

    # Points layer (focus)
    if QC_FOCUS_NAME not in viewer.layers:
        empty_points = np.empty((0, 2), dtype=float)
        viewer.add_points(
            empty_points,
            size=25,
            face_color="yellow",
            name=QC_FOCUS_NAME,
        )
        viewer.layers[QC_FOCUS_NAME].visible = False


def draw_tilt_line(viewer, coef, image_shape):
    """
    Update the existing Shapes layer with a single line.
    IMPORTANT: Shapes.data expects a list of arrays, even for one shape.
    """
    ensure_qc_layers(viewer)

    if coef is None or image_shape is None:
        viewer.layers[QC_TILT_NAME].visible = False
        viewer.layers[QC_TILT_NAME].data = []
        return

    h, w = image_shape
    x = np.array([0, w - 1], dtype=float)
    y = coef[0] * x + coef[1]
    points = np.column_stack((y, x))  # (row, col)

    viewer.layers[QC_TILT_NAME].data = [points]   # <- FIX: list of shapes
    viewer.layers[QC_TILT_NAME].visible = True


def draw_focus_point(viewer, row, col):
    """
    Update the existing Points layer with a single point.
    """
    ensure_qc_layers(viewer)

    point = np.array([[row, col]], dtype=float)  # (1,2)
    viewer.layers[QC_FOCUS_NAME].data = point
    viewer.layers[QC_FOCUS_NAME].visible = True


def clear_qc_overlays(viewer):
    """
    Zero-freeze clear: hide layers and clear data (do NOT remove layers).
    """
    if QC_TILT_NAME in viewer.layers:
        viewer.layers[QC_TILT_NAME].visible = False
        viewer.layers[QC_TILT_NAME].data = []

    if QC_FOCUS_NAME in viewer.layers:
        viewer.layers[QC_FOCUS_NAME].visible = False
        viewer.layers[QC_FOCUS_NAME].data = np.empty((0, 2), dtype=float)

