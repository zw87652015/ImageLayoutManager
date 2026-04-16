from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QScrollArea, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from src.app.i18n import tr


def _scroll_page(html: str) -> QWidget:
    """Wrap an HTML string in a scrollable QLabel page."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)

    lbl = QLabel(html)
    lbl.setWordWrap(True)
    lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    lbl.setOpenExternalLinks(True)
    lbl.setContentsMargins(16, 16, 16, 16)
    lbl.setTextFormat(Qt.TextFormat.RichText)

    scroll.setWidget(lbl)
    return scroll


def _shortcuts_page() -> QWidget:
    shortcuts = [
        ("Ctrl + N",       "New project"),
        ("Ctrl + O",       "Open project"),
        ("Ctrl + S",       "Save project"),
        ("Ctrl + Shift+S", "Save As…"),
        ("Ctrl + Z",       "Undo"),
        ("Ctrl + Y",       "Redo"),
        ("Ctrl + Shift+L", "Auto Label all cells"),
        ("Ctrl + Shift+A", "Auto Layout"),
        ("Ctrl + ]",       "Bring selected cell to front"),
        ("Ctrl + [",       "Send selected cell to back"),
        ("Ctrl + Delete",  "Delete image from selected cell"),
        ("Delete",         "Delete selected text item"),
        ("F5",             "Reload all images from disk"),
        ("Scroll wheel",   "Zoom canvas in / out"),
        ("Middle-click drag", "Pan canvas"),
        ("Ctrl + Shift+T", "Toggle light / dark theme"),
        ("Arrow keys",     "Nudge selected cell (freeform mode)"),
        ("Shift + Arrow",  "Navigate between cells"),
    ]

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(16, 16, 16, 16)

    table = QTableWidget(len(shortcuts), 2)
    table.setHorizontalHeaderLabels(["Shortcut", "Action"])
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setStyleSheet("QTableWidget { border: none; } QHeaderView::section { padding: 6px; }")

    for row, (key, desc) in enumerate(shortcuts):
        key_item = QTableWidgetItem(key)
        key_font = QFont("Courier New", 11)
        key_item.setFont(key_font)
        table.setItem(row, 0, key_item)
        table.setItem(row, 1, QTableWidgetItem(desc))

    layout.addWidget(table)
    return widget


_GETTING_STARTED_HTML = """
<h2 style="margin-top:0">Getting Started</h2>

<h3>Creating a New Layout</h3>
<ol>
  <li>Launch the app. A default 2×2 grid is created automatically.</li>
  <li>Go to <b>File → New</b> (<code>Ctrl+N</code>) to start from a blank canvas.</li>
  <li>Use the <b>Inspector</b> on the right to set the canvas size (width, height, DPI, gap).</li>
</ol>

<h3>Opening an Existing Layout</h3>
<p>Go to <b>File → Open</b> (<code>Ctrl+O</code>) and select a <code>.figlayout</code> file. 
All images are re-loaded from their original paths; if a path is missing, the cell shows a placeholder.</p>

<h3>Saving</h3>
<ul>
  <li><b>File → Save</b> (<code>Ctrl+S</code>) — saves over the current file.</li>
  <li><b>File → Save As…</b> — saves to a new <code>.figlayout</code> file.</li>
</ul>
<p>The title bar shows <b>[*]</b> when there are unsaved changes.</p>

<h3>The 3-Column Layout</h3>
<ul>
  <li><b>Left — Layers:</b> shows the row/cell tree. Click any row to select it.</li>
  <li><b>Centre — Canvas:</b> the live preview of your figure.</li>
  <li><b>Right — Inspector:</b> properties for the selected cell, row, or project.</li>
</ul>
"""

_IMAGES_HTML = """
<h2 style="margin-top:0">Working with Images</h2>

<h3>Importing Images</h3>
<ul>
  <li><b>Drag &amp; drop</b> an image file directly onto a cell in the canvas.</li>
  <li><b>File → Import Images…</b> — choose one or more images; they fill empty cells left-to-right, top-to-bottom.</li>
  <li><b>File → Open Images as Grid…</b> — automatically creates a grid sized to fit the chosen images.</li>
</ul>

<h3>Replacing / Swapping</h3>
<ul>
  <li>Drop an image onto an already-filled cell to <b>replace</b> it.</li>
  <li>Drag one cell onto another on the canvas to <b>swap</b> their images.</li>
  <li>Hold <b>Ctrl</b> while dragging to swap multiple selected cells at once.</li>
</ul>

<h3>Fit Mode (Inspector → Cell)</h3>
<ul>
  <li><b>Contain</b> — image fits entirely inside the cell, letter-boxed.</li>
  <li><b>Cover</b> — image fills the cell, cropped to fit.</li>
  <li><b>Stretch</b> — image is stretched to fill exactly.</li>
</ul>

<h3>Rotation</h3>
<p>Set 0 / 90 / 180 / 270° rotation in the Inspector. Rotation is applied before fit.</p>

<h3>Reloading Images</h3>
<p>Press <b>F5</b> or <b>File → Reload Images</b> to re-read all source files from disk 
(useful after external edits).</p>
"""

_CELLS_HTML = """
<h2 style="margin-top:0">Cells &amp; Splitting</h2>

<h3>Grid Mode</h3>
<p>By default the canvas is a simple grid of rows and columns. 
Each row can have a different column count and height ratio 
(set in the Inspector when a row is selected).</p>

<h3>Splitting a Cell</h3>
<ol>
  <li><b>Right-click</b> a cell on the canvas.</li>
  <li>Choose <b>Split Horizontal</b> or <b>Split Vertical</b>.</li>
  <li>Two sub-cells are created inside the parent cell.</li>
  <li>You can split sub-cells again — splitting is unlimited.</li>
</ol>

<h3>Adjusting Split Ratios</h3>
<p>Select a sub-cell and open the <b>Sub-Cell</b> section in the Inspector. 
Drag the ratio slider or type a value to resize proportionally.</p>
<p>Alternatively, drag the <b>divider bar</b> between sub-cells directly on the canvas.</p>

<h3>Freeform Mode</h3>
<ul>
  <li>Go to <b>Layout → Convert Grid → Freeform</b> to unlock free positioning.</li>
  <li>Drag cells anywhere. Resize via the Inspector (X, Y, W, H in mm).</li>
  <li>Use <b>Bring to Front</b> / <b>Send to Back</b> (<code>Ctrl+]</code> / <code>Ctrl+[</code>) to control overlap.</li>
  <li>Switch back to grid mode with <b>Layout → Switch to Grid Mode</b> (positions are retained).</li>
</ul>

<h3>Inserting Rows / Cells</h3>
<p>Right-click a row header or cell to access <b>Insert Row Above / Below</b> 
and <b>Insert Column</b> options.</p>
"""

_LABELS_HTML = """
<h2 style="margin-top:0">Labels &amp; Text</h2>

<h3>Auto Label</h3>
<p>Press <code>Ctrl+Shift+L</code> or <b>Edit → Auto Label</b> to add panel labels 
(a, b, c… or A, B, C…) to all leaf cells automatically.</p>
<p>The labelling scheme, font, size, colour, and position are all 
set in the <b>Inspector → Project Settings → Label</b> section.</p>

<h3>Editing a Label</h3>
<ol>
  <li>Click a label on the canvas to select it.</li>
  <li>The Inspector shows the <b>Label Cell</b> panel.</li>
  <li>Edit the text directly in the <b>Label Text</b> field.</li>
  <li>Use <b>Apply Color to All</b> to sync the colour across the whole group.</li>
</ol>

<h3>Adding Free Text</h3>
<p>Go to <b>Edit → Add Text</b> to insert a free-floating text item. 
Drag it anywhere on the canvas. Edit its font, size, and colour in the Inspector.</p>

<h3>Corner Labels</h3>
<p>Select a cell, then use the <b>Corner Labels</b> section in the Inspector 
to type short annotations at each corner (top-left, top-right, bottom-left, bottom-right).</p>

<h3>Scale Bar (Microscopy)</h3>
<p>Enable the scale bar in <b>Inspector → Scale Bar</b> for microscopy images. 
Set µm/px calibration, bar length, colour, and position.</p>
"""

_EXPORT_HTML = """
<h2 style="margin-top:0">Export</h2>

<h3>Supported Formats</h3>
<ul>
  <li><b>PDF</b> — vector-based; ideal for journal submission. Labels and SVG images remain vector.</li>
  <li><b>TIFF</b> — lossless raster at the DPI you specify (Inspector → Project → DPI).</li>
  <li><b>JPG</b> — compressed raster. Quality is fixed at 95%.</li>
</ul>

<h3>How to Export</h3>
<ol>
  <li>Click the <b>Export</b> toolbar button and pick a format, 
      or use the <b>File</b> menu.</li>
  <li>Choose a destination file in the dialog.</li>
  <li>The exported file matches the canvas layout exactly.</li>
</ol>

<h3>DPI Setting</h3>
<p>DPI (dots per inch) controls the pixel dimensions of raster exports:</p>
<p style="margin-left:16px"><code>pixels = (size_in_mm / 25.4) × DPI</code></p>
<p>For most journals, <b>300 DPI</b> is sufficient for TIFF/JPG. 
PDF export resolution is separate from this setting.</p>

<h3>Canvas Size</h3>
<p>Set <b>Width</b> and <b>Height</b> (in mm) in the Inspector. 
These define the physical dimensions of the exported figure regardless of DPI.</p>

<h3>Tips for Publication</h3>
<ul>
  <li>Keep gap ≥ 1 mm so panels don't touch.</li>
  <li>Use SVG source images when possible — they stay crisp in PDF exports.</li>
  <li>Set DPI ≥ 300 for raster exports submitted to journals.</li>
  <li>Save a <code>.figlayout</code> file alongside your exported figure for reproducibility.</li>
</ul>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("help_title"))
        self.resize(680, 540)
        self.setModal(False)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(_scroll_page(_GETTING_STARTED_HTML), tr("help_tab_start"))
        tabs.addTab(_scroll_page(_IMAGES_HTML),          tr("help_tab_images"))
        tabs.addTab(_scroll_page(_CELLS_HTML),           tr("help_tab_cells"))
        tabs.addTab(_scroll_page(_LABELS_HTML),          tr("help_tab_labels"))
        tabs.addTab(_scroll_page(_EXPORT_HTML),          tr("help_tab_export"))
        tabs.addTab(_shortcuts_page(),                   tr("help_tab_shortcuts"))
        root.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 0)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)
