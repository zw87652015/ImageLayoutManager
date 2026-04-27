from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QScrollArea, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from src.app.i18n import tr, current_language


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


_SHORTCUTS_EN = [
    ("Ctrl + N",          "New project"),
    ("Ctrl + O",          "Open project"),
    ("Ctrl + S",          "Save project"),
    ("Ctrl + Shift+S",    "Save As…"),
    ("Ctrl + T",          "New Tab"),
    ("Ctrl + W",          "Close current Tab"),
    ("Ctrl + Z",          "Undo"),
    ("Ctrl + Y",          "Redo"),
    ("Ctrl + Shift+L",    "Auto Label (in-cell)"),
    ("Ctrl + Shift+K",    "Auto Label (row above)"),
    ("Ctrl + Shift+A",    "Auto Layout"),
    ("Ctrl + Shift+P",    "Toggle Export Preview"),
    ("Ctrl + ]",          "Bring selected cell to front"),
    ("Ctrl + [",          "Send selected cell to back"),
    ("Ctrl + Delete",     "Delete image from selected cell"),
    ("Delete",            "Delete selected text item"),
    ("F5",                "Reload all images from disk"),
    ("Scroll wheel",      "Zoom canvas in / out"),
    ("Middle-click drag", "Pan canvas"),
    ("Ctrl + Shift+T",    "Toggle light / dark theme"),
    ("Ctrl + \\",         "Toggle Layers panel"),
    ("Arrow keys",        "Nudge selected cell (freeform mode)"),
    ("Shift + Arrow",     "Navigate between cells"),
]

_SHORTCUTS_ZH = [
    ("Ctrl + N",          "新建项目"),
    ("Ctrl + O",          "打开项目"),
    ("Ctrl + S",          "保存项目"),
    ("Ctrl + Shift+S",    "另存为…"),
    ("Ctrl + T",          "新建标签页"),
    ("Ctrl + W",          "关闭当前标签页"),
    ("Ctrl + Z",          "撤销"),
    ("Ctrl + Y",          "重做"),
    ("Ctrl + Shift+L",    "自动标注（嵌入图片）"),
    ("Ctrl + Shift+K",    "自动标注（上方行）"),
    ("Ctrl + Shift+A",    "自动布局"),
    ("Ctrl + Shift+P",    "切换导出预览模式"),
    ("Ctrl + ]",          "将选中单元格置于顶层"),
    ("Ctrl + [",          "将选中单元格置于底层"),
    ("Ctrl + Delete",     "删除选中单元格的图片"),
    ("Delete",            "删除选中的文字项"),
    ("F5",                "从磁盘重新加载所有图片"),
    ("滚轮",              "缩放画布"),
    ("中键拖动",          "平移画布"),
    ("Ctrl + Shift+T",    "切换浅色/深色主题"),
    ("Ctrl + \\",         "显示/隐藏图层面板"),
    ("方向键",            "微移选中单元格（自由布局模式）"),
    ("Shift + 方向键",    "在单元格间导航"),
]


def _shortcuts_page() -> QWidget:
    shortcuts = _SHORTCUTS_ZH if current_language() == "zh" else _SHORTCUTS_EN

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(16, 16, 16, 16)

    table = QTableWidget(len(shortcuts), 2)
    table.setHorizontalHeaderLabels([tr("help_shortcut_col"), tr("help_action_col")])
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


_GETTING_STARTED_HTML_EN = """
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

_GETTING_STARTED_HTML_ZH = """
<h2 style="margin-top:0">快速入门</h2>

<h3>新建布局</h3>
<ol>
  <li>启动应用后，将自动创建一个默认的 2×2 网格。</li>
  <li>通过 <b>文件 → 新建</b>（<code>Ctrl+N</code>）可从空白画布开始。</li>
  <li>使用右侧<b>检查器</b>设置画布尺寸（宽度、高度、分辨率、间距）。</li>
</ol>

<h3>打开已有布局</h3>
<p>通过 <b>文件 → 打开</b>（<code>Ctrl+O</code>）选择 <code>.figlayout</code> 文件。
所有图片将从原始路径重新加载；若路径缺失，单元格将显示占位符。</p>

<h3>保存</h3>
<ul>
  <li><b>文件 → 保存</b>（<code>Ctrl+S</code>）— 覆盖当前文件。</li>
  <li><b>文件 → 另存为…</b> — 保存为新的 <code>.figlayout</code> 文件。</li>
</ul>
<p>标题栏显示 <b>[*]</b> 表示有未保存的更改。</p>

<h3>三栏布局</h3>
<ul>
  <li><b>左侧 — 图层：</b>显示行/单元格树形结构，点击任意行可选中。</li>
  <li><b>中间 — 画布：</b>图表的实时预览。</li>
  <li><b>右侧 — 检查器：</b>显示选中单元格、行或项目的属性。</li>
</ul>
"""

_IMAGES_HTML_EN = """
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

<h3>Picture-in-Picture (PiP) / Insets</h3>
<ul>
  <li><b>Right-click</b> an image cell and choose <b>Insert → PiP</b> to add a smaller sub-image on top.</li>
  <li>Drag the PiP to move it; use the Inspector to adjust its size, border, and position (in % of parent).</li>
</ul>

<h3>Cropping</h3>
<ul>
  <li><b>Right-click</b> a cell and choose <b>Crop Image</b>.</li>
  <li>Drag handles to adjust; hold <b>Shift</b> to lock aspect ratio. Press <b>Enter</b> to apply.</li>
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

_IMAGES_HTML_ZH = """
<h2 style="margin-top:0">图片操作</h2>

<h3>导入图片</h3>
<ul>
  <li><b>拖放</b>图片文件到画布上的单元格中。</li>
  <li><b>文件 → 导入图片…</b> — 选择一张或多张图片，从左至右、从上至下依次填充空单元格。</li>
  <li><b>文件 → 以网格打开图片…</b> — 自动创建适合所选图片数量的网格。</li>
</ul>

<h3>替换与交换</h3>
<ul>
  <li>将图片拖放到已有图片的单元格上即可<b>替换</b>。</li>
  <li>在画布上将一个单元格拖到另一个单元格上即可<b>交换</b>图片。</li>
  <li>按住 <b>Ctrl</b> 拖动可同时交换多个选中的单元格。</li>
</ul>

<h3>画中画 (PiP) / 插图</h3>
<ul>
  <li><b>右键点击</b>图片单元格并选择<b>插入 → 以子图插入</b>，可在上方添加较小的子图。</li>
  <li>拖动子图可移动位置；使用检查器调整其大小、边框和位置（占父单元格的百分比）。</li>
</ul>

<h3>裁剪</h3>
<ul>
  <li><b>右键点击</b>单元格并选择<b>裁剪图片</b>。</li>
  <li>拖动手柄进行调整；按住 <b>Shift</b> 可锁定比例。按 <b>Enter</b> 确认应用。</li>
</ul>

<h3>缩放模式（检查器 → 单元格）</h3>
<ul>
  <li><b>包含</b> — 图片完整显示在单元格内，保留空白边。</li>
  <li><b>覆盖</b> — 图片填满单元格，超出部分被裁剪。</li>
  <li><b>拉伸</b> — 图片被拉伸以完全填充单元格。</li>
</ul>

<h3>旋转</h3>
<p>在检查器中设置 0 / 90 / 180 / 270° 旋转。旋转在缩放模式之前应用。</p>

<h3>重新加载图片</h3>
<p>按 <b>F5</b> 或 <b>文件 → 重新加载图片</b>，从磁盘重新读取所有源文件（适合外部编辑后刷新）。</p>
"""

_CELLS_HTML_EN = """
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

_CELLS_HTML_ZH = """
<h2 style="margin-top:0">单元格与分割</h2>

<h3>网格模式</h3>
<p>默认情况下，画布为简单的行列网格。
每行可以有不同的列数和高度比例（在检查器中选中行后设置）。</p>

<h3>分割单元格</h3>
<ol>
  <li>在画布上<b>右键单击</b>一个单元格。</li>
  <li>在插入菜单中选择<b>分割/子单元格</b>。</li>
  <li>在父单元格内生成两个子单元格。</li>
  <li>可继续分割子单元格，层级无限制。</li>
</ol>

<h3>调整分割比例</h3>
<p>选中子单元格后，在检查器的<b>子单元格</b>部分中拖动比例滑块或输入数值进行调整。</p>
<p>也可以直接在画布上拖动子单元格之间的<b>分隔条</b>。</p>

<h3>自由布局模式</h3>
<ul>
  <li>通过 <b>布局 → 切换至自由布局模式</b> 解锁自由定位。</li>
  <li>可任意拖动单元格，并在检查器中通过 X、Y、W、H（单位 mm）调整大小。</li>
  <li>使用 <b>置于顶层</b> / <b>置于底层</b>（<code>Ctrl+]</code> / <code>Ctrl+[</code>）控制重叠顺序。</li>
  <li>通过 <b>布局 → 切换至网格模式</b> 切换回网格模式（位置信息将保留）。</li>
</ul>

<h3>插入行/列</h3>
<p>右键单击单元格，选择<b>插入</b>菜单可访问<b>在上方插入行 / 在下方插入行</b>和<b>插入列</b>选项。</p>
"""

_LABELS_HTML_EN = """
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

_LABELS_HTML_ZH = """
<h2 style="margin-top:0">标注与文字</h2>

<h3>自动标注</h3>
<p>按 <code>Ctrl+Shift+L</code> 或 <b>编辑 → 自动标注</b>，自动为所有叶子单元格添加面板标签（a、b、c… 或 A、B、C…）。</p>
<p>标注方案、字体、大小、颜色和位置均在<b>检查器 → 项目设置 → 标注</b>部分设置。</p>

<h3>编辑标注</h3>
<ol>
  <li>点击画布上的标注将其选中。</li>
  <li>检查器将显示<b>标注单元格</b>面板。</li>
  <li>在<b>标注文字</b>字段中直接编辑文本。</li>
  <li>使用<b>应用颜色到全部</b>同步整组的颜色。</li>
</ol>

<h3>添加浮动文字</h3>
<p>通过 <b>编辑 → 添加浮动文字</b> 插入自由浮动的文字项，可拖放到画布任意位置，并在检查器中编辑字体、大小和颜色。</p>

<h3>角标</h3>
<p>选中单元格后，在检查器的<b>角标</b>部分可在四个角（左上、右上、左下、右下）输入简短的注释文字。</p>

<h3>比例尺（显微图像）</h3>
<p>在<b>检查器 → 比例尺</b>中为显微图像启用比例尺，可设置 µm/像素校准值、比例尺长度、颜色和位置。</p>
"""

_EXPORT_HTML_EN = """
<h2 style="margin-top:0">Export</h2>

<h3>Supported Formats</h3>
<ul>
  <li><b>PDF</b> — vector-based; ideal for journal submission. Labels and SVG images remain vector.</li>
  <li><b>TIFF</b> — lossless raster at the DPI you specify (Inspector → Project → DPI).</li>
  <li><b>JPG</b> — compressed raster. Quality is fixed at 95%.</li>
  <li><b>PNG / SVG</b> — web-friendly formats.</li>
</ul>

<h3>Project Bundles (.figpack)</h3>
<p>Standard <code>.figlayout</code> files only save paths to images. If you move your images, the layout breaks.
Use <b>File → Convert to .figpack</b> to create a self-contained archive that includes all source images.
Ideal for sharing with co-authors or archiving projects.</p>

<h3>Export Region</h3>
<p>By default, the whole page is exported. Use <b>Layout → Set Export Region</b> to drag a selection on the canvas.
Only the selected area will be saved in the exported file.</p>

<h3>DPI Setting</h3>
<p>DPI (dots per inch) controls the pixel dimensions of raster exports:</p>
<p style="margin-left:16px"><code>pixels = (size_in_mm / 25.4) × DPI</code></p>
<p>For most journals, <b>300 DPI</b> is sufficient for TIFF/JPG.
PDF export resolution is separate from this setting.</p>

<h3>Tips for Publication</h3>
<ul>
  <li>Keep gap ≥ 1 mm so panels don't touch.</li>
  <li>Use SVG source images when possible — they stay crisp in PDF exports.</li>
  <li>Set DPI ≥ 300 for raster exports submitted to journals.</li>
</ul>
"""

_EXPORT_HTML_ZH = """
<h2 style="margin-top:0">导出</h2>

<h3>支持的格式</h3>
<ul>
  <li><b>PDF</b> — 基于矢量；适合期刊投稿，标注和 SVG 图片保持矢量质量。</li>
  <li><b>TIFF</b> — 无损光栅，分辨率由检查器 → 项目 → DPI 指定。</li>
  <li><b>JPG</b> — 压缩光栅，质量固定为 95%。</li>
  <li><b>PNG / SVG</b> — 适合网页使用的格式。</li>
</ul>

<h3>项目包 (.figpack)</h3>
<p>标准的 <code>.figlayout</code> 文件仅保存图片路径。若移动图片，布局将失效。
使用<b>文件 → 转换为 .figpack</b> 可创建一个包含所有源图片的自持归档包。
非常适合与合作者分享或归档项目。</p>

<h3>导出区域</h3>
<p>默认导出整个页面。使用<b>布局 → 设置导出区域</b>在画布上拖拽选择，仅所选区域会被保存在导出文件中。</p>

<h3>DPI 设置</h3>
<p>DPI（每英寸像素数）决定光栅导出的像素尺寸：</p>
<p style="margin-left:16px"><code>像素数 = (尺寸_mm / 25.4) × DPI</code></p>
<p>大多数期刊要求 TIFF/JPG 导出时 <b>300 DPI</b> 即可。PDF 导出分辨率与此设置无关。</p>

<h3>出版建议</h3>
<ul>
  <li>间距保持 ≥ 1 mm，避免面板互相接触。</li>
  <li>尽量使用 SVG 源图片 — PDF 导出时保持清晰。</li>
  <li>向期刊投稿时，光栅导出 DPI 应 ≥ 300。</li>
</ul>
"""

_ADVANCED_HTML_EN = """
<h2 style="margin-top:0">Advanced Features</h2>

<h3>SVG Text Groups</h3>
<p>When using SVG cells, you can batch-edit text elements. 
Go to <b>View → SVG Text Groups…</b> to open the inspector. 
Group text elements across different cells to sync their font size and content.</p>

<h3>Size Groups</h3>
<p>Synchronize the dimensions of multiple cells or PiPs. 
In the Inspector, assign a <b>Size Group</b> to selected items. 
Changing the width or height of one member will automatically update all others in the group.</p>

<h3>Layer Tree</h3>
<p>Use the <b>Layers</b> panel on the left to see the hierarchical structure of your project. 
You can select, hide, or reorder elements easily from here.</p>
"""

_ADVANCED_HTML_ZH = """
<h2 style="margin-top:0">进阶功能</h2>

<h3>SVG 文字组</h3>
<p>使用 SVG 单元格时，您可以批量编辑文字元素。
通过 <b>视图 → SVG 文字组…</b> 打开检查器。跨不同单元格对文字元素进行分组，以同步它们的字号和内容。</p>

<h3>尺寸组</h3>
<p>同步多个单元格或子图的尺寸。
在检查器中为选中项分配<b>尺寸组</b>。更改其中一个成员的宽度或高度将自动更新组内所有其他成员。</p>

<h3>图层树</h3>
<p>使用左侧的<b>图层</b>面板查看项目的层级结构。
您可以从这里轻松地选择、隐藏或重新排序元素。</p>
"""


def _html(en: str, zh: str) -> str:
    return zh if current_language() == "zh" else en


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
        tabs.addTab(_scroll_page(_html(_GETTING_STARTED_HTML_EN, _GETTING_STARTED_HTML_ZH)), tr("help_tab_start"))
        tabs.addTab(_scroll_page(_html(_IMAGES_HTML_EN, _IMAGES_HTML_ZH)),                  tr("help_tab_images"))
        tabs.addTab(_scroll_page(_html(_CELLS_HTML_EN, _CELLS_HTML_ZH)),                    tr("help_tab_cells"))
        tabs.addTab(_scroll_page(_html(_LABELS_HTML_EN, _LABELS_HTML_ZH)),                  tr("help_tab_labels"))
        tabs.addTab(_scroll_page(_html(_EXPORT_HTML_EN, _EXPORT_HTML_ZH)),                  tr("help_tab_export"))
        tabs.addTab(_scroll_page(_html(_ADVANCED_HTML_EN, _ADVANCED_HTML_ZH)),              tr("help_tab_advanced"))
        tabs.addTab(_shortcuts_page(),                                                       tr("help_tab_shortcuts"))
        root.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 0)
        btn_row.addStretch()
        close_btn = QPushButton(tr("help_close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)
