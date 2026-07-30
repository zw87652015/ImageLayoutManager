"""User-facing changelog shown in the About dialog.

Keep every bullet to one short line in plain words — this page is for
users, not developers. Newest version first. Each bullet has an ``en``
and a ``zh`` text; the About dialog renders the current UI language.
"""

from src.app.i18n import current_language

# (version, date, bullets)
CHANGELOG = [
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
