from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import (
    QBuffer, QByteArray, QEvent, QIODevice, QObject, QRect, QRectF, QSaveFile,
    QStandardPaths, Qt, QTimer,
)
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QMessageBox, QScrollArea, QAbstractButton, QMenu, QToolButton

from src.app.i18n import current_language, tr
from src.app.inspector import CollapsibleSection
from src.app.motion import MotionTween
from src.model.data_model import Project, Cell, RowTemplate


def text(en, zh):
    return zh if current_language() == 'zh' else en


@dataclass(frozen=True)
class Step:
    key: str
    title: tuple
    body: tuple
    target: str = 'canvas'
    action: str = ''


LESSONS = {
    'first_figure': (
        Step('intro', ('Your own practice space', '独立的练习空间'),
             ('This is a new practice tab, not your research figure. Sample charts are synthetic. Back revisits instructions without undoing edits; Skip bypasses a step. Exit leaves this tab open so you can save or close it normally.',
              '这是新建的练习标签页，不是你的研究图。示例图使用合成数据。“上一步”仅回看说明，不撤销编辑；“跳过”可绕过步骤。退出后练习页保留，可正常保存或关闭。')),
        Step('delete_row', ('Remove the row you don\u2019t need', '删除不需要的行'),
             ('A new project starts as a 2\u00d72 grid, the same as File → New. This figure only needs one row of three panels, so right-click any cell in the second row → Delete → This Row, or press Delete second row below. Deleting a row removes its cells; the first row is untouched.',
              '新建工程默认是 2×2 网格，与“文件 → 新建”一致。这张图只需要一行三个面板，因此在第二行任意单元格上右键 → 删除 → 本行，或点击下方“删除第二行”。删除一行会移除其中的单元格；第一行不受影响。'),
             action='delete_row'),
        Step('add_cell', ('Add a third panel to the row', '为该行添加第三个面板'),
             ('The remaining row has two columns; this figure needs three. Click the + button at the row\u2019s right edge to add a cell there, or press Add a third cell below. This is how a row grows past its starting column count.',
              '剩下的这一行只有两列，而这张图需要三列。点击该行右边缘的 + 按钮即可在此处新增单元格，或点击下方“添加第三个单元格”。这就是让一行的列数超过初始设置的方法。'),
             action='add_cell'),
        Step('load', ('Load panels from three file formats', '载入三种格式的面板'),
             ('Click Load samples below. The three panels are SVG, PNG and TIFF, because ILM composes vector and raster sources side by side. After loading, each panel’s format appears on its Layers row, in the Inspector under Source Format, and in the status bar when a panel is selected. In your own work, use File → Import Images or drop images onto cells.',
              '点击下方“载入示例”。三个面板分别为 SVG、PNG 和 TIFF，因为 ILM 可以同时排布矢量与位图来源。载入后，可在图层行、检查器的“源文件格式”以及选中面板时的状态栏查看各面板格式。实际工作中可使用“文件 → 导入图片”或将图片拖到单元格。'), action='load'),
        Step('layout', ('Arrange the panels', '安排面板'),
             ('Click Auto Layout in the toolbar (Ctrl+Shift+A). Inspect the spacing and panel proportions. The tutorial recognizes the action; click Next when you are ready.',
              '点击工具栏的“自动布局”（Ctrl+Shift+A），检查间距和面板比例。教程会识别操作；准备好后点击“下一步”。'), target='_act_auto_layout'),
        Step('labels', ('Add panel labels', '添加面板编号'),
             ('Click Auto In-Cell Labels (Ctrl+Shift+L). Look for panel letters. This project uses the normal new-project label settings; the next step shows where to adjust the size for your page and journal. These annotations are separate from the text inside your source images.',
              '点击“自动图内标注”（Ctrl+Shift+L），观察面板编号。本工程使用普通新建工程的标注设置；下一步将介绍如何按页面尺寸和期刊要求调整字号。这些标注与源图片内部的文字相互独立。'), target='_act_auto_label_incell'),
        Step('label_size', ('Change a label’s size', '修改标注字号'),
             ('Click a panel letter on the canvas (or press Select a label below). In the Inspector, open Text Style Properties and use the highlighted Size field — that is where a label’s size is changed. Sizes apply to the selected label; use Apply to All to restyle the whole set.',
              '在画布上点击某个面板编号（或点击下方“选中标注”）。在检查器中展开“文字样式属性”，使用高亮的“字号”字段——标注大小就在这里修改。修改仅作用于所选标注；如需统一整组样式，请使用“应用到全部”。'),
             target='label_size', action='label_size'),
        Step('save', ('Save an editable project', '保存可编辑工程'),
             ('Click Save (Ctrl+S) and choose a new file. Choose .figpack to include the sample assets. Cancelling the file dialog does not complete this step. You may Skip if you do not want a practice file.',
              '点击“保存”（Ctrl+S），选择新文件。使用 .figpack 可包含示例素材。取消文件对话框不会完成本步骤；不想保存练习文件时可跳过。'), target='_act_save'),
        Step('preview', ('Check the composition', '检查构图'),
             ('Open the highlighted Export button and choose Export Preview to hide the editing aids, then check the labels and margins. The same toggle is under View → Export Preview, or press Ctrl+Shift+P. This is only a preview: use Export for a publication file, and inspect that file separately.',
              '点击高亮的“导出”按钮并选择“导出预览”，隐藏编辑辅助元素，然后检查标注和边距。该开关也位于“视图 → 导出预览”，或按 Ctrl+Shift+P。这只是预览：投稿文件需通过“导出”生成，并单独检查。'), target='_act_preview_mode'),
        Step('finish', ('Ready for your own figure', '开始制作自己的图'),
             ('You have explored importing, layout, labels, saving, and preview. Save the editable project as well as any export. Finish returns to your previous tab and leaves the practice project available. Replay any lesson from Help → Guided Tutorials.',
              '你已了解导入、布局、标注、保存和预览。除导出图外，还应保存可编辑工程。完成后返回之前的标签页，练习工程会保留。可随时从“帮助 → 引导教程”重新学习。')),
    ),
    'text_sizes': (
        Step('intro', ('Match size, not wording', '统一大小，而非文字内容'),
             ('This practice figure mixes two SVG charts with a PNG chart, and their text is deliberately inconsistent — a common problem when panels come from different tools. Each panel’s format is shown on its Layers row and in the Inspector. Text groups are project-wide; their sizes are points in the final figure, not source pixels. Source files are not overwritten. We will use a 9 pt group.',
              '练习图由两张 SVG 图和一张 PNG 图组成，其文字大小故意不一致——面板来自不同软件时常会如此。各面板格式显示在图层行和检查器中。文字组在整个工程共享，字号单位是最终图中的磅值，而非源像素；源文件不会被覆盖。下面使用 9 pt 文字组。')),
        Step('svg_open', ('Inspect the first SVG', '检查第一张 SVG'),
             ('Right-click the first panel → Edit SVG Text Groups, or use Open inspector below. Only actual SVG text is listed; outlined lettering is not editable text.',
              '右键第一张面板 → 编辑 SVG 文字组，或点击下方“打开检查器”。列表只显示真正的 SVG 文字，已转为轮廓的文字不可编辑。'), target='svg0', action='svg0'),
        Step('svg_assign', ('Create and assign a 9 pt group', '创建并分配 9 pt 文字组'),
             ('In the inspector, Add Group and set its size to 9 pt. Select the Time text element, choose the group in Assign to, and click Assign selected to group. Changes apply immediately; closing the inspector is not Cancel.',
              '在检查器中添加组，将字号设为 9 pt。选中 Time 文字元素，在“分配到”中选择该组，再点击“将所选分配到组”。修改即时生效，关闭检查器不等于取消。'), target='svg0', action='svg0'),
        Step('svg_shared', ('Reuse the group in the second SVG', '在第二张 SVG 中复用同一组'),
             ('Open the second panel’s inspector with the button below or its context menu. Assign its Time element to the same 9 pt group. Do not create a second group: one shared group keeps panels consistent.',
              '通过下方按钮或第二张面板的右键菜单打开检查器。将其 Time 元素分配到同一个 9 pt 组，不要另建组；共享组可保持各面板文字一致。'), target='svg1', action='svg1'),
        Step('raster_detect', ('Locate raster text with OCR', '用 OCR 定位位图文字'),
             ('Open the raster inspector below, then click Detect text (OCR). RapidOCR is the default. If OCR is unavailable, configure it in Preferences → Text Detection and Apply, or Skip this step. Detection may take a moment and can be cancelled.',
              '打开下方的位图检查器，再点击“检测文字（OCR）”。默认后端为 RapidOCR。若不可用，可在“偏好设置 → 文字检测”中配置并应用，或跳过此步。检测可能需要等待，也可取消。'), target='raster', action='raster'),
        Step('raster_assign', ('Assign and review a raster region', '分配并审查位图区域'),
             ('Select the Time region and assign it to the same group used by both SVG panels; keep its checkbox enabled. Read the status: review warnings are advisory, but collisions may still prevent resizing. Check neighbouring lines and data.',
              '选中 Time 区域，分配到两张 SVG 使用的同一组，并保持勾选。请阅读状态：审查提示仅供参考，但重叠等情况仍可能阻止缩放。检查附近线条和数据。'), target='raster', action='raster'),
        Step('review', ('Compare with the original', '与原图对比'),
             ('Toggle Show original in the raster inspector, then turn it off again. A group assignment does not prove the pixels are correct. Inspect each changed label; raster size estimates are approximate and enlargement cannot restore lost detail.',
              '在位图检查器中勾选“显示原图”，再取消勾选。分组成功并不代表像素处理正确。逐处检查修改的文字；位图字号估计是近似值，放大无法恢复缺失细节。'), target='raster', action='raster'),
        Step('finish', ('Verify before publication', '发表前核对'),
             ('Save a copy before extensive text edits; not every inspector edit supports undo. Inspect the exported file too: SVG group font sizes can differ from their targets in PDF output. Finish keeps the practice tab. Skipped steps can be revisited by replaying this lesson.',
              '大量文字修改前请另存副本，并非所有检查器操作都支持撤销。还要检查实际导出文件：PDF 中 SVG 组字号可能与目标值不同。完成后保留练习页；跳过的步骤可通过重学补做。')),
    ),
    'arrange_panels': (
        Step('intro', ('Grid, sub-cells, and freeform', '网格、子单元格与自由布局'),
             ('These three panels are already loaded — the same SVG, PNG, and TIFF mix from the first lesson. Here we focus on layout: subdividing a panel, swapping content, and switching to freeform for exact positions. This is a separate practice tab; your other projects are untouched.',
              '这三个面板已经载入完毕——与第一课相同的 SVG、PNG、TIFF 组合。本课聚焦于布局本身：细分面板、交换内容，以及切换到自由布局以获得精确位置。这是独立的练习标签页，不会影响你的其他工程。')),
        Step('split', ('Subdivide a panel', '细分面板'),
             ('Click Split third panel below. In real use, right-click any panel → Insert → Add Sub-Cell / Subdivide for one split at a time, or → Split into N Columns/Rows for several at once. This is how mismatched panel sizes — a wide photo next to two small insets — get built.',
              '点击下方“拆分第三个面板”。实际使用时，右键任意面板 → 插入 → 细分为子单元格，可一次拆出一个；或 → 拆分为 N 列/行，一次拆出多个。宽照片配两张小插图这类不对称排版就是这样搭建的。'),
             action='split_cols'),
        Step('ratio', ('Adjust the split ratio', '调整分割比例'),
             ('Click Select the new sub-cell below to reveal Sub-Cell Settings in the Inspector, then change the highlighted ratio. In real use, drag the divider between the two sub-cells directly on the canvas instead — the Inspector field gives you an exact number.',
              '点击下方“选中新的子单元格”，在检查器中展开“子单元格设置”，修改高亮的比例数值。实际使用时可直接在画布上拖动两个子单元格之间的分隔条；检查器字段则给出精确数值。'),
             target='subcell_ratio', action='select_subcell'),
        Step('swap', ('Swap two panels', '交换两个面板'),
             ('Click Swap panels below to exchange the first two panels’ images. In real use, drag one panel onto another on the canvas to swap them; hold Ctrl to select several cells and swap the whole set at once. Position, labels, and insets stay with the cell — only the image content moves.',
              '点击下方“交换面板”，交换前两个面板的图片。实际使用时，把画布上的一个面板拖到另一个上即可交换；按住 Ctrl 可多选几个单元格一起交换。位置、标注和插图都留在原单元格——只有图片内容会移动。'),
             action='swap'),
        Step('crop', ('Crop a panel\u2019s image', '裁剪面板图片'),
             ('Click Crop to square below. In real use, right-click a panel → Crop → pick a preset (Square, 4:3, 16:9…) for an exact ratio, or choose Crop Image to drag the handles freely. The same submenu\u2019s Reset Crop restores the full image — cropping never touches the source file.',
              '点击下方“裁剪为正方形”。实际使用时，右键任意面板 → 裁剪 → 选择预设比例（正方形、4:3、16:9…）即可精确裁剪，或选择“裁剪图片”自由拖动裁剪手柄。同一菜单中的“重置裁剪”可恢复完整图片——裁剪不会改动源文件。'),
             action='crop_square'),
        Step('fit_mode', ('Fit and align the image in its cell', '调整图片的填充与对齐方式'),
             ('Click Select a panel below. In the Inspector, Fit Mode chooses Contain (show the whole image, may leave gaps) or Cover (fill the cell, may crop edges); the 3\u00d73 alignment grid controls which part shows when Cover crops or the cell\u2019s proportions don\u2019t match the image.',
              '点击下方“选中面板”。在检查器中，“填充方式”可选择“包含”（显示完整图片，可能留白）或“覆盖”（填满单元格，可能裁去边缘）；3×3 对齐网格用于控制“覆盖”裁剪或单元格比例与图片不一致时显示图片的哪一部分。'),
             target='fit_mode_combo', action='select_cell'),
        Step('freeform', ('Switch to freeform', '切换到自由布局'),
             ('Open the highlighted Layout menu and choose Convert Grid → Freeform. Every panel keeps its current position but is no longer bound to row/column rules. Layout → Switch to Grid Mode reverts to grid positioning at any time — freeform is not a one-way trip.',
              '打开高亮的“布局”菜单，选择“网格转自由布局”。每个面板会保持当前位置，但不再受行列规则约束。随时可通过“布局 → 切换至网格模式”恢复网格定位——自由布局并非不可逆的操作。'),
             target='_act_bake'),
        Step('reposition', ('Position a panel precisely', '精确定位面板'),
             ('Click Select a panel below, then edit the highlighted X field in the Inspector — Y, Width, and Height are right below it, all in millimetres. In real use, drag the panel directly on the canvas for a quick placement, then fine-tune the exact numbers here. Bring to Front / Send to Back (Layout menu) controls which panel sits on top when two overlap.',
              '点击下方“选中面板”，然后修改检查器中高亮的 X 字段——Y、宽度和高度就在下方，单位均为毫米。实际使用时，可直接在画布上拖动面板快速摆放，再到这里微调精确数值。“置于顶层／置于底层”（布局菜单）控制两个面板重叠时的前后顺序。'),
             target='freeform_x', action='select_cell'),
        Step('finish', ('Ready to compose your own layout', '可以开始搭建自己的布局了'),
             ('You have subdivided a panel, adjusted a split ratio, swapped content, and repositioned a panel in freeform mode. Layout → Switch to Grid Mode returns to grid rules whenever you need consistent rows and columns again. Finish keeps this practice tab; replay this lesson anytime from Help → Guided Tutorials.',
              '你已经练习了细分面板、调整分割比例、交换内容，以及在自由布局中重新定位面板。需要恢复整齐的行列时，随时可用“布局 → 切换至网格模式”。完成后练习页会保留；可随时从“帮助 → 引导教程”重新学习本课。')),
    ),
    'labels_titles': (
        Step('intro', ('Panel letters vs. shared titles', '面板编号与共享标题'),
             ('These three panels are already loaded (SVG, PNG, TIFF). A panel letter (a, b, c…) identifies one panel. A shared label spans several panels at once — a column header or a rotated row title — and reserves its own band so it never overlaps the artwork. This is a separate practice tab.',
              '这三个面板已经载入完毕（SVG、PNG、TIFF）。面板编号（a、b、c…）用于标识单个面板；共享标签则同时跨越多个面板——例如列标题或旋转的行标题——并占用独立的标注带，因此不会遮挡图形内容。这是独立的练习标签页。')),
        Step('panel_letters', ('Add panel letters', '添加面板编号'),
             ('Click Auto In-Cell Labels (Ctrl+Shift+L) in the toolbar. These letters identify each panel individually and are unrelated to any shared label you add next — deleting or moving one never affects the other.',
              '点击工具栏的“自动图内标注”（Ctrl+Shift+L）。这些编号分别标识每个面板，与接下来添加的共享标签互不相关——删除或移动其中一个不会影响另一个。'),
             target='_act_auto_label_incell'),
        Step('shared_top', ('Add a header over two panels', '在两个面板上方添加标题'),
             ('Click Select two panels below (this is what Ctrl+click on the canvas does). Then open the highlighted Edit menu → Add Shared Label for Selection → Header above selected cells. The new band sits above both panels without covering either one.',
              '点击下方“选中两个面板”（在画布上按住 Ctrl 点选也是同样效果）。然后打开高亮的“编辑”菜单 → 为所选添加共享标注 → 所选单元格上方的标题。新的标注带会显示在两个面板上方，不会遮挡任何一个。'),
             target='group_label_top', action='select_pair'),
        Step('shared_row', ('Add a title for the whole row', '为整行添加标题'),
             ('Click Select the row below. A row title only needs the selection to sit inside one row — it always addresses the whole row, however many cells are selected. Open Edit menu → Add Shared Label for Selection → Title left of the row.',
              '点击下方“选中整行”。行标题只需要所选内容处于同一行——无论选中多少个单元格，它始终作用于整行。打开“编辑”菜单 → 为所选添加共享标注 → 所在行左侧的标题。'),
             target='group_label_left', action='select_row'),
        Step('rename', ('Give the header real text', '为标题填入实际文字'),
             ('Click Select the shared title below, then type into the highlighted Text field in the Inspector — for example "Day 7". Double-clicking the band directly on the canvas does the same thing. Drag the band up or down to restack it; select it and press Delete to remove it.',
              '点击下方“选中共享标题”，然后在检查器中高亮的“文字”字段输入实际内容，例如“第 7 天”。直接双击画布上的标注带效果相同。上下拖动标注带可调整叠放顺序；选中后按 Delete 可删除。'),
             target='gl_text_edit', action='select_shared_top'),
        Step('finish', ('Ready to label your own figure', '可以开始标注自己的图了'),
             ('Panel letters identify individual panels; shared labels group several panels under one heading or title without overlapping the artwork. Finish keeps this practice tab; replay this lesson anytime from Help → Guided Tutorials.',
              '面板编号用于标识单个面板；共享标签则将若干面板归入同一个标题之下，且不会遮挡图形内容。完成后练习页会保留；可随时从“帮助 → 引导教程”重新学习本课。')),
    ),
    'publication': (
        Step('intro', ('DPI, export region, and the real file', '分辨率、导出区域与真实文件'),
             ('These three panels are already loaded. This lesson covers three things that only show up at export time: resolution for raster output, restricting export to part of the page, and — most importantly — checking the file that actually gets submitted, not just the in-app preview.',
              '这三个面板已经载入完毕。本课涉及三件只在导出时才会显现的事：位图输出的分辨率、将导出范围限定在页面局部，以及最重要的一点——检查真正用于投稿的文件，而不仅仅是应用内的预览。')),
        Step('dpi', ('Set the export resolution', '设置导出分辨率'),
             ('Click Show project settings below (or click an empty part of the canvas), then change the highlighted DPI field — try 600. DPI only affects raster output (TIFF/PNG/JPG): pixels ≈ (size in mm ÷ 25.4) × DPI. It does not affect PDF/SVG vector content, and it cannot add detail that a low-resolution source image does not have.',
              '点击下方“显示工程设置”（或点击画布空白处），然后修改高亮的 DPI 字段——试着设为 600。DPI 只影响位图输出（TIFF/PNG/JPG）：像素数 ≈（尺寸毫米 ÷ 25.4）× DPI。它不影响 PDF/SVG 矢量内容，也无法为低分辨率的源图片补出本不存在的细节。'),
             target='dpi_spin', action='show_project'),
        Step('export_region', ('Restrict export to part of the page', '将导出范围限定在页面局部'),
             ('Open the highlighted Export button and choose Set Export Region — the same command sits under the Layout menu. This immediately creates a region covering the full page — drag its edges on the canvas to cover just part of it. Layout → Clear Export Region removes it and restores whole-page export.',
              '打开高亮的“导出”按钮，选择“设置导出区域”——同一命令也在“布局”菜单中。系统会立即创建一个覆盖整个页面的区域——在画布上拖动其边缘即可缩小到局部范围。“布局 → 清除导出区域”可移除该区域，恢复整页导出。'),
             target='_act_set_export_region'),
        Step('export', ('Open the Export menu', '打开导出菜单'),
             ('Click the highlighted Export button and choose a format — PDF for vector submission, TIFF/PNG for lossless raster, JPG for compressed raster. Cancelling the file dialog is fine; this step just wants you to see every format in one place.',
              '点击高亮的“导出”按钮，选择一种格式——矢量投稿用 PDF，无损位图用 TIFF/PNG，压缩位图用 JPG。取消文件对话框也没关系，本步骤只是想让你一次看到全部格式选项。'),
             target='_act_export_pdf'),
        Step('verify', ('Compare preview and real file', '对比预览与真实文件'),
             ('Toggle Export Preview — under the highlighted Export button, or View → Export Preview (Ctrl+Shift+P) — to see the DPI and region changes without the editing aids. But the preview is not the submission file: open the actual exported file in a separate viewer afterwards and check its page size, crop, and text sizes at the size it will actually be printed or displayed.',
              '切换“导出预览”——在高亮的“导出”按钮下，或“视图 → 导出预览”（Ctrl+Shift+P）——在没有编辑辅助元素的情况下查看 DPI 和导出区域的效果。但预览并不等同于投稿文件：请在另一个查看器中打开实际导出的文件，并按最终印刷或显示的尺寸核对页面大小、裁剪范围和文字大小。'),
             target='_act_preview_mode'),
        Step('finish', ('Ready to submit', '可以准备投稿了'),
             ('DPI controls raster detail, export region restricts the output area, and neither replaces inspecting the actual exported file at full size. Finish keeps this practice tab; replay this lesson anytime from Help → Guided Tutorials.',
              'DPI 决定位图细节，导出区域限定输出范围，但两者都不能替代按实际尺寸检查导出文件本身。完成后练习页会保留；可随时从“帮助 → 引导教程”重新学习本课。')),
    ),
    'insets_scale_bars': (
        Step('intro', ('Insets and scale bars', '插图与比例尺'),
             ('Three panels are already loaded. This lesson covers two things that live entirely in the Inspector and are easy to miss: adding a second image on top of a panel (an inset), and drawing a calibrated scale bar.',
              '现在有三个显微图像。本课介绍如何在面板上叠加第二张图片（插图），以及绘制经过校准的比例尺。')),
        Step('add_inset', ('Add an inset image', '添加插图'),
             ('Click Add inset below. In real use, drag any image file onto a panel that already has one — dropping onto an empty panel replaces it, but dropping onto a filled one adds an inset instead. Move it by dragging its body; the next step covers resizing.',
              '点击下方“添加插图”。实际使用时，把任意图片文件拖到已经有图片的面板上——拖到空面板会替换图片，拖到已有图片的面板则会新增一张插图。拖动插图主体即可移动它；下一步介绍如何调整大小。'),
             action='add_pip'),
        Step('resize_inset', ('Resize the inset', '调整插图大小'),
             ('Click Select inset below to reveal its resize handles and the Inspector\u2019s Selected PiP section. Drag a corner handle on the canvas, or edit the highlighted Width field directly — X/Y/W/H are all percentages of the host panel, not millimetres.',
              '点击下方“选中插图”，即可看到调整手柄以及检查器中的“选中插图”区域。可在画布上拖动角部手柄，或直接修改高亮的“宽度”字段——X/Y/宽/高均为相对于所在面板的百分比，而非毫米。'),
             target='pip_w', action='select_pip'),
        Step('scale_bar', ('Draw a calibrated scale bar', '绘制校准比例尺'),
             ('Click Select a panel below. In the Inspector, open Scale Bar and check Enable. Mapping and Length must match your instrument\u2019s actual pixel size to be meaningful — this practice figure has no real calibration, so the bar shown here is for layout only, not a real measurement.',
              '点击下方“选中面板”。在检查器中展开“比例尺”并勾选“启用”。要让比例尺真实可信，映射关系和长度必须与你所用仪器的实际像素尺寸匹配——本练习图没有真实校准，这里显示的比例尺仅用于演示排版，不代表真实测量值。'),
             target='scale_bar_enabled', action='select_cell'),
        Step('finish', ('Ready to annotate your own imaging figures', '可以开始为你自己的成像图添加标注了'),
             ('You have added and resized an inset image and enabled a scale bar. Insets also support their own border and scale bar, independent of the host panel\u2019s. Finish keeps this practice tab; replay this lesson anytime from Help → Guided Tutorials.',
              '你已经练习了添加与调整插图大小，以及启用比例尺。插图也可以拥有自己独立的边框和比例尺，与所在面板互不影响。完成后练习页会保留；可随时从“帮助 → 引导教程”重新学习本课。')),
    ),
    'size_groups': (
        Step('intro', ('Keep several panels the same size', '让多个面板保持相同大小'),
             ('These three panels are already loaded (SVG, PNG, TIFF) — a separate practice tab. A Size Group forces its member panels to share one width and height, so editing one (e.g. cropping) does not throw the others out of alignment. This is different from a shared label, which only adds a heading.',
              '这三个面板已经载入完毕（SVG、PNG、TIFF）——独立的练习标签页。“尺寸组”会强制其成员面板共享同一宽度和高度，这样修改其中一个（例如裁剪）也不会打乱其他面板的对齐。这与共享标签不同，共享标签只会添加标题。')),
        Step('create_group', ('Group two panels together', '将两个面板归入一组'),
             ('Click Create group below (this selects two panels, like Ctrl+click, then applies the group). In real use: select two or more panels, right-click → Create Size Group. A group starts in auto mode — its size follows the smallest member — until you pin an exact size in the next step.',
              '点击下方“创建组”（会先像 Ctrl+点选一样选中两个面板，再创建分组）。实际使用时：选中两个或更多面板，右键 → 创建尺寸组。分组创建后默认处于自动模式——尺寸跟随成员中最小的一个——直到下一步你固定一个精确尺寸。'),
             action='create_size_group'),
        Step('pin_size', ('Pin an exact shared size', '固定统一尺寸'),
             ('Click Select a panel below. In the Inspector\u2019s Sync Size Group section, set Pinned W (and H) to a specific value in millimetres — every member panel snaps to it immediately. Set either back to 0 to return that dimension to automatic.',
              '点击下方“选中面板”。在检查器的“尺寸同步组”部分，将“固定宽度”（和“固定高度”）设为具体的毫米数值——所有成员面板会立即统一为该尺寸。将其中一项改回 0 即可恢复该维度的自动模式。'),
             target='size_group_pinned_w', action='select_cell'),
        Step('add_member', ('Add a third panel to the group', '将第三个面板加入组'),
             ('Click Add third panel below. In real use: select the panel(s) to add, right-click → Add to Size Group → pick the group by name. A group can have any number of members, and a panel can only belong to one group at a time.',
              '点击下方“添加第三个面板”。实际使用时：选中要加入的面板，右键 → 添加到尺寸组 → 按名称选择目标组。一个组可以包含任意数量的成员，但每个面板同一时间只能属于一个组。'),
             action='add_to_size_group'),
        Step('finish', ('Ready to keep your own panels aligned', '可以开始统一你自己的面板尺寸了'),
             ('You created a Size Group, pinned an exact shared size, and added a third member. Right-click a grouped panel → Remove from Size Group to unlink it; the Inspector\u2019s Delete Group button removes the group entirely (members keep their current size). Finish keeps this practice tab; replay this lesson anytime from Help → Guided Tutorials.',
              '你已经练习了创建尺寸组、固定统一尺寸，以及添加第三个成员。右键已分组的面板 → “从尺寸组移除”可解除关联；检查器中的“删除组”按钮可整体删除该组（成员会保留当前尺寸）。完成后练习页会保留；可随时从“帮助 → 引导教程”重新学习本课。')),
    ),
}


_LESSON_TITLES = {
    'first_figure':      ('Basic function',      '基础功能'),
    'text_sizes':         ('Match text sizes',               '统一文字大小'),
    'arrange_panels':     ('Arrange panels',                 '排布面板'),
    'labels_titles':      ('Labels and shared titles',       '标注与共享标题'),
    'publication':        ('Prepare for publication',        '发表前准备'),
    'insets_scale_bars':  ('Insets and scale bars',          '插图与比例尺'),
    'size_groups':        ('Size groups',                    '尺寸组'),
}


def lesson_title(key):
    return text(*_LESSON_TITLES[key])


def _sample_svg(index, font_px, series):
    """Synthetic single-panel chart. ``font_px`` is source-pixel type size:
    the balanced lesson uses one value so the composed figure reads evenly,
    while the text lesson deliberately mixes sizes for the user to unify."""
    points = ' '.join(f'{115 + step * 99} {370 - value}' for step, value in enumerate(series))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="480" viewBox="0 0 720 480">
<rect width="720" height="480" fill="white"/>
<path d="M100 110 V370 H630" stroke="#444" fill="none" stroke-width="3"/>
<polyline points="{points}" stroke="#0891b2" fill="none" stroke-width="5"/>
<g font-family="Arial" fill="#222" font-size="{font_px}">
<text id="title" x="110" y="60">DEMO {index} - synthetic data</text>
<text id="time" x="320" y="430">Time</text>
<text id="response" x="125" y="105">Response</text>
<text id="zero" x="90" y="405">0</text>
<text id="ten" x="590" y="405">10</text>
</g></svg>'''


def _sample_micrograph(variant):
    """Synthetic dark-background 'imaging' panel for the insets/scale-bar
    lesson. Unlike the white-background charts used elsewhere, this has no
    light area for a (default white) scale bar to disappear into."""
    palettes = {
        0: ('#2a6f4a', '#5fbf8f', '#1f4f6b', '#4fa0c8'),
        1: ('#6b3f8f', '#b384dd', '#8f5a1f', '#e0a94f'),
        2: ('#1f6b5a', '#4fd6b8', '#6b1f3f', '#d64f7a'),
    }
    outer, inner, outer2, inner2 = palettes[variant % len(palettes)]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="480" viewBox="0 0 720 480">
<rect width="720" height="480" fill="#0c0c0c"/>
<circle cx="300" cy="230" r="120" fill="{outer}"/>
<circle cx="300" cy="230" r="60" fill="{inner}"/>
<circle cx="490" cy="150" r="55" fill="{outer2}"/>
<circle cx="490" cy="150" r="25" fill="{inner2}"/>
</svg>'''


def _sample_pip_icon():
    """Bold, high-contrast content for the guided 'Add inset' action.
    A line chart (like the other panel samples) turns into an unreadable
    smudge shrunk to a small inset; a single thick shape stays legible."""
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="480" viewBox="0 0 480 480">
<rect width="480" height="480" fill="#f4a300"/>
<circle cx="240" cy="240" r="170" fill="#ffffff" stroke="#1a1a1a" stroke-width="18"/>
<rect x="60" y="210" width="360" height="60" fill="#1a1a1a"/>
</svg>'''


def pip_icon_path() -> str:
    """Path to the shared PiP-inset sample (created once, reused after)."""
    root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'tutorial-samples-v2'
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'pip-icon.svg'
    if not path.exists():
        _write_bytes(path, _sample_pip_icon().encode('utf-8'))
    return str(path)


def _write_bytes(path, data):
    output = QSaveFile(str(path))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly) or output.write(data) != len(data) or not output.commit():
        raise OSError(output.errorString())


def _render_raster(svg, path, fmt):
    """Rasterise *svg* and save it as *fmt*. Pillow writes the file so the
    tutorial does not depend on optional Qt image-format plugins."""
    renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
    if not renderer.isValid():
        raise OSError('Could not render tutorial sample')
    image = QImage(1440, 960, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise OSError('Could not encode tutorial sample')
    buffer.close()
    from PIL import Image as PilImage
    temporary = path.with_name(path.name + '.part')
    try:
        with PilImage.open(BytesIO(bytes(buffer.data()))) as decoded:
            decoded.convert('RGB').save(temporary, fmt)
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def make_samples():
    """Create the practice images once and return them per lesson.

    Formats are deliberately mixed so the lessons show that panels can come
    from vector and raster sources at the same time. Files live in the app's
    local data directory, not a temporary folder, so a saved practice project
    keeps working references.
    """
    root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'tutorial-samples-v2'
    root.mkdir(parents=True, exist_ok=True)
    # (filename, source svg, raster format or None for vector)
    specs = (
        ('panel-1.svg', _sample_svg(1, 34, (45, 80, 60, 175, 200, 235)), None),
        ('panel-2.png', _sample_svg(2, 34, (60, 95, 140, 120, 205, 250)), 'PNG'),
        ('panel-3.tiff', _sample_svg(3, 34, (30, 70, 105, 160, 150, 215)), 'TIFF'),
        ('text-panel-1.svg', _sample_svg(1, 20, (45, 80, 60, 175, 200, 235)), None),
        ('text-panel-2.svg', _sample_svg(2, 30, (60, 95, 140, 120, 205, 250)), None),
        ('text-panel-3.png', _sample_svg(3, 26, (30, 70, 105, 160, 150, 215)), 'PNG'),
        ('micrograph-1.svg', _sample_micrograph(0), None),
        ('micrograph-2.svg', _sample_micrograph(1), None),
        ('micrograph-3.svg', _sample_micrograph(2), None),
    )
    created = {}
    for name, svg, fmt in specs:
        path = root / name
        if not path.exists():
            if fmt is None:
                _write_bytes(path, svg.encode('utf-8'))
            else:
                _render_raster(svg, path, fmt)
        created[name] = str(path)
    base = [created['panel-1.svg'], created['panel-2.png'], created['panel-3.tiff']]
    return {
        'first_figure': base,
        'text_sizes': [created['text-panel-1.svg'], created['text-panel-2.svg'], created['text-panel-3.png']],
        # These three lessons focus on layout, labelling, and export — not on
        # importing — so they reuse the same mixed-format set already loaded,
        # rather than repeating the "Load samples" teaching moment.
        'arrange_panels': base,
        'labels_titles': base,
        'publication': base,
        # Dark-background mocks so the (default white) scale bar has no
        # light margin to disappear into — the panel samples above are all
        # white-background charts.
        'insets_scale_bars': [created['micrograph-1.svg'], created['micrograph-2.svg'], created['micrograph-3.svg']],
        'size_groups': base,
    }


class TutorialHighlight(QWidget):
    """Outline drawn over the control a step refers to.

    ``compact`` marks small controls — toolbar buttons, menu rows — which get
    breathing room around the outline and the fade-and-contract entrance.
    A button is hosted by its window so the outline can sit outside the
    button's own bounds; menus and large areas host it themselves.
    """

    # Padding around a compact control, the settled distance of the outline
    # outside it, and how much further out the entrance starts. MARGIN must
    # cover GAP + LIFT + the pen width, or the widest frame gets clipped.
    MARGIN = 12
    GAP = 3
    LIFT = 6

    def __init__(self, target, compact=False):
        self.is_button = isinstance(target, QAbstractButton)
        self.compact = compact or self.is_button
        # Compact controls host the outline on their window so the ring can
        # sit outside the control instead of being clipped to it. A popup
        # menu is its own window, so its rows stay inside the popup.
        self.host = target.window() if self.compact else target
        super().__init__(self.host)
        self.target = target
        self.margin = self.MARGIN if self.compact else 0
        self._started = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet('background: transparent; border: none;')
        self.strength = MotionTween(self)
        self.settle = MotionTween(self)
        for tween in (self.strength, self.settle):
            tween.updated.connect(lambda _: self.update())
        self._rect = target.rect()
        target.installEventFilter(self)
        target.destroyed.connect(self.deleteLater)

    def set_target_rect(self, rect):
        self._rect = QRect(rect)
        mapped = QRect(self.target.mapTo(self.host, rect.topLeft()), rect.size())
        if self.compact:
            mapped = mapped.adjusted(-self.margin, -self.margin, self.margin, self.margin)
            mapped = mapped.intersected(self.host.rect())
        self.setGeometry(mapped)
        if not self._started:
            self._started = True
            self.show()
            self.strength.set_target(1.0, 180)
            self.settle.set_target(1.0, 180 if self.compact else 0, spatial=True)

    def eventFilter(self, obj, event):
        if obj is self.target:
            if event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
                self.set_target_rect(self._rect if self.compact else self.target.rect())
            elif event.type() == QEvent.Type.Hide:
                self.hide()
        return False

    def outline_rect(self):
        """Frame in local coordinates.

        Settled, it sits ``GAP`` outside the control so it reads as a ring
        around it rather than tracing the control's own border — on a filled
        accent button an on-border outline is invisible.
        """
        if not self.compact:
            return QRectF(self.rect()).adjusted(2, 2, -2, -2)
        inset = self.margin - self.GAP
        expansion = self.LIFT * (1 - self.settle.value)
        return QRectF(self.rect()).adjusted(inset - expansion, inset - expansion,
                                           expansion - inset, expansion - inset)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.palette().color(QPalette.ColorRole.Highlight))
        color.setAlpha(round(230 * self.strength.value))
        painter.setPen(QPen(color, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.outline_rect(), 5, 5)


class TutorialStatus(QLabel):
    def __init__(self):
        super().__init__()
        self.success = False
        self.reveal = MotionTween(self)
        self.reveal.updated.connect(lambda _: self.update())
        self.setContentsMargins(34, 8, 10, 8)

    def set_success(self, success, animate=False):
        if self.success == success:
            return
        self.success = success
        self.reveal.set_target(0.0, 0)
        if success:
            self.reveal.set_target(1.0, 160 if animate else 0)
        self.update()

    def paintEvent(self, event):
        if self.success:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
            color = QColor('#4ade80' if dark else '#15803d')
            fill = QColor(color)
            fill.setAlpha(round(24 * self.reveal.value))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)
            color.setAlpha(round(255 * self.reveal.value))
            painter.setPen(QPen(color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            y = self.height() / 2
            tick = QPainterPath()
            tick.moveTo(12, y)
            tick.lineTo(17, y + 5)
            tick.lineTo(25, y - 5)
            painter.drawPath(tick)
            painter.end()
        super().paintEvent(event)


class TutorialCard(QDialog):
    def __init__(self, controller):
        super().__init__(controller.window, Qt.WindowType.Tool)
        self.controller = controller
        self.setWindowTitle(tr('tutorials_title'))
        self.setMinimumWidth(360)
        self.resize(420, 300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.heading = QLabel()
        self.heading.setWordWrap(True)
        font = self.heading.font()
        font.setBold(True)
        self.heading.setFont(font)
        layout.addWidget(self.heading)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setMinimumHeight(130)
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)
        self.status = TutorialStatus()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.action = QPushButton()
        self.action.clicked.connect(controller.perform_action)
        layout.addWidget(self.action)
        row = QHBoxLayout()
        self.back = QPushButton()
        self.skip = QPushButton()
        self.next = QPushButton()
        self.exit = QPushButton()
        for button in (self.back, self.skip, self.next, self.exit):
            button.setAutoDefault(False)
            row.addWidget(button)
        self.back.clicked.connect(controller.back)
        self.skip.clicked.connect(controller.skip)
        self.next.clicked.connect(controller.next)
        self.exit.clicked.connect(controller.stop)
        layout.addLayout(row)

    def closeEvent(self, event):
        self.controller.stop()
        event.accept()

    def reject(self):
        self.controller.stop()


class TutorialController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.tab = None
        self.previous_tab = None
        self.lesson = None
        self.index = 0
        self.skipped = set()
        self.actions = set()
        self.original_seen = False
        self._reposition_baseline = None
        self._rename_baseline = None
        self._pip_baseline = None
        self.highlight = None
        self.card = TutorialCard(self)
        self._feedback_step = None
        self._step_ready = None
        self.center = None
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        window._act_auto_layout.triggered.connect(self._layout_triggered)
        for name in ('_act_export_pdf', '_act_export_tiff', '_act_export_png',
                    '_act_export_jpg', '_act_export_svg'):
            getattr(window, name).triggered.connect(self._export_triggered)

    @property
    def step(self):
        return LESSONS[self.lesson][self.index]

    def _active_step_action(self, key):
        """True when the practice tab is active and on the named step —
        the shared guard for signal-driven readiness (Auto Layout, Export)."""
        return bool(self.tab) and self.window.project is self.tab.project and self.step.key == key

    def _layout_triggered(self):
        if self._active_step_action('layout'):
            self.actions.add('layout')
            self.refresh()

    def _export_triggered(self):
        # Any export format counts: this step is about discovering the menu,
        # not about which format is chosen or whether the dialog is confirmed.
        if self._active_step_action('export'):
            self.actions.add('export')
            self.refresh()

    def _select_cells(self, *indices):
        """Select practice-tab cells by index, as Ctrl+click would on canvas."""
        self.tab.scene.clearSelection()
        for i in indices:
            item = self.tab.scene.cell_items.get(self.tab.project.cells[i].id)
            if item is not None:
                item.setSelected(True)
        self.window._on_selection_changed()

    def show_center(self):
        if self.center and not sip.isdeleted(self.center):
            self.center.close()
            self.center.deleteLater()
        self.center = QDialog(self.window)
        self.center.setWindowTitle(tr('tutorials_title'))
        self.center.resize(460, 300)
        layout = QVBoxLayout(self.center)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        intro = QLabel(text('Learn with synthetic sample figures. Each lesson opens a separate practice tab. Your existing projects are not replaced. You can exit at any step and replay lessons anytime.',
                            '使用合成示例图学习。每个教程会打开独立练习页，不会替换已有工程。可随时退出或重新学习。'))
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(intro)
        for key in LESSONS:
            status = self.window._settings.value(f'tutorials/v1/{key}', '')
            suffix = text(' — completed', ' — 已完成') if status == 'completed' else text(' — explored', ' — 已浏览') if status == 'explored' else ''
            button = QPushButton(lesson_title(key) + suffix)
            button.clicked.connect(lambda checked=False, lesson=key: self.start(lesson))
            layout.addWidget(button)
        if self.tab:
            resume = QPushButton(text('Return to active lesson', '返回当前教程'))
            resume.clicked.connect(self.resume)
            layout.addWidget(resume)
        close = QPushButton(tr('help_close'))
        close.clicked.connect(self.center.close)
        layout.addWidget(close)
        self.center.show()
        self.center.raise_()

    def start(self, lesson):
        if lesson not in LESSONS:
            raise ValueError(lesson)
        try:
            paths = make_samples()[lesson]
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.window, tr('tutorials_title'), text('Unable to prepare practice images: ', '无法准备练习图片：') + str(error))
            return
        self.stop()
        self.window._dismiss_welcome()
        self.previous_tab = self.window._tabs[self.window._active_tab_idx]
        self.lesson = lesson
        self.paths = paths
        self.index = 0
        self.actions = set()
        self.skipped = set()
        self.original_seen = False
        self._reposition_baseline = None
        self._rename_baseline = None
        self._pip_baseline = None
        if lesson == 'first_figure':
            # Starts exactly like a real new project (File → New's 2×2
            # grid), not a pre-built row — the lesson's own first steps
            # teach deleting the second row and adding a third cell to
            # reach the one-row-of-three layout the rest of the lesson uses.
            self.window._on_new_tab()
            self.tab = self.window._tabs[self.window._active_tab_idx]
            project = self.tab.project
        else:
            project = Project(name=tr('tutorials_practice') + ' — ' + lesson_title(lesson), page_width_mm=180, page_height_mm=72,
                              margin_left_mm=6, margin_right_mm=6, margin_top_mm=6, margin_bottom_mm=6, gap_mm=3.5, dpi=300)
            # Label size is a scale in this app, not typographic points: one unit
            # is roughly 1.8 mm of glyph box. The default 12 would draw ~22 mm
            # letters across a 54 mm panel, so the lesson would teach a figure no
            # journal would accept. 2 puts the bold letters just above the sample
            # charts' own axis text.
            project.label_font_size = 2
            project.title_label_font_size = 2
            project.rows = [RowTemplate(index=0, column_count=len(paths))]
            project.cells = [Cell(row_index=0, col_index=i, image_path=path, is_placeholder=False)
                             for i, path in enumerate(paths)]
            if lesson == 'insets_scale_bars':
                # These panels are dark end-to-end (see _sample_micrograph),
                # so any letterboxing from a column/image aspect mismatch
                # would show as a light gap — exactly where a default white
                # scale bar would then be invisible. Auto Layout sizes each
                # column to its image's aspect ratio, eliminating it.
                from src.app.commands import AutoLayoutCommand
                AutoLayoutCommand(project).redo()
            self.tab = self.window._create_tab(project)
        self._practice_project = project
        self._cell_ids = [cell.id for cell in project.cells]
        self.tab.tutorial_title = tr('tutorials_practice') + ' — ' + lesson_title(lesson)
        self.tab.undo_stack.resetClean()
        self.window._update_window_title()
        self.window.view.zoom_to_fit()
        if self.center:
            self.center.close()
        self.refresh()
        self.card.show()
        area = self.window.screen().availableGeometry()
        self.card.move(max(area.left(), area.right() - self.card.width() - 24),
                       max(area.top(), area.bottom() - self.card.height() - 48))
        self.card.raise_()
        self.timer.start()
        self.refresh()

    def resume(self):
        if self.tab in self.window._tabs:
            self.window._activate_tab(self.window._tabs.index(self.tab))
            self.card.show()
            self.card.raise_()
        if self.center:
            self.center.close()
        self.refresh()

    def _inspector(self, cell):
        return next((win for win in self.window._text_inspector_windows()
                     if win.isVisible() and win.project is self.tab.project
                     and getattr(win, '_cell', None) is cell), None)

    def _shared_groups(self):
        paths = {self.tab.project.cells[0].image_path, self.tab.project.cells[1].image_path}
        return [group for group in self.tab.project.svg_text_groups
                if abs(group.font_size_pt - 9.0) < 0.01 and paths <= {member.svg_path for member in group.members}]

    def valid(self):
        if (self.tab is None or self.tab not in self.window._tabs
                or self.tab.project is not self._practice_project):
            return False
        if self.lesson == 'first_figure':
            # This lesson's own 'delete_row'/'add_cell' steps deliberately
            # shrink and then grow the cell set (2x2 grid -> one row of
            # three), so the practice-project identity check above is the
            # only safety net that applies here.
            return True
        return [cell.id for cell in self.tab.project.cells] == self._cell_ids

    def ready(self):
        if not self.valid():
            return False
        key = self.step.key
        project = self.tab.project
        if key in ('intro', 'finish'):
            return True
        if key == 'delete_row':
            return len(project.rows) == 1
        if key == 'add_cell':
            return len(project.cells) == 3
        if key == 'load':
            return all(cell.image_path for cell in project.cells)
        if key == 'layout':
            return 'layout' in self.actions
        if key == 'labels':
            return any(item.subtype == 'numbering' for item in project.text_items)
        if key == 'label_size':
            inspector = self.window.inspector
            return (inspector._current_item_type == 'text'
                    and inspector.text_group.isVisible()
                    and not inspector.text_group._collapsed
                    and inspector.font_size.isVisible())
        if key == 'save':
            return bool(self.tab.path) and self.tab.undo_stack.isClean()
        if key == 'preview':
            return self.tab.scene.preview_mode
        if key == 'svg_open':
            return self._inspector(project.cells[0]) is not None
        if key == 'svg_assign':
            return any(abs(group.font_size_pt - 9.0) < 0.01 and any(member.svg_path == project.cells[0].image_path for member in group.members)
                       for group in project.svg_text_groups)
        if key == 'svg_shared':
            return bool(self._shared_groups())
        if key == 'raster_detect':
            return bool(project.cells[2].raster_text_regions)
        if key == 'raster_assign':
            ids = {group.id for group in self._shared_groups()}
            return any(region.enabled and region.group_id in ids for region in project.cells[2].raster_text_regions)
        if key == 'review':
            inspector = self._inspector(project.cells[2])
            if inspector:
                if inspector._chk_original.isChecked():
                    self.original_seen = True
                return self.original_seen and not inspector._chk_original.isChecked()
            return False
        # arrange_panels
        if key == 'split':
            # >= 2, not == 2: "Split into N" with N>2 also satisfies the step.
            return len(project.cells[2].children) >= 2
        if key == 'ratio':
            parent = project.cells[2]
            # 0.05, not 0.1: the Inspector ratio field steps by 0.1, and a
            # boundary check at exactly one step would accept or reject a
            # single click depending on float noise.
            return len(parent.split_ratios) >= 2 and abs(parent.split_ratios[0] - parent.split_ratios[1]) > 0.05
        if key == 'swap':
            return project.cells[0].image_path == self.paths[1] and project.cells[1].image_path == self.paths[0]
        if key == 'crop':
            cell = project.cells[0]
            return (cell.crop_left, cell.crop_top, cell.crop_right, cell.crop_bottom) != (0.0, 0.0, 1.0, 1.0)
        if key == 'fit_mode':
            cell = project.cells[0]
            return cell.fit_mode != 'contain' or cell.align_h != 'center' or cell.align_v != 'center'
        if key == 'freeform':
            return getattr(project, 'layout_mode', 'grid') == 'freeform'
        if key == 'reposition':
            cell = project.cells[0]
            current = (cell.freeform_x_mm, cell.freeform_y_mm, cell.freeform_w_mm, cell.freeform_h_mm)
            if self._reposition_baseline is None:
                # Captured lazily so a user who selected and moved the panel
                # without the guided button still gets a before/after check.
                self._reposition_baseline = current
                return False
            return any(abs(a - b) > 0.5 for a, b in zip(current, self._reposition_baseline))
        # labels_titles
        if key == 'panel_letters':
            return any(item.subtype == 'numbering' for item in project.text_items)
        if key == 'shared_top':
            return any(g.side == 'top' for g in project.group_labels)
        if key == 'shared_row':
            return any(g.side in ('left', 'right') for g in project.group_labels)
        if key == 'rename':
            label = next((g for g in project.group_labels if g.side == 'top'), None)
            if label is None:
                return False
            if self._rename_baseline is None:
                # Same lazy baseline as 'reposition': manual renames count too.
                self._rename_baseline = label.text
                return False
            return label.text != self._rename_baseline
        # publication
        if key == 'dpi':
            return project.dpi != 300
        if key == 'export_region':
            return project.export_region is not None
        if key == 'export':
            return 'export' in self.actions
        if key == 'verify':
            return self.tab.scene.preview_mode
        # insets_scale_bars
        if key == 'add_inset':
            return any(p.pip_type == 'external' for c in project.cells for p in c.pip_items)
        if key == 'resize_inset':
            pip = next((p for c in project.cells for p in c.pip_items if p.pip_type == 'external'), None)
            if pip is None:
                return False
            current = (pip.x, pip.y, pip.w, pip.h)
            if self._pip_baseline is None:
                # Captured lazily so a user who resized/moved it on the
                # canvas without the guided button still gets a before/after
                # check, matching 'reposition'/'rename'.
                self._pip_baseline = current
                return False
            return any(abs(a - b) > 0.005 for a, b in zip(current, self._pip_baseline))
        if key == 'scale_bar':
            return project.cells[0].scale_bar_enabled
        # size_groups
        if key == 'create_group':
            return bool(project.size_groups) and any(c.size_group_id for c in project.cells)
        if key == 'pin_size':
            return bool(project.size_groups) and project.size_groups[0].pinned_width_mm > 0
        if key == 'add_member':
            return bool(project.size_groups) and project.cells[2].size_group_id == project.size_groups[0].id
        return False

    def _clear_highlight(self):
        if self.highlight and not sip.isdeleted(self.highlight):
            self.highlight.hide()
            self.highlight.deleteLater()
        self.highlight = None

    @staticmethod
    def _menu_holds(menu, action):
        for candidate in menu.actions():
            if candidate is action:
                return True
            sub = candidate.menu()
            if sub is not None and TutorialController._menu_holds(sub, action):
                return True
        return False

    def _action_target(self, action):
        """Find the visible control for *action*.

        Not every action has a toolbar button: some live only inside a
        popup (Export Preview sits in the Export button's menu) or a menu
        bar. Point at whatever the user must actually click, and follow the
        action into its popup once that popup is open, so the step never
        degrades into "use the keyboard shortcut".
        """
        if action is None:
            return None, None, False
        for menu in self.window.findChildren(QMenu):
            if menu.isVisible() and action in menu.actions():
                rect = menu.actionGeometry(action)
                if not rect.isEmpty():
                    return menu, rect, True
        widget = self.window.toolbar.widgetForAction(action)
        if widget is not None and widget.isVisible():
            return widget, widget.rect(), True
        for button in self.window.toolbar.findChildren(QToolButton):
            menu = button.menu()
            if button.isVisible() and menu is not None and self._menu_holds(menu, action):
                return button, button.rect(), True
        bar = self.window.menuBar()
        for entry in bar.actions():
            menu = entry.menu()
            if menu is not None and self._menu_holds(menu, action):
                rect = bar.actionGeometry(entry)
                if not rect.isEmpty():
                    return bar, rect, True
        return None, None, False

    #: step.action -> button caption, for actions without a dedicated
    #: default label ('svg0'/'svg1'/'raster' fall back to "Open inspector").
    _ACTION_LABELS = {
        'delete_row': ('Delete second row', '删除第二行'),
        'add_cell': ('Add a third cell', '添加第三个单元格'),
        'load': ('Load samples', '载入示例'),
        'label_size': ('Select a label', '选中标注'),
        'split_cols': ('Split third panel', '拆分第三个面板'),
        'select_subcell': ('Select the new sub-cell', '选中新的子单元格'),
        'swap': ('Swap panels', '交换面板'),
        'select_cell': ('Select a panel', '选中面板'),
        'select_pair': ('Select two panels', '选中两个面板'),
        'select_row': ('Select the row', '选中整行'),
        'select_shared_top': ('Select the shared title', '选中共享标题'),
        'show_project': ('Show project settings', '显示工程设置'),
        'crop_square': ('Crop to square', '裁剪为正方形'),
        'add_pip': ('Add inset', '添加插图'),
        'select_pip': ('Select inset', '选中插图'),
        'create_size_group': ('Create group', '创建组'),
        'add_to_size_group': ('Add third panel', '添加第三个面板'),
    }

    #: target -> Inspector widget attribute name, for steps that highlight a
    #: single field once its section is on screen (visibility is checked by
    #: the caller, since some fields only appear for the right selection).
    _INSPECTOR_TARGETS = {
        'label_size': 'font_size',
        'subcell_ratio': 'subcell_ratio',
        'freeform_x': 'freeform_x',
        'dpi_spin': 'dpi_spin',
        'gl_text_edit': 'gl_text_edit',
        'fit_mode_combo': 'fit_mode_combo',
        'pip_w': 'pip_w',
        'scale_bar_enabled': 'scale_bar_enabled',
        'size_group_pinned_w': 'size_group_pinned_w',
    }

    def _show_target(self):
        target = self.step.target
        widget = self.window.view.viewport()
        rect = widget.rect()
        compact = False
        if target in self._INSPECTOR_TARGETS:
            field = getattr(self.window.inspector, self._INSPECTOR_TARGETS[target])
            if not field.isVisible():
                # Every Inspector section starts collapsed, and selecting an
                # item shows its section without unfolding it — so the field a
                # step points at can be hidden by nothing but a folded header.
                # Expand a section that is shown-but-collapsed; a section that
                # is hidden entirely means the wrong thing is selected, and
                # expanding it cannot help.
                ancestor = field.parentWidget()
                while ancestor is not None and not isinstance(ancestor, CollapsibleSection):
                    ancestor = ancestor.parentWidget()
                if (ancestor is not None and ancestor.isVisible()
                        and ancestor._collapsed):
                    ancestor.set_collapsed(False, animate=False)
            if field.isVisible():
                widget, rect, compact = field, field.rect(), True
        elif target.startswith('group_label_'):
            side = target.rsplit('_', 1)[-1]
            index = ('top', 'bottom', 'left', 'right').index(side)
            found, found_rect, found_compact = self._action_target(
                self.window._group_label_actions[index])
            if found is not None:
                widget, rect, compact = found, found_rect, found_compact
        elif target.startswith('_act_'):
            found, found_rect, found_compact = self._action_target(getattr(self.window, target, None))
            if found is not None:
                widget, rect, compact = found, found_rect, found_compact
        elif target in ('svg0', 'svg1', 'raster'):
            index = {'svg0': 0, 'svg1': 1, 'raster': 2}[target]
            cell = self.tab.project.cells[index]
            inspector = self._inspector(cell)
            if inspector:
                widget = inspector._btn_detect if self.step.key == 'raster_detect' else inspector._chk_original if self.step.key == 'review' else inspector._groups_widget
                rect = widget.rect()
                compact = True
            else:
                item = self.tab.scene.cell_items.get(cell.id)
                if item:
                    rect = self.tab.view.mapFromScene(item.sceneBoundingRect()).boundingRect().intersected(widget.rect())
        if widget is None or not widget.isVisible() or rect.isEmpty():
            self._clear_highlight()
            return
        if (self.highlight is None or sip.isdeleted(self.highlight)
                or self.highlight.target is not widget or self.highlight.compact != compact):
            self._clear_highlight()
            self.highlight = TutorialHighlight(widget, compact)
        self.highlight.set_target_rect(rect)
        self.highlight.show()
        self.highlight.raise_()

    def refresh(self):
        if self.tab is None:
            return
        if not self.valid():
            self.stop()
            self.window.statusBar().showMessage(text('Tutorial ended because the practice tab was closed or its layout was replaced. Replay it from Help → Guided Tutorials.',
                                                    '练习页已关闭或布局已改变，教程已结束。可从“帮助 → 引导教程”重新开始。'), 8000)
            return
        active = self.window.project is self.tab.project
        step_id = (self.lesson, self.index)
        if step_id != self._feedback_step:
            self._feedback_step = step_id
            self._step_ready = None
            self.card.status.set_success(False)
            self._clear_highlight()
        self.card.setWindowTitle(tr('tutorials_title'))
        self.card.heading.setText(f'{lesson_title(self.lesson)} — {self.index + 1}/{len(LESSONS[self.lesson])}\n' + text(*self.step.title))
        body = text(*self.step.body)
        if self.card.body.text() != body:
            self.card.body.setText(body)
            self.card.scroll.verticalScrollBar().setValue(0)
        ready = active and self.ready()
        success = ready and self.step.key not in ('intro', 'finish')
        self.card.status.set_success(success, animate=success and self._step_ready is False)
        if active:
            self._step_ready = ready
        self.card.status.setText(text('Return to the practice tab to continue.', '请返回练习标签页继续。') if not active else
                                 text('Step complete — well done. Continue when ready.', '本步骤已完成，做得好。准备好后可继续。') if success else
                                 text('Ready — continue when you are comfortable.', '已就绪，准备好后可继续。') if ready else
                                 text('Try the action above, or skip this step.', '请尝试上述操作，或跳过此步骤。'))
        self.card.back.setText(text('Back', '上一步'))
        self.card.skip.setText(text('Skip', '跳过'))
        self.card.next.setText(text('Finish', '完成') if self.step.key == 'finish' else text('Next', '下一步'))
        self.card.exit.setText(text('Exit', '退出'))
        self.card.back.setEnabled(active and self.index > 0)
        self.card.skip.setEnabled(active and self.step.key != 'finish')
        self.card.next.setEnabled(ready)
        self.card.action.setVisible(bool(self.step.action))
        self.card.action.setEnabled(active)
        self.card.action.setText(text(*self._ACTION_LABELS.get(
            self.step.action, ('Open inspector', '打开检查器'))))
        if active:
            self._show_target()
        else:
            self._clear_highlight()

    def perform_action(self):
        if not self.valid() or self.window.project is not self.tab.project:
            return
        action = self.step.action
        if action == 'delete_row':
            from src.app.commands import DeleteRowCommand
            project = self.tab.project
            if len(project.rows) > 1:
                self.tab.undo_stack.push(DeleteRowCommand(
                    project, 1, update_callback=self.window._refresh_and_update))
        elif action == 'add_cell':
            from src.app.commands import InsertCellCommand
            project = self.tab.project
            row = next((r for r in project.rows if r.index == 0), None)
            if row is not None and len(project.cells) < 3:
                self.tab.undo_stack.push(InsertCellCommand(
                    project, 0, row.column_count, update_callback=self.window._refresh_and_update))
        elif action == 'load':
            from src.app.commands import DropImageCommand
            if any(cell.image_path for cell in self.tab.project.cells):
                return
            stack = self.tab.undo_stack
            stack.beginMacro(text('Load tutorial samples', '载入教程示例'))
            try:
                for cell, path in zip(self.tab.project.cells, self.paths):
                    stack.push(DropImageCommand(cell, path, self.window._refresh_and_update))
            finally:
                stack.endMacro()
        elif action == 'label_size':
            label = next((item for item in self.tab.project.text_items
                          if item.subtype == 'numbering'), None)
            graphics = self.tab.scene.text_items.get(label.id) if label else None
            if graphics is None:
                return
            self.tab.scene.clearSelection()
            graphics.setSelected(True)
            self.window._on_selection_changed()
            # The inspector collapses every section at startup, so reveal the
            # one holding the size field instead of leaving the user hunting.
            self.window.inspector.text_group.set_collapsed(False, animate=False)
            self.window.inspector.text_group.show()
        elif action in ('svg0', 'svg1', 'raster'):
            cell = self.tab.project.cells[{'svg0': 0, 'svg1': 1, 'raster': 2}[action]]
            inspector = self._inspector(cell)
            if inspector:
                inspector.raise_()
                inspector.activateWindow()
            elif action == 'raster':
                self.window._on_open_raster_text_inspector(cell.image_path, cell)
            else:
                self.window._on_open_svg_text_inspector(cell.image_path, cell)
        # ── arrange_panels ──
        elif action == 'split_cols':
            from src.app.commands import SplitCellCommand
            target_cell = self.tab.project.cells[2]
            if target_cell.children:
                return
            self.tab.undo_stack.push(SplitCellCommand(
                self.tab.project, target_cell.id, 'horizontal', count=2,
                update_callback=self.window._refresh_and_update))
        elif action == 'select_subcell':
            parent = self.tab.project.cells[2]
            if len(parent.children) < 2:
                return
            item = self.tab.scene.cell_items.get(parent.children[1].id)
            if item is None:
                return
            self.tab.scene.clearSelection()
            item.setSelected(True)
            self.window._on_selection_changed()
            # Selecting shows the section but leaves it folded; unfold so the
            # highlighted ratio field is actually on screen.
            self.window.inspector.subcell_group.set_collapsed(False, animate=False)
            self.window.inspector.subcell_group.show()
        elif action == 'swap':
            from src.app.commands import SwapCellsCommand
            first, second = self.tab.project.cells[0], self.tab.project.cells[1]
            if first.image_path == self.paths[1] and second.image_path == self.paths[0]:
                return  # Already swapped — a second click would swap back.
            self.tab.undo_stack.push(SwapCellsCommand(
                first, second, self.tab.project, self.window._refresh_and_update))
        elif action == 'select_cell':
            cell = self.tab.project.cells[0]
            item = self.tab.scene.cell_items.get(cell.id)
            if item is None:
                return
            self.tab.scene.clearSelection()
            # A PiP selected earlier in this same cell (insets_scale_bars)
            # would otherwise keep routing the inspector to item_type='pip'
            # even after this cell is (re)selected.
            if hasattr(item, 'deselect_pip'):
                item.deselect_pip()
            item.setSelected(True)
            self.window._on_selection_changed()
            self.window.inspector.cell_group.set_collapsed(False, animate=False)
            self.window.inspector.cell_group.show()
            # Baseline for "did the user actually move it" in ready().
            self._reposition_baseline = (cell.freeform_x_mm, cell.freeform_y_mm,
                                         cell.freeform_w_mm, cell.freeform_h_mm)
        elif action == 'crop_square':
            cell = self.tab.project.cells[0]
            if not cell.image_path:
                return
            self.window._ctx_crop_to_aspect(cell.id, 1, 1)
        elif action == 'add_pip':
            from src.app.commands import AddPiPItemCommand
            from src.model.data_model import PiPItem
            project = self.tab.project
            if any(p.pip_type == 'external' for c in project.cells for p in c.pip_items):
                return
            cell = project.cells[0]
            pip = PiPItem(pip_type='external', image_path=pip_icon_path(), show_origin_box=False)
            self.tab.undo_stack.push(AddPiPItemCommand(cell, pip, self.window._refresh_and_update))
        elif action == 'select_pip':
            owner, pip = None, None
            for c in self.tab.project.cells:
                pip = next((p for p in c.pip_items if p.pip_type == 'external'), None)
                if pip:
                    owner = c
                    break
            if owner is None or pip is None:
                return
            item = self.tab.scene.cell_items.get(owner.id)
            if item is None:
                return
            self.tab.scene.clearSelection()
            item.setSelected(True)
            item.select_pip(pip.id, resize=True)
            self.window._on_selection_changed()
            # Baseline for "did the user actually resize/move it" in ready().
            self._pip_baseline = (pip.x, pip.y, pip.w, pip.h)
        elif action == 'create_size_group':
            if self.tab.project.size_groups:
                return
            self._select_cells(0, 1)
            self.window._on_size_group_create_from_selection()
        elif action == 'add_to_size_group':
            project = self.tab.project
            if not project.size_groups:
                return
            group_id = project.size_groups[0].id
            if project.cells[2].size_group_id == group_id:
                return
            self._select_cells(2)
            self.window._on_size_group_add_to_existing(group_id)
        # ── labels_titles ──
        elif action == 'select_pair':
            self._select_cells(0, 1)
        elif action == 'select_row':
            self._select_cells(0, 1, 2)
        elif action == 'select_shared_top':
            label = next((g for g in self.tab.project.group_labels if g.side == 'top'), None)
            if label is None:
                return
            item = self.tab.scene.group_label_items.get(label.id)
            if item is None:
                return
            self.tab.scene.clearSelection()
            item.setSelected(True)
            self.window._on_selection_changed()
            self._rename_baseline = label.text
        # ── publication ──
        elif action == 'show_project':
            # Deselecting reveals Project Settings in the Inspector; the
            # section still starts folded, so unfold it for the highlight.
            self.tab.scene.clearSelection()
            self.window._on_selection_changed()
            self.window.inspector.project_group.set_collapsed(False, animate=False)
            self.window.inspector.project_group.show()
        self.refresh()

    def back(self):
        if self.tab and self.window.project is self.tab.project and self.index:
            self.index -= 1
            self.refresh()

    def skip(self):
        if self.tab and self.window.project is self.tab.project and self.index < len(LESSONS[self.lesson]) - 1:
            self.skipped.add(self.step.key)
            self.index += 1
            self.refresh()

    def next(self):
        if not self.tab or self.window.project is not self.tab.project or not self.ready():
            return
        self.skipped.discard(self.step.key)
        if self.step.key == 'finish':
            key = f'tutorials/v1/{self.lesson}'
            if self.window._settings.value(key) != 'completed':
                self.window._settings.setValue(key, 'explored' if self.skipped else 'completed')
            self.stop()
        else:
            self.index += 1
            self.refresh()

    def stop(self):
        self.timer.stop()
        self._clear_highlight()
        self.card.hide()
        self.card.status.set_success(False)
        self._feedback_step = None
        self._step_ready = None
        previous, practice = self.previous_tab, self.tab
        self.tab = None
        self.previous_tab = None
        if practice and practice.project is not self._practice_project and hasattr(practice, 'tutorial_title'):
            del practice.tutorial_title
            self.window._update_window_title()
        if practice and self.window.project is self._practice_project and previous in self.window._tabs:
            self.window._activate_tab(self.window._tabs.index(previous))
