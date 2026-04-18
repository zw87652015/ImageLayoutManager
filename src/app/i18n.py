"""Lightweight dictionary-based i18n. Supports 'en' and 'zh' (Simplified Chinese)."""

_lang = "zh"

_T: dict[str, dict[str, str]] = {
    # ── Menus ────────────────────────────────────────────────────────
    "menu_file":            {"en": "File",              "zh": "文件"},
    "menu_edit":            {"en": "Edit",              "zh": "编辑"},
    "menu_layout":          {"en": "Layout",            "zh": "布局"},
    "menu_view":            {"en": "View",              "zh": "视图"},
    "menu_help":            {"en": "Help",              "zh": "帮助"},

    "action_undo":          {"en": "Undo",              "zh": "撤销"},
    "action_redo":          {"en": "Redo",              "zh": "重做"},
    "action_new":           {"en": "New",               "zh": "新建"},
    "action_open":          {"en": "Open",              "zh": "打开"},
    "action_save":          {"en": "Save",              "zh": "保存"},
    "action_save_as":       {"en": "Save As…",          "zh": "另存为…"},
    "action_import":        {"en": "Import Images…",    "zh": "导入图片…"},
    "action_open_grid":     {"en": "Open Images as Grid…", "zh": "以网格打开图片…"},
    "action_reload":        {"en": "Reload Images",     "zh": "重新加载图片"},
    "action_export_pdf":    {"en": "Export PDF…",       "zh": "导出 PDF…"},
    "action_export_tiff":   {"en": "Export TIFF…",      "zh": "导出 TIFF…"},
    "action_export_jpg":    {"en": "Export JPG…",       "zh": "导出 JPG…"},
    "action_add_text":      {"en": "Add Floating Text", "zh": "添加浮动文字"},
    "ctx_add_floating_text_here": {"en": "Add Floating Text Here", "zh": "在此处添加浮动文字"},
    "opt_color_custom":      {"en": "Custom…",             "zh": "自定义…"},
    "color_custom_tooltip":  {"en": "Custom color…",      "zh": "自定义颜色…"},
    "color_dialog_title":    {"en": "Pick Color",          "zh": "选取颜色"},
    "action_delete_sel":    {"en": "Delete Selected",   "zh": "删除所选"},
    "action_delete_img":    {"en": "Delete Image",      "zh": "删除图片"},
    "action_auto_label":          {"en": "Auto Label",                "zh": "自动标注"},
    "action_auto_label_incell":   {"en": "Auto In-Cell Labels",       "zh": "自动内嵌标注"},
    "action_auto_label_outcell":  {"en": "Auto Label Row",            "zh": "自动标注行"},
    "action_auto_layout":   {"en": "Auto Layout",       "zh": "自动布局"},
    "action_bake":          {"en": "Convert Grid → Freeform", "zh": "网格转自由布局"},
    "action_grid_mode":     {"en": "Switch to Grid Mode",     "zh": "切换至网格模式"},
    "action_bring_front":   {"en": "Bring to Front",    "zh": "置于顶层"},
    "action_send_back":     {"en": "Send to Back",      "zh": "置于底层"},
    "action_light_theme":   {"en": "☀ Light",           "zh": "☀ 浅色"},
    "action_dark_theme":    {"en": "☾ Dark",            "zh": "☾ 深色"},
    "action_switch_light":  {"en": "Switch to Light Theme", "zh": "切换至浅色主题"},
    "action_switch_dark":   {"en": "Switch to Dark Theme",  "zh": "切换至深色主题"},
    "action_switch_zh":     {"en": "切换到中文",         "zh": "Switch to English"},
    "action_toggle_layers": {"en": "Layers Panel",       "zh": "图层面板"},
    "action_about":         {"en": "About Academic Figure Layout", "zh": "关于学术图排版工具"},
    "action_user_guide":    {"en": "User Guide…",       "zh": "使用指南…"},
    "toolbar_export":       {"en": "Export",            "zh": "导出"},

    # ── Inspector group boxes ──────────────────────────────────────
    "grp_project":          {"en": "Project Settings",  "zh": "项目设置"},
    "grp_cell":             {"en": "Selected Cell",     "zh": "选中单元格"},
    "grp_label_cell":       {"en": "Label Cell Settings","zh": "标注单元格设置"},
    "grp_row":              {"en": "Row Settings",      "zh": "行设置"},
    "grp_subcell":          {"en": "Sub-Cell Settings", "zh": "子单元格设置"},
    "grp_text":             {"en": "Selected Text",     "zh": "选中文字"},

    # ── Inspector section dividers ────────────────────────────────
    "sec_grid":             {"en": "<b>Grid Settings</b>",    "zh": "<b>网格设置</b>"},
    "sec_corner_labels":    {"en": "<b>Corner Labels</b>",    "zh": "<b>角标</b>"},
    "sec_layout":           {"en": "<b>Layout</b>",           "zh": "<b>布局</b>"},
    "sec_freeform":         {"en": "— Freeform Geometry —",   "zh": "— 自由布局尺寸 —"},
    "sec_grid_override":    {"en": "— Grid Size Override (0=Auto) —", "zh": "— 网格尺寸覆盖 (0=自动) —"},
    "sec_padding":          {"en": "— Padding —",             "zh": "— 内边距 —"},
    "sec_scale_bar":        {"en": "— Scale Bar —",           "zh": "— 比例尺 —"},

    # ── Inspector buttons / checkboxes ────────────────────────────
    "btn_apply_all":        {"en": "Apply to All",      "zh": "应用到全部"},
    "chk_bold":             {"en": "Bold",              "zh": "粗体"},
    "chk_scale_enabled":    {"en": "Enable Scale Bar",  "zh": "启用比例尺"},
    "chk_scale_text":       {"en": "Show Text",         "zh": "显示文字"},
    "btn_manage":           {"en": "Manage…",           "zh": "管理…"},
    "lbl_fixed_width":      {"en": "Fixed Width:",      "zh": "固定宽度:"},
    "lbl_fixed_height":     {"en": "Fixed Height:",     "zh": "固定高度:"},

    # ── Inspector combo-box options ───────────────────────────────
    "opt_grid_stretch":     {"en": "Stretch Rows to Page",  "zh": "行填充页面"},
    "opt_grid_fixed":       {"en": "Fixed Cell Width",      "zh": "固定单元格宽度"},
    "opt_color_black":      {"en": "Black",                 "zh": "黑色"},
    "opt_color_white":      {"en": "White",                 "zh": "白色"},
    "opt_align_left":       {"en": "Left",                  "zh": "左"},
    "opt_align_center":     {"en": "Center",                "zh": "居中"},
    "opt_align_right":      {"en": "Right",                 "zh": "右"},
    "opt_row_left":         {"en": "left",                  "zh": "左"},
    "opt_row_center":       {"en": "center",                "zh": "居中"},
    "opt_row_right":        {"en": "right",                 "zh": "右"},

    # ── Inspector misc labels ──────────────────────────────────────
    "no_selection":              {"en": "No Selection",             "zh": "未选中任何内容"},
    "multi_cells_selected":      {"en": "{n} cells selected",       "zh": "已选中 {n} 个单元格"},
    "multi_cells_desc":          {"en": "Changes apply to all selected cells.", "zh": "更改将应用到所有选中的单元格。"},
    "btn_apply_all_corner":      {"en": "Apply to All Corner",      "zh": "应用到全部角标"},
    "btn_apply_all_numbering":   {"en": "Apply to All Numbering",   "zh": "应用到全部编号"},

    # ── Layers panel ──────────────────────────────────────────────
    "layers_header":        {"en": "LAYERS",            "zh": "图层"},
    "layers_row":           {"en": "Row",               "zh": "行"},
    "layers_empty":         {"en": "Empty",             "zh": "空"},
    "layers_split_h":       {"en": "⇔ Split",           "zh": "⇔ 水平分割"},
    "layers_split_v":       {"en": "⇕ Split",           "zh": "⇕ 垂直分割"},
    "layers_sub":           {"en": "Sub",               "zh": "子"},
    "layers_text_items":    {"en": "Text Items",        "zh": "文字图层"},

    # ── Inspector form row labels ─────────────────────────────────
    "lbl_dpi":              {"en": "DPI:",              "zh": "分辨率:"},
    "lbl_page_preset":      {"en": "Page Preset:",      "zh": "页面预设:"},
    "lbl_page_width":       {"en": "Page Width:",       "zh": "页面宽度:"},
    "lbl_page_height":      {"en": "Page Height:",      "zh": "页面高度:"},
    "lbl_margin_top":       {"en": "Margin Top:",       "zh": "上边距:"},
    "lbl_margin_bottom":    {"en": "Margin Bottom:",    "zh": "下边距:"},
    "lbl_margin_left":      {"en": "Margin Left:",      "zh": "左边距:"},
    "lbl_margin_right":     {"en": "Margin Right:",     "zh": "右边距:"},
    "lbl_grid_mode":        {"en": "Grid Mode:",        "zh": "网格模式:"},
    "lbl_row_align":        {"en": "Row Alignment:",    "zh": "行对齐:"},
    "lbl_font":             {"en": "Font:",             "zh": "字体:"},
    "lbl_size":             {"en": "Size:",             "zh": "大小:"},
    "lbl_color":            {"en": "Color:",            "zh": "颜色:"},
    "lbl_cell_gap":         {"en": "Cell Gap:",         "zh": "单元格间距:"},
    "lbl_fit_mode":         {"en": "Fit Mode:",         "zh": "填充模式:"},
    "lbl_rotation":         {"en": "Rotation:",         "zh": "旋转:"},
    "lbl_align_h":          {"en": "Align H:",          "zh": "水平对齐:"},
    "lbl_align_v":          {"en": "Align V:",          "zh": "垂直对齐:"},
    "lbl_pos_x":            {"en": "Pos X (mm):",       "zh": "X坐标 (mm):"},
    "lbl_pos_y":            {"en": "Pos Y (mm):",       "zh": "Y坐标 (mm):"},
    "lbl_width_mm":         {"en": "Width (mm):",       "zh": "宽度 (mm):"},
    "lbl_height_mm":        {"en": "Height (mm):",      "zh": "高度 (mm):"},
    "lbl_pad_top":          {"en": "Pad Top (mm):",     "zh": "上内边距 (mm):"},
    "lbl_pad_bottom":       {"en": "Pad Bottom:",       "zh": "下内边距:"},
    "lbl_pad_left":         {"en": "Pad Left:",         "zh": "左内边距:"},
    "lbl_pad_right":        {"en": "Pad Right:",        "zh": "右内边距:"},
    "lbl_corner_tl":        {"en": "Label TL:",         "zh": "角标 左上:"},
    "lbl_corner_tr":        {"en": "Label TR:",         "zh": "角标 右上:"},
    "lbl_corner_bl":        {"en": "Label BL:",         "zh": "角标 左下:"},
    "lbl_corner_br":        {"en": "Label BR:",         "zh": "角标 右下:"},
    "lbl_mapping":          {"en": "Mapping:",          "zh": "比例映射:"},
    "lbl_length":           {"en": "Length:",           "zh": "长度:"},
    "lbl_custom_text":      {"en": "Custom Text:",      "zh": "自定义文字:"},
    "lbl_text_size":        {"en": "Text Size:",        "zh": "文字大小:"},
    "lbl_thickness":        {"en": "Thickness:",        "zh": "粗细:"},
    "lbl_position":         {"en": "Position:",         "zh": "位置:"},
    "lbl_offset_x_mm":      {"en": "Offset X (mm):",   "zh": "X偏移 (mm):"},
    "lbl_offset_y_mm":      {"en": "Offset Y (mm):",   "zh": "Y偏移 (mm):"},
    "lbl_text":             {"en": "Text:",             "zh": "文字:"},
    "lbl_scheme":           {"en": "Scheme:",           "zh": "标注方案:"},
    "lbl_size_pt":          {"en": "Size (pt):",        "zh": "大小 (pt):"},
    "lbl_align":            {"en": "Align:",            "zh": "对齐:"},
    "lbl_offset_x":         {"en": "Offset X:",         "zh": "X偏移:"},
    "lbl_offset_y":         {"en": "Offset Y:",         "zh": "Y偏移:"},
    "lbl_row_height":       {"en": "Row Height:",       "zh": "行高:"},
    "lbl_height_ratio":     {"en": "Height Ratio:",     "zh": "高度比例:"},
    "lbl_col_ratios":       {"en": "Col Ratios:",       "zh": "列比例:"},
    "lbl_size_ratio":       {"en": "Size Ratio:",       "zh": "大小比例:"},
    "lbl_content":          {"en": "Content:",          "zh": "内容:"},

    # ── Help dialog ───────────────────────────────────────────────
    "help_title":           {"en": "Help — Academic Figure Layout", "zh": "帮助 — 学术图排版工具"},
    "help_tab_start":       {"en": "Getting Started",  "zh": "快速入门"},
    "help_tab_images":      {"en": "Images",            "zh": "图片"},
    "help_tab_cells":       {"en": "Cells & Splitting", "zh": "单元格与分割"},
    "help_tab_labels":      {"en": "Labels & Text",     "zh": "标注与文字"},
    "help_tab_export":      {"en": "Export",            "zh": "导出"},
    "help_tab_shortcuts":   {"en": "Shortcuts",         "zh": "快捷键"},

    # ── About dialog ─────────────────────────────────────────────
    "about_title":          {"en": "About Academic Figure Layout", "zh": "关于学术图排版工具"},
    "about_app_name":       {"en": "Academic Figure Layout",       "zh": "学术图排版工具"},
    "about_desc":           {"en": "A desktop tool for producing consistent, publication-ready\nmulti-panel figures with precise spacing, labels, and export.",
                             "zh": "一款用于制作一致、符合出版要求的\n多面板学术图表的桌面工具，支持精确的间距、标注与导出。"},
    "about_developer":      {"en": "Developer",         "zh": "开发者"},
    "about_website":        {"en": "Website",           "zh": "官方网站"},
    "about_download":       {"en": "Download",          "zh": "下载"},
    "status_update_available": {"en": "New version {tag} available — click to open About",
                                 "zh": "新版本 {tag} 可用 — 点击打开「关于」以下载"},
    "status_update_tooltip":   {"en": "Open About dialog to download the latest version",
                                 "zh": "打开「关于」对话框下载最新版本"},
    "about_repository":     {"en": "Repository",        "zh": "代码仓库"},
    "about_license":        {"en": "License",           "zh": "许可协议"},
    "about_check_btn":      {"en": "Check for Updates", "zh": "检查更新"},
    "about_open_github":    {"en": "Open GitHub",       "zh": "打开 GitHub"},
    "about_close":          {"en": "Close",             "zh": "关闭"},
    "about_checking":       {"en": "Checking…",         "zh": "正在检查…"},
    "about_latest":         {"en": "✔ You are running the latest version.", "zh": "✔ 当前已是最新版本。"},
    "about_pre":            {"en": "✔ You are running a pre-release version.", "zh": "✔ 当前运行的是预发布版本。"},
    "about_no_conn":        {"en": "⚠ Could not reach GitHub. Check your connection.", "zh": "⚠ 无法连接 GitHub，请检查网络连接。"},
    "about_click_check":    {"en": "Click \"Check for Updates\" to check.", "zh": "点击「检查更新」以检查新版本。"},

    # ── Status bar / misc ─────────────────────────────────────────
    "zoom_label":           {"en": "Zoom:",             "zh": "缩放:"},
    "canvas_label":         {"en": "Canvas:",           "zh": "画布:"},
}


def tr(key: str) -> str:
    """Return the translation for *key* in the current language, falling back to English."""
    return _T.get(key, {}).get(_lang) or _T.get(key, {}).get("en") or key


def set_language(lang: str) -> None:
    global _lang
    if lang in ("en", "zh"):
        _lang = lang


def current_language() -> str:
    return _lang
