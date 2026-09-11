"""User-facing changelog shown in the About dialog.

Keep every bullet to one short line in plain words — this page is for
users, not developers. Newest version first. Each bullet has an ``en``
and a ``zh`` text; the About dialog renders the current UI language.
"""

from src.app.i18n import current_language

# (version, date, bullets)
CHANGELOG = [
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
        {"en": "Providing tutorial lessons for new users.",
         "zh": "为新用户提供了教学模式。"},
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
