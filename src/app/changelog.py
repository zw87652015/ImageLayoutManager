"""User-facing changelog shown in the About dialog.

Keep every bullet to one short line in plain words — this page is for
users, not developers. Newest version first. Each bullet has an ``en``
and a ``zh`` text; the About dialog renders the current UI language.
"""

from src.app.i18n import current_language

# (version, date, bullets)
CHANGELOG = [
    ("3.4.1", "2026-09-18", [
        {"en": "Align Plot Areas: mark each chart's plotting area, then match plot heights and bottom axes across panels in grid or freeform layouts, without editing the source files. Open it from the arrow beside Auto Layout, the Layout menu, a panel's right-click menu, or the Inspector's new Plot alignment row.",
         "zh": "新增“对齐绘图区”：标记每张图的绘图区，即可在网格或自由排布中统一绘图高度并对齐底部坐标轴，不修改源文件。可从“自动布局”旁的箭头、“布局”菜单、面板右键菜单或检查器中新增的“绘图区对齐”行打开。"},
        {"en": "Alignment is saved with .figlayout and .figpack projects; projects saved by this version need version 3.4.1 or later to open.",
         "zh": "对齐设置会随 .figlayout 和 .figpack 工程保存；由本版本保存的工程需使用 3.4.1 或更高版本打开。"},
        {"en": "New tutorial lessons: Divide cells and Align plot areas, in a clearer learning order, with a compact lesson list.",
         "zh": "新增教程：细分单元格、对齐绘图区，学习顺序更清晰，教程列表更紧凑。"},
        {"en": "Export all source images from the current project to a folder in their original formats from the File menu.",
         "zh": "可从“文件”菜单将当前项目使用的全部源图片按原始格式导出到文件夹。"},
        {"en": "In the first-figure lesson, the Save step completes when you click Save or press Ctrl+S, even if you cancel the file dialog.",
         "zh": "在“第一张图”教程中，点击“保存”或按 Ctrl+S 即可完成保存步骤，即使取消了文件对话框。"},
        {"en": "Interface animations now run at your display's refresh rate (for example 120 or 144 Hz) instead of 60 fps, with the same durations, and step back automatically when the figure is heavy to keep interaction smooth.",
         "zh": "界面动画现在按显示器刷新率运行（如 120 或 144 Hz），不再固定 60 帧，时长不变；图面较重时会自动降速以保持操作流畅。"},
        {"en": "The Welcome window now shows the ILM logo, drawn as vector figure panels that follow the light and dark themes.",
         "zh": "欢迎窗口新增 ILM 徽标：由矢量图面板拼成，并随浅色/深色主题变化。"},
        {"en": "Subdivide is now directly in a cell's right-click menu.",
         "zh": "“细分为子单元格”现在直接位于单元格右键菜单中。"},
        {"en": "Lighter interface text in both languages.",
         "zh": "中英文界面文字更纤细。"},
        {"en": "Inset images default to a black border in the top-right corner.",
         "zh": "插图默认使用黑色边框并置于右上角。"},
        {"en": "Fixed the Inspector's right edge being cut off at its default width (scale-bar length and inset position fields).",
         "zh": "修复检查器在默认宽度下右侧被裁切的问题（比例尺长度和插图位置字段）。"},
        {"en": "Fixed a flicker when folding Inspector sections.",
         "zh": "修复折叠设置区时的闪烁。"},
    ]),
    ("3.4.0", "2026-09-11", [
        {"en": "Match selected text sizes across SVG and raster panels without changing the source files.",
         "zh": "无需修改源文件，即可统一 SVG 和位图面板中所选文字的大小。"},
        {"en": "Drop several images or a folder onto the app to create an automatically arranged layout.",
         "zh": "将多张图片或一个文件夹拖入软件，即可自动创建并排布版面。"},
        {"en": "Drag a saved project onto the welcome window to open it directly.",
         "zh": "将已保存的工程拖到欢迎窗口，即可直接打开。"},
        {"en": "Older project files now open through safer, versioned upgrades.",
         "zh": "旧版工程文件现在会通过更安全、带版本的升级流程打开。"},
        {"en": "Choose Standard, Reduced, or Off motion in Preferences for calmer interactions.",
         "zh": "可在“首选项”中选择标准、减少或关闭动效，让交互更从容。"},
        {"en": "Tutorial lessons are now available.",
         "zh": "新增引导教程。"},
        {"en": "In freeform mode, drag panels in the Layers panel to reorder them like Photoshop layers; PiP insets can be reordered the same way.",
         "zh": "自由排布模式下，可在图层面板中像 Photoshop 图层一样拖动面板调整前后顺序；画中画插图也可以同样排序。"},
    ]),
    ("3.3.5", "2026-08-21", [
        {"en": "New shared labels are numbered automatically: Label 1, Label 2, and so on.",
         "zh": "新建共享标签会自动编号：标注 1、标注 2，以此类推。"},
        {"en": "The + row/cell buttons always stay in the margin now, even with shared labels.",
         "zh": "+ 加行/加列按钮现在始终呆在边距里，即使有共享标签也不会叠上去。"},
        {"en": "Label text in exported files now matches the size you see in the app.",
         "zh": "导出文件里的标注文字大小，现在和软件里看到的一样了。"},
    ]),
    ("3.3.3", "2026-07-30", [
        {"en": "Shared labels can span several cells; drag a label band outward to stack it.",
         "zh": "共享标签可以跨多个单元格了；把标签带往外拖，就能调整叠放顺序。"},
        {"en": "Press Delete to remove a selected shared label.",
         "zh": "选中共享标签后，按 Delete 键就能删掉。"},
        {"en": "Scrolling the side panel no longer changes values by accident.",
         "zh": "滚动右侧面板时，不会再不小心改掉数值了。"},
        {"en": "All menus and dialogs now follow the chosen language.",
         "zh": "菜单和对话框现在都会跟着界面语言走了。"},
        {"en": "Changing the theme in Preferences now recolours the canvas too.",
         "zh": "在“首选项”里换深色/浅色，画布颜色也会一起变了。"},
        {"en": "The day/night button left the toolbar; use Edit > Preferences instead.",
         "zh": "工具栏上的昼夜切换按钮去掉了，换主题请到“编辑 > 首选项”。"},
        {"en": "The app is now called Image Layout Manager everywhere.",
         "zh": "应用名字统一改成 Image Layout Manager 了。"},
    ]),
]


def render_changelog_html() -> str:
    """Render the changelog as simple HTML in the current UI language."""
    lang = current_language()
    parts = []
    for version, date, bullets in CHANGELOG:
        parts.append(f"<p><b>Version {version}</b> "
                     f"<span style='color:#888888;'>({date})</span></p><ul>")
        for bullet in bullets:
            parts.append(f"<li>{bullet.get(lang, bullet['en'])}</li>")
        parts.append("</ul>")
    return "".join(parts)
