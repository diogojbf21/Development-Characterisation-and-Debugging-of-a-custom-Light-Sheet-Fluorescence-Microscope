import math
def speed_from_exposure_ms(exposure_ms: float) -> float:
    """
    Convert camera exposure time in ms to scanner speed.
    Valid fit range is the calibrated confocal operating range.
    """
    return 0.2196 * (exposure_ms ** 2) - 10.669 * exposure_ms + 257.98


def exposure_ms_from_speed(speed: float) -> float:
    """
    Convert scanner speed to camera exposure time in ms.
    Valid fit range is the calibrated confocal operating range.
    """
    return 0.0008 * (speed ** 2) - 0.4635 * speed + 66.224


def clamp_confocal_exposure_ms(exposure_ms: float) -> float:
    """
    Clamp exposure to the experimentally validated confocal range.
    """
    return max(0.001, min(20.0, exposure_ms))


def clamp_confocal_speed(speed: float) -> float:
    """
    Clamp scanner speed to the experimentally validated confocal range.
    """
    return max(100.0, min(400.0, speed))