"""Real-world scale for the canvas: what "100%" means on a given monitor.

Scene units are millimetres and the canvas transform is px-per-mm. At 100%
the page should print at its true size, so the 100% reference is the number
of device-independent pixels that span one physical millimetre on the screen
the view is shown on, times a per-monitor calibration factor.

The math below is Qt-free so it can be tested without a QApplication; the
Qt adapters (screen identity, QSettings) import Qt lazily.
"""

import math
import re

MM_PER_INCH = 25.4
FALLBACK_DPI = 96.0
PLAUSIBLE_DPI = (48.0, 400.0)        # device-independent px per inch
CALIBRATION_RANGE = (0.5, 2.0)
SETTINGS_PREFIX = "display_calibration/"


def clamp_calibration(factor) -> float:
    try:
        value = float(factor)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(value):
        return 1.0
    lo, hi = CALIBRATION_RANGE
    return min(hi, max(lo, value))


def _plausible_dpi(value) -> bool:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    lo, hi = PLAUSIBLE_DPI
    return math.isfinite(v) and lo <= v <= hi


def base_px_per_mm(physical_dpi, logical_dpi=None) -> tuple:
    if _plausible_dpi(physical_dpi):
        return float(physical_dpi) / MM_PER_INCH, "physical"
    if _plausible_dpi(logical_dpi):
        return float(logical_dpi) / MM_PER_INCH, "logical"
    return FALLBACK_DPI / MM_PER_INCH, "fallback"


def actual_px_per_mm(physical_dpi, logical_dpi=None, calibration=1.0) -> float:
    base, _source = base_px_per_mm(physical_dpi, logical_dpi)
    return base * clamp_calibration(calibration)


def zoom_fraction(m11, px_per_mm) -> float:
    if px_per_mm <= 0:
        return m11
    return m11 / px_per_mm


def calibration_after_measurement(current, nominal_mm, measured_mm) -> float:
    try:
        measured = float(measured_mm)
    except (TypeError, ValueError):
        return clamp_calibration(current)
    if not math.isfinite(measured) or measured <= 0:
        return clamp_calibration(current)
    return clamp_calibration(clamp_calibration(current) * nominal_mm / measured)


def screen_key(manufacturer, model, serial, name, width, height) -> str:
    size = f"{int(width)}x{int(height)}"
    if model or serial:
        parts = [manufacturer or "", model or "", serial or "", size]
    else:
        parts = [name or "", size]
    key = re.sub(r"[^A-Za-z0-9._-]", "_", "|".join(parts))
    return key or "screen"


# ── Qt adapters ──────────────────────────────────────────────────────────

def _settings():
    from PyQt6.QtCore import QSettings
    return QSettings("AcademicFigureLayout", "ImageLayoutManager")


def key_for_screen(screen) -> str:
    size = screen.size()
    return screen_key(screen.manufacturer(), screen.model(), screen.serialNumber(),
                      screen.name(), size.width(), size.height())


def screen_calibration(screen, settings=None) -> float:
    if settings is None:
        settings = _settings()
    return clamp_calibration(
        settings.value(SETTINGS_PREFIX + key_for_screen(screen), 1.0))


def set_screen_calibration(screen, factor, settings=None) -> None:
    if settings is None:
        settings = _settings()
    key = SETTINGS_PREFIX + key_for_screen(screen)
    value = clamp_calibration(factor)
    if abs(value - 1.0) < 1e-6:
        settings.remove(key)
    else:
        settings.setValue(key, value)


def screen_px_per_mm(screen, settings=None) -> float:
    if screen is None:
        return FALLBACK_DPI / MM_PER_INCH
    return actual_px_per_mm(screen.physicalDotsPerInch(), screen.logicalDotsPerInch(),
                            screen_calibration(screen, settings))


def screen_report(screen) -> dict:
    physical = screen.physicalSize()
    dpi = screen.physicalDotsPerInch()
    base, source = base_px_per_mm(dpi, screen.logicalDotsPerInch())
    return {
        "model": screen.model() or screen.name(),
        "physical_dpi": dpi,
        "physical_w_mm": physical.width(),
        "physical_h_mm": physical.height(),
        "source": source,
        "base_px_per_mm": base,
        "calibration": screen_calibration(screen),
    }
