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
    "action_convert_to_bundle": {"en": "Convert to .figpack…", "zh": "转换为 .figpack…"},
    "action_import":        {"en": "Import Images…",    "zh": "导入图片…"},
    "action_open_grid":     {"en": "Open Images as Grid…", "zh": "以网格打开图片…"},
    "action_reload":        {"en": "Reload Images",     "zh": "重新加载图片"},
    "action_export_pdf":    {"en": "Export PDF…",       "zh": "导出 PDF…"},
    "action_export_tiff":   {"en": "Export TIFF…",      "zh": "导出 TIFF…"},
    "action_export_jpg":    {"en": "Export JPG…",       "zh": "导出 JPG…"},
    "action_export_png":    {"en": "Export PNG…",       "zh": "导出 PNG…"},
    "action_export_svg":    {"en": "Export SVG…",       "zh": "导出 SVG…"},
    "lbl_bg_color":         {"en": "BG Color",          "zh": "背景色"},
    "lbl_bg_padding":       {"en": "BG Padding",        "zh": "背景内边距"},
    "lbl_label_placement":  {"en": "Placement",         "zh": "标注位置"},
    "lbl_label_col_width":  {"en": "Column Width",      "zh": "标注列宽"},
    "menu_label_placement": {"en": "All Labels Placement", "zh": "全部标注位置"},
    "placement_in_cell":    {"en": "In-Cell",           "zh": "嵌入图片"},
    "placement_row_above":  {"en": "Row Above",         "zh": "上方行"},
    "placement_row_below":  {"en": "Row Below",         "zh": "下方行"},
    "placement_col_left":   {"en": "Column Left",       "zh": "左侧列"},
    "placement_col_right":  {"en": "Column Right",      "zh": "右侧列"},
    "action_add_text":      {"en": "Add Floating Text", "zh": "添加浮动文字"},
    "ctx_add_floating_text_here": {"en": "Add Floating Text Here", "zh": "在此处添加浮动文字"},
    "opt_color_custom":      {"en": "Custom…",             "zh": "自定义…"},
    "color_custom_tooltip":  {"en": "Custom color…",      "zh": "自定义颜色…"},
    "color_dialog_title":    {"en": "Pick Color",          "zh": "选取颜色"},
    "action_delete_sel":    {"en": "Delete Selected",   "zh": "删除所选"},
    "action_delete_img":    {"en": "Delete Image",      "zh": "删除图片"},
    "action_auto_label":          {"en": "Auto Label",                "zh": "自动标注"},
    "action_auto_label_incell":   {"en": "Auto In-Cell Labels",       "zh": "自动内嵌标注"},
    "action_auto_label_outcell":  {"en": "Auto Above-Cell Labels",    "zh": "自动图外标注"},
    "tooltip_auto_label_incell":  {"en": "Place panel labels (a, b, c…) directly inside each image cell",
                                   "zh": "将面板标注（a、b、c…）直接叠加在图片格内"},
    "tooltip_auto_label_outcell": {"en": "Place panel labels in a dedicated header row above each image — keeps labels off the images",
                                   "zh": "将面板标注置于每行图片上方的独立标注行中，避免遮挡图片内容"},
    "action_auto_layout":   {"en": "Auto Layout",       "zh": "自动布局"},
    "action_set_export_region":   {"en": "Set Export Region",    "zh": "设置导出区域"},
    "action_clear_export_region": {"en": "Clear Export Region",  "zh": "清除导出区域"},
    "msg_define_export_region_hint": {
        "en": "Drag on the page to select the export region. Press Esc to cancel.",
        "zh": "在页面上拖拽以选择导出区域。按 Esc 取消。"
    },
    "action_bake":          {"en": "Convert Grid → Freeform", "zh": "转换为自由布局"},
    "action_grid_mode":     {"en": "Switch to Grid Mode",     "zh": "切换至网格模式"},
    "action_bring_front":   {"en": "Bring to Front",    "zh": "置于顶层"},
    "action_send_back":     {"en": "Send to Back",      "zh": "置于底层"},
    "action_light_theme":   {"en": "☀ Light",           "zh": "☀ 浅色"},
    "action_dark_theme":    {"en": "☾ Dark",            "zh": "☾ 深色"},
    "action_switch_light":  {"en": "Switch to Light Theme", "zh": "切换至浅色主题"},
    "action_switch_dark":   {"en": "Switch to Dark Theme",  "zh": "切换至深色主题"},
    "theme_light":          {"en": "Light",                  "zh": "浅色"},
    "theme_dark":           {"en": "Dark",                   "zh": "深色"},
    "dlg_unsaved_title":    {"en": "Unsaved Changes",        "zh": "未保存的更改"},
    "dlg_unsaved_body":     {"en": "'{name}' has unsaved changes. Save now?",
                             "zh": "「{name}」有未保存的更改，是否立即保存？"},
    "btn_save":             {"en": "Save",                   "zh": "保存"},
    "btn_discard":          {"en": "Discard",                "zh": "放弃更改"},
    "btn_cancel":           {"en": "Cancel",                 "zh": "取消"},
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
    "grp_pip":              {"en": "Selected PiP",      "zh": "选中插图"},

    # ── Inspector section dividers ────────────────────────────────
    "sec_grid":             {"en": "<b>Grid Settings</b>",    "zh": "<b>网格设置</b>"},
    "sec_corner_labels":    {"en": "<b>Corner Labels</b>",    "zh": "<b>角标</b>"},
    "sec_label_placement":  {"en": "<b>Label Placement</b>",  "zh": "<b>标注位置</b>"},
    "sec_layout":           {"en": "<b>Layout</b>",           "zh": "<b>布局</b>"},
    "sec_freeform":         {"en": "— Freeform Geometry —",   "zh": "— 自由布局尺寸 —"},
    "sec_grid_override":    {"en": "— Grid Size Override (0=Auto) —", "zh": "— 网格尺寸覆盖 (0=自动) —"},
    "sec_size_group":       {"en": "— Size Group —",          "zh": "— 尺寸组 —"},
    "sec_padding":          {"en": "— Padding —",             "zh": "— 内边距 —"},
    "sec_scale_bar":        {"en": "— Scale Bar —",           "zh": "— 比例尺 —"},

    # ── Inspector buttons / checkboxes ────────────────────────────
    "btn_apply_all":        {"en": "Apply to All",      "zh": "应用到全部"},
    "chk_bold":             {"en": "Bold",              "zh": "粗体"},
    "chk_border_enabled":   {"en": "Enable Border",     "zh": "启用边框"},
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
    "opt_border_solid":     {"en": "solid",                 "zh": "实线"},
    "opt_border_dashed":    {"en": "dashed",                "zh": "虚线"},

    # ── Page Size Presets ──────────────────────────────────────────
    "opt_page_custom":      {"en": "Custom",                "zh": "自定义"},
    "opt_page_a4":          {"en": "A4 (210×297mm)",        "zh": "A4 (210×297mm)"},
    "opt_page_letter":      {"en": "Letter (216×279mm)",    "zh": "信纸 (216×279mm)"},
    "opt_page_single":      {"en": "Single Column (85×120mm)", "zh": "单栏 (85×120mm)"},
    "opt_page_1_5":         {"en": "1.5 Column (114×160mm)", "zh": "1.5 栏 (114×160mm)"},
    "opt_page_double":      {"en": "Double Column (178×240mm)", "zh": "双栏 (178×240mm)"},

    # ── Journal Presets ────────────────────────────────────────────
    "opt_page_nature_single":  {"en": "Nature Single (89×247mm)",   "zh": "Nature 单栏 (89×247mm)"},
    "opt_page_nature_double":  {"en": "Nature Double (183×247mm)",  "zh": "Nature 双栏 (183×247mm)"},
    "opt_page_cell_single":    {"en": "Cell Single (85×228mm)",     "zh": "Cell 单栏 (85×228mm)"},
    "opt_page_cell_double":    {"en": "Cell Double (174×228mm)",    "zh": "Cell 双栏 (174×228mm)"},
    "opt_page_science_single": {"en": "Science Single (90×245mm)",  "zh": "Science 单栏 (90×245mm)"},
    "opt_page_science_double": {"en": "Science Double (180×245mm)", "zh": "Science 双栏 (180×245mm)"},
    "opt_page_pnas_single":    {"en": "PNAS Single (87×246mm)",     "zh": "PNAS 单栏 (87×246mm)"},
    "opt_page_pnas_double":    {"en": "PNAS Double (178×246mm)",    "zh": "PNAS 双栏 (178×246mm)"},

    # ── Placeholders & Special ─────────────────────────────────────
    "placeholder_scale_bar_text": {"en": "Auto (e.g. 10 µm)", "zh": "自动 (例如 10 µm)"},
    "placeholder_label_text":     {"en": "Label text",        "zh": "标注文字"},
    "placeholder_col_ratios":     {"en": "e.g. 1,2,1 (equal if empty)", "zh": "例如 1,2,1 (为空则等分)"},
    "special_auto":               {"en": "Auto",              "zh": "自动"},
    "special_auto_ratio":         {"en": "Auto (use ratio)",  "zh": "自动 (使用比例)"},

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
    "lbl_fit_mode":         {"en": "Fit Mode:",         "zh": "缩放模式:"},
    "lbl_rotation":         {"en": "Rotation:",         "zh": "旋转:"},
    "lbl_align_h":          {"en": "Align H:",          "zh": "水平对齐:"},
    "lbl_align_v":          {"en": "Align V:",          "zh": "垂直对齐:"},
    "lbl_alignment":        {"en": "Alignment:",        "zh": "对齐方式:"},
    "tip_align_tl":         {"en": "Top Left",          "zh": "左上"},
    "tip_align_tc":         {"en": "Top Center",        "zh": "顶部居中"},
    "tip_align_tr":         {"en": "Top Right",         "zh": "右上"},
    "tip_align_ml":         {"en": "Middle Left",       "zh": "居中左侧"},
    "tip_align_mc":         {"en": "Center",            "zh": "居中"},
    "tip_align_mr":         {"en": "Middle Right",      "zh": "居中右侧"},
    "grp_scale_bar":        {"en": "Scale Bar Settings", "zh": "比例尺设置"},
    "tip_align_bl":         {"en": "Bottom Left",       "zh": "左下"},
    "tip_align_bc":         {"en": "Bottom Center",     "zh": "底部居中"},
    "tip_align_br":         {"en": "Bottom Right",      "zh": "右下"},
    "lbl_pos_x":            {"en": "Pos X (mm):",       "zh": "X坐标 (mm):"},
    "lbl_pos_y":            {"en": "Pos Y (mm):",       "zh": "Y坐标 (mm):"},
    "lbl_width_mm":         {"en": "Width (mm):",       "zh": "宽度 (mm):"},
    "lbl_height_mm":        {"en": "Height (mm):",      "zh": "高度 (mm):"},
    "lbl_pad_top":          {"en": "Pad Top (mm):",     "zh": "上内边距 (mm):"},
    "lbl_pad_bottom":       {"en": "Pad Bottom (mm):",  "zh": "下内边距 (mm):"},
    "lbl_pad_left":         {"en": "Pad Left (mm):",    "zh": "左内边距 (mm):"},
    "lbl_pad_right":        {"en": "Pad Right (mm):",   "zh": "右内边距 (mm):"},
    "lbl_corner_tl":        {"en": "Label TL:",         "zh": "角标 左上:"},
    "lbl_corner_tr":        {"en": "Label TR:",         "zh": "角标 右上:"},
    "lbl_corner_bl":        {"en": "Label BL:",         "zh": "角标 左下:"},
    "lbl_corner_br":        {"en": "Label BR:",         "zh": "角标 右下:"},
    "lbl_mapping":          {"en": "Mapping:",          "zh": "比例映射:"},
    "lbl_length":           {"en": "Length:",           "zh": "长度:"},
    "lbl_custom_text":      {"en": "Custom Text:",      "zh": "自定义文字:"},
    "lbl_text_size":        {"en": "Text Size:",        "zh": "文字大小:"},
    "btn_delete_pip":        {"en": "Delete PiP",        "zh": "删除插图"},
    "lbl_pip_x":            {"en": "X (left %):",       "zh": "X (左侧 %):"},
    "lbl_pip_y":            {"en": "Y (top %):",        "zh": "Y (顶部 %):"},
    "lbl_pip_w":            {"en": "Width %:",          "zh": "宽度 %:"},
    "lbl_pip_h":            {"en": "Height %:",         "zh": "高度 %:"},
    "lbl_thickness":        {"en": "Thickness:",        "zh": "粗细:"},
    "lbl_border_style":     {"en": "Border Style:",     "zh": "边框样式:"},
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
    "help_tab_advanced":    {"en": "Advanced",          "zh": "进阶功能"},
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
                                 "zh": "新版本 {tag} 可用 — 点击查看「关于」"},
    "status_update_tooltip":   {"en": "Open About dialog to download the latest version",
                                 "zh": "打开「关于」对话框下载最新版本"},
    "about_repository":     {"en": "Repository",        "zh": "代码仓库"},
    "about_license":        {"en": "License",           "zh": "许可协议"},
    "about_check_btn":      {"en": "Check for Updates", "zh": "检查更新"},
    "about_open_github":    {"en": "Open GitHub",       "zh": "打开 GitHub"},
    "about_close":          {"en": "Close",             "zh": "关闭"},

    # ── Common Dialogs ───────────────────────────────────────────
    "title_error":          {"en": "Error",             "zh": "错误"},
    "title_info":           {"en": "Info",              "zh": "提示"},
    "title_question":       {"en": "Question",          "zh": "询问"},
    "btn_ok":               {"en": "OK",                "zh": "确定"},
    "btn_cancel":           {"en": "Cancel",            "zh": "取消"},
    "btn_close":            {"en": "Close",             "zh": "关闭"},
    "btn_overwrite":        {"en": "Overwrite",         "zh": "覆盖"},
    "btn_save_as":          {"en": "Save As…",          "zh": "另存为…"},
    "title_success":        {"en": "Success",           "zh": "成功"},
    "title_import":         {"en": "Import",            "zh": "导入"},
    "about_checking":       {"en": "Checking…",         "zh": "正在检查…"},
    "about_latest":         {"en": "✔ You are running the latest version.", "zh": "✔ 当前已是最新版本。"},
    "about_pre":            {"en": "✔ You are running a pre-release version.", "zh": "✔ 当前运行的是预发布版本。"},
    "about_no_conn":        {"en": "⚠ Could not reach GitHub. Check your connection.", "zh": "⚠ 无法连接 GitHub，请检查网络连接。"},
    "about_click_check":    {"en": "Click \"Check for Updates\" to check.", "zh": "点击「检查更新」以检查新版本。"},

    # ── Tabs ─────────────────────────────────────────────────────
    "action_new_tab":          {"en": "New Tab",            "zh": "新建标签页"},
    "action_close_tab":        {"en": "Close Tab",          "zh": "关闭标签页"},
    "tab_layers":              {"en": "Layers",             "zh": "图层"},
    "tab_history":             {"en": "History",            "zh": "历史"},

    # ── Export preview ────────────────────────────────────────────
    "action_preview_mode":     {"en": "Export Preview",     "zh": "导出预览"},

    # ── History settings (kept for back-compat; now lives in Preferences) ──
    "action_history_settings": {"en": "History Settings…",  "zh": "历史设置…"},
    "history_settings_title":  {"en": "History Settings",   "zh": "历史设置"},
    "history_settings_label":  {"en": "Max History Items:",  "zh": "最大历史步数:"},

    # ── Preferences dialog ────────────────────────────────────────
    "action_preferences":           {"en": "Preferences…",          "zh": "偏好设置…"},
    "prefs_title":                  {"en": "Preferences",            "zh": "偏好设置"},
    "prefs_tab_general":            {"en": "General",                "zh": "通用"},
    "prefs_tab_files":              {"en": "Files & Editing",        "zh": "文件与编辑"},
    "prefs_tab_bundles":            {"en": "Bundles (.figpack)",     "zh": "项目包 (.figpack)"},

    # General tab
    "prefs_language":               {"en": "Language:",              "zh": "语言:"},
    "prefs_theme":                  {"en": "Theme:",                 "zh": "主题:"},
    "prefs_theme_light":            {"en": "Light",                  "zh": "浅色"},
    "prefs_theme_dark":             {"en": "Dark",                   "zh": "深色"},
    "prefs_undo_limit":             {"en": "Max undo steps:",        "zh": "最大撤销步数:"},

    # Files & Editing tab
    "prefs_default_save_format":    {"en": "Default save format:",   "zh": "默认保存格式:"},
    "prefs_fmt_figlayout":          {"en": ".figlayout (JSON, lightweight)", "zh": ".figlayout（JSON，轻量）"},
    "prefs_fmt_figpack":            {"en": ".figpack (bundle, portable)",    "zh": ".figpack（项目包，包含素材）"},
    "prefs_export_dir_policy":      {"en": "Export destination:",    "zh": "导出目录:"},
    "prefs_export_dir_project":     {"en": "Same folder as project", "zh": "与项目文件同目录"},
    "prefs_export_dir_last":        {"en": "Remember last used folder", "zh": "记住上次使用的目录"},
    "prefs_export_dir_custom":      {"en": "Always use this folder:", "zh": "始终使用此目录:"},
    "prefs_export_dir_browse":      {"en": "Browse…",                "zh": "浏览…"},
    "prefs_hot_reload":             {"en": "Auto-reload changed images", "zh": "自动重新加载已更改的图片"},
    "prefs_hot_reload_tip":         {"en": "When a source image is modified on disk, reload it on the canvas automatically.", "zh": "当源图片在磁盘上被修改时，自动在画布中重新加载。"},

    # Bundles tab
    "prefs_cache_location":         {"en": "Cache location:",        "zh": "缓存位置:"},
    "prefs_cache_default":          {"en": "(system default)",       "zh": "（系统默认）"},
    "prefs_cache_browse":           {"en": "Browse…",                "zh": "浏览…"},
    "prefs_cache_reset":            {"en": "Reset to default",       "zh": "恢复默认"},
    "prefs_cache_quota":            {"en": "Cache quota (GB):",      "zh": "缓存配额（GB）:"},
    "prefs_watch_original":         {"en": "Watch original sources for bundles", "zh": "监视包项目的原始图片文件"},
    "prefs_watch_original_tip":     {"en": "When an original source image is edited while a .figpack is open, reload it automatically.", "zh": "当 .figpack 打开时，若原始图片被编辑，自动重新加载。"},
    "prefs_compress_assets":        {"en": "Compress assets (LZMA, slower save)", "zh": "压缩资产（LZMA，保存较慢）"},
    "prefs_compress_assets_tip":    {"en": "Reduce bundle file size at the cost of slower save and open times.", "zh": "以较慢的保存/打开速度换取更小的包文件体积。"},
    "prefs_open_cache_folder":      {"en": "Open Cache Folder",      "zh": "打开缓存文件夹"},
    "prefs_clear_cache":            {"en": "Clear Cache Now",        "zh": "立即清除缓存"},
    "prefs_clear_cache_confirm":    {"en": "Delete all unused figpack working directories?", "zh": "删除所有未使用的 figpack 工作目录？"},
    "prefs_cache_cleared":          {"en": "Cleared {n} orphaned cache director{y}.", "zh": "已清除 {n} 个孤立缓存目录。"},

    # ── Status bar / misc ─────────────────────────────────────────
    "zoom_label":           {"en": "Zoom:",             "zh": "缩放:"},
    "canvas_label":         {"en": "Canvas:",           "zh": "画布:"},

    # ── Cell context menu ─────────────────────────────────────────
    "ctx_delete_label":              {"en": "Delete Label",                    "zh": "删除标注"},
    "ctx_import_image":              {"en": "Import Image…",                   "zh": "导入图片…"},
    "ctx_labels":                    {"en": "Labels",                          "zh": "标注"},
    "ctx_delete_label_cell":         {"en": "Delete Label Cell",               "zh": "删除标注单元格"},
    "ctx_add_label_cell":            {"en": "Add Label Cell",                  "zh": "添加标注单元格"},
    "ctx_delete_label_cell_n":       {"en": "Delete Label Cell ({n} cells)",   "zh": "删除标注单元格（{n} 个）"},
    "ctx_add_label_cell_n":          {"en": "Add Label Cell ({n} cells)",      "zh": "添加标注单元格（{n} 个）"},
    "ctx_delete_label_above_box":    {"en": "Delete Label Cell Above Box",     "zh": "删除上方容器标注"},
    "ctx_add_label_above_box":       {"en": "Add Label Cell Above Box",        "zh": "添加上方容器标注"},
    "ctx_corner_top_left":           {"en": "Top Left",                        "zh": "左上"},
    "ctx_corner_top_right":          {"en": "Top Right",                       "zh": "右上"},
    "ctx_corner_bottom_left":        {"en": "Bottom Left",                     "zh": "左下"},
    "ctx_corner_bottom_right":       {"en": "Bottom Right",                    "zh": "右下"},
    "ctx_delete_corner_label":       {"en": "Delete {name} Label",             "zh": "删除{name}角标"},
    "ctx_add_corner_label":          {"en": "Add {name} Label",                "zh": "添加{name}角标"},
    "ctx_fit_mode":                  {"en": "Fit Mode",                        "zh": "缩放模式"},
    "ctx_fit_contain":               {"en": "Contain",                          "zh": "等比缩放 (包含)"},
    "ctx_fit_cover":                 {"en": "Cover (Fill)",                     "zh": "等比缩放 (覆盖)"},
    "ctx_rotation":                  {"en": "Rotation",                        "zh": "旋转"},
    "ctx_enable_scale_bar":          {"en": "Enable Scale Bar",                "zh": "启用比例尺"},
    "ctx_disable_scale_bar":         {"en": "Disable Scale Bar",               "zh": "禁用比例尺"},
    "ctx_crop_image":                {"en": "Crop Image",                      "zh": "裁剪图片"},
    "ctx_crop_aspect_menu":          {"en": "Crop to Aspect Ratio",            "zh": "按比例裁剪"},
    "ctx_crop_reset":                {"en": "Reset Crop",                      "zh": "重置裁剪"},
    "ctx_crop_preset_free":          {"en": "Free (reset)",                    "zh": "自由（重置）"},
    "ctx_crop_preset_square":        {"en": "Square 1:1",                      "zh": "正方形 1:1"},
    "ctx_crop_preset_portrait_3_4":  {"en": "3:4 Portrait",                    "zh": "3:4 纵向"},
    "ctx_crop_preset_portrait_2_3":  {"en": "2:3 Portrait",                    "zh": "2:3 纵向"},
    "ctx_crop_preset_portrait_9_16": {"en": "9:16 Portrait",                   "zh": "9:16 纵向"},
    "crop_hint":                     {"en": "↵ Apply  ·  Esc Cancel  ·  Shift+drag corner: Lock aspect",
                                      "zh": "↵ 确认  ·  Esc 取消  ·  Shift+拖角点：锁定比例"},
    "ctx_insert":                    {"en": "Insert",                          "zh": "插入"},
    "ctx_row_above":                 {"en": "Row Above",                       "zh": "在上方插入行"},
    "ctx_row_below":                 {"en": "Row Below",                       "zh": "在下方插入行"},
    "ctx_col_left":                  {"en": "Column Left",                     "zh": "在左侧插入列"},
    "ctx_col_right":                 {"en": "Column Right",                    "zh": "在右侧插入列"},
    "ctx_split_subcell":             {"en": "Split / Sub-Cell",                "zh": "分割/子单元格"},
    "ctx_cell_above":                {"en": "Cell Above",                      "zh": "上方单元格"},
    "ctx_cell_below":                {"en": "Cell Below",                      "zh": "下方单元格"},
    "ctx_cell_left":                 {"en": "Cell Left",                       "zh": "左侧单元格"},
    "ctx_cell_right":                {"en": "Cell Right",                      "zh": "右侧单元格"},
    "ctx_split_n_cols":              {"en": "Split into N Columns…",           "zh": "拆分为 N 列…"},
    "ctx_split_n_rows":              {"en": "Split into N Rows…",              "zh": "拆分为 N 行…"},
    "ctx_delete":                    {"en": "Delete",                          "zh": "删除"},
    "ctx_this_row":                  {"en": "This Row",                        "zh": "本行"},
    "ctx_this_column":               {"en": "This Column",                     "zh": "本列"},
    "ctx_cant_delete_last_row":      {"en": "Cannot delete the last row",      "zh": "无法删除最后一行"},
    "ctx_cant_delete_last_cell":     {"en": "Cannot delete the last cell in a row", "zh": "无法删除行中最后一个单元格"},
    "ctx_this_subcell":              {"en": "This Sub-Cell",                   "zh": "本子单元格"},
    "ctx_split_dialog_title":        {"en": "Split Cell",                      "zh": "拆分单元格"},
    "ctx_split_n_cols_label":        {"en": "Number of columns:",              "zh": "列数:"},
    "ctx_split_n_rows_label":        {"en": "Number of rows:",                 "zh": "行数:"},

    # ── Help dialog ───────────────────────────────────────────────
    "pip_zone_label":                {"en": "PiP",                             "zh": "以子图插入"},
    "layers_zoom_inset":             {"en": "Zoom Inset",                      "zh": "缩放插图"},
    "pip_ctx_resize":                {"en": "Resize",                          "zh": "调整大小"},
    "pip_ctx_remove":                {"en": "Remove Inset",                    "zh": "删除插图"},

    # ── Size Groups ───────────────────────────────────────────────
    "lbl_size_group":                {"en": "Size Group:",                     "zh": "尺寸组:"},
    "lbl_size_group_name":           {"en": "Group Name:",                     "zh": "组名:"},
    "lbl_size_group_pinned_w":       {"en": "Pinned W (mm, 0=auto):",          "zh": "固定宽度 (mm，0=自动):"},
    "lbl_size_group_pinned_h":       {"en": "Pinned H (mm, 0=auto):",          "zh": "固定高度 (mm，0=自动):"},
    "size_group_none":               {"en": "(None)",                          "zh": "（无）"},
    "size_group_new":                {"en": "+ Create New Group…",             "zh": "+ 创建新组…"},
    "size_group_members":            {"en": "Members: {n}",                    "zh": "成员数: {n}"},
    "size_group_delete":             {"en": "Delete Group",                    "zh": "删除组"},
    "size_group_default_name":       {"en": "Group {n}",                       "zh": "组 {n}"},
    "ctx_create_size_group":         {"en": "Create Size Group",               "zh": "创建尺寸组"},
    "ctx_add_to_size_group":         {"en": "Add to Size Group",               "zh": "加入尺寸组"},
    "ctx_remove_from_size_group":    {"en": "Remove from Size Group",          "zh": "从尺寸组移除"},

    "help_close":                    {"en": "Close",                           "zh": "关闭"},
    "help_shortcut_col":             {"en": "Shortcut",                        "zh": "快捷键"},
    "help_action_col":               {"en": "Action",                          "zh": "操作"},

    # ── SVG Text Groups ──────────────────────────────────────────────
    "action_svg_text_groups":        {"en": "SVG Text Groups…",                "zh": "SVG 文字组…"},
    "ctx_svg_text_inspector":        {"en": "Edit SVG Text Groups…",           "zh": "编辑 SVG 文字组…"},

    "svgtxt_inspector_title":        {"en": "SVG Text Inspector",              "zh": "SVG 文字检查器"},
    "svgtxt_groups_panel_title":     {"en": "SVG Text Groups",                 "zh": "SVG 文字组"},
    "svgtxt_preview_label":          {"en": "SVG Preview",                     "zh": "SVG 预览"},
    "svgtxt_preview_failed":         {"en": "Could not render SVG preview.",   "zh": "无法渲染 SVG 预览。"},
    "svgtxt_elements_label":         {"en": "Text Elements  (select to assign)", "zh": "文字元素（选中后分配）"},
    "svgtxt_assign_group_box":       {"en": "Assign to Group",                 "zh": "分配到组"},
    "svgtxt_group_label":            {"en": "Group:",                          "zh": "组："},
    "svgtxt_no_groups":              {"en": "— no groups —",                   "zh": "— 无组 —"},
    "svgtxt_new_group_label":        {"en": "New group:",                      "zh": "新建组："},
    "svgtxt_new_group_placeholder":  {"en": "Group name…",                     "zh": "组名…"},
    "svgtxt_create_group_btn":       {"en": "Create",                          "zh": "创建"},
    "svgtxt_assign_btn":             {"en": "Assign selected to group",        "zh": "将所选分配到组"},
    "svgtxt_remove_from_group_btn":  {"en": "Remove selected from group",      "zh": "从组中移除所选"},
    "svgtxt_font_size_box":          {"en": "Group Font Size",                 "zh": "组字体大小"},
    "svgtxt_font_size_label":        {"en": "Font size:",                      "zh": "字体大小："},
    "svgtxt_apply_size_btn":         {"en": "Apply font size to group",        "zh": "应用字体大小到组"},
    "svgtxt_info_title":             {"en": "Info",                            "zh": "提示"},
    "svgtxt_select_elements_hint":   {"en": "Please select text elements first.", "zh": "请先选择文字元素。"},
    "svgtxt_select_group_hint":      {"en": "Please select or create a group first.", "zh": "请先选择或创建一个组。"},
    "svgtxt_default_group_name":     {"en": "Text Group",                      "zh": "文字组"},

    "svgtxt_groups_list_label":      {"en": "Groups",                          "zh": "组"},
    "svgtxt_add_group_btn":          {"en": "Add Group",                       "zh": "添加组"},
    "svgtxt_delete_group_btn":       {"en": "Delete Group",                    "zh": "删除组"},
    "svgtxt_group_props_box":        {"en": "Group Properties",                "zh": "组属性"},
    "svgtxt_group_name_label":       {"en": "Name:",                           "zh": "名称："},
    "svgtxt_group_name_placeholder": {"en": "Group name…",                     "zh": "组名…"},
    "svgtxt_save_group_btn":         {"en": "Save",                            "zh": "保存"},
    "svgtxt_members_box":            {"en": "Members  (svg file — element key)", "zh": "成员（SVG 文件 — 元素键）"},
    "svgtxt_remove_members_btn":     {"en": "Remove selected members",         "zh": "移除所选成员"},
    "svgtxt_confirm_delete_title":   {"en": "Delete Group",                    "zh": "删除组"},
    "svgtxt_confirm_delete_msg":     {"en": "Delete group \"{name}\"?",        "zh": "删除组 \"{name}\"？"},

    # ── Sidecar assets dialog ──────────────────────────────────────
    "msg_sidecar_title":            {"en": "Save sidecar assets?",          "zh": "保存附件资源？"},
    "msg_sidecar_text":             {"en": "This project is currently backed by a .figpack cache.\n\n"
                                           "Copy its assets into\n  {assets_dir}\n"
                                           "so the saved .figlayout keeps working after the cache is "
                                           "purged?\n\nChoosing 'Skip' will save image references that "
                                           "break on next launch.",
                                     "zh": "保存为 .figlayout 将仅保存排版和图片路径，源图不会被打包到项目文件中。\n\n"
                                           "是否将图片复制到以下附件文件夹以防链接失效？\n"
                                           "  {assets_dir}\n\n"
                                           "选择“跳过”将仅保存路径引用，若缓存被清理，下次打开时图片将无法显示。"},
    "btn_copy_assets":              {"en": "Copy assets",                   "zh": "复制并保存"},
    "btn_skip_links":               {"en": "Skip (links only)",             "zh": "仅保存路径"},
    "err_create_assets":            {"en": "Could not create assets folder:\n{e}", "zh": "无法创建资源文件夹：\n{e}"},

    # ── External change dialog ────────────────────────────────────
    "msg_bundle_changed_title":     {"en": "Bundle changed externally",     "zh": "项目包已在外部被修改"},
    "msg_bundle_changed_text":      {"en": "This .figpack has been modified on disk since it "
                                           "was opened.\n\nOverwriting will discard those "
                                           "external changes.",
                                     "zh": "该 .figpack 自打开以来已在磁盘上被修改。\n\n"
                                           "覆盖将丢失这些外部更改。"},

    # ── Cloud detection dialog ────────────────────────────────────
    "msg_cloud_detected_title":     {"en": "Cloud-only files detected",     "zh": "检测到仅云端存储的文件"},
    "msg_cloud_detected_text":      {"en": "{n} source file(s) live online (OneDrive / "
                                           "iCloud / similar) and may take a long time to download:"
                                           "\n\n{preview}{tail}\n\nHydrate now and bundle them, "
                                           "skip them (mark as missing), or cancel the save?",
                                     "zh": "{n} 个源文件仅存储在云端（OneDrive / iCloud 等），"
                                           "下载可能需要较长时间：\n\n{preview}{tail}\n\n"
                                           "现在下载并打包它们，还是跳过（标记为缺失），或取消保存？"},
    "btn_hydrate_include":          {"en": "Hydrate & include",             "zh": "下载并包含"},
    "btn_skip_missing":             {"en": "Skip (mark missing)",           "zh": "跳过 (标记为缺失)"},

    # ── Grid / Placeholders ───────────────────────────────────────
    "msg_no_placeholders_text":     {"en": "No more placeholder cells available. {n} images not imported.",
                                     "zh": "没有更多占位单元格可用。有 {n} 张图片未被导入。"},
    "dlg_open_images_grid_title":   {"en": "Open Images as Grid",           "zh": "以网格形式打开图片"},
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
