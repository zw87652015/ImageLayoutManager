# ──────────────────────────────────────────────
# Application Version  (update this before release)
# ──────────────────────────────────────────────
APP_VERSION = "3.3.2"

# Single source of truth for attribution metadata. These strings end up in:
#   - Windows VS_VERSIONINFO embedded in ImageLayoutManager.exe / imagelayout-cli.exe
#   - Inno Setup AppPublisher / AppCopyright fields shown in Apps & Features
#   - macOS Info.plist NSHumanReadableCopyright
#   - The in-app About dialog
APP_PUBLISHER = "zw87652015"
APP_COPYRIGHT_YEAR = "2026"
APP_LICENSE = "Apache-2.0"
APP_COPYRIGHT = (
    f"Copyright (C) {APP_COPYRIGHT_YEAR} {APP_PUBLISHER}. "
    f"Licensed under {APP_LICENSE}."
)
APP_PUBLISHER_URL = "https://github.com/zw87652015/ImageLayoutManager"
