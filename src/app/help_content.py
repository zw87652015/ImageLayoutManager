"""User Guide content and pure helpers (no Qt imports).

Cards, shortcut groups and tour steps are bilingual (en, zh). Steps use [chips] for keys
and menu paths; details are short facts. See help_redesign_spec.md for the content rules.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpTopic:
    key: str
    icon: str
    title: tuple
    steps: tuple
    details: tuple = ()
    show_me: tuple | None = None
    contexts: tuple = ()
    keywords: tuple = ()


@dataclass(frozen=True)
class TourStep:
    target: tuple
    title: tuple
    caption: tuple


TOPICS = (
    HelpTopic(
        key="first_figure", icon="first_figure",
        title=("Make your first figure", "制作第一张组合图"),
        steps=(
            ("Choose [File → Import Images…] or drop an image on an empty cell.",
             "选择 [文件 → 导入图片…]，或将图片拖到空单元格上。"),
            ("Click empty canvas space to set [Global Project Settings] page size and gap.",
             "点击画布空白处，在检查器中设置页面尺寸和间距。"),
            ("Arrange panels, add labels, then save and export the figure.",
             "排列面板、添加标注，然后保存并导出。"),
        ),
        details=(
            ("Rows hold cells; a row's column count is its number of panels.",
             "行包含单元格；行内列数即面板数量。"),
            ("The Layers panel on the left selects any cell.",
             "左侧的图层面板可选择任意单元格。"),
            ("Page and gap values are millimetres, not screen zoom.",
             "页面和间距数值以毫米为单位，与屏幕缩放无关。"),
        ),
        show_me=("widget", "canvas"),
        contexts=("none",),
        keywords=("start", "new", "begin", "welcome", "入门", "新建", "开始"),
    ),
    HelpTopic(
        key="add_images", icon="add",
        title=("Add images", "添加图片"),
        steps=(
            ("Drop one image on an empty cell, or right-click it → [Import Image…].",
             "将一张图拖到空单元格，或右键 → [导入图片…]。"),
            ("Use [File → Import Images…] to fill empty cells in order.",
             "使用 [文件 → 导入图片…] 按顺序填充空单元格。"),
            ("Use [File → Open Images as Grid…] to build a new layout.",
             "使用 [文件 → 新建图片网格…] 从一批图片建立新布局。"),
        ),
        details=(
            ("Supported: PNG, JPEG, TIFF, BMP, GIF, WebP, SVG and PDF.",
             "支持 PNG、JPEG、TIFF、BMP、GIF、WebP、SVG 和 PDF。"),
            ("Opening images as a grid replaces the current layout; save first.",
             "新建图片网格会替换当前布局，请先保存。"),
            ("Dropping a folder includes its subfolders and skips other files.",
             "拖入文件夹时会包含子文件夹，并忽略其他文件。"),
            ("The welcome window opens saved projects, not image folders.",
             "欢迎窗口只打开已保存的工程，不接受图片文件夹。"),
        ),
        show_me=("action", "_act_import"),
        keywords=("import", "drop", "folder", "文件", "导入", "拖入"),
    ),
    HelpTopic(
        key="swap_replace", icon="swap",
        title=("Swap or replace panels", "交换或替换面板"),
        steps=(
            ("Drop one image on a filled cell to replace its picture.",
             "将图片拖到已有图片的单元格上即可替换。"),
            ("Drag one cell onto another to swap their images.",
             "将一个单元格拖到另一个上，可交换图片。"),
            ("Check the highlighted target before releasing the drag.",
             "松开前请确认高亮的目标位置。"),
        ),
        details=(
            ("Ctrl+click selects several cells at once.",
             "Ctrl+点击可同时选择多个单元格。"),
            ("Drop on the top-right inset zone of a panel to add an inset instead.",
             "拖到面板右上角的插图投放区，则会添加插图。"),
        ),
        show_me=("widget", "canvas"),
        keywords=("replace", "swap", "drag", "替换", "交换"),
    ),
    HelpTopic(
        key="rows_cells", icon="rows",
        title=("Rows & cells", "行与单元格"),
        steps=(
            ("Use the canvas [+] buttons or right-click → [Insert] to add rows and columns.",
             "使用画布上的 [+] 或右键 → [插入]，添加行和列。"),
            ("For mixed-size panels, right-click → [Add Sub-Cell / Subdivide].",
             "混合尺寸面板：右键 → [细分为子单元格]。"),
            ("Drag dividers, or use [Sub-Cell Layout] in the Inspector to adjust splits.",
             "拖动分隔线，或在检查器的 [子单元格排版] 中调整分割。"),
        ),
        details=(
            ("Adding a cell to one row does not add a column to other rows.",
             "给一行添加单元格不会给其他行增加列。"),
            ("Row height ratios share vertical space; they are not millimetres.",
             "行高比例分配纵向空间，不是毫米高度。"),
            ("Right-click → Delete removes layout cells; Ctrl+Delete only removes the image.",
             "右键 → 删除 会移除布局单元格；Ctrl+Delete 只移除图片。"),
        ),
        show_me=("widget", "canvas"),
        contexts=("cell",),
        keywords=("row", "column", "insert", "delete", "subcell", "行", "列", "单元格"),
    ),
    HelpTopic(
        key="auto_layout", icon="auto",
        title=("Auto Layout", "自动布局"),
        steps=(
            ("Press [Ctrl+Shift+A] or the toolbar [Auto Layout] to fit rows to the images.",
             "按 [Ctrl+Shift+A] 或工具栏 [自动布局]，按图片调整行高。"),
            ("Check the result; press [Ctrl+Z] to undo if it is not right.",
             "检查结果；不合适时按 [Ctrl+Z] 撤销。"),
            ("Set page size and margins first, then run auto layout.",
             "先设置页面尺寸和边距，再执行自动布局。"),
        ),
        details=(
            ("Fill Page Width: every row spans the page width, minus the gaps between cells.",
             "铺满页宽：各行铺满页宽，扣除单元格间距。"),
            ("Match Cell Size: rows with fewer cells stay shorter so cells keep the fullest row's size.",
             "统一单元格尺寸：单元格较少的行保持较短，单元格与最满一行同尺寸。"),
            ("Changing Cell Gap re-fits rows and page height in one undo step.",
             "修改单元格间距会重新适配行高和页面高度，并作为一步撤销。"),
        ),
        show_me=("action", "_act_auto_layout"),
        keywords=("fit", "size", "stretch", "fixed", "match", "自动", "布局", "适配", "统一"),
    ),
    HelpTopic(
        key="page_setup", icon="margins",
        title=("Page size, margins & gap", "页面尺寸、边距与间距"),
        steps=(
            ("Click empty canvas space to open [Global Project Settings] in the Inspector.",
             "点击画布空白处，在检查器中打开 [全局排版设置]。"),
            ("Set page width and height, then margins and gap, in millimetres.",
             "以毫米为单位设置页面宽高、边距和间距。"),
            ("With images in a grid, changing the gap re-fits rows and page height.",
             "网格中有图片时，修改间距会重新适配行高和页面高度。"),
        ),
        details=(
            ("The gap is the space between cells; margins sit at the page edge.",
             "间距是单元格之间的距离；边距位于页面边缘。"),
            ("Cell padding is set per cell in Image Cell Properties.",
             "单元格内边距在“图像单元格属性”中逐格设置。"),
        ),
        show_me=("section", "project_group"),
        keywords=("page", "margin", "gap", "mm", "padding", "页面", "边距", "间距", "内边距"),
    ),
    HelpTopic(
        key="crop_fit", icon="crop",
        title=("Crop, fit & rotate", "裁剪、适应与旋转"),
        steps=(
            ("Choose [Scale to Fit] to see the whole image, or [Crop to Fill].",
             "选择 [适应] 显示完整图片，或选择 [填充] 裁切填满。"),
            ("Right-click a panel → [Crop Image], drag the handles, then press Enter.",
             "右键面板 → [裁剪图片]，拖动手柄，然后按 Enter。"),
            ("Use the cell's rotation controls for quarter turns.",
             "使用单元格的旋转控件进行 90° 旋转。"),
        ),
        details=(
            ("Right-click → [Auto-Trim Margins] crops away empty borders around the content.",
             "右键 → [自动裁去空白边] 可裁掉内容周围的空白。"),
            ("Esc cancels a crop; Reset Crop removes cropping.",
             "Esc 取消裁剪；重置裁剪可移除裁剪。"),
            ("Layout adjustments never overwrite the source file.",
             "布局调整不会覆盖源文件。"),
            ("Check that cropping has not hidden labels, scale bars or data.",
             "检查裁剪是否隐藏了标注、比例尺或数据。"),
        ),
        show_me=("widget", "canvas"),
        keywords=("crop", "fit", "rotate", "裁剪", "旋转", "适应", "填充"),
    ),
    HelpTopic(
        key="insets", icon="inset",
        title=("Insets", "插图"),
        steps=(
            ("Drag one image over a filled panel and release on its top-right inset zone.",
             "将图片拖到已有图片的面板上，松开于右上角的插图区。"),
            ("Drag the inset to move it; click it, then drag a handle to resize.",
             "拖动插图即可移动；点击后拖动手柄即可调整大小。"),
            ("Right-click an inset to remove it or reveal its source file.",
             "右键插图可移除，或在文件资源管理器中显示其源文件。"),
        ),
        details=(
            ("Resizing keeps the inset's shape; exact X, Y, W and H are in the Inspector.",
             "调整大小时保持插图比例；精确的 X、Y、宽、高在检查器中。"),
            ("Zoom-type insets can show an origin box on the host image.",
             "放大型插图可在主图上显示源区域框。"),
            ("An inset can carry its own scale bar.",
             "插图可以带有自己的比例尺。"),
        ),
        show_me=("widget", "canvas"),
        contexts=("pip",),
        keywords=("pip", "inset", "picture in picture", "插图", "子图"),
    ),
    HelpTopic(
        key="panel_labels", icon="label",
        title=("Panel labels", "面板编号"),
        steps=(
            ("Choose [Edit → Auto In-Cell Labels] for a, b, c… inside the panels.",
             "选择 [编辑 → 自动图内标注]，在面板内添加 a、b、c…"),
            ("Choose [Auto Above-Cell Labels] to place them in a band above the images.",
             "选择 [自动图外标注]，将编号放在图片上方的标注带中。"),
            ("Select a label to edit its font, colour and position.",
             "选中编号即可编辑字体、颜色和位置。"),
        ),
        details=(
            ("Apply Style to All copies the style to labels of the same tier.",
             "将样式应用到全部：复制给同一层级的标注。"),
            ("The numbering scheme and strip size are under All labels.",
             "编号方案和标注带尺寸位于 [全部标注] 中。"),
            ("[Layout → All Labels Placement] offers other placements.",
             "[布局 → 全部标注位置] 提供其他放置方式。"),
            ("Big gap to a label? Right-click the image → [Auto-Trim Margins].",
             "标注与图片间距过大？右键图片 → [自动裁去空白边]。"),
        ),
        show_me=("action", "_act_auto_label_incell"),
        contexts=("label",),
        keywords=("label", "letter", "numbering", "标注", "编号", "字母"),
    ),
    HelpTopic(
        key="shared_titles", icon="titles",
        title=("Row & column titles", "行列共享标题"),
        steps=(
            ("Select the cells that should share a title.",
             "选中需要共用标题的单元格。"),
            ("Choose [Edit → Add Shared Label for Selection], then pick a side.",
             "选择 [编辑 → 为所选添加共享标注]，再选择一侧。"),
            ("Double-click the title to edit it; drag its band to move it.",
             "双击标题编辑文字；拖动标注带可移动它。"),
        ),
        details=(
            ("Select the title band and press Delete to remove it.",
             "选中标注带后按 Delete 即可删除。"),
            ("Shared labels add annotations; text-size groups adjust existing text.",
             "共享标注用于添加注释；文字大小组用于调整已有文字。"),
        ),
        show_me=None,
        contexts=("group_label",),
        keywords=("shared", "title", "band", "group label", "标题", "共享", "标注带"),
    ),
    HelpTopic(
        key="scale_bar", icon="scale_bar",
        title=("Scale bar", "比例尺"),
        steps=(
            ("Turn on the scale bar in the cell's context menu or the Inspector.",
             "在单元格右键菜单或检查器中开启比例尺。"),
            ("Enter the calibration in µm per pixel from your acquisition data.",
             "填入采集数据中的校准值（µm/像素）。"),
            ("Choose the bar length, position and appearance.",
             "设置比例尺的长度、位置和外观。"),
        ),
        details=(
            ("Do not infer calibration from screen zoom.",
             "不要根据屏幕缩放推断校准值。"),
            ("Check the bar after cropping, resizing and export.",
             "裁剪、调整大小和导出后都应核对比例尺。"),
            ("New projects use final-figure points for label sizes; older ones keep legacy sizes.",
             "新工程的标注字号以最终成图磅值计；旧工程保留旧版字号。"),
        ),
        show_me=("section", "scale_bar_group"),
        keywords=("calibration", "µm", "scale", "比例尺", "校准"),
    ),
    HelpTopic(
        key="marks", icon="marks",
        title=("Arrows & shapes", "箭头与图形"),
        steps=(
            ("Click [Draw Mode] on the toolbar; the shape tools appear on the canvas.",
             "点击工具栏的 [绘制模式]，图形工具会出现在画布上。"),
            ("Pick a shape and drag on the page; the tool stays armed.",
             "选择图形并在页面上拖动；工具会保持激活，可继续绘制。"),
            ("Press Esc to put the tool down; press Esc again or [Done] to leave.",
             "按 Esc 放下工具；再按 Esc 或点击 [完成] 退出。"),
        ),
        details=(
            ("Shift snaps lines to 45° and keeps squares and circles.",
             "Shift 将直线吸附到 45°，并保持正方形和圆形。"),
            ("Ctrl draws rectangles and ellipses from the centre.",
             "Ctrl 从中心绘制矩形和椭圆。"),
            ("Polygon: press at the centre, then drag to set radius and rotation.",
             "多边形：在中心按下，拖动即可设置半径和旋转。"),
            ("Marks stay fixed on the page; they do not follow panels when reflowing.",
             "标记固定在页面上，布局重排时不会随面板移动。"),
        ),
        show_me=("action", "_act_draw_mode"),
        contexts=("mark",),
        keywords=("draw", "arrow", "shape", "line", "polygon", "标记", "绘制", "箭头", "图形"),
    ),
    HelpTopic(
        key="text_sizes", icon="text_aa",
        title=("Match text sizes", "统一文字大小"),
        steps=(
            ("Right-click an image cell → [Text & Plot] → [Match Text Size…].",
             "右键图片单元格 → [文字与图表] → [匹配文字大小…]。"),
            ("Select texts, then click a group chip, or the [+] chip to make one.",
             "选中文字，点击组芯片，或点击 [+] 新建一个组。"),
            ("Set the group size in points (pt); members update across the project.",
             "设置组字号（pt），组内文字在整个工程中同步更新。"),
        ),
        details=(
            ("Sizes are final-figure points, independent of export DPI.",
             "字号为最终成图的磅值，与导出 DPI 无关。"),
            ("Raster text is found by OCR; check the detected regions.",
             "位图文字由 OCR 识别，请检查检测区域。"),
            ("Only real SVG text can be grouped; outlined text cannot.",
             "只能分组真正的 SVG 文字；已转为轮廓的文字不能分组。"),
            ("Tick a raster region to allow it to be resized.",
             "勾选位图区域后，才允许对其缩放。"),
        ),
        show_me=("section", "cell_group"),
        contexts=("text_size_window",),
        keywords=("font", "size", "pt", "ocr", "raster", "svg", "text group", "文字", "字号", "文字组"),
    ),
    HelpTopic(
        key="align_plots", icon="align",
        title=("Align plot areas", "对齐绘图区"),
        steps=(
            ("Open [Align Plot Areas…] from the Layout menu or beside Auto Layout.",
             "从 [布局] 菜单或 [自动布局] 旁打开 [对齐绘图区…]。"),
            ("Tick the panels, then press Enter on each suggested box to keep it.",
             "勾选面板，然后在每个建议框上按 Enter 保留。"),
            ("Use the ★ panel as the reference, then check the preview and Apply.",
             "以 ★ 面板为参照，检查预览后点击应用。"),
        ),
        details=(
            ("Drag a box around the plot interior, excluding axis labels and legends.",
             "框选绘图区内部，不含坐标标签和图例。"),
            ("This marks the plot area; it does not crop the source image.",
             "这只是标记绘图区，不会裁剪源图片。"),
            ("Ctrl+Z and Ctrl+Y undo and redo marks.",
             "Ctrl+Z 与 Ctrl+Y 可撤销和重做标记。"),
            ("Ticking a panel when no group exists creates a new group.",
             "在没有组时勾选面板，会自动新建一个组。"),
        ),
        show_me=("action", "_act_align_plots"),
        contexts=("align_dialog",),
        keywords=("plot", "axes", "baseline", "align", "绘图区", "对齐", "基线", "坐标轴"),
    ),
    HelpTopic(
        key="same_size", icon="equal",
        title=("Same-size panels", "等大面板"),
        steps=(
            ("Select the cells that should share a width and height.",
             "选中需要相同宽高的单元格。"),
            ("Right-click → [Selected Cells] → [Create Size Group] to link their size.",
             "右键 → [所选单元格] → [创建尺寸组]，关联它们的尺寸。"),
            ("Select one member and edit the group size in [Image Cell Properties].",
             "选中一个成员，在 [图像单元格属性] 中编辑组尺寸。"),
        ),
        details=(
            ("A size group controls cell size, not the axes drawn inside images.",
             "尺寸组控制单元格大小，不控制图片内部绘制的坐标轴。"),
            ("Arrow keys move between cells on the canvas; they do not nudge panels.",
             "画布中的方向键用于切换单元格，不会微移面板。"),
        ),
        show_me=("section", "cell_group"),
        contexts=("multi_cell",),
        keywords=("size group", "same size", "equal", "尺寸组", "等大", "同样大小"),
    ),
    HelpTopic(
        key="freeform", icon="floating",
        title=("Freeform positioning", "自由定位"),
        steps=(
            ("Choose [Layout → Convert Grid → Freeform] to position cells directly.",
             "选择 [布局 → 网格转自由布局]，直接定位单元格。"),
            ("Set exact X, Y, width and height in the Inspector, in millimetres.",
             "在检查器中以毫米设置精确的 X、Y、宽度和高度。"),
            ("Use [Bring to Front] and [Send to Back] to fix overlapping panels.",
             "面板重叠时，用 [置于顶层] 和 [置于底层] 调整顺序。"),
        ),
        details=(
            ("Drag a panel onto another in the Layers panel to stack it precisely.",
             "在图层面板中把一个面板拖到另一个上，可精确调整上下层级。"),
            ("[Layout → Switch to Grid Mode] returns to grid placement; positions may shift.",
             "[布局 → 切换至网格模式] 可恢复网格定位；位置可能会改变。"),
        ),
        show_me=None,
        keywords=("freeform", "position", "layer", "bring", "自由", "定位", "层级"),
    ),
    HelpTopic(
        key="export", icon="export",
        title=("Export", "导出"),
        steps=(
            ("Open the toolbar [Export] menu and choose PDF, SVG, TIFF, PNG or JPG.",
             "打开工具栏的 [导出] 菜单，选择 PDF、SVG、TIFF、PNG 或 JPG。"),
            ("Open the exported file in a separate viewer at its final size.",
             "用独立查看器按最终尺寸打开导出文件。"),
            ("Use [Export Preview] ([Ctrl+Shift+P]) to hide editing aids first.",
             "导出前用 [导出预览]（[Ctrl+Shift+P]）隐藏编辑辅助元素。"),
        ),
        details=(
            ("Raster pixels ≈ (mm ÷ 25.4) × DPI.",
             "位图像素数 ≈（毫米 ÷ 25.4）× DPI。"),
            ("A higher DPI cannot restore detail missing from a source image.",
             "提高 DPI 不能恢复源图中缺失的细节。"),
            ("[Layout → Set Export Region] exports only part of the page.",
             "[布局 → 设置导出区域] 可只导出页面的一部分。"),
            ("[File → Copy as PNG to Clipboard] copies the same PNG.",
             "[文件 → 复制为 PNG 到剪贴板] 可复制相同的 PNG。"),
        ),
        show_me=("action", "_act_export_pdf"),
        keywords=("pdf", "png", "tiff", "svg", "jpg", "dpi", "export", "导出", "分辨率"),
    ),
    HelpTopic(
        key="save_share", icon="package",
        title=("Save & share", "保存与分享"),
        steps=(
            ("Save with [Ctrl+S]; keep an editable copy of the project.",
             "用 [Ctrl+S] 保存，并保留可编辑的工程副本。"),
            ("Use [File → Convert to .figpack…] to bundle source images for sharing.",
             "用 [文件 → 打包为 .figpack 项目…] 将源图片打包后分享。"),
            ("Use [File → Export All Source Images…] to copy only the originals.",
             "用 [文件 → 导出全部源图片…] 只复制原始素材。"),
        ),
        details=(
            (".figlayout stores links to source images; keep those files available.",
             ".figlayout 只保存源图片的链接，请保留这些文件。"),
            (".figpack includes source assets, so it is easier to share.",
             ".figpack 包含源素材，更便于分享。"),
            ("An asterisk in the title means there are unsaved changes.",
             "标题中的星号表示有未保存的更改。"),
        ),
        show_me=("action", "_act_save"),
        keywords=("save", "figpack", "figlayout", "bundle", "share", "保存", "分享", "打包"),
    ),
    HelpTopic(
        key="troubleshoot", icon="wrench",
        title=("Something looks wrong", "显示异常怎么办"),
        steps=(
            ("Missing image: check the source path, or re-import the panel.",
             "图片缺失：检查源路径，或重新导入面板。"),
            ("Unexpected crop or fit: check the fit mode, group and region settings.",
             "裁剪或适应异常：检查缩放模式、组和区域设置。"),
            ("Shortcut does nothing on the canvas: click the canvas first.",
             "快捷键无效：先点击画布。"),
        ),
        details=(
            ("Compare with the original and inspect the final export.",
             "与原图对比，并检查最终导出文件。"),
            ("Text-size matching needs a supported image type and an OCR backend.",
             "文字大小匹配需要支持的图片类型和 OCR 后端。"),
            ("Keep a copy before automated edits or large rearrangements.",
             "自动编辑或大幅调整前，请先保存副本。"),
        ),
        show_me=None,
        keywords=("missing", "wrong", "problem", "help", "问题", "异常", "缺失", "帮助"),
    ),
)


SHORTCUT_GROUPS = (
    (("File & tabs", "文件与标签页"), (
        ("Ctrl + N", ("New project", "新建工程")),
        ("Ctrl + O", ("Open project", "打开工程")),
        ("Ctrl + S", ("Save project", "保存工程")),
        ("Ctrl + Shift + S", ("Save As…", "另存为…")),
        ("Ctrl + T", ("New tab", "新建标签页")),
        ("Ctrl + W", ("Close current tab", "关闭当前标签页")),
        ("F5", ("Reload images from disk", "从磁盘重新加载图片")),
    )),
    (("Edit & layout", "编辑与布局"), (
        ("Ctrl + Z", ("Undo", "撤销")),
        ("Ctrl + Y", ("Redo (Windows)", "重做（Windows）")),
        ("Ctrl + Shift + L", ("Auto In-Cell Labels", "自动图内标注")),
        ("Ctrl + Shift + K", ("Auto Above-Cell Labels", "自动图外标注")),
        ("Ctrl + Shift + A", ("Auto Layout", "自动布局")),
        ("Ctrl + ]", ("Bring selected cell or mark to front", "将选中单元格或标记置于顶层")),
        ("Ctrl + [", ("Send selected cell or mark to back", "将选中单元格或标记置于底层")),
        ("Ctrl + Delete", ("Remove image from selected cell, not the source file", "移除选中单元格中的图片，不删除源文件")),
        ("Delete", ("Delete selected text, mark, or shared label", "删除选中的文字、标记或共享标注")),
    )),
    (("Drawing", "绘制"), (
        ("Shift (drawing)", ("Snap 45° · square/circle · aspect resize · axis-locked move", "吸附 45° · 正方形/圆形 · 等比缩放 · 单轴移动")),
        ("Ctrl (drawing)", ("Draw rectangles/ellipses from the centre", "从中心绘制矩形/椭圆")),
        ("Enter / double-click", ("Finish a polyline", "完成折线")),
        ("Backspace", ("Remove the last polyline vertex", "删除上一个折线顶点")),
        ("Esc (Draw mode)", ("Cancel the shape in progress, then put the tool down, then leave Draw mode", "取消正在绘制的图形，然后放下工具，再退出绘制模式")),
        ("Ctrl + C / V / D (Draw mode)", ("Copy, paste (cascades 2 mm) and duplicate selected shapes", "复制、粘贴（每次级联偏移 2 毫米）和创建选中形状的副本")),
    )),
    (("Canvas & navigation", "画布与导航"), (
        ("Wheel", ("Scroll canvas", "滚轮：滚动画布")),
        ("Ctrl + Wheel", ("Zoom canvas around the pointer", "Ctrl + 滚轮：以指针位置为中心缩放画布")),
        ("Middle drag", ("Pan canvas", "中键拖动：平移画布")),
        ("Ctrl + + / -", ("Zoom canvas in / out (canvas focused)", "放大／缩小画布（画布获得焦点时）")),
        ("Ctrl + 0", ("Fit page in view (canvas focused)", "将页面适配到视图（画布获得焦点时）")),
        ("Ctrl + 1", ("Set canvas zoom to 100% (canvas focused)", "画布缩放设为 100%（画布获得焦点时）")),
        ("Arrow keys", ("Navigate to a neighbouring cell (canvas focused)", "方向键：选择相邻单元格（画布获得焦点时）")),
        ("Ctrl + Arrow", ("Swap with a neighbouring cell (canvas focused)", "Ctrl + 方向键：与相邻单元格交换（画布获得焦点时）")),
        ("Tab / Shift + Tab", ("Next / previous cell (canvas focused)", "选择下一个／上一个单元格（画布获得焦点时）")),
        ("Esc", ("Cancel an active drag/crop or clear selection", "取消当前拖动／裁剪，或清除选择")),
    )),
    (("View & interface", "视图与界面"), (
        ("Ctrl + Shift + P", ("Toggle export preview", "切换导出预览")),
        ("Ctrl + Alt + + / -", ("Increase / decrease interface font size", "放大／缩小界面字体")),
        ("Ctrl + Alt + 0", ("Reset interface font size", "重置界面字体大小")),
        ("Ctrl + Shift + T", ("Switch light / dark theme", "切换浅色／深色主题")),
        ("Ctrl + Shift + G", ("Switch interface language", "切换界面语言")),
        ("Ctrl + \\", ("Show / hide Layers", "显示／隐藏图层面板")),
        ("Ctrl + R", ("Show / hide rulers", "显示／隐藏标尺")),
        ("Ctrl + ,", ("Preferences…", "偏好设置…")),
        ("F1", ("User Guide…", "使用指南…")),
    )),
)


TOUR_STEPS = (
    TourStep(("widget", "toolbar"), ("Toolbar", "工具栏"),
             ("Common actions: import, export, auto layout and draw mode.",
              "常用操作：导入、导出、自动布局和绘制模式。")),
    TourStep(("widget", "layers"), ("Layers", "图层"),
             ("Select any cell or shape from the layout tree.",
              "从布局树中选择任意单元格或图形。")),
    TourStep(("widget", "canvas"), ("Canvas", "画布"),
             ("Arrange the figure here. Ctrl+wheel zooms; middle-drag pans.",
              "在此排版。Ctrl+滚轮缩放，中键拖动平移。")),
    TourStep(("widget", "inspector"), ("Inspector", "检查器"),
             ("Edit page, cell and selected-item settings.",
              "编辑页面、单元格和所选对象的设置。")),
    TourStep(("widget", "statusbar_zoom"), ("Zoom controls", "缩放控件"),
             ("Zoom the current canvas without a keyboard.",
              "无需键盘即可缩放当前画布。")),
    TourStep(("action", "_act_export_pdf"), ("Export", "导出"),
             ("Choose a format from the toolbar Export menu.",
              "在工具栏的导出菜单中选择格式。")),
    TourStep(("menu", "help"), ("Help", "帮助"),
             ("Press F1 in any window for context help.",
              "在任意窗口中按 F1 获取上下文帮助。")),
)


def parse_chips(text):
    """Split *text* into (segment, is_chip) pairs; ``[...]`` marks a key or menu-path chip.

    An unclosed or nested bracket stays plain text.
    """
    out = []
    buf = ""
    i = 0
    while i < len(text):
        if text[i] == "[":
            j = text.find("]", i + 1)
            if j != -1 and "[" not in text[i + 1:j]:
                if buf:
                    out.append((buf, False))
                    buf = ""
                out.append((text[i + 1:j], True))
                i = j + 1
                continue
        buf += text[i]
        i += 1
    if buf:
        out.append((buf, False))
    return out


def _terms(query):
    return [term for term in (query or "").lower().split() if term]


def search(query, lang="en"):
    """Keys of topics matching every term; title matches come first, then TOPICS order."""
    terms = _terms(query)
    if not terms:
        return [topic.key for topic in TOPICS]
    matches = []
    for topic in TOPICS:
        title_text = " ".join(topic.title).lower()
        body = " ".join(
            [title_text]
            + [part for pair in topic.steps for part in pair]
            + [part for pair in topic.details for part in pair]
            + list(topic.keywords)
        ).lower()
        if all(term in body for term in terms):
            title_hit = all(term in title_text for term in terms)
            matches.append((0 if title_hit else 1, topic.key))
    matches.sort(key=lambda item: item[0])
    return [key for _rank, key in matches]


def search_shortcuts(query, lang="en"):
    """SHORTCUT_GROUPS filtered to entries matching every term; empty groups are dropped."""
    terms = _terms(query)
    groups = []
    for title, entries in SHORTCUT_GROUPS:
        kept = []
        for key, (en, zh) in entries:
            haystack = f"{key} {en} {zh}".lower()
            if all(term in haystack for term in terms):
                kept.append((key, (en, zh)))
        if kept:
            groups.append((title, tuple(kept)))
    return tuple(groups)


def topic_for_context(context):
    for topic in TOPICS:
        if context in topic.contexts:
            return topic.key
    return "first_figure"


def place_bubble(hole, size, bounds, margin=12):
    """Top-left (x, y) for a caption bubble of *size* beside the *hole* rectangle.

    Tries right, left, below, then above the hole; the first placement that fits
    inside *bounds* (keeping *margin* from every edge) wins. If none fits, the right
    placement is clamped into bounds.
    """
    hx, hy, hw, hh = hole
    bw, bh = size
    bx, by, bwidth, bheight = bounds

    def clamp(x, y):
        x = min(max(x, bx + margin), bx + bwidth - margin - bw)
        y = min(max(y, by + margin), by + bheight - margin - bh)
        return (x, y)

    def fits(x, y):
        return (x >= bx + margin and y >= by + margin
                and x + bw <= bx + bwidth - margin and y + bh <= by + bheight - margin)

    def overlaps(x, y):
        return x < hx + hw and hx < x + bw and y < hy + hh and hy < y + bh

    candidates = [
        (hx + hw + margin, hy),
        (hx - margin - bw, hy),
        (hx, hy + hh + margin),
        (hx, hy - margin - bh),
    ]
    for x, y in candidates:
        if fits(x, y):
            return (x, y)
    for x, y in candidates:
        cx, cy = clamp(x, y)
        if not overlaps(cx, cy):
            return (cx, cy)
    return clamp(*candidates[0])
