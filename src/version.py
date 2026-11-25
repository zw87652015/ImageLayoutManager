# ──────────────────────────────────────────────
# Application Version  (update this before release)
# ──────────────────────────────────────────────
APP_VERSION = "3.7.1"

# Display name shown inside the app (window title, About, Help).
APP_NAME = "Image Layout Manager"

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

# Keep the software-wide DOI and author in sync with CITATION.cff.
APP_CITATION_DOI = "10.5281/zenodo.23957684"
APP_CITATION_URL = f"https://doi.org/{APP_CITATION_DOI}"
_CITATION_YEAR = 2026
APP_CITATION_REFERENCE = (
    f"Jiang, L. ({_CITATION_YEAR}). {APP_NAME} [Computer software]. Zenodo."
)
APP_CITATION_BIBTEX = (
    "@misc{jiang_image_layout_manager,\n"
    "  author = {Jiang, Luojia},\n"
    f"  title = {{{{{APP_NAME}}}}},\n"
    f"  year = {{{_CITATION_YEAR}}},\n"
    "  howpublished = {Zenodo},\n"
    f"  doi = {{{APP_CITATION_DOI}}},\n"
    f"  url = {{{APP_CITATION_URL}}}\n"
    "}\n"
)
