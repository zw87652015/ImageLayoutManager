"""Tick-step selection and label formatting for the canvas rulers.

Pure math — no Qt imports, so it can be unit-tested without a QApplication.
Scene units are millimetres; the ruler converts them into the display unit.
"""

import math

MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72.0}
UNITS = ("mm", "cm", "in", "pt")

_MINUS = "\u2212"
_MAX_TICKS = 20000


def _candidates(unit: str) -> list:
    """Ordered candidate major steps, expressed in display units."""
    if unit == "in":
        # Binary fractions for fine steps, decimal multiples above 1 inch.
        steps = [2.0 ** k for k in range(-6, 1)]
        steps += [m * 10.0 ** k for k in range(0, 8) for m in (1, 2, 5)]
    else:
        steps = [m * 10.0 ** k for k in range(-4, 8) for m in (1, 2, 5)]
    return sorted(set(steps))


def _leading_digit(step: float) -> int:
    if step <= 0:
        return 0
    return int(round(step / 10.0 ** math.floor(math.log10(step))))


def _subdivision_choices(step: float, unit: str) -> tuple:
    """Subdivision counts to try, largest first."""
    if unit == "in" and step <= 1.0:
        return (8, 4, 2)  # binary halving matches the fractional inch steps
    d = _leading_digit(step)
    if d == 1:
        return (10, 5, 2)
    if d == 2:
        return (4, 2)
    if d == 5:
        return (5,)
    return (2,)


def choose_steps(px_per_unit: float, unit: str, min_major_px: float,
                 min_minor_px: float = 5.0):
    """Pick (major_step, subdivisions) in display units.

    major_step is the smallest candidate that keeps major ticks at least
    min_major_px apart; subdivisions is the largest allowed count that keeps
    minor ticks at least min_minor_px apart (1 = majors only).
    """
    cands = _candidates(unit)
    major = cands[-1]
    for cand in cands:
        if cand * px_per_unit >= min_major_px:
            major = cand
            break
    for n in _subdivision_choices(major, unit):
        if (major / n) * px_per_unit >= min_minor_px:
            return major, n
    return major, 1


def ticks(start_units: float, end_units: float, major_step: float,
          subdivisions: int):
    """Return [(value, kind)] with kind in {"major", "half", "minor"}.

    Values are computed as i * minor from an integer index so repeated
    float addition can never drift; -0.0 is normalised to 0.0.
    """
    if major_step <= 0 or subdivisions < 1 or end_units < start_units:
        return []
    minor = major_step / subdivisions
    i0 = math.floor(start_units / minor)
    i1 = math.ceil(end_units / minor)
    if i1 - i0 + 1 > _MAX_TICKS:
        return []
    out = []
    for i in range(i0, i1 + 1):
        value = i * minor
        if i % subdivisions == 0:
            kind = "major"
        elif subdivisions % 2 == 0 and i % subdivisions == subdivisions // 2:
            kind = "half"
        else:
            kind = "minor"
        out.append((0.0 if value == 0 else value, kind))
    return out


def _label_decimals(major_step: float) -> int:
    if major_step <= 0:
        return 0
    decimals = max(0, -math.floor(math.log10(major_step) + 1e-9))
    # Binary inch fractions (1/8, 1/64, …) need enough decimals to print
    # the exact value instead of a rounded decimal.
    if major_step < 1.0:
        log2v = math.log2(major_step)
        if abs(log2v - round(log2v)) < 1e-9:
            decimals = max(decimals, -int(round(log2v)))
    return decimals


def format_label(value: float, major_step: float) -> str:
    """Format a major-tick label: exact, no float noise, U+2212 minus."""
    decimals = _label_decimals(major_step)
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text.replace("-", _MINUS)
