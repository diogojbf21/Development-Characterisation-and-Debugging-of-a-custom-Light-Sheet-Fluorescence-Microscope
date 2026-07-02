import math


# ============================================================
# FOV calibration
# ============================================================

PX_MIN = 0.0
PX_MAX = 2047.0

# Scanner/sample positions corresponding to the camera FOV
SCAN_AT_PX_MIN = 2300.0
SCAN_AT_PX_MAX = -2900.0

# Linear mapping: px = m * scan + b
M_PX_PER_SCAN_UNIT = (PX_MAX - PX_MIN) / (SCAN_AT_PX_MAX - SCAN_AT_PX_MIN)
B_PX = PX_MIN - M_PX_PER_SCAN_UNIT * SCAN_AT_PX_MIN

# Useful absolute conversion
SCAN_UNITS_PER_PX = abs(1.0 / M_PX_PER_SCAN_UNIT)   # ≈ 2.540302882


# ============================================================
# Confocal timing / UI calibration
# ============================================================

# If you want 1 image pixel per exposure:
DEFAULT_PIXELS_PER_EXPOSURE = 1.0

# Exposure range actually validated experimentally
MIN_EXPOSURE_MS = 0.272842
MAX_EXPOSURE_MS = 19.956451

# Speed setting range observed experimentally
MIN_UI_SPEED = 129.0
MAX_UI_SPEED = 258.0

# Empirical parameters combining:
#   required physical scan rate from the FOV
#   -> UI speed setting
#
# ui_speed = UI_GAIN * required_scan_rate + UI_OFFSET
#
# where:
# required_scan_rate =
#     pixels_per_exposure * SCAN_UNITS_PER_PX / (exposure_ms + OVERHEAD_MS)
#
# These values are consistent with your measured exposure-speed table.
OVERHEAD_MS = 19.2763241
UI_GAIN = 1945.1507828
UI_OFFSET = 4.58888922


# ============================================================
# Clamp utilities
# ============================================================

def clamp_confocal_exposure_ms(exposure_ms: float) -> float:
    return max(MIN_EXPOSURE_MS, min(MAX_EXPOSURE_MS, float(exposure_ms)))


def clamp_confocal_speed(speed: float) -> float:
    return max(MIN_UI_SPEED, min(MAX_UI_SPEED, float(speed)))


# ============================================================
# Geometry helpers
# ============================================================

def scanner_to_pixel(scan_pos: float) -> float:
    """
    Convert scanner position to camera pixel coordinate.
    """
    return M_PX_PER_SCAN_UNIT * float(scan_pos) + B_PX


def pixel_to_scanner(px: float) -> float:
    """
    Convert camera pixel coordinate to scanner position.
    """
    return (float(px) - B_PX) / M_PX_PER_SCAN_UNIT


def scanner_units_per_frame(pixels_per_exposure: float = DEFAULT_PIXELS_PER_EXPOSURE) -> float:
    """
    How many scanner units correspond to the requested number of pixels per frame.
    """
    return float(pixels_per_exposure) * SCAN_UNITS_PER_PX


# ============================================================
# Physical model
# ============================================================

def required_scan_rate_units_per_ms(
    exposure_ms: float,
    pixels_per_exposure: float = DEFAULT_PIXELS_PER_EXPOSURE,
    overhead_ms: float = OVERHEAD_MS,
) -> float:
    """
    Required scanner rate in scanner-units/ms to move by the requested
    number of image pixels during one effective frame interval.
    """
    exposure_ms = clamp_confocal_exposure_ms(exposure_ms)
    effective_time_ms = exposure_ms + float(overhead_ms)

    if effective_time_ms <= 0:
        raise ValueError("Effective frame time must be > 0 ms")

    return scanner_units_per_frame(pixels_per_exposure) / effective_time_ms


# ============================================================
# UI mapping
# ============================================================

def speed_from_exposure_ms(
    exposure_ms: float,
    pixels_per_exposure: float = DEFAULT_PIXELS_PER_EXPOSURE,
) -> float:
    """
    Return the scanner UI speed setting required for the given exposure time,
    based on:
      1) the FOV geometry calibration, and
      2) the empirical mapping from required scan rate to UI speed setting.
    """
    scan_rate = required_scan_rate_units_per_ms(
        exposure_ms=exposure_ms,
        pixels_per_exposure=pixels_per_exposure,
        overhead_ms=OVERHEAD_MS,
    )

    ui_speed = UI_GAIN * scan_rate + UI_OFFSET
    return clamp_confocal_speed(ui_speed)


def exposure_ms_from_speed(
    speed: float,
    pixels_per_exposure: float = DEFAULT_PIXELS_PER_EXPOSURE,
) -> float:
    """
    Inverse mapping: estimate the exposure time corresponding to a given
    scanner UI speed setting.
    """
    speed = clamp_confocal_speed(speed)

    scan_rate = (speed - UI_OFFSET) / UI_GAIN
    if scan_rate <= 0:
        raise ValueError("Estimated scan rate must be > 0")

    exposure_ms = scanner_units_per_frame(pixels_per_exposure) / scan_rate - OVERHEAD_MS
    return clamp_confocal_exposure_ms(exposure_ms)