"""Lightweight dictionary-based i18n for the Plot Editor (Qt-free).

Supports 'en' and 'zh'. The language is set once at startup from ILM's
saved settings (``chrome.saved_language``); there is no live switching.
Chinese wording mirrors ``src/app/i18n.py`` where the concept is the
same. Strings that end up inside the plot or saved file (axis titles,
column letters, chart keys, override JSON) are never translated.
"""

_lang = 'en'

_STRINGS = {
    # ── Menus ────────────────────────────────────────────────────────
    'menu_file':   {'en': 'File',   'zh': '文件'},
    'menu_edit':   {'en': 'Edit',   'zh': '编辑'},
    'menu_plot':   {'en': 'Plot',   'zh': '绘图'},
    'menu_help':   {'en': 'Help',   'zh': '帮助'},
    'menu_export': {'en': 'Export', 'zh': '导出'},

    # ── Actions ──────────────────────────────────────────────────────
    'act_new':      {'en': 'New',        'zh': '新建'},
    'act_open':     {'en': 'Open…',      'zh': '打开…'},
    'act_save':     {'en': 'Save',       'zh': '保存'},
    'act_save_as':  {'en': 'Save As…',   'zh': '另存为…'},
    'act_import_data': {'en': 'Import Data…', 'zh': '导入数据…'},
    'act_close':    {'en': 'Close',      'zh': '关闭'},
    'act_quit':     {'en': 'Quit',       'zh': '退出'},
    'act_undo':     {'en': 'Undo',       'zh': '撤销'},
    'act_redo':     {'en': 'Redo',       'zh': '重做'},
    'act_cut':      {'en': 'Cut',        'zh': '剪切'},
    'act_copy':     {'en': 'Copy',       'zh': '复制'},
    'act_paste':    {'en': 'Paste',      'zh': '粘贴'},
    'act_delete':   {'en': 'Delete',     'zh': '删除'},
    'act_select_all': {'en': 'Select All', 'zh': '全选'},
    'act_plot':     {'en': 'Plot',       'zh': '绘图'},
    'act_style':    {'en': 'Plot Style…', 'zh': '图表样式…'},
    'act_add_note':    {'en': 'Add Text', 'zh': '添加文本'},
    'act_add_bracket': {'en': 'Add Significance Bracket',
                        'zh': '添加显著性标注'},
    'act_tutorials': {'en': 'Tutorials…', 'zh': '教程…'},
    'act_shortcuts': {'en': 'Keyboard Shortcuts', 'zh': '键盘快捷键'},
    'act_about':    {'en': 'About Plot Editor',
                     'zh': '关于图表编辑器'},
    'act_export_ilmplot': {'en': 'ILM Plot (*.ilmplot.svg)…',
                           'zh': 'ILM 图表 (*.ilmplot.svg)…'},
    'act_export_pdf':   {'en': 'PDF…',  'zh': 'PDF…'},
    'act_export_svg':   {'en': 'SVG…',  'zh': 'SVG…'},
    'act_export_png':   {'en': 'PNG…',  'zh': 'PNG…'},
    'act_export_tiff':  {'en': 'TIFF…', 'zh': 'TIFF…'},
    'act_export_jpg':   {'en': 'JPEG…', 'zh': 'JPEG…'},

    'tip_new':      {'en': 'New plot tab', 'zh': '新建图表标签页'},
    'tip_open':     {'en': 'Open an ILM plot (*.ilmplot.svg)',
                     'zh': '打开 ILM 图表（*.ilmplot.svg）'},
    'tip_save':     {'en': 'Save the plot and its data (*.ilmplot.svg)',
                     'zh': '保存图表及其数据（*.ilmplot.svg）'},
    'tip_save_as':  {'en': 'Save under a new name (*.ilmplot.svg)',
                     'zh': '以新名称保存（*.ilmplot.svg）'},
    'tip_import_data': {'en': 'Import data from a text or Excel file',
                        'zh': '从文本或 Excel 文件导入数据'},
    'tip_close':    {'en': 'Close the current tab', 'zh': '关闭当前标签页'},
    'tip_quit':     {'en': 'Quit Plot Editor', 'zh': '退出图表编辑器'},
    'tip_undo':     {'en': 'Nothing to undo', 'zh': '没有可撤销的操作'},
    'tip_redo':     {'en': 'Nothing to redo', 'zh': '没有可重做的操作'},
    'tip_cut':      {'en': 'Cut the selected cells', 'zh': '剪切所选单元格'},
    'tip_copy':     {'en': 'Copy the selected cells', 'zh': '复制所选单元格'},
    'tip_paste':    {'en': 'Paste cells from the clipboard',
                     'zh': '从剪贴板粘贴单元格'},
    'tip_delete':   {'en': 'Clear the selected cells',
                     'zh': '清除所选单元格的内容'},
    'tip_select_all': {'en': 'Select all data cells',
                       'zh': '选择所有数据单元格'},
    'tip_plot':     {'en': 'Plot the selected columns as the chosen '
                           'chart type',
                     'zh': '以所选图表类型绘制选中列'},
    'tip_style':    {'en': 'Manage plot style presets',
                     'zh': '管理图表样式预设'},
    'tip_add_note':    {'en': 'Add floating text at the plot centre',
                        'zh': '在图表中心添加浮动文本'},
    'tip_add_bracket': {'en': 'Add a significance bracket between two '
                              'groups or bars',
                        'zh': '在两组或两列之间添加显著性标注'},
    'tip_tutorials': {'en': 'Guided lessons for the Plot Editor',
                      'zh': '图表编辑器引导教程'},
    'tip_shortcuts': {'en': 'Not implemented yet', 'zh': '尚未实现'},
    'tip_about':    {'en': 'About the Plot Editor',
                     'zh': '关于图表编辑器'},
    'about_title':  {'en': 'About Plot Editor',
                     'zh': '关于图表编辑器'},
    'about_version': {'en': 'Version {version}', 'zh': '版本 {version}'},
    'about_suite':  {'en': 'Part of {name}',
                     'zh': '{name} 的独立图表编辑器'},
    'about_description': {
        'en': 'A standalone scientific plot editor for creating, '
              'styling, and saving editable figures.',
        'zh': '独立的科学图表编辑器，用于创建、设置样式和保存可编辑图表。'},
    'about_tools_title': {'en': 'From data to figures',
                          'zh': '从数据到图表'},
    'about_tools_body': {
        'en': 'Work with worksheet data or import text and Excel files. '
              'Create line, scatter, violin, ridgeline, and '
              'stacked-column plots; edit plot elements directly, apply '
              'colour themes and style presets, and add text or '
              'significance brackets.',
        'zh': '使用工作表数据，或导入文本和 Excel 文件。创建折线、散点、'
              '小提琴、山脊和堆叠柱状图；直接编辑图表元素、应用颜色主题与'
              '样式预设，并添加文本或显著性标注。'},
    'about_native_title': {'en': 'One editable .ilmplot.svg file',
                           'zh': '一个可编辑的 .ilmplot.svg 文件'},
    'about_native_body': {
        'en': 'Save a .ilmplot.svg to keep the SVG image, worksheet, '
              'and editable plot settings together. Open it in the '
              'Plot Editor to continue editing, or place it in ILM.',
        'zh': '保存为 .ilmplot.svg，将 SVG 图像、工作表和可编辑图表设置保存'
              '在同一个文件中。可在图表编辑器中重新打开继续编辑，也可放入 '
              'ILM。'},
    'about_reflow_title': {'en': 'REFLOW ON in ILM',
                           'zh': 'ILM 中的 REFLOW ON'},
    'about_reflow_body': {
        'en': 'ILM shows the saved SVG by default. REFLOW ON adapts the '
              'plot layout to its cell while keeping text and line '
              'widths at true point sizes. Enable it per cell in ILM.',
        'zh': 'ILM 默认显示保存的 SVG。开启 REFLOW ON 后，图表布局会适应'
              '单元格，文字和线宽保持真实磅值。在 ILM 中可按单元格启用。'},
    'about_developer': {'en': 'Developer: {publisher}',
                        'zh': '开发者：{publisher}'},
    'about_license': {
        'en': 'Application source: {license}. Bundled components have '
              'their own licenses; see Licenses and source for details.',
        'zh': '应用源码：{license}。随附组件遵循各自的许可协议；'
              '详见“许可协议与源代码”。'},
    'about_repository': {'en': 'Repository', 'zh': '代码仓库'},
    'about_licenses': {'en': 'Licenses and source…',
                       'zh': '许可协议与源代码…'},
    'tip_export_ilmplot': {'en': 'Export an editable ILM plot',
                           'zh': '导出可编辑的 ILM 图表'},
    'tip_export_pdf':   {'en': 'Export the plot as PDF',
                         'zh': '将图表导出为 PDF'},
    'tip_export_svg':   {'en': 'Export the plot as SVG',
                         'zh': '将图表导出为 SVG'},
    'tip_export_png':   {'en': 'Export the plot as PNG',
                         'zh': '将图表导出为 PNG'},
    'tip_export_tiff':  {'en': 'Export the plot as TIFF',
                         'zh': '将图表导出为 TIFF'},
    'tip_export_jpg':   {'en': 'Export the plot as JPEG',
                         'zh': '将图表导出为 JPEG'},

    # ── Chart types / groups ─────────────────────────────────────────
    'grp_line':            {'en': 'Line',            'zh': '折线'},
    'grp_violin':          {'en': 'Violin',          'zh': '小提琴图'},
    'grp_column':          {'en': 'Column',          'zh': '柱状图'},
    'chart_pure_line':     {'en': 'Pure Line',       'zh': '纯线'},
    'chart_pure_scatters': {'en': 'Pure Scatters',   'zh': '纯散点'},
    'chart_line_scatters': {'en': 'Line + Scatters', 'zh': '线 + 散点'},
    'chart_stacked_line':  {'en': 'Stacked Line',    'zh': '堆叠折线'},
    'chart_ridgeline':     {'en': 'Ridgeline',       'zh': '山脊图'},
    'chart_violin':        {'en': 'Violin',          'zh': '小提琴图'},
    'chart_column':        {'en': 'Column',        'zh': '柱状图'},
    'chart_stacked_column_pct': {'en': '100% Stacked Column',
                                 'zh': '百分比堆积柱状图'},
    'chart_stacked_column': {'en': 'Stacked Column', 'zh': '堆积柱状图'},

    # ── Window / tabs ────────────────────────────────────────────────
    'window_title':    {'en': '{name} — Plot Editor',
                        'zh': '{name} — 图表编辑器'},
    'untitled':        {'en': 'Untitled {n}', 'zh': '未命名 {n}'},
    'untitled_plain':  {'en': 'Untitled', 'zh': '未命名'},
    'plot_from_ilm':   {'en': 'Plot from ILM', 'zh': '来自 ILM 的图表'},
    'app_name':        {'en': 'Plot Editor', 'zh': '图表编辑器'},

    # ── Undo/redo tooltips ───────────────────────────────────────────
    'undo_with':       {'en': 'Undo {action}', 'zh': '撤销 {action}'},
    'redo_with':       {'en': 'Redo {action}', 'zh': '重做 {action}'},
    'hist_edit':           {'en': 'Edit',           'zh': '编辑'},
    'hist_paste':          {'en': 'Paste',          'zh': '粘贴'},
    'hist_cut':            {'en': 'Cut',            'zh': '剪切'},
    'hist_clear':          {'en': 'Clear',          'zh': '清除'},
    'hist_insert_rows':    {'en': 'Insert Rows',    'zh': '插入行'},
    'hist_delete_rows':    {'en': 'Delete Rows',    'zh': '删除行'},
    'hist_insert_column':  {'en': 'Insert Column',  'zh': '插入列'},
    'hist_delete_column':  {'en': 'Delete Column',  'zh': '删除列'},
    'hist_set_as':         {'en': 'Set As',         'zh': '设置为'},
    'hist_import':         {'en': 'Import',         'zh': '导入'},

    # ── Toolbar export button ────────────────────────────────────────
    'export_ready':    {'en': 'Export the plot', 'zh': '导出图表'},
    'export_needs':    {'en': 'Create a plot to export',
                        'zh': '先创建图表才能导出'},
    'plot_tooltip':    {'en': 'Plot — {chart} ({group})',
                        'zh': '绘图 — {chart}（{group}）'},

    # ── File dialogs / messages ──────────────────────────────────────
    'dlg_open':        {'en': 'Open',        'zh': '打开'},
    'dlg_save_as':     {'en': 'Save As',     'zh': '另存为'},
    'dlg_export':      {'en': 'Export',      'zh': '导出'},
    'dlg_save':        {'en': 'Save',        'zh': '保存'},
    'dlg_plot':        {'en': 'Plot',        'zh': '绘图'},
    'err_plot_newer_schema': {
        'en': 'This plot was made by a newer version of the Plot Editor '
              '(format {found}; this version reads {supported}). '
              'Update ILM to edit it.',
        'zh': '此图表由更新版本的图表编辑器创建（格式 {found}；'
              '当前版本支持 {supported}）。请更新 ILM 后再编辑。'},
    'err_plot_newer_features': {
        'en': 'This plot uses features from a newer version of the Plot '
              'Editor: {features}. Update ILM to edit it.',
        'zh': '此图表使用了更新版本图表编辑器的功能：{features}。'
              '请更新 ILM 后再编辑。'},
    'warn_worksheet_rebuilt': {
        'en': 'The worksheet in this file could not be read ({error}), '
              'so it was rebuilt from the plot. Saving to the original '
              'file is disabled to protect it — use Save As.',
        'zh': '无法读取此文件中的工作表（{error}），已根据图表重建。'
              '为保护原文件，已禁用直接保存——请使用“另存为”。'},
    'err_save_verify': {
        'en': 'The plot could not be saved because the written file '
              'would not be readable: {error}',
        'zh': '无法保存图表：写出的文件将无法读取：{error}'},
    'err_svg_entities': {
        'en': 'Unsupported SVG: entity declarations are not allowed',
        'zh': '不支持的 SVG：不允许实体声明'},
    'msg_open_failed': {'en': 'Could not open {name}:\n{error}',
                        'zh': '无法打开 {name}：\n{error}'},
    'msg_save_failed': {'en': 'Could not save the plot:\n{error}',
                        'zh': '无法保存图表：\n{error}'},
    'msg_export_failed': {'en': 'Could not export the plot:\n{error}',
                          'zh': '无法导出图表：\n{error}'},
    'msg_unsaved':     {'en': 'Save changes to "{name}" before closing?',
                        'zh': '是否在关闭之前保存对“{name}”的更改？'},
    'msg_no_plot':     {'en': 'Create a plot before saving.',
                        'zh': '请先创建图表再保存。'},
    'msg_launch_failed': {'en': 'Unable to launch Plot Editor.',
                          'zh': '无法启动图表编辑器。'},
    'msg_handoff_failed': {'en': 'Unable to pass the plot to Plot '
                                 'Editor:\n{error}',
                           'zh': '无法将图表传递给图表编辑器：\n{error}'},
    'msg_unexpected':  {'en': 'An unexpected error occurred:\n{error}',
                        'zh': '程序发生未预期的错误：\n{error}'},

    # ── Plot selection errors ────────────────────────────────────────
    'err_no_y':        {'en': 'Select at least one Y column to plot.',
                        'zh': '请选择至少一个 Y 列进行绘图。'},
    'err_no_numeric':  {'en': 'The selected columns contain no numeric '
                              'data.',
                        'zh': '所选列中没有数值数据。'},
    'err_too_many_cols': {'en': 'Too many columns (max {max})',
                          'zh': '列数过多（最多 {max} 列）'},
    'err_paste_cells': {'en': 'Pasted data exceeds {max} cells',
                        'zh': '粘贴的数据超过 {max} 个单元格'},
    'err_remove_every': {'en': 'Cannot remove every column',
                         'zh': '不能删除所有列'},
    'err_unknown_designation': {'en': 'Unknown designation {value}',
                                'zh': '未知的列类型 {value}'},
    'err_unknown_chart': {'en': 'Unknown chart type {value}',
                          'zh': '未知的图表类型 {value}'},
    'err_unknown_export': {'en': 'Unknown export format {value}',
                           'zh': '未知的导出格式 {value}'},

    # ── Worksheet ────────────────────────────────────────────────────
    'meta_long_name':  {'en': 'Long Name', 'zh': '长名称'},
    'meta_units':      {'en': 'Units',     'zh': '单位'},
    'meta_comments':   {'en': 'Comments',  'zh': '注释'},
    'menu_set_as':     {'en': 'Set As',    'zh': '设置为'},
    'design_xerr':     {'en': 'X Error',   'zh': 'X 误差'},
    'design_yerr':     {'en': 'Y Error',   'zh': 'Y 误差'},
    'design_yerr_plus':  {'en': 'Y Error +', 'zh': 'Y 误差 +'},
    'design_yerr_minus': {'en': 'Y Error −', 'zh': 'Y 误差 −'},
    'design_label':    {'en': 'Label',     'zh': '标签'},
    'design_disregard': {'en': 'Disregard', 'zh': '忽略'},
    'ws_insert_column_here':  {'en': 'Insert Column Here',
                               'zh': '在此处插入列'},
    'ws_insert_column_left':  {'en': 'Insert Column Left',
                               'zh': '在左侧插入列'},
    'ws_insert_column_right': {'en': 'Insert Column Right',
                               'zh': '在右侧插入列'},
    'ws_add_column':          {'en': 'Add New Column', 'zh': '添加新列'},
    'ws_delete_column':       {'en': 'Delete Column',  'zh': '删除列'},
    'ws_clear_column':        {'en': 'Clear Column',   'zh': '清空列'},
    'ws_insert_rows':         {'en': 'Insert Rows',    'zh': '插入行'},
    'ws_delete_rows':         {'en': 'Delete Rows',    'zh': '删除行'},
    'ws_clear':               {'en': 'Clear',          'zh': '清除'},
    'ws_paste_title':         {'en': 'Paste',          'zh': '粘贴'},
    'ws_insert_column_title': {'en': 'Insert Column',  'zh': '插入列'},

    # ── Title field ──────────────────────────────────────────────────
    'title_placeholder': {'en': 'Double-click to add title',
                          'zh': '双击添加标题'},

    # ── Reset formatting overlay ─────────────────────────────────────
    'reset_all':          {'en': 'Reset formatting', 'zh': '重置格式'},
    'reset_all_confirm':  {'en': 'Reset all plot formatting to '
                                 'defaults? The title and data are '
                                 'kept; axis titles and legend text '
                                 'return to the spreadsheet values.',
                           'zh': '要将所有图表格式重置为默认值吗？'
                                 '标题和数据将保留；坐标轴标题和'
                                 '图例文字恢复为表格中的值。'},

    # ── Element panel ────────────────────────────────────────────────
    'panel_title':   {'en': 'Title',        'zh': '标题'},
    'panel_xlabel':  {'en': 'X axis title', 'zh': 'X 轴标题'},
    'panel_ylabel':  {'en': 'Y axis title', 'zh': 'Y 轴标题'},
    'panel_xticks':  {'en': 'X axis',       'zh': 'X 轴'},
    'panel_yticks':  {'en': 'Y axis',       'zh': 'Y 轴'},
    'panel_legend':  {'en': 'Legend',       'zh': '图例'},
    'panel_frame':   {'en': 'Axes & grid',  'zh': '坐标轴和网格'},
    'panel_series':  {'en': 'Series {name}', 'zh': '系列 {name}'},
    'panel_series_detached': {
        'en': 'This series is not worksheet-backed; in-place edits are '
              'unavailable.',
        'zh': '此系列不来自工作表，无法进行就地编辑。'},

    'row_text':      {'en': 'Text',        'zh': '文字'},
    'row_font':      {'en': 'Font',        'zh': '字体'},
    'row_size':      {'en': 'Size',        'zh': '字号'},
    'row_style':     {'en': 'Style',       'zh': '样式'},
    'row_align':     {'en': 'Align',       'zh': '对齐'},
    'row_rotation':  {'en': 'Rotation',    'zh': '旋转'},
    'row_prefix':    {'en': 'Prefix',      'zh': '前缀'},
    'row_suffix':    {'en': 'Suffix',      'zh': '后缀'},
    'row_decimals':  {'en': 'Decimals',    'zh': '小数位数'},
    'row_tick_spacing': {'en': 'Tick spacing', 'zh': '刻度间距'},
    'row_minor_ticks':  {'en': 'Minor ticks',  'zh': '次刻度'},
    'row_direction':    {'en': 'Direction',    'zh': '方向'},
    'row_tick_len':     {'en': 'Tick len',     'zh': '刻度长度'},
    'row_min':          {'en': 'Min',          'zh': '最小值'},
    'row_max':          {'en': 'Max',          'zh': '最大值'},
    'row_log_scale':    {'en': 'Log scale',    'zh': '对数刻度'},
    'row_reversed':     {'en': 'Reversed',     'zh': '反向'},
    'row_label':        {'en': 'Label',        'zh': '标签'},
    'row_colour':       {'en': 'Colour',       'zh': '颜色'},
    'row_line_width':   {'en': 'Line width',   'zh': '线宽'},
    'row_line_style':   {'en': 'Line style',   'zh': '线型'},
    'row_marker':       {'en': 'Marker',       'zh': '标记'},
    'row_marker_size':  {'en': 'Marker size',  'zh': '标记大小'},
    'row_show_legend':  {'en': 'Show legend',  'zh': '显示图例'},
    'row_location':     {'en': 'Location',     'zh': '位置'},
    'row_frame':        {'en': 'Frame',        'zh': '边框'},
    'row_frame_colour': {'en': 'Frame colour', 'zh': '边框颜色'},
    'row_columns':      {'en': 'Columns',      'zh': '列数'},
    'row_show_grid':    {'en': 'Show grid',    'zh': '显示网格'},
    'row_axis':         {'en': 'Axis',         'zh': '坐标轴'},
    'row_lines':        {'en': 'Lines',        'zh': '刻度线'},
    'row_grid_colour':  {'en': 'Grid colour',  'zh': '网格颜色'},
    'row_width':        {'en': 'Width',        'zh': '宽度'},
    'row_opacity':      {'en': 'Opacity',      'zh': '不透明度'},
    'row_hide_top':     {'en': 'Hide top',     'zh': '隐藏上边框'},
    'row_hide_right':   {'en': 'Hide right',   'zh': '隐藏右边框'},
    'row_hide_left':    {'en': 'Hide left',    'zh': '隐藏左边框'},
    'row_hide_bottom':  {'en': 'Hide bottom',  'zh': '隐藏下边框'},
    'row_theme':        {'en': 'Colour theme', 'zh': '颜色主题'},
    'row_reverse_colours': {'en': 'Reverse colours',
                            'zh': '反转颜色'},
    'row_fill_opacity': {'en': 'Fill opacity', 'zh': '填充不透明度'},
    'row_edge_width':   {'en': 'Edge width',   'zh': '边缘宽度'},
    'row_edge_colour':  {'en': 'Edge colour',  'zh': '边缘颜色'},
    'row_point_size':   {'en': 'Point size',   'zh': '点大小'},
    'row_point_opacity': {'en': 'Point opacity', 'zh': '点不透明度'},
    'row_point_edge_colour': {'en': 'Point outline colour',
                              'zh': '点轮廓颜色'},
    'row_point_edge_width': {'en': 'Point outline width (0 = none)',
                             'zh': '点轮廓宽度（0 = 无）'},
    'row_enhance_contrast': {'en': 'Enhance contrast',
                             'zh': '增强对比度'},
    'row_show_box':     {'en': 'Show box',     'zh': '显示箱体'},
    'row_show_points':  {'en': 'Show points',  'zh': '显示数据点'},
    'row_points_beside': {'en': 'Points beside', 'zh': '数据点侧置'},
    'row_bandwidth':    {'en': 'Bandwidth',    'zh': '带宽'},
    'row_bar_width':    {'en': 'Bar width',    'zh': '柱宽'},
    'row_show_values':  {'en': 'Show values',  'zh': '显示数值'},
    'row_value_threshold': {'en': 'Threshold %', 'zh': '阈值 %'},
    'row_value_colour': {'en': 'Value colour', 'zh': '数值颜色'},
    'row_bold_values':  {'en': 'Bold values',  'zh': '数值加粗'},
    'row_value_size':   {'en': 'Value size',   'zh': '数值字号'},
    'row_offset':       {'en': 'Offset',       'zh': '偏移'},
    'row_reverse_order': {'en': 'Reverse order', 'zh': '反转顺序'},
    'row_baseline_colour': {'en': 'Baseline colour',
                            'zh': '基线颜色'},
    'row_baseline_width': {'en': 'Baseline width',
                           'zh': '基线宽度'},
    'row_show_labels':  {'en': 'Show labels',  'zh': '显示标签'},
    'row_position':     {'en': 'Position',     'zh': '位置'},
    'row_box':          {'en': 'Box',          'zh': '边框背景'},
    'row_from':         {'en': 'From',         'zh': '起点'},
    'row_to':           {'en': 'To',           'zh': '终点'},
    'btn_delete':       {'en': 'Delete',       'zh': '删除'},
    'bw_scott':         {'en': 'Scott',        'zh': 'Scott'},
    'bw_silverman':     {'en': 'Silverman',    'zh': 'Silverman'},
    'bw_custom':        {'en': 'Custom',       'zh': '自定义'},
    'bw_factor':        {'en': 'factor',       'zh': '系数'},
    'note_default':     {'en': 'Note',         'zh': '注释'},
    'anchor_free':      {'en': 'Free (dragged)',
                         'zh': '自由（拖拽）'},
    'ctx_add_text_here': {'en': 'Add Text Here',
                          'zh': '在此处添加文本'},
    'ctx_create_first': {'en': 'Create a plot first',
                         'zh': '请先创建图表'},
    'ctx_edit':         {'en': 'Edit…',        'zh': '编辑…'},
    'menu_colour_theme': {'en': 'Colour Theme', 'zh': '颜色主题'},
    'menu_edit_themes': {'en': 'Edit Colour Themes…',
                         'zh': '编辑颜色主题…'},
    'tip_edit_themes':  {'en': 'Edit colour themes',
                         'zh': '编辑颜色主题'},
    'row_edge_width_none': {'en': 'Edge width (0 = none)',
                            'zh': '边缘宽度（0 = 无）'},
    'sec_group_labels': {'en': 'Group labels', 'zh': '分组标签'},
    'sec_bar_labels':   {'en': 'Bar labels',   'zh': '柱标签'},
    'row_label_n':      {'en': 'Item {n}',     'zh': '第 {n} 项'},
    'btn_edit':         {'en': 'Edit…',        'zh': '编辑…'},
    'btn_remove':       {'en': 'Remove',       'zh': '移除'},
    'btn_up':           {'en': 'Up',           'zh': '上移'},
    'btn_down':         {'en': 'Down',         'zh': '下移'},
    'btn_new':          {'en': 'New',          'zh': '新建'},
    'btn_close':        {'en': 'Close',        'zh': '关闭'},
    'te_title':         {'en': 'Colour Themes', 'zh': '颜色主题'},
    'te_name':          {'en': 'Theme name',   'zh': '主题名称'},
    'te_builtin':       {'en': '(built-in)',   'zh': '（内置）'},
    'te_builtin_hint':  {'en': 'Built-in themes are read-only — '
                               'duplicate to customise.',
                         'zh': '内置主题为只读 — 复制后可自定义。'},
    'te_add_colour':    {'en': 'Add colour',   'zh': '添加颜色'},
    'te_new_name':      {'en': 'Custom theme', 'zh': '自定义主题'},
    'te_rename_prompt': {'en': 'New name:',    'zh': '新名称：'},
    'te_delete_confirm': {'en': 'Delete theme "{name}"?',
                          'zh': '要删除主题“{name}”吗？'},
    'te_err_min_colors': {'en': 'A theme needs at least one colour.',
                          'zh': '主题至少需要一种颜色。'},

    'sec_labels':    {'en': 'Labels',   'zh': '标签'},
    'sec_ticks':     {'en': 'Ticks',    'zh': '刻度'},
    'sec_scale':     {'en': 'Scale',    'zh': '刻度范围'},
    'sec_frame':     {'en': 'Frame',    'zh': '边框'},
    'sec_grid':      {'en': 'Grid',     'zh': '网格'},
    'sec_theme':     {'en': 'Colour theme', 'zh': '颜色主题'},
    'sec_violin':    {'en': 'Violin',   'zh': '小提琴图'},
    'sec_columns':   {'en': 'Columns',  'zh': '柱状图'},
    'sec_ridgeline': {'en': 'Ridgeline', 'zh': '山脊图'},

    'tip_bold':         {'en': 'Bold',      'zh': '加粗'},
    'tip_italic':       {'en': 'Italic',    'zh': '斜体'},
    'tip_underline':    {'en': 'Underline', 'zh': '下划线'},
    'tip_choose_colour': {'en': 'Choose colour', 'zh': '选择颜色'},
    'tip_reset_default': {'en': 'Reset to default', 'zh': '重置为默认值'},
    'tip_align_left':    {'en': 'Align left',    'zh': '左对齐'},
    'tip_align_center':  {'en': 'Align center',  'zh': '居中对齐'},
    'tip_align_right':   {'en': 'Align right',   'zh': '右对齐'},
    'tip_tick_spacing':  {'en': 'Distance between major ticks, in data '
                               'units',
                          'zh': '主刻度之间的距离（数据单位）'},
    'tip_reset_text':    {'en': 'Use spreadsheet value',
                          'zh': '使用表格中的值'},
    'btn_reset':         {'en': 'Reset',     'zh': '重置'},
    'font_default':      {'en': 'Default ({family})',
                          'zh': '默认（{family}）'},
    'auto_placeholder':  {'en': 'Auto',      'zh': '自动'},

    # ── Combo items ──────────────────────────────────────────────────
    'line_solid':    {'en': 'Solid',     'zh': '实线'},
    'line_dashed':   {'en': 'Dashed',    'zh': '虚线'},
    'line_dashdot':  {'en': 'Dash-dot',  'zh': '点划线'},
    'line_dotted':   {'en': 'Dotted',    'zh': '点线'},
    'line_none':     {'en': 'None',      'zh': '无'},
    'marker_none':       {'en': 'None',         'zh': '无'},
    'marker_circle':     {'en': 'Circle',       'zh': '圆形'},
    'marker_square':     {'en': 'Square',       'zh': '方形'},
    'marker_tri_up':     {'en': 'Triangle up',  'zh': '上三角'},
    'marker_tri_down':   {'en': 'Triangle down', 'zh': '下三角'},
    'marker_diamond':    {'en': 'Diamond',      'zh': '菱形'},
    'marker_plus':       {'en': 'Plus',         'zh': '加号'},
    'marker_cross':      {'en': 'Cross',        'zh': '叉号'},
    'marker_point':      {'en': 'Point',        'zh': '点'},
    'dir_out':     {'en': 'Out',  'zh': '向外'},
    'dir_in':      {'en': 'In',   'zh': '向内'},
    'dir_both':    {'en': 'Both', 'zh': '双向'},
    'grid_axis_both': {'en': 'Both', 'zh': '两者'},
    'grid_axis_x':    {'en': 'X',    'zh': 'X'},
    'grid_axis_y':    {'en': 'Y',    'zh': 'Y'},
    'grid_which_major': {'en': 'Major',         'zh': '主刻度'},
    'grid_which_both':  {'en': 'Major + minor', 'zh': '主刻度 + 次刻度'},
    'loc_best':          {'en': 'Best',         'zh': '最佳'},
    'loc_upper_right':   {'en': 'Upper right',  'zh': '右上'},
    'loc_upper_left':    {'en': 'Upper left',   'zh': '左上'},
    'loc_lower_left':    {'en': 'Lower left',   'zh': '左下'},
    'loc_lower_right':   {'en': 'Lower right',  'zh': '右下'},
    'loc_right':         {'en': 'Right',        'zh': '右侧'},
    'loc_center_left':   {'en': 'Center left',  'zh': '左侧居中'},
    'loc_center_right':  {'en': 'Center right', 'zh': '右侧居中'},
    'loc_lower_center':  {'en': 'Lower center', 'zh': '底部居中'},
    'loc_upper_center':  {'en': 'Upper center', 'zh': '顶部居中'},
    'loc_center':        {'en': 'Center',       'zh': '居中'},
    'loc_outside_right': {'en': 'Outside right', 'zh': '右侧外部'},
    'anchor_upper_left':   {'en': 'Upper left',   'zh': '左上'},
    'anchor_upper_center': {'en': 'Upper center', 'zh': '顶部居中'},
    'anchor_upper_right':  {'en': 'Upper right',  'zh': '右上'},
    'anchor_lower_left':   {'en': 'Lower left',   'zh': '左下'},
    'anchor_lower_center': {'en': 'Lower center', 'zh': '底部居中'},
    'anchor_lower_right':  {'en': 'Lower right',  'zh': '右下'},
    'anchor_center_left':  {'en': 'Center left',  'zh': '左侧居中'},
    'anchor_center_right': {'en': 'Center right', 'zh': '右侧居中'},
    'panel_violin':     {'en': 'Violin {name}', 'zh': '小提琴图 {name}'},
    'panel_stack':      {'en': 'Category {name}', 'zh': '类别 {name}'},
    'panel_annotation': {'en': 'Note',          'zh': '注释'},
    'panel_bracket':    {'en': 'Significance bracket',
                         'zh': '显著性标注'},
    'pal_default':    {'en': 'Default',    'zh': '默认'},
    'pal_wong':       {'en': 'Wong',       'zh': 'Wong'},
    'pal_blue_pink':  {'en': 'Blue-pink',  'zh': '蓝粉'},
    'pal_blue_red':   {'en': 'Blue-red',   'zh': '蓝红'},
    'pal_blue_red_preserve_ends': {'en': 'Blue-red (ends)',
                                   'zh': '蓝红（保留端点）'},
    'pal_purple_brown': {'en': 'Purple-brown', 'zh': '紫棕'},
    'pal_ocean':      {'en': 'Ocean',      'zh': '海洋'},
    'pal_rainbow':    {'en': 'Rainbow',    'zh': '彩虹'},
    'pal_colorful':   {'en': 'Colorful',   'zh': '多彩'},
    'pal_high_moderate_low': {'en': 'High-moderate-low',
                              'zh': '高-中-低'},

    # ── Import data ──────────────────────────────────────────────────
    'dlg_import':      {'en': 'Import Data',   'zh': '导入数据'},
    'imp_filter_data': {'en': 'Data files (*.csv *.tsv *.txt *.dat '
                              '*.xlsx)',
                        'zh': '数据文件 (*.csv *.tsv *.txt *.dat '
                              '*.xlsx)'},
    'imp_filter_excel': {'en': 'Excel (*.xlsx)', 'zh': 'Excel (*.xlsx)'},
    'imp_filter_all':  {'en': 'All files (*)', 'zh': '所有文件 (*)'},
    'imp_sheet':       {'en': 'Sheet',         'zh': '工作表'},
    'imp_delimiter':   {'en': 'Delimiter',     'zh': '分隔符'},
    'imp_encoding':    {'en': 'Encoding',      'zh': '编码'},
    'imp_skip_lines':  {'en': 'Skip lines',    'zh': '跳过行数'},
    'imp_header_rows': {'en': 'Header rows',   'zh': '标题行数'},
    'imp_header_role': {'en': 'Row {n}',       'zh': '第 {n} 行'},
    'imp_first_column': {'en': 'First column', 'zh': '首列'},
    'imp_destination': {'en': 'Destination',   'zh': '导入位置'},
    'imp_dest_replace': {'en': 'Replace current sheet',
                         'zh': '替换当前工作表'},
    'imp_dest_append': {'en': 'Append columns', 'zh': '追加列'},
    'imp_dest_new_tab': {'en': 'New tab',       'zh': '新标签页'},
    'imp_auto':        {'en': 'Auto ({value})', 'zh': '自动（{value}）'},
    'imp_delim_comma': {'en': 'Comma',         'zh': '逗号'},
    'imp_delim_tab':   {'en': 'Tab',           'zh': '制表符'},
    'imp_delim_semicolon': {'en': 'Semicolon', 'zh': '分号'},
    'imp_delim_pipe':  {'en': 'Pipe',          'zh': '竖线'},
    'imp_delim_whitespace': {'en': 'Whitespace', 'zh': '空白'},
    'role_ignore':     {'en': 'Ignore',        'zh': '忽略'},
    'imp_xlsx_note':   {'en': 'Excel dates are imported as serial '
                              'numbers.',
                        'zh': 'Excel 日期将以序列号导入。'},
    'err_import_read': {'en': 'Could not read the file:\n{error}',
                        'zh': '无法读取文件：\n{error}'},
    'err_file_too_large': {'en': 'The file is too large (max {max})',
                           'zh': '文件过大（最大 {max}）'},
    'err_xls_old':     {'en': 'Old .xls files are not supported — save '
                             'as .xlsx or CSV',
                        'zh': '不支持旧版 .xls 文件——请另存为 .xlsx '
                              '或 CSV'},
    'err_zip_unsafe':  {'en': 'The workbook is too large or unsafe to '
                             'open',
                        'zh': '工作簿过大或不安全，无法打开'},
    'err_no_sheets':   {'en': 'The workbook contains no sheets',
                        'zh': '工作簿中没有工作表'},
    'err_unknown_sheet': {'en': 'No sheet named {value}',
                          'zh': '没有名为 {value} 的工作表'},
    'err_import_empty': {'en': 'The file contains no importable '
                               'columns',
                         'zh': '文件中没有可导入的列'},

    # ── Style presets ────────────────────────────────────────────────
    'btn_style':          {'en': 'Style',         'zh': '样式'},
    'tip_style_presets':  {'en': 'Style presets', 'zh': '样式预设'},
    'preset_default':     {'en': '(default)',     'zh': '（默认）'},
    'preset_builtin':     {'en': '(built-in)',    'zh': '（内置）'},
    'preset_save':        {'en': 'Save current formatting as preset…',
                           'zh': '将当前格式保存为预设…'},
    'preset_save_title':  {'en': 'Save Style Preset',
                           'zh': '保存样式预设'},
    'preset_save_prompt': {'en': 'Preset name:',   'zh': '预设名称：'},
    'preset_manage':      {'en': 'Manage styles…', 'zh': '管理样式…'},
    'preset_name_title':  {'en': 'Preset Name',    'zh': '预设名称'},
    'preset_rename_prompt': {'en': 'New name:',    'zh': '新名称：'},
    'preset_duplicate':   {'en': 'A preset named "{name}" already '
                                 'exists.',
                           'zh': '已存在名为“{name}”的预设。'},
    'preset_invalid_name': {'en': 'Enter a preset name of up to 60 '
                                  'characters, without / \\ : * ? " '
                                  '< > |.',
                            'zh': '请输入不超过 60 个字符的预设名称，'
                                  '且不能包含 / \\ : * ? " < > |。'},
    'preset_save_failed': {'en': 'Could not save the preset:\n{error}',
                           'zh': '无法保存预设：\n{error}'},
    'preset_delete_confirm': {'en': 'Delete preset "{name}"?',
                              'zh': '要删除预设“{name}”吗？'},
    'preset_errors':      {'en': 'Some preset files could not be '
                                 'loaded: {files}',
                           'zh': '部分预设文件无法加载：{files}'},
    'style_mgr_title':    {'en': 'Plot Style',     'zh': '图表样式'},
    'btn_new_from_plot':  {'en': 'New from current plot',
                           'zh': '从当前图表新建'},
    'btn_duplicate':      {'en': 'Duplicate',      'zh': '复制'},
    'btn_rename':         {'en': 'Rename',         'zh': '重命名'},
    'btn_delete':         {'en': 'Delete',         'zh': '删除'},
    'btn_set_default':    {'en': 'Set as default', 'zh': '设为默认'},
    'btn_apply':          {'en': 'Apply to current plot',
                           'zh': '应用到当前图表'},
    'btn_open_folder':    {'en': 'Open folder',    'zh': '打开文件夹'},
    'sum_font':           {'en': 'Font: {value}',  'zh': '字体：{value}'},
    'sum_legend':         {'en': 'Legend: {value}',
                           'zh': '图例：{value}'},
    'sum_grid':           {'en': 'Grid: {value}',  'zh': '网格：{value}'},
    'sum_colors':         {'en': 'Colors:',        'zh': '颜色：'},
    'sum_default':        {'en': 'Default',        'zh': '默认'},
    'sum_on':             {'en': 'On',             'zh': '开'},
    'sum_off':            {'en': 'Off',            'zh': '关'},
    'sum_inherit':        {'en': 'document default', 'zh': '文档默认'},

    # ── Guided tutorials ─────────────────────────────────────────────
    'tut_title':        {'en': 'Tutorials',  'zh': '教程'},
    'tut_chooser_intro': {'en': 'Each lesson opens a separate practice '
                                'tab — your other tabs are untouched.',
                          'zh': '每课都会打开独立的练习标签页，'
                                '不影响其他标签页。'},
    'tut_practice':     {'en': 'Practice — {name}', 'zh': '练习 — {name}'},
    'tut_step_fmt':     {'en': 'Step {n} of {m}',
                         'zh': '第 {n} 步，共 {m} 步'},
    'tut_back':         {'en': 'Back',   'zh': '上一步'},
    'tut_skip':         {'en': 'Skip',   'zh': '跳过'},
    'tut_next':         {'en': 'Next',   'zh': '下一步'},
    'tut_finish':       {'en': 'Finish', 'zh': '完成'},
    'tut_exit':         {'en': 'Exit',   'zh': '退出'},
    'tut_status_paused': {'en': 'Return to the practice tab to continue.',
                          'zh': '请返回练习标签页继续。'},
    'tut_status_ready':  {'en': 'Done — choose Next when you are ready.',
                          'zh': '已完成——准备好后点击“下一步”。'},
    'tut_status_info':   {'en': 'Choose Next to continue.',
                          'zh': '点击“下一步”继续。'},
    'tut_status_wait':   {'en': 'Follow the step above; Next becomes '
                               'available once it is done.',
                          'zh': '请按上方说明操作；完成后“下一步”即可用。'},
    'tut_act_fill_sample': {'en': 'Fill sample data', 'zh': '填入示例数据'},
    'tut_act_plot_sample': {'en': 'Plot it for me',   'zh': '帮我绘图'},

    'tut_lessons_first_plot_title': {'en': 'Your first plot',
                                     'zh': '你的第一张图表'},
    'tut_lessons_first_plot_summary': {
        'en': 'Enter data, set column roles, plot, style in place, '
              'and save an editable .ilmplot.svg.',
        'zh': '录入数据、设置列角色、绘图、就地编辑样式，'
              '并保存可编辑的 .ilmplot.svg。'},
    'tut_lessons_styling_title': {'en': 'Styling and presets',
                                  'zh': '样式与预设'},
    'tut_lessons_styling_summary': {
        'en': 'Colour themes, style presets, per-element restore, and '
              'resetting all formatting.',
        'zh': '颜色主题、样式预设、单个元素恢复自动，'
              '以及一键重置全部格式。'},

    # ── Lesson: first_plot ───────────────────────────────────────────
    'tut_fp_intro_title': {'en': 'Worksheet on the left, plot on the right',
                           'zh': '左边是表格，右边是图表'},
    'tut_fp_intro_body': {
        'en': 'The Plot Editor has two halves: a worksheet on the left '
              'holds your numbers, and a live plot appears on the '
              'right. Each column has a role — X for the shared axis '
              'values, Y for a data series, Label for row names.\n\n'
              'In this practice tab we will build a small line plot '
              'together. Nothing here touches your real files or your '
              'other tabs.',
        'zh': '图表编辑器分为两半：左边的工作表放数据，右边实时显示图表。'
              '每一列都有角色——X 是共用的坐标轴数值，Y 是数据系列，'
              'Label 是行名。\n\n'
              '我们将在练习标签页里一起做一张折线图。'
              '这里的一切不会影响你的真实文件和其他标签页。'},
    'tut_fp_enter_data_title': {'en': 'Enter some data',
                                'zh': '录入数据'},
    'tut_fp_enter_data_body': {
        'en': 'A plot needs numbers first. Click a cell and type, or '
              'press Fill sample data below to drop in a three-column '
              'practice set: Time in column A, two measurement series '
              'in B and C — just sample values, not real data.\n\n'
              'The Long Name and Units rows above the data name each '
              'column; the plot uses them for axis titles and the '
              'legend.',
        'zh': '绘图先要有数据。点击单元格直接输入，或点击下方'
              '“填入示例数据”，放入三列练习数据：A 列是 Time，'
              'B、C 是两组测量值——仅为示例数值。\n\n'
              '数据上方的 Long Name 和 Units 行给每列命名；'
              '绘图时会用它们做坐标轴标题和图例。'},
    'tut_fp_roles_title': {'en': 'Give each column a role',
                           'zh': '为每列指定角色'},
    'tut_fp_roles_body': {
        'en': 'Plotting needs to know which column is which. '
              'Right-click a column header → Set As → X or Y. The '
              'header badge shows the role, like A(X) or B(Y).\n\n'
              'The sample columns are already marked: A is X, B and C '
              'are Y — one X plus one or more Y columns with a few '
              'numbers is enough to plot.',
        'zh': '绘图需要知道每列的角色。右键点击列头 → 设置为 → X 或 Y，'
              '列头标记会显示角色，例如 A(X) 或 B(Y)。\n\n'
              '示例列已设置好：A 是 X，B、C 是 Y——一个 X 列加上一个或'
              '多个含若干数值的 Y 列就可以绘图。'},
    'tut_fp_plot_title': {'en': 'Plot it', 'zh': '开始绘图'},
    'tut_fp_plot_body': {
        'en': 'Drag across the headers of columns B and C to select '
              'them, then press the Plot toolbar button (Ctrl+Enter) — '
              'or click Plot it for me below.\n\n'
              'The arrow beside Plot picks the chart type; this '
              'practice uses Line + Scatters. The plot on the right '
              'updates live as the data changes.',
        'zh': '拖动选中 B、C 两列的列头，然后点击工具栏的“绘图”按钮'
              '（Ctrl+Enter），或点击下方“帮我绘图”。\n\n'
              '“绘图”按钮旁的箭头选择图表类型；本练习使用“线 + 散点”。'
              '数据变化时，右侧图表会实时更新。'},
    'tut_fp_edit_in_place_title': {'en': 'Edit in place',
                                   'zh': '就地编辑'},
    'tut_fp_edit_in_place_body': {
        'en': 'Every part of the plot is editable right on the canvas. '
              'Double-click an axis title, a series line, or the legend '
              'to open its panel, then change one setting — a colour, '
              'a size, a style.\n\n'
              'Undo reverses the last change. A ↺ button beside a '
              'setting restores that setting to its automatic value.',
        'zh': '图表的每个部分都可以在画布上直接编辑。双击坐标轴标题、'
              '某条数据线或图例打开对应面板，改一项设置——颜色、'
              '字号或样式都可以。\n\n'
              '撤销可恢复上一次修改前的状态。设置旁的 ↺ 按钮'
              '可将该设置恢复为自动值。'},
    'tut_fp_title_title': {'en': 'Give it a title',
                           'zh': '添加标题'},
    'tut_fp_title_body': {
        'en': 'Double-click the title area above the plot and type a '
              'title — for example "Two signals over time". The title '
              'is saved into the file along with everything else.',
        'zh': '双击图表上方的标题区域，输入标题——例如'
              '“两条曲线随时间变化”。标题会随其他内容一起保存进文件。'},
    'tut_fp_save_title': {'en': 'Save the editable plot',
                          'zh': '保存可编辑图表'},
    'tut_fp_save_body': {
        'en': 'File → Save (Ctrl+S) writes a *.ilmplot.svg file. It is '
              'an ordinary SVG — any viewer shows it exactly the same — '
              'and it also carries the worksheet and every editable '
              'setting inside, so the Plot Editor can open it again '
              'and keep editing. After a successful save, this lesson '
              'continues automatically.',
        'zh': '“文件 → 保存”（Ctrl+S）会写出 *.ilmplot.svg 文件。'
              '它是普通的 SVG——任何查看器看到的效果完全一致——'
              '同时还带有工作表和全部可编辑设置，'
              '图表编辑器可以再次打开继续编辑。保存成功后，'
              '本课程会自动进入下一步。'},
    'tut_fp_finish_title': {'en': 'From editor to figure',
                            'zh': '从编辑器到成图'},
    'tut_fp_finish_body': {
        'en': 'In ILM, a saved .ilmplot.svg drops into a cell and looks '
              'exactly as you saved it — text and lines scale with the '
              'panel like a picture.\n\n'
              'Turn REFLOW ON there and the plot re-lays itself for any '
              'cell shape at true point sizes. ILM’s own lesson "Native '
              'plots & Reflow" (Help → Guided Tutorials) shows it in '
              'action.',
        'zh': '在 ILM 中，保存好的 .ilmplot.svg 放进单元格后'
              '与保存时完全一致——文字和线条随面板整体缩放，'
              '如同一张图片。\n\n'
              '在那里开启 REFLOW，图表会按任意单元格形状重新排版，'
              '文字保持真实磅值。ILM 自带的课程“原生图表与 REFLOW”'
              '（帮助 → 引导教程）会演示这一功能。'},

    # ── Lesson: styling ──────────────────────────────────────────────
    'tut_sty_intro_title': {'en': 'Style without redrawing',
                            'zh': '无需重画的样式'},
    'tut_sty_intro_body': {
        'en': 'This practice tab already has eight sample series '
              'plotted, so a colour theme shows its full range of '
              'colours. '
              'You can change colours, fonts, ticks, and legend '
              'formatting, then undo or reset those changes.\n\n'
              'We will try themes and presets, then learn how to get '
              'the automatic formatting back.',
        'zh': '练习页已绘制八组示例数据，便于完整展示颜色主题的各种颜色。'
              '可以修改颜色、字体、刻度和'
              '图例格式，也可以撤销或重置这些修改。\n\n'
              '我们先试试主题和预设，再学习如何恢复自动格式。'},
    'tut_sty_theme_title': {'en': 'Try a colour theme',
                            'zh': '试用颜色主题'},
    'tut_sty_theme_body': {
        'en': 'Right-click the plot → Colour Theme ▸, or use Plot → '
              'Colour Theme. Pick any theme — the whole palette swaps '
              'in one step.\n\n'
              'Themes are named colour lists. Edit… in that menu opens '
              'the theme editor, where you can keep your own palettes.',
        'zh': '右键点击图表 → “颜色主题 ▸”，或使用“绘图 → 颜色主题”。'
              '任选一个主题——整套配色一步替换。\n\n'
              '主题是命名好的颜色列表；菜单中的“编辑…”会打开主题编辑器，'
              '可以管理自己的配色。'},
    'tut_sty_presets_title': {'en': 'Style presets',
                              'zh': '样式预设'},
    'tut_sty_presets_body': {
        'en': 'The Style button — beside Reset formatting at the '
              'plot’s bottom-right — applies a saved bundle of '
              'formatting for this plot type.\n\n'
              'Each type can carry one default preset (applied when you '
              'plot) plus any number of custom ones; Save current '
              'formatting as preset… stores your own. Line and scatter '
              'charts share the "Line" preset type.',
        'zh': '图表右下角“重置格式”左侧的“样式”按钮，'
              '可以应用该图表类型下保存好的一组格式。\n\n'
              '每种类型可以有一个默认预设（绘图时自动应用）'
              '和任意多个自定义预设；“将当前格式保存为预设…”'
              '可保存你自己的预设。折线图和散点图同属“折线”预设类型。'},
    'tut_sty_manager_title': {'en': 'The style manager',
                              'zh': '样式管理器'},
    'tut_sty_manager_body': {
        'en': 'Plot → Plot Style… opens the manager: presets grouped by '
              'plot type, each with a preview strip. Rename, duplicate, '
              'delete, or set a per-type default there.\n\n'
              'Presets are files in a folder on this machine — Open '
              'folder in the manager shows where they live.',
        'zh': '“绘图 → 图表样式…”打开管理器：预设按图表类型分组，'
              '每项带预览条。可在其中重命名、复制、删除或设为该类型默认。\n\n'
              '预设是本机文件夹中的文件；管理器中的“打开文件夹”'
              '可查看存放位置。'},
    'tut_sty_restore_title': {'en': 'Restore one element',
                              'zh': '恢复单个元素'},
    'tut_sty_restore_body': {
        'en': 'Double-click an element — a series line, an axis title, '
              'or the legend — and change a setting. Use the ↺ button '
              'beside that setting to restore its automatic value. '
              'Other settings remain unchanged.',
        'zh': '双击某个元素——数据线、坐标轴标题或图例——并修改一项设置。'
              '点击该设置旁的 ↺ 按钮，可将其恢复为自动值，'
              '其他设置保持不变。'},
    'tut_sty_reset_title': {'en': 'Reset everything',
                            'zh': '重置全部格式'},
    'tut_sty_reset_body': {
        'en': 'The Reset formatting button at the plot’s bottom-right '
              'clears every override at once — after a confirmation, '
              'the plot returns to its automatic look while data and '
              'title stay. Make any styling change first, then try it.',
        'zh': '图表右下角的“重置格式”按钮会一次清除所有覆盖项——'
              '确认后图表恢复自动样式，数据和标题保持不变。'
              '请先做一次样式修改，再试这个功能。'},
    'tut_sty_finish_title': {'en': 'Style is reversible',
                             'zh': '样式随时可回退'},
    'tut_sty_finish_body': {
        'en': 'Themes restyle the whole palette, presets bundle your '
              'choices, and every single override can be returned to '
              'automatic. Your saved file always keeps both the picture '
              'and the settings.\n\n'
              'Finish leaves the practice tab open; reopen these '
              'lessons anytime from Help → Tutorials….',
        'zh': '主题整体换配色，预设打包你的设置，每个覆盖项都能恢复自动。'
              '保存的文件始终同时包含图形和设置。\n\n'
              '完成后练习页会保留；可随时从“帮助 → 教程…”重新打开课程。'},
}


def set_language(lang):
    """Set the UI language; only 'en' and 'zh' are accepted."""
    global _lang
    if lang in ('en', 'zh'):
        _lang = lang


def current_language():
    return _lang


def tr(key, **fmt):
    """Translate *key* in the current language, falling back to English.

    ``str.format`` is applied when keyword arguments are given.
    """
    entry = _STRINGS[key]
    text = entry.get(_lang) or entry['en']
    return text.format(**fmt) if fmt else text


def history_label(label):
    """Translate a worksheet undo-history label; unknown → unchanged."""
    key = 'hist_' + label.lower().replace(' ', '_')
    return tr(key) if key in _STRINGS else label
