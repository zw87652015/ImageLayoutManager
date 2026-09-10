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
    ("Ctrl + Shift + S",  "Save As…"),
    ("Ctrl + T",          "New tab"),
    ("Ctrl + W",          "Close current tab"),
    ("Ctrl + Z",          "Undo"),
    ("Ctrl + Y",          "Redo (Windows)"),
    ("Ctrl + Shift + L",  "Auto In-Cell Labels"),
    ("Ctrl + Shift + K",  "Auto Above-Cell Labels"),
    ("Ctrl + Shift + A",  "Auto Layout"),
    ("Ctrl + Shift + P",  "Toggle export preview"),
    ("Ctrl + ]",          "Bring selected cell to front"),
    ("Ctrl + [",          "Send selected cell to back"),
    ("Ctrl + Delete",     "Remove image from selected cell, not the source file"),
    ("Delete",            "Delete selected text or shared label"),
    ("F5",                "Reload images from disk"),
    ("Wheel",             "Scroll canvas"),
    ("Ctrl + Wheel",      "Zoom canvas around the pointer"),
    ("Middle drag",       "Pan canvas; Space + drag also works"),
    ("Ctrl + + / -",      "Zoom canvas in / out (canvas focused)"),
    ("Ctrl + 0",          "Fit page in view (canvas focused)"),
    ("Ctrl + 1",          "Set canvas zoom to 100% (canvas focused)"),
    ("Arrow keys",        "Navigate to a neighbouring cell (canvas focused)"),
    ("Ctrl + Arrow",      "Swap with a neighbouring cell (canvas focused)"),
    ("Tab / Shift + Tab", "Next / previous cell (canvas focused)"),
    ("Esc",               "Cancel an active drag/crop or clear selection"),
    ("Ctrl + Alt + + / -", "Increase / decrease interface font size"),
    ("Ctrl + Alt + 0",    "Reset interface font size"),
    ("Ctrl + Shift + T",  "Switch light / dark theme"),
    ("Ctrl + Shift + G",  "Switch interface language"),
    ("Ctrl + \\",         "Show / hide Layers"),
    ("Ctrl + ,",          "Preferences…"),
    ("F1",                "User Guide…"),
]

_SHORTCUTS_ZH = [
    ("Ctrl + N",          "新建工程"),
    ("Ctrl + O",          "打开工程"),
    ("Ctrl + S",          "保存工程"),
    ("Ctrl + Shift + S",  "另存为…"),
    ("Ctrl + T",          "新建标签页"),
    ("Ctrl + W",          "关闭当前标签页"),
    ("Ctrl + Z",          "撤销"),
    ("Ctrl + Y",          "重做（Windows）"),
    ("Ctrl + Shift + L",  "自动图内标注"),
    ("Ctrl + Shift + K",  "自动图外标注"),
    ("Ctrl + Shift + A",  "自动布局"),
    ("Ctrl + Shift + P",  "切换导出预览"),
    ("Ctrl + ]",          "将选中单元格置于顶层"),
    ("Ctrl + [",          "将选中单元格置于底层"),
    ("Ctrl + Delete",     "移除选中单元格中的图片，不删除源文件"),
    ("Delete",            "删除选中的文字或共享标注"),
    ("F5",                "从磁盘重新加载图片"),
    ("Wheel",             "滚轮：滚动画布"),
    ("Ctrl + Wheel",      "Ctrl + 滚轮：以指针位置为中心缩放画布"),
    ("Middle drag",       "中键拖动：平移画布；也可按住空格拖动"),
    ("Ctrl + + / -",      "放大／缩小画布（画布获得焦点时）"),
    ("Ctrl + 0",          "将页面适配到视图（画布获得焦点时）"),
    ("Ctrl + 1",          "画布缩放设为 100%（画布获得焦点时）"),
    ("Arrow keys",        "方向键：选择相邻单元格（画布获得焦点时）"),
    ("Ctrl + Arrow",      "Ctrl + 方向键：与相邻单元格交换（画布获得焦点时）"),
    ("Tab / Shift + Tab", "选择下一个／上一个单元格（画布获得焦点时）"),
    ("Esc",               "取消当前拖动／裁剪，或清除选择"),
    ("Ctrl + Alt + + / -", "放大／缩小界面字体"),
    ("Ctrl + Alt + 0",    "重置界面字体大小"),
    ("Ctrl + Shift + T",  "切换浅色／深色主题"),
    ("Ctrl + Shift + G",  "切换界面语言"),
    ("Ctrl + \\",         "显示／隐藏图层面板"),
    ("Ctrl + ,",          "偏好设置…"),
    ("F1",                "使用指南…"),
]


def _shortcuts_page() -> QWidget:
    shortcuts = _SHORTCUTS_ZH if current_language() == "zh" else _SHORTCUTS_EN

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(16, 16, 16, 16)
    hint = QLabel(tr("help_shortcuts_hint"))
    hint.setWordWrap(True)
    layout.addWidget(hint)

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

    table.resizeRowsToContents()
    layout.addWidget(table)
    return widget


_GETTING_STARTED_HTML_EN = """
<h2 style="margin-top:0">Your First Figure</h2>
<ol>
  <li>At the welcome window, choose <b>New Project</b> to reveal the initial 2×2 grid,
      or <b>Open Project…</b> to resume work. Recent projects are listed below the buttons.</li>
  <li>In the main window, use <b>File → Open Images as Grid…</b>, or drop several image files
      or a folder onto the window. ILM chooses a grid and runs Auto Layout.</li>
  <li>Set the final page width and height in millimetres, margins, gap, and export DPI in
      the Inspector's <b>Global Project Settings</b>.</li>
  <li>Arrange the panels, add labels, and use the <b>Text Sizes</b> guide tab to match text across panels.</li>
  <li>Save the editable project, then use the toolbar's <b>Export</b> menu to create a figure file.</li>
</ol>
<p><b>Save first:</b> opening images as a new grid replaces the current tab's layout.
Use a new tab (<code>Ctrl+T</code>) if you want to keep both layouts open.</p>
<h3>Finding Your Way Around</h3>
<ul>
  <li><b>Layers, left:</b> select cells and inspect the layout hierarchy.</li>
  <li><b>Canvas, centre:</b> arrange the figure. Ctrl+wheel zooms; middle-button or Space+drag pans.</li>
  <li><b>Inspector, right:</b> edit project settings or the properties of the selected item.</li>
</ul>
<p>Canvas zoom and interface font zoom are separate. Neither changes the figure's physical dimensions.</p>
<h3>Open, Save, and Share</h3>
<ul>
  <li>Open <code>.figpack</code>, <code>.figlayout</code>, or supported legacy <code>.json</code> projects
      with <b>File → Open…</b>. You can also drop them onto the welcome window.</li>
  <li><code>.figlayout</code> stores layout settings and source-image references. Keep those images available.</li>
  <li><code>.figpack</code> includes source assets for portable sharing. Use Save As or
      <b>File → Convert to .figpack…</b> to create a bundle.</li>
  <li><code>Ctrl+S</code> saves; <code>Ctrl+Shift+S</code> saves a separate copy.
      An asterisk indicates unsaved changes. An exported image is not an editable project.</li>
</ul>
<p>Supported older projects are upgraded in memory when opened; opening alone does not rewrite the file.
Keep a copy before saving an upgrade. If a project requires a newer version, update ILM rather than changing
its version fields manually.</p>
"""

_GETTING_STARTED_HTML_ZH = """
<h2 style="margin-top:0">制作第一张组合图</h2>
<ol>
  <li>在欢迎窗口选择<b>新建工程</b>，进入初始的 2×2 网格；或选择<b>打开工程…</b>继续工作。
      按钮下方列出了最近打开的工程。</li>
  <li>在主窗口使用<b>文件 → 新建图片网格…</b>，或将多张图片、一个文件夹拖入窗口。
      ILM 会选择网格行列数并执行自动布局。</li>
  <li>在右侧检查器的<b>全局排版设置</b>中，设置最终页面的宽高（毫米）、边距、间距和导出 DPI。</li>
  <li>安排面板、添加标注；如需统一各面板中的文字大小，请阅读<b>文字大小</b>页。</li>
  <li>先保存可编辑工程，再通过工具栏的<b>导出</b>菜单生成图像文件。</li>
</ol>
<p><b>先保存：</b>新建图片网格会替换当前标签页的布局。若要同时保留两个布局，请先新建标签页
（<code>Ctrl+T</code>）。</p>
<h3>认识界面</h3>
<ul>
  <li><b>左侧图层：</b>选择单元格、查看布局层级。</li>
  <li><b>中间画布：</b>安排组合图。Ctrl+滚轮缩放；中键拖动或空格+拖动平移。</li>
  <li><b>右侧检查器：</b>编辑全局设置或所选对象的属性。</li>
</ul>
<p>画布缩放与界面字体缩放相互独立，都不会改变图的实际物理尺寸。</p>
<h3>打开、保存与分享</h3>
<ul>
  <li>通过<b>文件 → 打开…</b>打开 <code>.figpack</code>、<code>.figlayout</code>
      或支持的旧版 <code>.json</code> 工程；也可将工程拖到欢迎窗口。</li>
  <li><code>.figlayout</code> 保存布局设置和源图片引用，请保留可访问的源图片。</li>
  <li><code>.figpack</code> 将源素材包含在包内，适合分享。可通过“另存为”或
      <b>文件 → 打包为 .figpack 项目…</b>创建。</li>
  <li><code>Ctrl+S</code> 保存；<code>Ctrl+Shift+S</code> 另存副本。
      星号表示有未保存的更改。导出的图片不能代替可编辑工程。</li>
</ul>
<p>打开支持的旧工程时，会在内存中执行升级；仅打开不会重写源文件。保存升级前建议保留副本。
若提示工程需要更新版本，请升级 ILM，不要手动修改工程中的版本字段。</p>
"""

_IMAGES_HTML_EN = """
<h2 style="margin-top:0">Import and Prepare Images</h2>
<h3>Choose the Right Import Method</h3>
<ul>
  <li><b>One panel:</b> right-click a cell → <b>Import Image…</b>, or drop one image onto it.</li>
  <li><b>Fill an existing grid:</b> <b>File → Import Images…</b> fills empty cells in layout order.
      Add cells first if there are not enough empty positions.</li>
  <li><b>Create a layout:</b> <b>File → Open Images as Grid…</b>, or drop multiple images/a folder
      onto the main window. Folder imports find supported images in subfolders and ignore other files.</li>
</ul>
<p>Common inputs include PNG, JPEG, TIFF, BMP, GIF, WebP, SVG, and PDF.
The welcome window accepts saved projects, not image folders: choose New Project first.</p>
<h3>Replace, Swap, or Add an Inset</h3>
<p>Dropping one image onto an occupied cell replaces its image, except when you target the inset drop zone.
Dragging an existing cell onto another swaps their images. Use Ctrl+click to select multiple cells;
check the highlighted destination before releasing a drag.</p>
<p>To add an external inset, drag a single image over a filled panel and release over its inset drop zone.
Select the inset to move it or edit <b>Inset Image Properties</b> in the Inspector.
Right-click the inset for resize and other inset operations.</p>
<h3>Fit, Crop, and Rotate</h3>
<ul>
  <li><b>Scale to Fit:</b> keeps the entire image visible, with space left over if the proportions differ.</li>
  <li><b>Crop to Fill:</b> fills the cell while maintaining image proportions; edges may be hidden.</li>
  <li><b>Crop Image:</b> right-click a panel, drag crop handles, then press Enter to apply or Esc to cancel.
      Shift+drag a corner locks the crop aspect ratio. Use <b>Reset Crop</b> to remove cropping.</li>
  <li>Use the cell's rotation controls for quarter-turn rotation.</li>
</ul>
<p>These layout adjustments do not overwrite the source image. Check that cropping has not hidden relevant
labels, scale bars, or scientific content.</p>
<h3>After Editing a Source Elsewhere</h3>
<p>Press <b>F5</b> or choose <b>File → Reload Images</b>.
Automatic reload can be enabled under <b>Edit → Preferences… → Files &amp; Editing</b>.
Apply the preference before returning to your figure.</p>
"""

_IMAGES_HTML_ZH = """
<h2 style="margin-top:0">导入与准备图片</h2>
<h3>选择合适的导入方式</h3>
<ul>
  <li><b>单个面板：</b>右键单元格 → <b>导入图片…</b>，或将一张图片拖到该单元格。</li>
  <li><b>填充已有网格：</b><b>文件 → 导入图片…</b>按布局顺序填充空单元格。
      若空位不足，请先添加单元格。</li>
  <li><b>新建布局：</b><b>文件 → 新建图片网格…</b>，或将多张图片／文件夹拖入主窗口。
      文件夹导入会查找子文件夹中的支持图片，并忽略其他文件。</li>
</ul>
<p>常见输入包括 PNG、JPEG、TIFF、BMP、GIF、WebP、SVG 和 PDF。
欢迎窗口只接受已保存的工程，不接受图片文件夹；请先选择“新建工程”。</p>
<h3>替换、交换与插图</h3>
<p>将单张图片拖到已占用的单元格通常会替换图片；拖到插图投放区则会添加插图。
将画布上的一个单元格拖到另一个上可交换图片。Ctrl+点击可多选，松开拖动前请确认高亮的目标位置。</p>
<p>添加外部插图时，将单张图片拖到已有图片的面板上，在插图投放区松开。
选中插图后可移动，或在检查器的<b>插图属性</b>中调整。右键插图可进入调整大小等操作。</p>
<h3>适应、裁剪与旋转</h3>
<ul>
  <li><b>适应 (Scale to Fit)：</b>完整显示图片；比例不一致时保留空白。</li>
  <li><b>填充 (Crop to Fill)：</b>保持图片比例并填满单元格，边缘可能被隐藏。</li>
  <li><b>裁剪图片：</b>右键面板后选择此项，拖动裁剪手柄；Enter 应用，Esc 取消。
      Shift+拖动角手柄可锁定裁剪比例。<b>重置裁剪</b>可移除裁剪。</li>
  <li>使用单元格的旋转控件进行 90 度步进旋转。</li>
</ul>
<p>这些布局调整不会覆盖源图片。请检查裁剪是否隐藏了重要标注、比例尺或科学内容。</p>
<h3>在其他软件中修改源图片后</h3>
<p>按 <b>F5</b>，或选择<b>文件 → 重新加载图片</b>。
可在<b>编辑 → 偏好设置… → 文件与编辑</b>中启用自动重载；返回画布前请先应用设置。</p>
"""

_CELLS_HTML_EN = """
<h2 style="margin-top:0">Arrange Panels</h2>
<h3>Grid and Sub-Cells</h3>
<p>Use rows and columns for regular figures. Each row can have its own column count and height ratio.
Select a row or cell to edit its properties in the Inspector.</p>
<ul>
  <li>Use the canvas <b>+</b> controls or right-click → <b>Insert</b> to add rows and columns.</li>
  <li>For mixed-size panels, right-click → <b>Insert → Add Sub-Cell / Subdivide</b>.
      Add a sibling above, below, left, or right; a leaf cell can also be split into several rows or columns.</li>
  <li>Drag dividers or use <b>Sub-Cell Layout</b> in the Inspector to adjust the split.</li>
  <li>Use the right-click <b>Delete</b> menu to remove layout cells. This is different from
      <code>Ctrl+Delete</code>, which removes the image but keeps the cell.</li>
</ul>
<h3>Auto Layout</h3>
<p><b>Edit → Auto Layout</b> (<code>Ctrl+Shift+A</code>) adjusts the arrangement to the images.
Check the result and undo if it is not appropriate. Set the page dimensions and margins before final fine-tuning.</p>
<h3>Freeform Positioning</h3>
<p><b>Layout → Convert Grid → Freeform</b> starts from the current grid geometry and enables direct positioning.
Use the Inspector's X, Y, width, and height fields for precise dimensions in millimetres.
<b>Bring to Front</b> and <b>Send to Back</b> control overlapping cells.</p>
<p><b>Layout → Switch to Grid Mode</b> returns to grid-based positioning; do not expect arbitrary freeform
positions to remain visually unchanged. Save a copy before major rearrangements.</p>
<h3>Selection and Consistent Sizes</h3>
<p>Click a cell, Ctrl+click to extend the selection, or drag a selection rectangle from empty canvas space.
Arrow keys navigate between cells when the canvas has focus; they do not nudge a panel.
Use a shared <b>Sync Size Group</b> in the Inspector when items need linked dimensions.</p>
"""

_CELLS_HTML_ZH = """
<h2 style="margin-top:0">安排面板</h2>
<h3>网格与子单元格</h3>
<p>规则组合图可使用行列网格。每行可设置不同的列数和高度比例。
选中行或单元格后，在检查器中修改对应属性。</p>
<ul>
  <li>使用画布上的 <b>+</b> 控件，或右键 → <b>插入</b>，添加行列。</li>
  <li>混合尺寸面板可通过右键 → <b>插入 → 细分为子单元格</b>实现。
      在上下左右添加同级单元格；叶子单元格还可一次拆分为多行或多列。</li>
  <li>拖动分隔条，或通过检查器的<b>子单元格排版</b>调整分割。</li>
  <li>右键<b>删除</b>菜单用于删除布局单元格；<code>Ctrl+Delete</code> 则仅移除图片，保留单元格。</li>
</ul>
<h3>自动布局</h3>
<p><b>编辑 → 自动布局</b>（<code>Ctrl+Shift+A</code>）根据图片调整排布。
请检查结果，不合适时可撤销。建议先确定页面尺寸和边距，再做最终微调。</p>
<h3>自由定位</h3>
<p><b>布局 → 网格转自由布局</b>保留当前网格几何位置作为起点，并允许自由定位。
使用检查器中的 X、Y、宽度和高度字段，以毫米为单位精确调整。
<b>置于顶层</b>和<b>置于底层</b>控制单元格的重叠顺序。</p>
<p><b>布局 → 切换至网格模式</b>会恢复网格定位；任意自由布局的位置不一定保持视觉不变。
重大调整前建议另存副本。</p>
<h3>选择与尺寸一致性</h3>
<p>点击选择单元格，Ctrl+点击扩展选择，或从画布空白处拖动框选。
画布获得焦点时，方向键用于在单元格之间导航，不用于微移面板。
需要联动尺寸时，可在检查器中使用相同的<b>尺寸同步组</b>。</p>
"""

_LABELS_HTML_EN = """
<h2 style="margin-top:0">Labels and Annotations</h2>
<h3>Panel Numbers</h3>
<p>Use <b>Edit → Auto In-Cell Labels</b> (<code>Ctrl+Shift+L</code>) to place a, b, c… labels inside panels.
<b>Auto Above-Cell Labels</b> (<code>Ctrl+Shift+K</code>) puts them in a separate band above the images.
<b>Layout → All Labels Placement</b> provides other placement choices.</p>
<p>Set label appearance and placement rules in the Inspector. Select a label to edit its text and style;
use the available <b>Apply to All</b> controls only when you intend a wider change.</p>
<h3>Shared Row and Column Titles</h3>
<ol>
  <li>Select the cells that should share a title.</li>
  <li>Choose <b>Edit → Add Shared Label for Selection</b>, then choose a side.</li>
  <li>Edit the title in the Inspector or double-click it. Drag its band to reposition it;
      select it and press Delete to remove it.</li>
</ol>
<p>A shared label occupies its own band. It is not a text-size group: shared labels add annotations,
whereas text-size groups adjust text already inside source panels.</p>
<h3>Free Text and Corner Labels</h3>
<p><b>Edit → Add Text Box</b> adds a movable annotation. Adjust its font, point size, and colour in the Inspector.
Cell corner labels provide short annotations anchored to an image corner.</p>
<h3>Scale Bars</h3>
<p>Enable a scale bar from the cell's context menu or Inspector. Enter the correct source-image calibration
in µm per pixel, then choose the bar length and appearance. Obtain calibration from the acquisition data;
do not infer it from screen zoom. Verify the scale bar after cropping, resizing, and export.</p>
"""

_LABELS_HTML_ZH = """
<h2 style="margin-top:0">标注与注释</h2>
<h3>面板编号</h3>
<p><b>编辑 → 自动图内标注</b>（<code>Ctrl+Shift+L</code>）将 a、b、c… 放在面板内部。
<b>自动图外标注</b>（<code>Ctrl+Shift+K</code>）将编号放在图片上方的独立标注带中。
<b>布局 → 全部标注位置</b>提供其他放置方式。</p>
<p>在检查器中设置标注样式与位置规则。选中标注可修改文字和样式；
仅在确实需要批量修改时，使用相应的<b>应用到全部</b>控件。</p>
<h3>共享行列标题</h3>
<ol>
  <li>选中需要共用标题的单元格。</li>
  <li>选择<b>编辑 → 为所选添加共享标注</b>，再选择标注所在的一侧。</li>
  <li>在检查器中或双击标题编辑文字；拖动标注带可调整位置，选中后按 Delete 删除。</li>
</ol>
<p>共享标注占据独立的标注带。它与文字大小组不同：共享标注添加新注释，文字大小组则调整源面板中已有的文字。</p>
<h3>自由文字与角标</h3>
<p><b>编辑 → 添加文本框</b>用于创建可移动的注释，在检查器中调整字体、磅值和颜色。
单元格角标用于将简短注释固定在图片的角落。</p>
<h3>比例尺</h3>
<p>在单元格右键菜单或检查器中启用比例尺。输入正确的源图像校准值（µm/像素），再设置长度和外观。
校准值应来自采集数据，不可根据屏幕缩放推断。裁剪、调整尺寸和导出后，均应核对比例尺。</p>
"""

_TYPOGRAPHY_HTML_EN = """
<h2 style="margin-top:0">Match Text Sizes Across Panels</h2>
<p>Text-size groups are shared across the <b>whole project</b>, including SVG and raster panels.
A group's size is a target in <b>points in the final figure</b>, not source pixels or screen pixels.
ILM compensates for each panel's scale. Use separate groups for axis labels, tick labels, and other roles.</p>
<h3>SVG Panels</h3>
<ol>
  <li>Right-click an SVG image cell → <b>Edit SVG Text Groups…</b>.</li>
  <li>Select text elements from the list; use Ctrl or Shift for multiple selections.</li>
  <li>Click <b>Add Group</b>, give it a meaningful name, and set its point size.</li>
  <li>Choose the group in <b>Assign to</b>, then click <b>Assign selected to group</b>.</li>
  <li>Open another panel's inspector and assign matching text to the same group.
      Editing the group's size updates its members throughout the project.</li>
</ol>
<p>Only real SVG text elements can be grouped. Text converted to vector outlines is not editable text.
Grouping changes font size, not the wording of axis labels or measured values.</p>
<h3>Raster Panels: PNG, TIFF, JPEG, and Similar Images</h3>
<ol>
  <li>Open <b>Edit → Preferences… → Text Detection</b>. RapidOCR is the built-in default.
      Use <b>Check availability</b>, then Apply any changes. Tesseract requires a separate installation;
      a custom command is an advanced alternative.</li>
  <li>Right-click a raster image cell → <b>Match Raster Text Size…</b>, then <b>Detect text (OCR)</b>.
      Detection runs in the background; Cancel stops waiting for that result.</li>
  <li>Review the detected regions in the list and preview. Selecting a region is different from
      ticking it: the checkbox enables resizing.</li>
  <li>Create or choose a group, select the regions, and assign them to it. Set the group's size in pt.
      Adjust the anchor or vertical-text setting where needed.</li>
  <li>Use <b>Show original</b> to compare. Inspect each changed label and its surroundings at a useful zoom.</li>
</ol>
<p>OCR locates text; recognised words are a reference, not replacement lettering.
ILM scales extracted foreground pixels rather than retyping the text, so enlarging low-resolution lettering
cannot recover missing detail. Raster font-size estimates are approximate.</p>
<h3>Review Warnings and Keep a Reversible Workflow</h3>
<ul>
  <li>A review warning is advisory, not a ban. You may enable a flagged region after checking it.
      Actual resizing may still be skipped if it would leave the image or overlap other content; read the status.</li>
  <li>Untick a raster region or remove its group assignment to stop its group-based resizing.
      Deleting a group affects all its members, not just the current panel.</li>
  <li>Text-group edits take effect immediately; closing the inspector is not Cancel.
      Save a project copy before extensive changes rather than relying on undo for every text-inspector edit.</li>
  <li>The source files are not overwritten. Raster resizing does change pixels in the composed figure:
      check that nearby data, ticks, symbols, and lines remain correct, and follow your journal's image policy.</li>
</ul>
<p><b>Export check:</b> inspect the actual exported figure, not just the preview.
SVG group text can currently differ from its target point size in PDF output; verify important font sizes
before submission.</p>
"""

_TYPOGRAPHY_HTML_ZH = """
<h2 style="margin-top:0">统一各面板的文字大小</h2>
<p>文字大小组在<b>整个工程</b>中共享，可包含 SVG 和位图面板。
组字号是<b>最终图中的磅值（pt）</b>，不是源图片像素或屏幕像素；ILM 会补偿各面板的缩放比例。
建议为坐标轴标题、刻度文字等不同用途分别建组。</p>
<h3>SVG 面板</h3>
<ol>
  <li>右键 SVG 图片单元格 → <b>编辑 SVG 文字组…</b>。</li>
  <li>在列表中选择文字元素，Ctrl 或 Shift 可多选。</li>
  <li>点击<b>添加组</b>，输入便于识别的名称，设置磅值。</li>
  <li>在<b>分配到</b>中选择组，再点击<b>将所选分配到组</b>。</li>
  <li>打开另一面板的文字检查器，将同类文字分配到同一组。
      修改该组字号会更新整个工程中的组成员。</li>
</ol>
<p>只有真正的 SVG 文字元素可分组，已转为矢量轮廓的文字不能作为文字编辑。
分组调整字号，不修改坐标轴标题或测量数值的内容。</p>
<h3>位图面板：PNG、TIFF、JPEG 等</h3>
<ol>
  <li>打开<b>编辑 → 偏好设置… → 文字检测</b>。默认内置 RapidOCR。
      点击<b>检查可用性</b>，修改后应用设置。Tesseract 需要另行安装；自定义命令适合高级用户。</li>
  <li>右键位图单元格 → <b>匹配位图文字大小…</b>，再点击<b>检测文字（OCR）</b>。
      检测在后台进行，“取消”可停止等待该次结果。</li>
  <li>在列表和预览中检查检测区域。选中区域与勾选区域不同：勾选才会启用缩放。</li>
  <li>新建或选择组，选中区域并分配到组，设置组字号（pt）。按需调整锚点或竖排文字选项。</li>
  <li>通过<b>显示原图</b>进行对比，在合适的缩放下检查每处文字及周边内容。</li>
</ol>
<p>OCR 用于定位文字；识别结果仅供参考，不会作为替换文本。
ILM 缩放提取的前景像素，而非重新打字，因此放大低分辨率文字不能恢复缺失的细节。位图字号估计是近似值。</p>
<h3>处理提示并保留可恢复的工作方式</h3>
<ul>
  <li>审查提示仅供参考，不是禁止操作。检查后可启用被标记的区域。
      若缩放会超出图片或覆盖其他内容，实际处理仍可能跳过，请查看状态说明。</li>
  <li>取消勾选位图区域或移除其分组，可停止对应的组缩放。
      删除组会影响所有成员，而不仅是当前面板。</li>
  <li>文字组修改即时生效，关闭检查器不等于取消。大量修改前请另存工程副本，
      不要依赖撤销来恢复所有文字检查器操作。</li>
  <li>源文件不会被覆盖。但位图文字缩放会改变组合图中的像素，
      请核对邻近数据、刻度、符号和线条，并遵守期刊的图像处理要求。</li>
</ul>
<p><b>导出检查：</b>请检查实际导出文件，而不只是预览。
目前 PDF 输出中的 SVG 文字组字号可能与目标磅值不同，投稿前应核对重要文字的实际大小。</p>
"""

_EXPORT_HTML_EN = """
<h2 style="margin-top:0">Export and Check the Final Figure</h2>
<h3>Choose a Format</h3>
<p>Use the toolbar's <b>Export</b> menu or the individual export commands in <b>File</b>.</p>
<ul>
  <li><b>PDF / SVG:</b> can preserve vector elements such as supported SVG content and annotations.
      Raster source panels remain raster; these formats do not turn pixels into vectors.</li>
  <li><b>TIFF / PNG:</b> lossless raster output, useful when a submission system requests images.</li>
  <li><b>JPG:</b> lossy output; compression can introduce artifacts around lettering and fine lines.</li>
</ul>
<h3>Page Size, DPI, and Export Region</h3>
<p>Set the physical page size and DPI in the Inspector. For raster output:</p>
<p><code>pixels ≈ (size in mm / 25.4) × DPI</code></p>
<p>Increasing DPI does not recover detail missing from a source image. Follow the journal's requirements
for photographs, line art, and mixed figures instead of assuming one DPI suits all cases.
Vector geometry is resolution-independent, but raster panels and rasterized effects are not.</p>
<p><b>Layout → Set Export Region</b> lets you drag a region on the page; Esc cancels the selection gesture.
<b>Clear Export Region</b> restores whole-page output. Check for a saved export region if an export
unexpectedly omits part of the page.</p>
<h3>Before Submission</h3>
<ol>
  <li>Save the editable project. Use a <code>.figpack</code> copy when sharing source assets with collaborators.</li>
  <li>Toggle export preview (<code>Ctrl+Shift+P</code>) to hide editing aids and inspect the composition.</li>
  <li>Open the exported file in a separate viewer. Check page size, crop, panel order, labels,
      font sizes, scale bars, and raster text adjustments at the final intended figure size.</li>
  <li>Keep the original data and images. Exporting or bundling is not a substitute for a research-data backup.</li>
</ol>
<p>Interface motion does not animate exported content. The export uses the project's committed layout,
not an intermediate visual transition.</p>
"""

_EXPORT_HTML_ZH = """
<h2 style="margin-top:0">导出与最终检查</h2>
<h3>选择格式</h3>
<p>使用工具栏的<b>导出</b>菜单，或<b>文件</b>菜单中的各项导出命令。</p>
<ul>
  <li><b>PDF / SVG：</b>可保留支持的 SVG 内容、标注等矢量元素。
      位图源面板仍是位图，这些格式不会把像素变成矢量。</li>
  <li><b>TIFF / PNG：</b>无损位图输出，适用于投稿系统要求图片文件的情况。</li>
  <li><b>JPG：</b>有损输出，压缩可能在文字和细线周围产生伪影。</li>
</ul>
<h3>页面尺寸、DPI 与导出区域</h3>
<p>在检查器中设置物理页面尺寸和 DPI。位图输出的像素数近似为：</p>
<p><code>像素数 ≈ (尺寸毫米 / 25.4) × DPI</code></p>
<p>提高 DPI 不能恢复源图像缺失的细节。请分别遵循期刊对照片、线图和混合图的要求，
不要假设同一 DPI 适合所有图。矢量几何不依赖分辨率，但位图面板和栅格化效果仍受分辨率限制。</p>
<p><b>布局 → 设置导出区域</b>允许在页面上拖选区域；Esc 取消本次选择操作。
<b>清除导出区域</b>恢复整页输出。若导出意外缺少页面的一部分，请检查是否保存了导出区域。</p>
<h3>投稿前检查</h3>
<ol>
  <li>保存可编辑工程。需要与合作者共享源素材时，使用 <code>.figpack</code> 副本。</li>
  <li>切换导出预览（<code>Ctrl+Shift+P</code>），隐藏编辑辅助元素并检查构图。</li>
  <li>在独立查看器中打开导出文件，按最终使用尺寸核对页面大小、裁剪、面板顺序、标注、字号、
      比例尺及位图文字调整。</li>
  <li>保留原始数据和图片。导出文件或工程包不能代替研究数据备份。</li>
</ol>
<p>界面动效不会进入导出内容。导出使用工程已提交的布局，而不是视觉过渡中的中间状态。</p>
"""

_ADVANCED_HTML_EN = """
<h2 style="margin-top:0">Preferences and Workflow</h2>
<h3>Apply, OK, and Cancel</h3>
<p>Open <b>Edit → Preferences…</b> (<code>Ctrl+,</code>).
Changing a setting stages it: <b>Apply</b> activates and saves it while keeping the dialog open;
<b>OK</b> applies and closes; <b>Cancel</b> discards only changes made since the last Apply.
Look for <b>Settings applied</b> as confirmation.</p>
<h3>Comfort Without Changing the Figure</h3>
<ul>
  <li><b>General:</b> select language, theme, and interface motion.
      Standard uses subtle transitions and respects Windows' reduced-animation setting;
      Reduced minimizes movement; Off updates immediately.</li>
  <li><b>View → Zoom UI In / Out:</b> changes interface font size, not figure text.
      Ctrl+Alt+0 resets it. Ctrl+0 on the canvas fits the page instead.</li>
  <li><b>Files &amp; Editing:</b> choose the default save format, export destination, and image auto-reload.</li>
  <li><b>Text Detection:</b> select and check the OCR backend for raster text matching.</li>
</ul>
<h3>Recovery and Bundles</h3>
<p>Autosave creates recovery snapshots, not a replacement for explicit Save. If recovery is offered after
an unexpected exit, review the recovered figure and save it to a known location.</p>
<p>Opened bundles use temporary working copies. Configure cache location and original-source watching in
<b>Bundles (.figpack)</b>. Avoid editing files in the cache directly; retain the saved bundle and originals.</p>
<h3>When Something Looks Wrong</h3>
<ul>
  <li><b>Missing panel:</b> check the source path, reimport the image, or obtain a complete bundle.</li>
  <li><b>Text-size matching unavailable:</b> check the image type and the OCR backend in Preferences,
      then Apply. SVG text converted to outlines cannot appear in the editable-text list.</li>
  <li><b>Unexpected appearance:</b> check crop, fit mode, group membership, and region enable state.
      Compare with the original and inspect the final export.</li>
  <li><b>Shortcut not acting on the canvas:</b> click the canvas first; a focused text field uses keys for editing.</li>
</ul>
<h3>Optional Automation</h3>
<p><b>Tools → MCP Setup Guide…</b> explains agent integration. Enable the server only when you intend to
use an automation client. Save a copy before automated edits and review the resulting figure.</p>
"""

_ADVANCED_HTML_ZH = """
<h2 style="margin-top:0">偏好设置与工作流程</h2>
<h3>应用、确定与取消</h3>
<p>打开<b>编辑 → 偏好设置…</b>（<code>Ctrl+,</code>）。修改控件只是暂存设置：
<b>应用</b>使设置生效并保存，保持对话框打开；<b>确定</b>应用后关闭；
<b>取消</b>仅放弃上一次应用之后的修改。出现<b>设置已应用</b>即表示已生效。</p>
<h3>改善操作体验，不改变图的内容</h3>
<ul>
  <li><b>通用：</b>选择语言、主题和界面动效。标准模式使用轻柔过渡，并遵循 Windows 的减少动画设置；
      减少模式尽量减少运动；关闭模式即时更新。</li>
  <li><b>视图 → 界面放大／缩小：</b>调整界面字体，不改变图中文字。
      Ctrl+Alt+0 重置界面缩放；画布中的 Ctrl+0 则是适配页面。</li>
  <li><b>文件与编辑：</b>设置默认保存格式、导出位置及图片自动重载。</li>
  <li><b>文字检测：</b>选择并检查位图文字匹配使用的 OCR 后端。</li>
</ul>
<h3>恢复与工程包</h3>
<p>自动保存创建的是恢复快照，不能代替主动保存。异常退出后若出现恢复提示，
请检查恢复后的图，并保存到明确的位置。</p>
<p>打开工程包时会使用临时工作副本，可在<b>项目包 (.figpack)</b>中配置缓存位置和原始图片监视。
避免直接编辑缓存文件；请保留已保存的工程包和原始素材。</p>
<h3>常见问题</h3>
<ul>
  <li><b>面板图片缺失：</b>检查源路径，重新导入图片，或获取包含完整素材的工程包。</li>
  <li><b>文字匹配不可用：</b>检查图片类型及偏好设置中的 OCR 后端，再应用设置。
      已转为轮廓的 SVG 文字不会出现在可编辑文字列表中。</li>
  <li><b>外观不符合预期：</b>检查裁剪、缩放模式、文字组归属及区域启用状态，
      与原图对比，并核对最终导出文件。</li>
  <li><b>快捷键未作用于画布：</b>先点击画布；文本框获得焦点时，按键用于编辑输入内容。</li>
</ul>
<h3>可选自动化</h3>
<p><b>工具 → MCP 配置指南…</b>介绍智能体集成。仅在需要连接自动化客户端时启用服务。
自动编辑前请另存副本，操作后检查生成的图。</p>
"""


def _html(en: str, zh: str) -> str:
    return zh if current_language() == "zh" else en


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("help_title"))
        self.resize(760, 580)
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
        tabs.addTab(_scroll_page(_html(_TYPOGRAPHY_HTML_EN, _TYPOGRAPHY_HTML_ZH)),          tr("help_tab_typography"))
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
