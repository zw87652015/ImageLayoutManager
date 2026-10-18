"""Which distribution channel this build was installed through (Qt-free).

Channels: ``"store"`` (Microsoft Store / MSIX package — Store policy 10.2.5
forbids any non-Store update path), ``"installer"`` (frozen Inno Setup exe),
``"macos"`` (frozen .app) and ``"source"`` (anything else).

``ILM_INSTALL_CHANNEL`` overrides detection for manual verification.
"""

import os
import sys

STORE_PRODUCT_ID = "9NGNW4D8L5QH"
STORE_URI = f"ms-windows-store://pdp/?productid={STORE_PRODUCT_ID}"
STORE_WEB_URL = f"https://apps.microsoft.com/detail/{STORE_PRODUCT_ID}"

_CHANNELS = ("store", "installer", "macos", "source")

_ERROR_INSUFFICIENT_BUFFER = 122  # returned when the process IS MSIX-packaged


def install_channel() -> str:
    override = os.environ.get("ILM_INSTALL_CHANNEL", "")
    if override in _CHANNELS:
        return override
    if sys.platform == "win32":
        packaged = False
        try:
            import ctypes
            length = ctypes.c_uint32(0)
            rc = ctypes.windll.kernel32.GetCurrentPackageFullName(
                ctypes.byref(length), None)
            packaged = rc == _ERROR_INSUFFICIENT_BUFFER
        except Exception:
            packaged = False
        if packaged:
            return "store"
        return "installer" if getattr(sys, "frozen", False) else "source"
    if sys.platform == "darwin":
        return "macos" if getattr(sys, "frozen", False) else "source"
    return "source"
