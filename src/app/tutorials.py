from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import (
    QBuffer, QByteArray, QCoreApplication, QEvent, QIODevice, QObject, QPoint,
    QRect, QRectF, QSaveFile, QSize, QStandardPaths, Qt, QTimer,
)
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QMessageBox,
    QScrollArea, QAbstractButton, QMenu, QToolButton, QFrame, QSizePolicy,
    QStyle, QStyleOptionButton, QStylePainter,
)

from src.app.commands import DropImageCommand
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
        Step('intro', ('Rows, cells, and your first figure', '先认识行与单元格'),
             ('ILM combines existing images into one figure. In grid mode, build rows first, then place cells from left to right within each row. A cell is a slot for an image; \u201ccolumns\u201d means the cells across that row. Different rows can have different numbers of cells. An image in the finished figure is often called a panel.\n\nFor this lesson, we will put three supplied sample charts side by side: one SVG, one PNG, and one TIFF. Three cells let us try these formats together; your own figure can have any layout you need.\n\nThis is a separate practice tab with synthetic data. Your other projects are untouched.',
              'ILM 用于把已有图片组合成一张图。网格布局先分行，再在每一行中从左到右放置单元格。单元格是放图片的格子；界面里的“列数”就是这一行有几个单元格，各行的数量可以不同。组合图中的每一幅图片也称为面板。\n\n本课要把三张自带的示例图并排放在一行：SVG、PNG、TIFF 各一张。因此准备三个单元格，练习混合使用不同格式；你自己的图不必采用这个布局。\n\n这是使用合成数据的独立练习页，不会改动其他工程。')),
        Step('delete_row', ('Keep one row for the three samples', '为三张示例图保留一行'),
             ('Look at the canvas: a new project starts with two rows, each containing two empty cells. Our side-by-side example uses only the top row, so remove the empty lower row first.\n\nRight-click either cell in the second row \u2192 Delete \u2192 This Row, or click Delete second row below. Afterwards, you should see one row with two cells. Deleting a row removes all its cells, not just the clicked cell.',
              '先看画布：新建工程有两行，每行两个空单元格。本课要将示例图左右并排，只用上面一行，因此先删掉空的第二行。\n\n右键第二行中的任意单元格 → 删除 → 本行，或点击下方“删除第二行”。完成后应剩下一行、两个单元格。删除一行会移除该行全部单元格，而不只是右键点击的那个。'),
             action='delete_row'),
        Step('add_cell', ('Make room for the third sample', '给第三张示例图留出位置'),
             ('We now have two image slots, but three sample charts to place. Add one cell to the remaining row.\n\nClick the + at that row\u2019s right edge, or Add a third cell below. You should now see three empty cells side by side. This adds a cell to this row; it does not add a column to every row in a larger figure.',
              '现在有两个图片位置，还差一个才能放下三张示例图。接下来给剩下的这一行添加一个单元格。\n\n点击该行右边缘的 +，或下方“添加第三个单元格”。完成后应看到三个左右并排的空格子。这个操作只给当前行增加单元格，不会给多行布局中的每一行都增加一列。'),
             action='add_cell'),
        Step('load', ('Load panels from three file formats', '载入三种格式的面板'),
             ('Click Load samples below to put one chart in each of the three cells. SVG stores vector shapes and text; PNG and TIFF store pixels. ILM can combine these formats in one figure.\n\nThe Layers panel on the left lists the cells and their file formats. Click a cell to see its properties in the Inspector on the right. For your own images, File \u2192 Import Images fills empty cells, or you can drag one file onto an empty cell.',
              '点击下方“载入示例”，将三张图各放入一个单元格。SVG 保存矢量图形和文字，PNG、TIFF 保存像素；ILM 可以把它们放进同一张组合图。\n\n左侧“图层”列出单元格及文件格式。点击单元格，可在右侧检查器查看其属性。使用自己的图片时，可通过“文件 → 导入图片”填充空单元格，也可将单个文件拖到空格子上。'), action='load'),
        Step('layout', ('Arrange the panels', '安排面板'),
             ('The cells currently use the starting grid proportions, which need not suit the images inside them. Click Auto Layout in the toolbar (Ctrl+Shift+A) to size the layout for the loaded images.\n\nCompare the result with the starting layout: are the charts readable, and is the space between them appropriate? Auto Layout is a starting point, not a judgement about your figure. Use Undo if you prefer the previous arrangement.',
              '单元格目前沿用初始网格的比例，不一定适合放入的图片。点击工具栏“自动布局”（Ctrl+Shift+A），让布局按已载入的图片调整。\n\n对比调整前后：图表是否清楚，图与图之间的空隙是否合适？自动布局提供的是起点，并不替你决定最终排版。不满意时可以撤销。'), target='_act_auto_layout'),
        Step('labels', ('Add panel labels', '添加面板编号'),
             ('Panel letters let you refer to individual images in a caption, such as \u201csee panel a\u201d. They are annotations you add in ILM, not the axis text already inside the charts.\n\nClick Auto In-Cell Labels (Ctrl+Shift+L). A letter should appear inside each panel. If the letters look too large for these samples, keep them for now: the next step shows how to change their size.',
              '面板编号便于在图注中指明某张图片，例如“见图 a”。它是 ILM 添加的标注，与图表原有的坐标轴文字不同。\n\n点击“自动图内标注”（Ctrl+Shift+L），每张图内应出现一个编号。如果这些编号相对于示例图显得太大，先保留，下一步会介绍如何调整。'), target='_act_auto_label_incell'),
        Step('label_size', ('Change a label’s size', '修改标注字号'),
             ('Select a panel letter, not its image: click the letter on the canvas, or use Select a label below. In the right-hand Inspector, expand Text Style Properties and try a smaller value in Size. Check that the letter is readable without covering the chart.\n\nThis edits only the selected label. Use Apply Style to All if you want the other panel letters to match; it applies within the same label style tier.',
              '要调整编号，请选中文字，而不是图片：点击画布上的编号，或下方“选中标注”。在右侧检查器展开“文字样式属性”，试着减小“字号”，观察编号是否清楚且不遮挡图表。\n\n这只修改当前标注。若希望其他面板编号也采用相同样式，点击“将样式应用到全部”；它作用于同一样式层级的标注。'),
             target='label_size', action='label_size'),
        Step('save', ('Save an editable project', '保存可编辑工程'),
             ('Save a project so you can reopen the cells, images, and labels for editing. An exported PDF or image is a finished figure, not a substitute for this project.\n\nClick Save (Ctrl+S). For this exercise, choose .figpack: it includes the sample image files. A .figlayout file stores links instead, so its images must remain available. If you do not want to keep the exercise, you may cancel the dialog and continue; cancelling does not save a file.',
              '保存工程后，才能重新打开并继续编辑单元格、图片和标注。导出的 PDF 或图片是成图，不能代替可编辑工程。\n\n点击“保存”（Ctrl+S）。本次练习可选 .figpack，它会包含示例图片；.figlayout 则只记录图片链接，需要保留对应源文件。如果不想保留练习，可以取消对话框后继续；取消不会保存文件。'), target='_act_save'),
        Step('preview', ('Check the composition', '检查构图'),
             ('Open the highlighted Export button and choose Export Preview to hide the editing aids, then check the labels and margins. The same toggle is under View → Export Preview, or press Ctrl+Shift+P. This is only a preview: use Export for a publication file, and inspect that file separately.',
              '点击高亮的“导出”按钮并选择“导出预览”，隐藏编辑辅助元素，然后检查标注和边距。该开关也位于“视图 → 导出预览”，或按 Ctrl+Shift+P。这只是预览：投稿文件需通过“导出”生成，并单独检查。'), target='_act_preview_mode'),
        Step('finish', ('Ready for your own figure', '开始制作自己的图'),
             ('The example started with three images to place, so we made one row with three cells. For your own figure, decide which images belong together first, then choose the rows and cells they need.\n\nYou can now import images, try Auto Layout, add panel letters, and save an editable project. Export creates the file you share. Finish returns to your previous tab and keeps this practice tab available. Reopen lessons from Help → Guided Tutorials.',
              '这次先确定要并排放三张图，再把布局改成一行三个单元格。制作自己的图时，也先决定哪些图片需要放在一起，再安排所需的行和单元格。\n\n现在你已了解导入图片、尝试自动布局、添加面板编号和保存可编辑工程。“导出”用于生成分享的成图。点击“完成”会返回之前的标签页，并保留练习页；可从“帮助 → 引导教程”重新打开课程。')),
    ),
    'text_sizes': (
        Step('intro', ('Match size, not wording', '统一大小，而非文字内容'),
             ('Charts exported from different tools can have mismatched axis text even after their images fit the page. In this practice figure, two SVG charts and one PNG chart deliberately use different text sizes. We will make their \u201cTime\u201d labels share one target size.\n\nA text-size group links text that should have the same size across panels. Its value is in points (pt) in the final figure, not source pixels. We will try 9 pt as a practice target, not a publication rule. Source files are not overwritten.',
              '来自不同软件的图表，即使图片已经放得合适，坐标轴文字也可能大小不一。本练习图中的两张 SVG 和一张 PNG 故意使用不同字号；目标是让三张图的“Time”文字采用同一个目标大小。\n\n“文字组”把不同面板中需要相同字号的文字关联起来。组字号的单位是最终成图中的磅（pt），不是源图片像素。本课用 9 pt 练习，并非投稿通用标准；源文件不会被覆盖。')),
        Step('svg_open', ('Inspect the first SVG', '检查第一张 SVG'),
             ('Right-click the first panel → Match Text Size, or use Open inspector below. Only actual SVG text is listed; outlined lettering is not editable text.',
              '右键第一张面板 → 匹配文字大小，或点击下方“打开检查器”。列表只显示真正的 SVG 文字，已转为轮廓的文字不可编辑。'), target='svg0', action='svg0'),
        Step('svg_assign', ('Create and assign a 9 pt group', '创建并分配 9 pt 文字组'),
             ('Create the shared size rule before assigning text to it. In the Match Text Size window, click Add Group, name it \u201cAxis labels\u201d, and set its size to 9 pt.\n\nSelect Time in the text-element list, choose Axis labels in Assign to, then click Assign selected to group. That text now follows the group\u2019s size. Changes take effect immediately; closing this window does not cancel them.',
              '先建立共同的字号设置，再指定哪些文字使用它。在“匹配文字大小”窗口点击“添加组”，命名为“坐标轴标题”，将字号设为 9 pt。\n\n在文字元素列表中选中 Time，在“分配到”中选择“坐标轴标题”，然后点击“将所选分配到组”。这处文字便使用该组字号。修改即时生效，关闭窗口不会取消修改。'), target='svg0', action='svg0'),
        Step('svg_shared', ('Reuse the group in the second SVG', '在第二张 SVG 中复用同一组'),
             ('Open the second panel’s inspector with the button below or its context menu. Assign its Time element to the same 9 pt group. Do not create a second group: one shared group keeps panels consistent.',
              '通过下方按钮或第二张面板的右键菜单打开检查器。将其 Time 元素分配到同一个 9 pt 组，不要另建组；共享组可保持各面板文字一致。'), target='svg1', action='svg1'),
        Step('raster_detect', ('Locate raster text with OCR', '用 OCR 定位位图文字'),
             ('The PNG panel stores its lettering as pixels, so ILM must locate the text before resizing it. OCR (optical character recognition) finds candidate text regions; it does not retype the chart.\n\nOpen the raster inspector below and click Detect text (OCR). RapidOCR is the default detector. If detection is unavailable, check Preferences \u2192 Text Detection and Apply any changes, or skip this step. Wait for the regions to appear; detection can be cancelled.',
              'PNG 面板中的文字由像素组成，因此缩放前要先找到文字所在区域。OCR（光学字符识别）用于定位可能的文字区域，并不会重新打字替换图表。\n\n点击下方按钮打开位图文字窗口，再点击“检测文字（OCR）”。默认检测器为 RapidOCR。如果不可用，请在“偏好设置 → 文字检测”中检查配置并应用，或跳过此步。等待检测区域出现；检测过程可以取消。'), target='raster', action='raster'),
        Step('raster_assign', ('Assign and review a raster region', '分配并审查位图区域'),
             ('Select the detected Time region and choose the same group used by the two SVG panels. Keep the region\u2019s checkbox enabled: selecting a row chooses what to edit, while ticking it permits resizing.\n\nCheck the preview and the region\u2019s status. A review warning asks you to inspect the result; it does not by itself disable the region. If resizing would overlap other content or leave the image, ILM may skip it. Check that nearby lines and data remain intact.',
              '选中检测到的 Time 区域，选择两张 SVG 使用的同一个文字组，并保持该区域勾选。选中一行表示要编辑它，勾选则表示允许它缩放，两者不同。\n\n查看预览和该区域的状态。审查提示要求你检查效果，本身并不禁用区域；如果缩放会覆盖其他内容或超出图片，ILM 可能跳过处理。请确认附近线条和数据仍然完整。'), target='raster', action='raster'),
        Step('review', ('Compare with the original', '与原图对比'),
             ('Toggle Show original in the raster inspector, then turn it off again. A group assignment does not prove the pixels are correct. Inspect each changed label; raster size estimates are approximate and enlargement cannot restore lost detail.',
              '在位图检查器中勾选“显示原图”，再取消勾选。分组成功并不代表像素处理正确。逐处检查修改的文字；位图字号估计是近似值，放大无法恢复缺失细节。'), target='raster', action='raster'),
        Step('finish', ('Verify before publication', '发表前核对'),
             ('One shared group now provides the size rule for text in different panels. In your own figure, use separate groups when axis titles and tick labels need different sizes.\n\nSave a copy before extensive edits; not every text-inspector edit supports undo. Check the actual exported file at its intended size, including the resized raster text and nearby content. Finish keeps the practice tab; replay this lesson to revisit skipped steps.',
              '同一个文字组可以为不同面板中的文字提供共同的字号设置。制作自己的图时，如果坐标轴标题和刻度文字需要不同大小，应分别建组。\n\n大量修改前请先另存副本，并非所有文字检查器编辑都支持撤销。按最终使用尺寸检查实际导出文件，尤其核对缩放后的位图文字及附近内容。完成后保留练习页；可重学本课补做跳过的步骤。')),
    ),
    'divide_cells': (
        Step('intro', ('Build a layout inside one panel', '在一个面板内搭建布局'),
             ('Sometimes one position in a figure needs several related images, such as an overview beside two detail views. A sub-cell is a smaller image slot inside an existing cell; splitting that slot again creates a nested layout.\n\nThis practice tab has three sample panels. We will subdivide only the rightmost (TIFF) cell, keeping the first two unchanged. The samples demonstrate the layout, not a real overview/detail relationship. Source files are unchanged; use Undo to reverse layout edits. Back only revisits instructions.',
              '一张组合图中的某个位置有时需要放多张相关图片，例如一张全景图旁边放两张细节图。“子单元格”就是现有单元格内部更小的图片位置；继续细分子单元格，就形成嵌套布局。\n\n练习页已有三个示例面板。本课只细分最右侧的 TIFF 单元格，前两个保持不变。示例素材仅演示排版，并不是真实的全景与细节关系。源文件不变；撤销可恢复布局编辑，“上一步”只回看说明。')),
        Step('split', ('Subdivide a panel', '细分面板'),
             ('Right-click the third panel → Add Sub-Cell / Subdivide → Subdivide into N Columns… (nested), then choose 2, or click Split third panel below. This divides only that panel, not the whole page. Its TIFF image stays in the left sub-cell; the right sub-cell starts empty.',
              '右键第三个面板 → 细分为子单元格 → 细分为 N 列…（嵌套），选择 2，或点击下方“拆分第三个面板”。这只细分该面板，不会拆分整页。原 TIFF 图片保留在左侧子单元格，右侧子单元格为空。'),
             target='division_panel', action='split_cols'),
        Step('ratio', ('Adjust the split ratio', '调整分割比例'),
             ('The two sub-cells start equally wide. To leave more room for one image, change their relative widths rather than splitting the whole page again.\n\nClick Select the new sub-cell below, then change the highlighted ratio field in the Inspector\u2019s Sub-Cell Layout section. The ratio is a share of the available space, not a width in millimetres. Watch the divider move. You can also drag that divider directly on the canvas. If the field is out of view, click the Image Cell Properties header to fold that section and bring Sub-Cell Layout into view.',
              '两个子单元格最初等宽。若想给其中一张图片留更多空间，应调整两者的宽度比例，而不是重新细分整页。\n\n点击下方“选中新的子单元格”，在检查器的“子单元格排版”中修改分割比例。比例表示它占可用空间的份额，不是毫米宽度。观察分隔条如何移动；也可直接在画布上拖动分隔条。若该字段被挤到视野之外，点击“图像单元格属性”标题将其折叠，让“子单元格排版”进入视野。'),
             target='subcell_ratio', action='select_subcell'),
        Step('nested_rows', ('Nest two rows on the right', '在右侧嵌套两行'),
             ('To try an overview-and-details arrangement, keep the left sub-cell intact and turn the empty right sub-cell into two stacked slots.\n\nRight-click the rightmost sub-cell \u2192 Add Sub-Cell / Subdivide \u2192 Subdivide into N Rows\u2026 (nested), choose 2, or use Divide the right sub-cell below. Only that sub-cell is divided; the left image and the other original panels stay in place.',
              '接下来尝试“一张大图配两张小图”的结构：保留左侧子单元格，把右侧空白子单元格分成上下两个位置。\n\n右键最右侧子单元格 → 细分为子单元格 → 细分为 N 行…（嵌套），选择 2，或点击下方“细分右侧子单元格”。这只细分右侧这一格；左侧图片及另外两个原始面板保持原位。'),
             target='division_panel', action='nested_rows'),
        Step('add_sibling', ('Add a cell at the same level', '在同一层级添加单元格'),
             ('Suppose you now need another image beside the overview, without dividing the overview itself. Add a sibling: a new cell at the same level as the selected cell.\n\nRight-click the left sub-cell \u2192 Add Sub-Cell / Subdivide \u2192 Add Sibling Right, or use the button below. The new slot joins the inner row. The two stacked slots on the right remain together; no whole-page column is added.',
              '假设现在还需要在大图旁边放一张图片，但不想把大图本身再分开。这时应添加“同级单元格”，也就是与所选单元格处在同一层的新格子。\n\n右键左侧子单元格 → 细分为子单元格 → 在右侧添加同级单元格，或点击下方按钮。新格子加入内部这一行；右侧上下两格仍保持在一起，也不会为整页增加一列。'),
             target='division_panel', action='add_sibling'),
        Step('fill_subcells', ('Fill the empty sub-cells', '填充空白子单元格'),
             ('Drag image files onto the empty sub-cells to fill them. Fill empty sub-cells below uses the same samples and only fills blanks, never replacing images already there. The sample fill is one undo step; the original TIFF remains in the left sub-cell.',
              '将图片文件拖到空白子单元格即可填充。下方“填充空白子单元格”会复用示例素材，只填空白位置，不会替换已有图片。示例填充可一次撤销；原 TIFF 仍保留在左侧子单元格。'),
             target='division_panel', action='fill_subcells'),
        Step('finish', ('A nested layout, one panel at a time', '逐个面板搭建嵌套布局'),
             ('You have divided a panel, adjusted its ratio, nested rows, added a sibling, and filled empty sub-cells without changing the other panels or source files. Finish returns to your previous tab and keeps this practice project available. Replay from Help → Guided Tutorials anytime.',
              '你已练习细分面板、调整比例、嵌套分行、添加同级单元格和填充空白位置，其他面板和源文件均保持不变。完成后返回之前的标签页，并保留练习工程。可随时从“帮助 → 引导教程”重新学习。')),
    ),
    'arrange_panels': (
        Step('intro', ('Grid and freeform', '网格与自由布局'),
             ('A useful layout needs more than equal boxes: you may want to change reading order, choose how an image fits, or place a panel independently. We will try each on a separate practice figure containing SVG, PNG, and TIFF samples.\n\nGrid mode organizes cells into rows. Freeform mode lets you position cells individually. We will start in the grid, then switch to freeform; your other projects are untouched.',
              '排版不只是把格子排整齐：你可能需要改变阅读顺序、调整图片在格子中的显示方式，或单独定位某个面板。本课用独立练习页中的 SVG、PNG、TIFF 示例分别尝试这些操作。\n\n网格模式按行组织单元格，自由布局则允许逐个定位。我们先在网格中练习，再切换到自由布局，不会改动其他工程。')),
        Step('swap', ('Swap two panels', '交换两个面板'),
             ('Click Swap panels below to exchange the first two panels’ images. In real use, drag one panel onto another on the canvas to swap them; hold Ctrl to select several cells and swap the whole set at once. Position, labels, and insets stay with the cell — only the image content moves.',
              '点击下方“交换面板”，交换前两个面板的图片。实际使用时，把画布上的一个面板拖到另一个上即可交换；按住 Ctrl 可多选几个单元格一起交换。位置、标注和插图都留在原单元格——只有图片内容会移动。'),
             action='swap'),
        Step('crop', ('Crop a panel\u2019s image', '裁剪面板图片'),
             ('Cropping chooses which part of an image is visible; it does not change the source file. We will use a square crop just to make the effect easy to see, not because these charts require a square shape.\n\nClick Crop to square below, then check which edges disappear. In your own work, use right-click \u2192 Crop \u2192 a ratio preset, or Crop Image for handles. Reset Crop restores the full image. Do not hide important chart labels or data.',
              '裁剪决定图片的哪一部分可见，不会改动源文件。本步用正方形裁剪，是为了方便观察效果，并不是说这些图表应该裁成正方形。\n\n点击下方“裁剪为正方形”，看看哪些边缘被隐藏。使用自己的图片时，可右键 → 裁剪 → 选择比例预设，或用“裁剪图片”拖动手柄。“重置裁剪”恢复完整图片。请不要裁掉重要标注或数据。'),
             action='crop_square'),
        Step('fit_mode', ('Fit and align the image in its cell', '调整图片的填充与对齐方式'),
             ('The image and its cell can have different proportions. Fit Mode decides whether to show the whole image or fill the cell.\n\nClick Select a panel below. In Image Cell Properties, try cover in Fit Mode: it fills the cell but may hide image edges. contain keeps the whole current crop visible and may leave blank space. Change the 3\u00d73 alignment control to choose where that space, or the hidden edge, falls. Watch the first panel as you compare.',
              '图片和单元格的宽高比可能不同。“自适应模式”决定是显示完整图片，还是填满单元格。\n\n点击下方“选中面板”，在“图像单元格属性”的自适应模式中尝试 cover：它填满格子，但可能隐藏图片边缘。contain 保留当前裁剪范围的完整内容，可能留下空白。改变 3×3 对齐控件，可调整空白或被隐藏边缘所在的一侧。对比时观察第一个面板。'),
             target='fit_mode_combo', action='select_cell'),
        Step('freeform', ('Switch to freeform', '切换到自由布局'),
             ('Use freeform when a panel needs a position that the row layout cannot express. Open Layout \u2192 Convert Grid \u2192 Freeform. The cells keep their current positions as a starting point, then become individually movable.\n\nLayout \u2192 Switch to Grid Mode returns to row-based positioning, but it may rearrange cells; it does not preserve every freeform position. Save a copy before a major rearrangement.',
              '如果某个面板需要的位置无法用行布局表达，可以使用自由布局。打开“布局 → 网格转自由布局”：当前单元格位置作为起点保留，随后可逐个移动。\n\n“布局 → 切换至网格模式”会恢复按行定位，但可能重新排布单元格，并不保证保留每个自由布局位置。大幅调整前请先另存副本。'),
             target='_act_bake'),
        Step('reposition', ('Position a panel precisely', '精确定位面板'),
             ('Click Select a panel below, then edit the highlighted X field in the Inspector — Y, Width, and Height are right below it, all in millimetres. Drag the panel on the canvas for quick placement, then fine-tune the numbers here. In freeform mode, drag rows in Layers to change the overlap order: the top row is frontmost.',
              '点击下方“选中面板”，然后修改检查器中高亮的 X 字段——Y、宽度和高度就在下方，单位均为毫米。可在画布上拖动面板快速摆放，再到这里微调数值。自由布局中，拖动“图层”中的条目可调整重叠顺序：最上方条目位于最前。'),
             target='freeform_x', action='select_cell'),
        Step('finish', ('Ready to compose your own layout', '可以开始搭建自己的布局了'),
             ('You have swapped content, cropped and aligned an image, and repositioned a panel in freeform mode. Layout → Switch to Grid Mode returns to grid rules whenever you need consistent rows and columns again. Finish keeps this practice tab; replay this lesson anytime from Help → Guided Tutorials.',
              '你已经练习了交换内容、裁剪与对齐图片，以及在自由布局中重新定位面板。需要恢复整齐的行列时，随时可用“布局 → 切换至网格模式”。完成后练习页会保留；可随时从“帮助 → 引导教程”重新学习本课。')),
    ),
    'labels_titles': (
        Step('intro', ('Panel letters vs. shared titles', '面板编号与共享标题'),
             ('A caption may refer to one panel (\u201ca\u201d) or describe several panels together (\u201cDay 7\u201d). These need different annotations: panel letters identify individual images; a shared label puts one heading across several cells or beside a whole row.\n\nWe will add both kinds to this separate three-panel practice figure. Shared labels have their own bands outside the images. The example heading is for practice, not a description of the synthetic data.',
              '图注有时指向一张图片（如“a”），有时需要给多张图片一个共同标题（如“第 7 天”）。两者使用不同标注：面板编号标识单张图片；共享标注横跨多个单元格，或放在整行旁边。\n\n本课在独立的三面板练习图中添加这两类标注。共享标注有自己的图外标注带。示例标题仅用于练习，不代表这些合成数据的实际含义。')),
        Step('panel_letters', ('Add panel letters', '添加面板编号'),
             ('Click Auto In-Cell Labels (Ctrl+Shift+L) in the toolbar. These letters identify each panel individually and are unrelated to any shared label you add next — deleting or moving one never affects the other.',
              '点击工具栏的“自动图内标注”（Ctrl+Shift+L）。这些编号分别标识每个面板，与接下来添加的共享标签互不相关——删除或移动其中一个不会影响另一个。'),
             target='_act_auto_label_incell'),
        Step('shared_top', ('Add a header over two panels', '在两个面板上方添加标题'),
             ('First, give the first two panels one shared heading so a reader can see they belong together. Click Select two panels below, or Ctrl+click those panels on the canvas.\n\nOpen Edit \u2192 Add Shared Label for Selection \u2192 Header above selected cells. A band with placeholder text appears above those two cells; the third panel stays outside it. Leave the placeholder for now: the rename step will show where to enter your heading.',
              '先给前两个面板加一个共同标题，让读者看出它们属于一组。点击下方“选中两个面板”，或在画布上按住 Ctrl 点选这两个面板。\n\n打开“编辑 → 为所选添加共享标注 → 所选单元格上方的标题”。这两个单元格上方会出现带默认文字的标注带，第三个面板不在其中。暂时保留默认文字，后面的改名步骤会介绍在哪里输入自己的标题。'),
             target='group_label_top', action='select_pair'),
        Step('shared_row', ('Add a title for the whole row', '为整行添加标题'),
             ('A heading above selected cells covers just those cells; a row title describes the entire row. Add one now to compare the two scopes.\n\nClick Select the row below, then Edit \u2192 Add Shared Label for Selection \u2192 Title left of the row. A band with placeholder text appears at the left of the row. Even if you select only one cell in that row, this command still titles the whole row.',
              '上方标题只覆盖选中的单元格，而行标题描述的是整行。接下来添加行标题，比较两种标注的范围。\n\n点击下方“选中整行”，再打开“编辑 → 为所选添加共享标注 → 所在行左侧的标题”。行左侧会出现带默认文字的标注带。即使只选中该行一个单元格，这条命令也始终为整行添加标题。'),
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
             ('Saving a project lets you keep editing; exporting creates the figure file you send to a collaborator or publisher. The output needs the right physical size, file format, and image resolution for its destination.\n\nThis separate practice figure is already assembled. We will try a raster resolution setting, choose which part of the page to export, and open the export options. The example values are for practice; use the recipient\u2019s requirements for real work.',
              '保存工程是为了继续编辑，导出则生成发给合作者或出版社的成图文件。输出需要符合使用场景要求的实际尺寸、格式和图像分辨率。\n\n独立练习页已排好图。本课将尝试设置位图分辨率、指定导出页面的哪一部分，并查看导出选项。练习数值不是通用标准，实际工作应遵循接收方要求。')),
        Step('dpi', ('Set the export resolution', '设置导出分辨率'),
             ('DPI means pixels per inch of the exported figure: at the same physical size, a higher value produces more pixels. Click Show project settings below and try changing DPI from 300 to 600. This is a comparison exercise, not a recommendation for every figure.\n\nFor raster output (TIFF/PNG/JPG), pixels \u2248 (size in mm \u00f7 25.4) \u00d7 DPI. More output pixels cannot recover detail missing from a source image. Vector shapes in PDF/SVG do not need extra DPI to stay sharp.',
              'DPI 表示成图每英寸对应的像素数：实际尺寸相同时，数值越高，导出像素越多。点击下方“显示工程设置”，尝试把 DPI 从 300 改为 600。这是对比练习，不是建议所有图都使用 600。\n\n位图输出（TIFF/PNG/JPG）的像素数约为（尺寸毫米 ÷ 25.4）× DPI。增加输出像素无法恢复源图缺失的细节；PDF/SVG 中的矢量图形不需要靠提高 DPI 保持清晰。'),
             target='dpi_spin', action='show_project'),
        Step('export_region', ('Restrict export to part of the page', '将导出范围限定在页面局部'),
             ('Use an export region when you want to output only part of a page without deleting the rest of the layout. In this exercise, try including just the first two panels.\n\nOpen Export \u2192 Set Export Region (also in Layout). A rectangle initially covers the full page; drag its edges to the area you want to keep. Content outside remains in the project but is omitted from export. Layout \u2192 Clear Export Region restores whole-page output.',
              '如果只想输出页面的一部分，又不想删除其余布局，可以设置导出区域。本步试着只包含前两个面板。\n\n打开“导出 → 设置导出区域”（布局菜单中也有）：最初的矩形覆盖整页，拖动边缘，缩到要保留的范围。区域外内容仍在工程中，但不会导出。“布局 → 清除导出区域”恢复整页输出。'),
             target='_act_set_export_region'),
        Step('export', ('Open the Export menu', '打开导出菜单'),
             ('Choose a format for the intended use, not simply the first item in the list. Open the highlighted Export menu: PDF can preserve supported vector content, TIFF/PNG provide lossless pixel images, and JPG compresses with some loss of detail. Raster source images remain raster even inside PDF.\n\nChoose a format and save a practice file if you want to inspect it in the next step. You may cancel the dialog to avoid creating a file; cancelling does not export anything.',
              '选择格式应依据用途，而不是直接选列表第一项。打开高亮的“导出”菜单：PDF 可保留支持的矢量内容，TIFF/PNG 提供无损像素图，JPG 压缩会损失一些细节。位图源图片即使放进 PDF 也仍是位图。\n\n选择一种格式；若想在下一步核对实际文件，可保存一份练习输出。不想生成文件时可以取消对话框，取消不会执行导出。'),
             target='_act_export_pdf'),
        Step('verify', ('Compare preview and real file', '对比预览与真实文件'),
             ('Turn on Export Preview from the Export menu or View \u2192 Export Preview (Ctrl+Shift+P). With editing aids hidden, check the panel order, labels, and margins. This view is not a proof of the exported file\u2019s DPI or exact appearance.\n\nIf you saved an export, open it in a separate viewer and check the physical page size, crop, lettering, and image detail at the intended display or print size. If you cancelled export, do this check when you export your own figure.',
              '从导出菜单或“视图 → 导出预览”（Ctrl+Shift+P）开启预览。隐藏编辑辅助元素后，检查面板顺序、标注和边距。这个视图不能用来确认导出文件的 DPI 或每一处实际效果。\n\n如果已保存输出，请用独立查看器打开，按最终显示或印刷尺寸核对页面大小、裁剪范围、文字和图像细节。若刚才取消了导出，请在以后导出自己的图时完成这项检查。'),
             target='_act_preview_mode'),
        Step('finish', ('Keep the project and check the export', '保留工程，核对导出文件'),
             ('Page size sets the physical dimensions; DPI sets the pixel count for raster output; the export region chooses what part of the page is included. None of these replaces checking the file you actually send.\n\nKeep the editable project as well as the export, and follow the recipient\u2019s format and resolution requirements. Finish returns to your previous tab and keeps this practice figure available.',
              '页面尺寸决定实际大小，DPI 决定位图输出的像素数，导出区域决定包含页面的哪一部分。这些设置都不能代替检查最终发送的文件。\n\n除导出文件外，请保留可编辑工程，并按接收方要求设置格式和分辨率。完成后返回之前的标签页，练习图会保留。')),
    ),
    'insets_scale_bars': (
        Step('intro', ('Insets and scale bars', '插图与比例尺'),
             ('An inset is a small image placed over a larger panel, often used to show a detail. A scale bar tells readers what a distance in an image represents in real units. These are different tasks: an inset controls layout; a meaningful scale bar also needs calibration.\n\nThis practice tab uses synthetic, microscopy-like images. We will place a sample icon over the first panel, resize it, then enable a demonstration scale bar. The samples have no real physical calibration.',
              '插图是在大面板上叠放的一张小图片，常用于显示细节；比例尺则告诉读者，图中的一段距离代表多长的实际长度。两者不同：插图解决排版问题，有实际意义的比例尺还需要校准数据。\n\n练习页使用模拟显微图的合成素材。我们将在第一个面板上叠放一个示例图标，调整大小，再启用演示比例尺。这些素材没有真实的物理校准。')),
        Step('add_inset', ('Add an inset image', '添加插图'),
             ('Click Add inset below to place a sample icon on the first panel. It is a separate image, not a magnified part of the chart.\n\nWith your own files, drag one image over a filled cell and release in the top-right drop zone labelled Inset. Dropping elsewhere on the cell replaces the main image instead. Dragging an inset\u2019s body moves it within its host panel; the next step changes its size.',
              '点击下方“添加插图”，在第一个面板上放置一个示例图标。它是独立图片，并不是原图某处的放大。\n\n使用自己的文件时，将单张图片拖到已有图片的单元格上，在右上角标有“插图”的投放区松开。拖到该单元格的其他位置会替换主图。拖动插图主体可调整它在主面板内的位置，下一步再改变大小。'),
             action='add_pip'),
        Step('resize_inset', ('Resize the inset', '调整插图大小'),
             ('The inset should be large enough to read without covering important parts of its host image. Click Select inset below to show its resize handles, then drag a corner or edit Width in the Inspector\u2019s Inset Image Properties.\n\nX, Y, Width, and Height are percentages of the host panel\u2019s content area, not millimetres. For example, Width 25% takes one quarter of that area\u2019s width. In normal use, select the inset on the canvas or its own child row in Layers to edit these fields.',
              '插图既要足够清楚，也不应遮挡主图的重要内容。点击下方“选中插图”显示调整手柄，然后拖动角部手柄，或在检查器的“插图属性”中修改宽度。\n\nX、Y、宽度和高度都是相对于主面板内容区域的百分比，不是毫米。例如宽度 25% 表示占该区域宽度的四分之一。平时可点击画布上的插图，或在图层中选择它自己的子条目，再编辑这些字段。'),
             target='pip_w', action='select_pip'),
        Step('scale_bar', ('Draw a calibrated scale bar', '绘制校准比例尺'),
             ('A scale bar needs two different values: calibration says how many micrometres one source-image pixel represents; Length says the real distance you want the bar to show. Screen zoom cannot supply calibration.\n\nClick Select a panel below, expand Scale Bar, and enable it to see the layout controls. Calibration \u2192 Manage lets you store a known pixel size from your image acquisition data. For this synthetic sample, the displayed bar is a layout demonstration only, not a measurement. Use verified calibration before adding a bar to real data.',
              '比例尺需要两个不同的数值：“像素校准”表示源图一个像素对应多少微米；“长度”表示这根尺要展示多长的实际距离。屏幕缩放不能提供校准值。\n\n点击下方“选中面板”，展开“比例尺”并启用，观察排版控件。像素校准旁的“管理”可保存采集数据中已知的像素尺寸。本合成示例中的尺仅用于演示排版，不代表测量结果；给真实数据添加比例尺前，必须使用核实过的校准值。'),
             target='scale_bar_enabled', action='select_cell'),
        Step('finish', ('Ready to annotate your own imaging figures', '可以开始为你自己的成像图添加标注了'),
             ('You have added and resized an inset image and enabled a scale bar. Insets also support their own border and scale bar, independent of the host panel\u2019s. Finish keeps this practice tab; replay this lesson anytime from Help → Guided Tutorials.',
              '你已经练习了添加与调整插图大小，以及启用比例尺。插图也可以拥有自己独立的边框和比例尺，与所在面板互不影响。完成后练习页会保留；可随时从“帮助 → 引导教程”重新学习本课。')),
    ),
    'align_plots': (
        Step('intro', ('Line up the plots, not the files', '对齐绘图区，而不是文件边缘'),
             ('This practice row holds three synthetic charts saved with different margins, as if they came from different plotting tools. Auto Layout fits each file\u2019s edges, so the bottom axes sit at different heights and the plot boxes differ in size. The fix is to mark each chart\u2019s plotting area and match them. Marking is a reference, not a crop: labels stay visible and source files are never edited.',
              '这一行练习面板包含三张合成图表，它们保存时留白各不相同，就像来自不同的绘图软件。“自动布局”按文件边缘适配，因此底部坐标轴高低不一，绘图框大小也不同。解决办法是标记每张图的绘图区，然后统一匹配。标记只是参照，不是裁剪：标签仍然可见，源文件不会被修改。')),
        Step('mark_plots', ('Mark the three plot areas and apply', '标记三个绘图区并应用'),
             ('Click Open Align Plot Areas below. Create a New group, name it \u201cRow 1\u201d, and check the three sample panels. A group records which charts should align together.\n\nFor each checked image, draw a box around the plotting rectangle where the data are drawn, keeping tick labels, titles, and legends outside. Use Mark next image to continue. Choose panel 1 as the reference: its plot supplies the target height and bottom line.\n\nPreview alignment, compare the three bottom axes, then Apply. If the group is reduced to fit, read the notice; Fit plots within cells makes that sizing choice explicit. For your own figure, open this tool from the arrow beside Auto Layout, the Layout menu, or a panel\u2019s context menu.',
              '点击下方“打开对齐绘图区”。点击“新建对齐组”，命名为“第一行”，勾选三张示例图。对齐组用于记录哪些图表需要一起对齐。\n\n逐张框选数据所在的绘图矩形，刻度文字、标题和图例留在框外；用“标记下一张”继续。选择面板 1 为参照图，它的绘图区提供目标高度和底部对齐线。\n\n点击“预览对齐”，比较三张图的底部坐标轴，再点击“应用”。若提示整组已缩小以适应空间，请阅读提示；“适应单元格边界”可明确采用该尺寸策略。制作自己的图时，可从自动布局旁的箭头、布局菜单或面板右键菜单打开此工具。'),
             target='_act_align_plots', action='open_align_plots'),
        Step('layout', ('Auto Layout keeps the alignment', '自动布局会保留对齐'),
             ('Click Auto Layout in the toolbar (Ctrl+Shift+A) again. The cells are rearranged, but the alignment is a saved relationship: the plot heights and bottom axes are recalculated, not lost. If a later change leaves too little room for a panel\u2019s title or labels, the whole group shrinks together so nothing is cut off, and the status bar tells you.',
              '再次点击工具栏的“自动布局”（Ctrl+Shift+A）。单元格会重新排布，但对齐关系已被保存：绘图高度和底部坐标轴会重新计算，而不会丢失。若之后的修改让某个面板的标题或标签放不下，整组会一起缩小以免裁掉内容，状态栏会给出提示。'),
             target='_act_auto_layout'),
        Step('preview', ('Check the result', '检查结果'),
             ('Open the highlighted Export button and choose Export Preview (Ctrl+Shift+P) to hide the editing aids. Compare the bottom axes across the row: they now share one line and the plots share one height, while each chart\u2019s own labels remain. Exported PDF, PNG, and SVG files use the same placement.',
              '点击高亮的“导出”按钮并选择“导出预览”（Ctrl+Shift+P），隐藏编辑辅助元素。对比这一行的底部坐标轴：它们现在处于同一条线上，绘图高度也一致，而各图自身的标签仍然保留。导出的 PDF、PNG 和 SVG 使用同样的位置。'),
             target='_act_preview_mode'),
        Step('finish', ('Ready to align your own charts', '可以开始对齐你自己的图表了'),
             ('The marked plot rectangles, not the image-file edges, now determine the alignment. Reopen Align Plot Areas to change the marks or reference; Remove alignment restores normal image fitting. Apply is one undo step, and saving the project preserves the alignment.\n\nMatch reference exactly keeps the reference size only while every panel fits. Otherwise the group is reduced together and a notice explains why. Axis titles remain part of their source images, not independently movable labels. Finish keeps this practice tab.',
              '现在决定对齐的是标记的绘图矩形，而不是图片文件的边缘。可重新打开“对齐绘图区”修改标记或参照图；“移除对齐”恢复普通图片适配。“应用”只占一步撤销，保存工程会保留对齐关系。\n\n“精确匹配参照图”仅在所有面板都能容纳时保持参照尺寸，否则整组一起缩小并显示原因。坐标轴标题仍是源图的一部分，不会变成可单独移动的标注。完成后保留练习页。')),
    ),
    'size_groups': (
        Step('intro', ('Keep several panels the same size', '让多个面板保持相同大小'),
             ('When several images should occupy equally sized slots, changing each cell separately is easy to get wrong. A Size Group links the member cells\u2019 width and height so you can set those dimensions once. It does not align the axes drawn inside their images; that is the Align Plot Areas lesson.\n\nIn this separate practice tab, we will group the first two sample panels, set a shared size, then add the third. The group changes layout, not the source files.',
              '当几张图片需要占据同样大小的位置时，逐个调整单元格容易出现差异。“尺寸组”将成员单元格的宽度和高度关联起来，只需设置一次。它不会对齐图片内部画出的坐标轴；那是“对齐绘图区”课程的内容。\n\n本课在独立练习页中，先把前两个示例面板归组并设置共同尺寸，再加入第三个。分组只影响布局，不修改源文件。')),
        Step('create_group', ('Group two panels together', '将两个面板归入一组'),
             ('Click Create group below to group the first two panels. To do this yourself, Ctrl+click two or more cells, then right-click \u2192 Create Size Group.\n\nThe group begins with automatic dimensions: it uses the smallest available member width and the smallest available member height, calculated separately. In the next step, you will replace those automatic choices with a size you specify.',
              '点击下方“创建组”，将前两个面板归为一组。手动操作时，按住 Ctrl 点选两个或更多单元格，再右键 → 创建尺寸组。\n\n分组最初使用自动尺寸：宽度取成员可用宽度的最小值，高度另取可用高度的最小值。下一步将用自己指定的尺寸替代自动值。'),
             action='create_size_group'),
        Step('pin_size', ('Pin an exact shared size', '固定统一尺寸'),
             ('Pinning means giving the whole group an explicit dimension instead of letting the layout choose it. Click Select a panel below. In Image Cell Properties, find Pinned W and Pinned H beside the size-group controls.\n\nTry a width that fits the page, then watch both members change together. Values are millimetres; 0 means automatic for that dimension, not zero width or height. The value belongs to the group, even though one member is selected.',
              '“固定尺寸”是指为整组指定数值，而不再由布局自动决定。点击下方“选中面板”，在“图像单元格属性”的尺寸组控件处找到“固定宽度”和“固定高度”。\n\n尝试一个页面能容纳的宽度，观察两个成员是否一起改变。单位是毫米；0 表示该维度自动决定，并不是宽或高为零。虽然只选中了一个成员，这个数值属于整组。'),
             target='size_group_pinned_w', action='select_cell'),
        Step('add_member', ('Add a third panel to the group', '将第三个面板加入组'),
             ('Click Add third panel below. In real use: select the panel(s) to add, right-click → Add to Size Group → pick the group by name. A group can have any number of members, and a panel can only belong to one group at a time.',
              '点击下方“添加第三个面板”。实际使用时：选中要加入的面板，右键 → 添加到尺寸组 → 按名称选择目标组。一个组可以包含任意数量的成员，但每个面板同一时间只能属于一个组。'),
             action='add_to_size_group'),
        Step('finish', ('Ready to keep your own panels aligned', '可以开始统一你自己的面板尺寸了'),
             ('A Size Group keeps its members\u2019 cell dimensions linked; it does not make their image content identical. Use different groups for panels that need different shared sizes.\n\nRight-click a member \u2192 Remove from Size Group to unlink just that cell. Delete Group in the Inspector removes the link for all members; their sizes are then determined by their own layout settings. Finish keeps this practice tab.',
              '尺寸组关联的是成员单元格的尺寸，不会把图片内容变成一样。不同面板若需要不同的共同尺寸，可分别建组。\n\n右键成员 → 从尺寸组移除，只解除该单元格的关联。检查器中的“删除组”解除所有成员的关联，之后尺寸由各自布局设置决定。完成后会保留练习页。')),
    ),
}


LESSON_ORDER = (
    'first_figure', 'divide_cells', 'arrange_panels', 'size_groups', 'align_plots',
    'labels_titles', 'text_sizes', 'insets_scale_bars', 'publication',
)
LESSONS = {key: LESSONS[key] for key in LESSON_ORDER}

LESSON_GROUPS = (
    (('Build the layout', '搭建布局'), ('first_figure', 'divide_cells', 'arrange_panels', 'size_groups', 'align_plots')),
    (('Annotate the figure', '标注图形'), ('labels_titles', 'text_sizes', 'insets_scale_bars')),
    (('Prepare to publish', '准备发表'), ('publication',)),
)

_LESSON_SUMMARIES = {
    'first_figure': ('Learn rows and cells, then combine three sample images and save the figure.',
                     '先认识行与单元格，再组合三张示例图并保存工程。'),
    'divide_cells': ('Build nested rows and columns inside a cell.',
                     '在单元格内搭建嵌套的行与列。'),
    'arrange_panels': ('Swap, crop, and position panels in freeform mode.',
                       '交换、裁剪面板，并在自由排布模式下调整位置。'),
    'size_groups': ('Share panel dimensions with size groups.',
                    '使用尺寸组统一面板尺寸。'),
    'align_plots': ('Mark plot interiors and match their height and bottom axis across panels.',
                    '标记绘图区，让多个面板的绘图高度和底部坐标轴对齐。'),
    'labels_titles': ('Add panel numbers and shared titles.',
                      '添加面板编号和共享标题。'),
    'text_sizes': ('Match typography across SVG and raster panels.',
                   '统一 SVG 与位图面板中的文字大小。'),
    'insets_scale_bars': ('Add insets and scale bars to microscopy figures.',
                          '为显微图添加插图与比例尺。'),
    'publication': ('Set DPI, choose an output format, and check the export.',
                     '设置 DPI、选择输出格式，并检查导出结果。'),
}


_LESSON_TITLES = {
    'first_figure':      ('Your first figure',      '制作第一张组合图'),
    'divide_cells':       ('Divide cells',                   '细分单元格'),
    'text_sizes':         ('Match text sizes',               '统一文字大小'),
    'arrange_panels':     ('Arrange panels',                 '排布面板'),
    'labels_titles':      ('Labels and shared titles',       '标注与共享标题'),
    'publication':        ('Prepare for publication',        '发表前准备'),
    'insets_scale_bars':  ('Insets and scale bars',          '插图与比例尺'),
    'size_groups':        ('Size groups',                    '尺寸组'),
    'align_plots':        ('Align plot areas',               '对齐绘图区'),
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


#: (left, top, right, bottom) of each misaligned sample's plot frame, in
#: source pixels of the 720×480 page. Variant 0 has the smallest plot
#: height so, as the default reference, the other two scale *down* and
#: "Match reference exactly" fits their cells without needing Fit.
_ALIGN_PLOT_PIXELS = ((100, 170, 630, 360), (190, 90, 660, 410), (120, 60, 600, 320))
ALIGN_PLOT_FRAMES = tuple((l / 720, t / 480, r / 720, b / 480) for l, t, r, b in _ALIGN_PLOT_PIXELS)


def _sample_misaligned_chart(variant):
    """Synthetic chart whose plot frame sits differently on the page for
    each variant — imitating panels saved by different plotting tools —
    so Auto Layout visibly misaligns the bottom axes and plot heights."""
    left, top, right, bottom = _ALIGN_PLOT_PIXELS[variant]
    series = ((45, 80, 60, 175, 200, 235), (60, 95, 140, 120, 205, 250), (30, 70, 105, 160, 150, 215))[variant]
    width, height = right - left, bottom - top
    points = ' '.join(f'{left + 15 + step * (width - 30) / 5:.0f} {bottom - 20 - value * (height - 40) / 250:.0f}'
                      for step, value in enumerate(series))
    ticks = ''.join(f'<line x1="{left}" y1="{bottom - height * f:.0f}" x2="{left - 8}" y2="{bottom - height * f:.0f}" stroke="#444" stroke-width="3"/>'
                    for f in (0.25, 0.5, 0.75))
    extras = {
        0: (f'<text x="{left + 10}" y="{top - 30}">DEMO 1 - synthetic data</text>'
            f'<text x="{(left + right) / 2 - 30:.0f}" y="{bottom + 60}">Time</text>'
            f'<text x="{left - 40}" y="{bottom + 12}">0</text><text x="{left - 60}" y="{top + 12}">10</text>'),
        1: (f'<text x="{left + 10}" y="{top - 60}">DEMO 2 - synthetic data</text>'
            f'<text x="{left + 10}" y="{top - 22}">saved with wide tick labels</text>'
            f'<text x="{(left + right) / 2 - 30:.0f}" y="{bottom + 60}">Time</text>'
            f'<text x="{left - 150}" y="{bottom + 12}">1000</text><text x="{left - 170}" y="{top + 12}">10000</text>'),
        2: (f'<text x="{left + 10}" y="{top - 20}">DEMO 3 - synthetic data</text>'
            f'<text x="{(left + right) / 2 - 140:.0f}" y="{bottom + 60}">Time after treatment</text>'
            f'<text x="{(left + right) / 2 - 110:.0f}" y="{bottom + 100}">(synthetic units)</text>'
            f'<rect x="{right + 14}" y="{top + 8}" width="20" height="20" fill="#0891b2"/>'
            f'<text x="{right + 42}" y="{top + 26}" font-size="24">series</text>'
            f'<text x="{left - 40}" y="{bottom + 12}">0</text><text x="{left - 60}" y="{top + 12}">10</text>'),
    }[variant]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="480" viewBox="0 0 720 480">
<rect width="720" height="480" fill="white"/>
<path d="M{left} {top} V{bottom} H{right}" stroke="#444" fill="none" stroke-width="3"/>
{ticks}
<polyline points="{points}" stroke="#0891b2" fill="none" stroke-width="5"/>
<g font-family="Arial" fill="#222" font-size="30">
<text x="{left - 8}" y="{(top + bottom) / 2:.0f}" text-anchor="end" transform="rotate(-90 {left - 60} {(top + bottom) / 2:.0f})">Response</text>
{extras}
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
        ('plot-panel-1.svg', _sample_misaligned_chart(0), None),
        ('plot-panel-2.png', _sample_misaligned_chart(1), 'PNG'),
        ('plot-panel-3.svg', _sample_misaligned_chart(2), None),
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
        'divide_cells': base,
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
        # Deliberately misaligned plot frames (see _sample_misaligned_chart)
        # so the lesson has something visible to fix.
        'align_plots': [created['plot-panel-1.svg'], created['plot-panel-2.png'], created['plot-panel-3.svg']],
    }


class TutorialLessonButton(QPushButton):
    def __init__(self, key, state='new', parent=None):
        super().__init__(parent)
        self.setText(lesson_title(key))
        self.setObjectName('tutorialLesson')
        self.setProperty('lessonKey', key)
        self.setProperty('lessonState', state)
        self.setAccessibleName(self.text())
        self.setAutoDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(6)
        self.title_label = QLabel(self.text())
        self.title_label.setObjectName('tutorialLessonTitle')
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.title_label, 1)
        status = {'completed': ('Completed', '已完成'), 'explored': ('Explored', '已浏览')}
        status_text = text(*status.get(state, ('Not started', '未开始')))
        self.status_label = QLabel(status_text if state in status else '')
        self.status_label.setObjectName('tutorialLessonStatus')
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status_label)
        self.status_label.setVisible(state in status)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        steps = sum(step.key not in ('intro', 'finish') for step in LESSONS[key])
        description = ' '.join((
            text(*_LESSON_SUMMARIES[key]), text(f'{steps} steps', f'{steps} 个步骤'), status_text,
            text('Press to start this lesson.', '按下以开始本课。')))
        self.setToolTip(description)
        self.setAccessibleDescription(description)

    def sizeHint(self):
        self.ensurePolished()
        return QSize(420, self.heightForWidth(420))

    def minimumSizeHint(self):
        self.ensurePolished()
        return self.layout().totalMinimumSize()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.layout().totalHeightForWidth(width)

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ''
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        ancestor = self.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                ancestor.ensureWidgetVisible(self)
                break
            ancestor = ancestor.parentWidget()


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
        font.setWeight(QFont.Weight.Medium)
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


class _FillSubcellImageCommand(DropImageCommand):
    def __init__(self, project, cell, path, update_callback):
        super().__init__(cell, path, update_callback)
        self.project = project

    def redo(self):
        cell = self.project.find_cell_by_id(self.cell.id)
        if cell is not None:
            self.cell = cell
            super().redo()

    def undo(self):
        cell = self.project.find_cell_by_id(self.cell.id)
        if cell is not None:
            self.cell = cell
            super().undo()


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
        self._target_hint = None
        self.center = None
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        window._act_auto_layout.triggered.connect(self._layout_triggered)
        window._act_save.triggered.connect(self._save_triggered)
        window._act_save_as.triggered.connect(self._save_triggered)
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

    def _save_triggered(self):
        # Save or Save As (button or Ctrl+S) counts even when the file dialog
        # is cancelled: the step teaches where Save is, and a learner who does
        # not want a practice file must not be stuck with Next disabled.
        if self._active_step_action('save'):
            self.actions.add('save')
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
        self.center.setObjectName('tutorialCenter')
        self.center.setWindowTitle(tr('tutorials_title'))
        self.center.resize(480, 460)
        self.center.setMinimumSize(420, 360)
        layout = QVBoxLayout(self.center)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        intro = QLabel(text('New to ILM? Start with Your first figure. Each lesson opens a separate practice tab; you can also choose a topic directly.',
                            '初次使用 ILM？从“制作第一张组合图”开始。每课都会打开独立练习页，也可直接选择需要的主题。'))
        intro.setObjectName('tutorialCenterSubtitle')
        intro.setTextFormat(Qt.TextFormat.PlainText)
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(intro)
        states = {key: self.window._settings.value(f'tutorials/v1/{key}', '') for key in LESSON_ORDER}
        completed = sum(state == 'completed' for state in states.values())
        total = len(LESSON_ORDER)
        self.center.progress_label = QLabel(text(f'{completed} of {total} completed', f'已完成 {completed} / {total}'))
        self.center.progress_label.setObjectName('tutorialCenterProgress')
        layout.addWidget(self.center.progress_label)
        scroll = QScrollArea()
        scroll.setObjectName('tutorialLessonScroll')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.center.lesson_scroll = scroll
        content = QWidget()
        content.setObjectName('tutorialLessonList')
        lessons = QVBoxLayout(content)
        lessons.setContentsMargins(0, 0, 0, 0)
        lessons.setSpacing(6)
        buttons = []
        for key in LESSON_ORDER:
            state = states[key] if states[key] in ('completed', 'explored') else 'new'
            button = TutorialLessonButton(key, state)
            button.clicked.connect(lambda checked=False, lesson=key: self.start(lesson))
            lessons.addWidget(button)
            buttons.append(button)
        lessons.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.center.resume_button = None
        if self.tab:
            resume = QPushButton(text('Resume lesson', '继续教程'))
            resume.setObjectName('tutorialCenterResume')
            resume.setProperty('accent', 'true')
            resume.setAutoDefault(False)
            resume.clicked.connect(self.resume)
            footer.addWidget(resume)
            self.center.resume_button = resume
        close = QPushButton(tr('help_close'))
        close.setObjectName('tutorialCenterClose')
        close.setAutoDefault(False)
        close.clicked.connect(self.center.close)
        footer.addWidget(close)
        self.center.close_button = close
        layout.addLayout(footer)
        self.center.show()
        self.center.raise_()
        next((button for button in buttons if button.property('lessonState') != 'completed'), buttons[0]).setFocus()

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
            if lesson in ('insets_scale_bars', 'align_plots'):
                # These panels are dark end-to-end (see _sample_micrograph),
                # so any letterboxing from a column/image aspect mismatch
                # would show as a light gap — exactly where a default white
                # scale bar would then be invisible. Auto Layout sizes each
                # column to its image's aspect ratio, eliminating it. The
                # plot-alignment lesson starts from the same file-edge fit
                # so the misaligned axes it teaches about are visible.
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

    def _plots_aligned(self):
        """True once every practice panel is marked and belongs to one
        alignment group that resolves without an active conflict."""
        from src.utils.plot_alignment import resolve_image_placements
        project = self.tab.project
        ids = set(self._cell_ids)
        if not any(ids <= set(group.cell_ids) for group in project.plot_alignment_groups):
            return False
        if any(cell.plot_area is None for cell in project.cells):
            return False
        return not any(issue.group_id or not issue.cell_id
                       for issue in resolve_image_placements(project).issues)

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
            return 'layout' in self.actions and (self.lesson != 'align_plots' or self._plots_aligned())
        if key == 'mark_plots':
            return self._plots_aligned()
        if key == 'labels':
            return any(item.subtype == 'numbering' for item in project.text_items)
        if key == 'label_size':
            inspector = self.window.inspector
            return (inspector._current_item_type == 'text'
                    and inspector.text_group.isVisible()
                    and not inspector.text_group._collapsed
                    and inspector.font_size.isVisible())
        if key == 'save':
            return 'save' in self.actions
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
            root = project.cells[2]
            return len(root.children) >= 2 and (self.lesson != 'divide_cells' or root.split_direction == 'horizontal')
        if key == 'ratio':
            parent = project.cells[2]
            # 0.05, not 0.1: the Inspector ratio field steps by 0.1, and a
            # boundary check at exactly one step would accept or reject a
            # single click depending on float noise.
            return len(parent.split_ratios) >= 2 and abs(parent.split_ratios[0] - parent.split_ratios[1]) > 0.05
        if self.lesson == 'divide_cells' and key in ('nested_rows', 'add_sibling', 'fill_subcells'):
            root = project.cells[2]
            nested = (root.split_direction == 'horizontal' and len(root.children) >= 2
                      and any(child.split_direction == 'vertical' and len(child.children) >= 2
                              for child in root.children))
            if key == 'nested_rows':
                return nested
            if key == 'add_sibling':
                return root.split_direction == 'horizontal' and len(root.children) >= 3
            return nested and all(cell.image_path and not cell.is_placeholder
                                  for cell in root.get_all_leaves())
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
        'nested_rows': ('Divide the right sub-cell', '细分右侧子单元格'),
        'add_sibling': ('Add a sibling on the right', '在右侧添加同级单元格'),
        'fill_subcells': ('Fill empty sub-cells', '填充空白子单元格'),
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
        'open_align_plots': ('Open Align Plot Areas', '打开对齐绘图区'),
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

    @staticmethod
    def _rect_in_viewport(rect, viewport):
        """Fully inside on the vertical scroll axis and at least partly
        visible horizontally — the horizontal scrollbar is disabled, so a
        field wider than the viewport still counts as in view when it is
        vertically contained."""
        return (rect.top() >= viewport.top() and rect.bottom() <= viewport.bottom()
                and rect.left() <= viewport.right() and rect.right() >= viewport.left())

    def _foldable_blocker(self, scroll, own_section, field_top):
        """First expanded section the user can fold to un-block the target:
        visible, not *own_section*, above the field, and with its header
        inside the scroll viewport so it can actually be clicked."""
        viewport = scroll.viewport().rect()
        candidates = []
        for section in self.window.inspector.findChildren(CollapsibleSection):
            if (section is own_section or section._collapsed
                    or not section.isVisible()):
                continue
            top = section._header.mapTo(scroll.viewport(), QPoint(0, 0))
            header_rect = QRect(top, section._header.size())
            if top.y() < field_top and self._rect_in_viewport(header_rect, viewport):
                candidates.append((top.y(), section))
        candidates.sort(key=lambda pair: pair[0])
        return candidates[0][1] if candidates else None

    def _reveal_section(self, section):
        """Unfold *section* for a guided action and fold the other expanded
        sections, so the highlighted field lands inside the scroll viewport."""
        for other in self.window.inspector.findChildren(CollapsibleSection):
            if (other is not section and other.isVisible()
                    and not other._collapsed):
                other.set_collapsed(True, animate=False)
        section.set_collapsed(False, animate=False)
        section.show()

    def _show_target(self):
        target = self.step.target
        widget = self.window.view.viewport()
        rect = widget.rect()
        compact = False
        hint = None
        if target in self._INSPECTOR_TARGETS:
            field = getattr(self.window.inspector, self._INSPECTOR_TARGETS[target])
            ancestor = field.parentWidget()
            while ancestor is not None and not isinstance(ancestor, CollapsibleSection):
                ancestor = ancestor.parentWidget()
            if not field.isVisible():
                # Every Inspector section starts collapsed, and selecting an
                # item shows its section without unfolding it — so the field a
                # step points at can be hidden by nothing but a folded header.
                # Expand a section that is shown-but-collapsed; a section that
                # is hidden entirely means the wrong thing is selected, and
                # expanding it cannot help.
                if (ancestor is not None and ancestor.isVisible()
                        and ancestor._collapsed):
                    ancestor.set_collapsed(False, animate=False)
            if field.isVisible():
                scroll = self.window.inspector._scroll
                # A just-expanded section leaves nested layouts queued behind
                # deferred LayoutRequests; flush until the field has real
                # geometry so the viewport check measures the true position.
                for _ in range(4):
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
                    if field.height() > 0:
                        break
                field_rect = QRect(field.mapTo(scroll.viewport(), QPoint(0, 0)),
                                   field.size())
                if self._rect_in_viewport(field_rect, scroll.viewport().rect()):
                    widget, rect, compact = field, field.rect(), True
                else:
                    blocker = self._foldable_blocker(scroll, ancestor, field_rect.top())
                    if blocker is not None:
                        widget, rect = blocker._header, blocker._header.rect()
                        section_name = (ancestor._title_lbl.text()
                                        if ancestor is not None else '')
                        hint = text(
                            f'Fold “{blocker._title_lbl.text()}” (click its header) so “{section_name}” comes into view, then change the highlighted field.',
                            f'点击“{blocker._title_lbl.text()}”的标题将其折叠，让“{section_name}”进入视野，再修改高亮字段。')
                    else:
                        scroll.ensureWidgetVisible(field, 0, 24)
                        widget, rect, compact = field, field.rect(), True
        elif target == 'division_panel':
            bounds = QRectF()
            for cell in self.tab.project.cells[2].get_all_leaves():
                item = self.tab.scene.cell_items.get(cell.id)
                if item is not None:
                    bounds = bounds.united(item.sceneBoundingRect())
            rect = (self.tab.view.mapFromScene(bounds).boundingRect().intersected(widget.rect())
                    if not bounds.isEmpty() else QRect())
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
            return None
        if (self.highlight is None or sip.isdeleted(self.highlight)
                or self.highlight.target is not widget or self.highlight.compact != compact):
            self._clear_highlight()
            self.highlight = TutorialHighlight(widget, compact)
        self.highlight.set_target_rect(rect)
        self.highlight.show()
        self.highlight.raise_()
        return hint

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
        if active:
            hint = self._show_target()
        else:
            self._clear_highlight()
            hint = None
        self._target_hint = hint
        self.card.status.setText(text('Return to the practice tab to continue.', '请返回练习标签页继续。') if not active else
                                 text('Action detected. Check the result, then choose Next.', '已检测到操作。检查结果后，点击“下一步”。') if success else
                                 (text('Choose Next to begin.', '点击“下一步”开始练习。') if self.step.key == 'intro' else text('Choose Finish to leave the lesson; the practice tab stays open.', '点击“完成”退出教程，练习页会保留。')) if ready else
                                 hint or text('Follow the step above. Next becomes available when its action is detected; Skip moves on without doing it.', '请按上方说明操作。检测到相应操作后可点击“下一步”；“跳过”会直接进入下一步，不代做操作。'))
        self.card.back.setText(text('Back', '上一步'))
        self.card.skip.setText(text('Skip', '跳过'))
        self.card.next.setText(text('Finish', '完成') if self.step.key == 'finish' else text('Next', '下一步'))
        self.card.exit.setText(text('Exit', '退出'))
        self.card.back.setToolTip(text('Review the previous instructions without undoing your edits.', '回看上一步说明，不会撤销已做的编辑。'))
        self.card.skip.setToolTip(text('Move to the next step without performing this one. Later steps may need its result.', '不执行本步，直接进入下一步；后续步骤可能需要本步的结果。'))
        self.card.exit.setToolTip(text('Stop the lesson and return to your previous tab. The practice project stays open.', '结束教程并返回之前的标签页，练习工程仍会保留。'))
        self.card.back.setEnabled(active and self.index > 0)
        self.card.skip.setEnabled(active and self.step.key != 'finish')
        self.card.next.setEnabled(ready)
        self.card.action.setVisible(bool(self.step.action))
        self.card.action.setEnabled(active)
        self.card.action.setText(text(*self._ACTION_LABELS.get(
            self.step.action, ('Open inspector', '打开检查器'))))

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
            self._reveal_section(self.window.inspector.text_group)
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
            self._reveal_section(self.window.inspector.subcell_group)
        elif self.lesson == 'divide_cells' and action == 'nested_rows':
            from src.app.commands import SplitCellCommand
            root = self.tab.project.cells[2]
            if (root.split_direction != 'horizontal' or len(root.children) < 2
                    or any(child.split_direction == 'vertical' and len(child.children) >= 2
                           for child in root.children)
                    or not root.children[-1].is_leaf):
                return
            self.tab.undo_stack.push(SplitCellCommand(
                self.tab.project, root.children[-1].id, 'vertical', count=2,
                update_callback=self.window._refresh_and_update))
        elif self.lesson == 'divide_cells' and action == 'add_sibling':
            root = self.tab.project.cells[2]
            if (root.split_direction != 'horizontal' or not root.children
                    or len(root.children) >= 3 or not root.children[0].is_leaf):
                return
            self.window._ctx_wrap_and_insert(root.children[0].id, 'horizontal', 'after')
        elif self.lesson == 'divide_cells' and action == 'fill_subcells':
            root = self.tab.project.cells[2]
            if root.is_leaf:
                return
            blanks = [cell for cell in root.get_all_leaves() if not cell.image_path or cell.is_placeholder]
            if not blanks:
                return
            stack = self.tab.undo_stack
            stack.beginMacro(text('Fill empty sub-cells', '填充空白子单元格'))
            try:
                for index, cell in enumerate(blanks):
                    stack.push(_FillSubcellImageCommand(
                        self.tab.project, cell, self.paths[index % len(self.paths)],
                        self.window._refresh_and_update))
            finally:
                stack.endMacro()
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
            self._reveal_section(self.window.inspector.cell_group)
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
        # ── align_plots ──
        elif action == 'open_align_plots':
            if self._plots_aligned():
                return
            self._select_cells(0, 1, 2)
            # Modal: the card is blocked until the dialog closes, and the
            # dialog's own Select → Mark → Match → Apply guidance takes over.
            self.window._on_align_plot_areas([cell.id for cell in self.tab.project.cells])
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
            self._reveal_section(self.window.inspector.project_group)
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
        self._target_hint = None
        previous, practice = self.previous_tab, self.tab
        self.tab = None
        self.previous_tab = None
        if practice and practice.project is not self._practice_project and hasattr(practice, 'tutorial_title'):
            del practice.tutorial_title
            self.window._update_window_title()
        if practice and self.window.project is self._practice_project and previous in self.window._tabs:
            self.window._activate_tab(self.window._tabs.index(previous))
