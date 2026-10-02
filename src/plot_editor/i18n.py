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
    'act_edit_data': {'en': 'Edit Data…', 'zh': '编辑数据…'},
    'act_axes':     {'en': 'Axes and Labels…', 'zh': '坐标轴和标签…'},
    'act_legend':   {'en': 'Legend…',    'zh': '图例…'},
    'act_style':    {'en': 'Plot Style…', 'zh': '绘图样式…'},
    'act_guide':    {'en': 'User Guide', 'zh': '使用指南'},
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
    'tip_import_data': {'en': 'Not implemented yet', 'zh': '尚未实现'},
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
    'tip_edit_data': {'en': 'Not implemented yet', 'zh': '尚未实现'},
    'tip_axes':     {'en': 'Not implemented yet', 'zh': '尚未实现'},
    'tip_legend':   {'en': 'Not implemented yet', 'zh': '尚未实现'},
    'tip_style':    {'en': 'Not implemented yet', 'zh': '尚未实现'},
    'tip_guide':    {'en': 'Not implemented yet', 'zh': '尚未实现'},
    'tip_shortcuts': {'en': 'Not implemented yet', 'zh': '尚未实现'},
    'tip_about':    {'en': 'Not implemented yet', 'zh': '尚未实现'},
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
    'chart_pure_line':     {'en': 'Pure Line',       'zh': '纯线'},
    'chart_pure_scatters': {'en': 'Pure Scatters',   'zh': '纯散点'},
    'chart_line_scatters': {'en': 'Line + Scatters', 'zh': '线 + 散点'},
    'chart_stacked_line':  {'en': 'Stacked Line',    'zh': '堆叠折线'},

    # ── Window / tabs ────────────────────────────────────────────────
    'window_title':    {'en': '{name} — Plot Editor',
                        'zh': '{name} — 图表编辑器'},
    'untitled':        {'en': 'Untitled {n}', 'zh': '未命名 {n}'},
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

    'sec_labels':    {'en': 'Labels',   'zh': '标签'},
    'sec_ticks':     {'en': 'Ticks',    'zh': '刻度'},
    'sec_scale':     {'en': 'Scale',    'zh': '刻度范围'},
    'sec_frame':     {'en': 'Frame',    'zh': '边框'},
    'sec_grid':      {'en': 'Grid',     'zh': '网格'},

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
