import os
import math
from typing import Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QPushButton, QToolButton, QSplitter, QSplitterHandle, QFileDialog,
    QMessageBox, QSpinBox, QLabel, QComboBox, QFrame, QGraphicsOpacityEffect,
    QLabel, QStyle, QMenu, QTabWidget, QDialog, QFormLayout, QDialogButtonBox,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize, QSettings, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QUndoStack
from PyQt6.QtWidgets import QUndoView
from src.app.theme import build_palette, get_stylesheet, get_layers_tree_stylesheet, get_tokens, DARK, LIGHT
from src.app.icons import make_icon
from src.app.theme_segmented import ThemeSegmented
from src.app.i18n import tr, set_language, current_language

# Try importing QOpenGLWidget for GPU acceleration
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False

from src.model.data_model import Project, Cell, RowTemplate, TextItem
from src.canvas.canvas_scene import CanvasScene
from src.canvas.canvas_view import CanvasView
from src.app.inspector import Inspector
from src.app.layers_panel import LayersPanel
from src.app.about_dialog import AboutDialog, StartupUpdateChecker
from src.app.help_dialog import HelpDialog
from src.model.enums import PageSizePreset
from src.export.pdf_exporter import PdfExporter
from src.export.image_exporter import ImageExporter
from src.utils.auto_label import AutoLabel
from src.app.commands import (
    PropertyChangeCommand, MultiPropertyChangeCommand, SwapCellsCommand, MultiSwapCellsCommand,
    DropImageCommand, ChangeRowCountCommand, InsertRowCommand, InsertCellCommand,
    DeleteRowCommand, DeleteCellCommand,
    AddTextCommand, DeleteTextCommand, AutoLabelCommand, AutoLabelOutCellCommand, AutoLayoutCommand, ChangeLabelSchemeCommand,
    SplitCellCommand, InsertSubCellCommand, DeleteSubCellCommand, WrapAndInsertCommand,
    ChangeSubCellRatioCommand,
    FreeformGeometryCommand, FreeformLayoutModeCommand, ZIndexChangeCommand,
    DividerDragCommand,
    AddPiPItemCommand, SetPiPGeometryCommand, SetPiPOriginCommand
)
from src.model.data_model import PiPItem
from src.utils.image_proxy import get_image_proxy

class _CollapseHandle(QSplitterHandle):
    """Splitter handle with a bookmark-style button to collapse/expand the side panel."""

    _BTN_W, _BTN_H = 14, 48

    def __init__(self, orientation, parent: QSplitter):
        super().__init__(orientation, parent)
        self._saved: dict[int, int] = {}

        btn = QToolButton(self)
        btn.setFixedSize(self._BTN_W, self._BTN_H)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet(
            "QToolButton { border: 1px solid #AAAAAA; background: #E0E0E0;"
            " border-radius: 3px; font-size: 9px; color: #333333; }"
            "QToolButton:hover { background: #C8C8C8; }"
        )
        btn.clicked.connect(self._toggle)
        self._btn = btn

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addStretch(1)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)

        # splitterMoved fires on user drag; setSizes() override handles programmatic changes.
        parent.splitterMoved.connect(lambda *_: self._refresh_arrow())

    def _handle_idx(self) -> int:
        sp = self.splitter()
        for i in range(1, sp.count()):
            if sp.handle(i) is self:
                return i
        return 1

    def _panel_idx(self) -> int:
        hi = self._handle_idx()
        sp = self.splitter()
        # First handle → collapse left outer panel; last handle → collapse right outer panel.
        return sp.count() - 1 if hi == sp.count() - 1 else hi - 1

    def _toggle(self):
        sp = self.splitter()
        pi = self._panel_idx()
        sizes = list(sp.sizes())
        if sizes[pi] > 0:
            self._saved[pi] = sizes[pi]
            sizes[pi] = 0
        else:
            sizes[pi] = self._saved.get(pi, 200)
        sp.setSizes(sizes)   # CollapsibleSplitter.setSizes refreshes all arrows

    def refresh_arrow(self):
        sp = self.splitter()
        if sp is None:
            return
        pi = self._panel_idx()
        hi = self._handle_idx()
        collapsed = sp.sizes()[pi] == 0
        # Arrow points toward the hidden panel so the user knows where it went.
        if pi < hi:   # left panel
            self._btn.setText("▶" if collapsed else "◀")
        else:         # right panel
            self._btn.setText("◀" if collapsed else "▶")

    # Keep old name as alias so the splitterMoved lambda still works
    _refresh_arrow = refresh_arrow

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_arrow()


class CollapsibleSplitter(QSplitter):
    """QSplitter whose handles each carry a small collapse/expand bookmark button."""

    def createHandle(self) -> _CollapseHandle:
        return _CollapseHandle(self.orientation(), self)

    def setSizes(self, sizes: list[int]) -> None:
        super().setSizes(sizes)
        # Refresh every handle arrow after any programmatic size change.
        for i in range(1, self.count()):
            h = self.handle(i)
            if isinstance(h, _CollapseHandle):
                h.refresh_arrow()


class ProjectTabState:
    """Holds all per-tab state: project, undo stack, canvas scene/view, and file path."""
    def __init__(self, project, path: Optional[str] = None):
        self.project = project
        self.path = path
        self.undo_stack = QUndoStack()
        self.scene = CanvasScene()
        self.view = CanvasView(self.scene)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        from src.version import APP_VERSION
        self._app_version = APP_VERSION
        self.setWindowTitle(f"Academic Figure Layout v{APP_VERSION}[*]")
        self.resize(1400, 850)

        # Persistent settings
        self._settings = QSettings("AcademicFigureLayout", "ImageLayoutManager")

        # Tab management — these attributes always reflect the active tab
        self._tabs: list[ProjectTabState] = []
        self._active_tab_idx: int = -1
        self.project = None
        self.undo_stack = None
        self.scene = None
        self.view = None
        self._current_project_path = None
        self._current_theme = LIGHT

        # Registry for toolbar actions whose icon is recoloured on theme
        # change. Populated by _setup_ui via _register_themed_action().
        self._themed_actions: dict[QAction, str] = {}

        # UI Components (tab_widget, layers panel, inspector created here)
        self._setup_ui()

        # Connect inspector / layers panel signals (once, not per-tab)
        self._connect_static_signals()

        # Theme-switch fade overlay (covers the whole window briefly)
        self._theme_overlay = QWidget(self)
        self._theme_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._theme_overlay.setStyleSheet("background-color: rgba(0,0,0,1);")
        self._theme_overlay.hide()
        self._overlay_fx = QGraphicsOpacityEffect(self._theme_overlay)
        self._overlay_fx.setOpacity(0.0)
        self._theme_overlay.setGraphicsEffect(self._overlay_fx)
        self._overlay_anim: QPropertyAnimation | None = None

        # Create the first tab with a default project
        initial_project = Project()
        initial_project.rows = [
            RowTemplate(index=0, column_count=2, height_ratio=1.0),
            RowTemplate(index=1, column_count=2, height_ratio=1.0)
        ]
        self._create_tab(initial_project, path=None)

        # Apply persisted theme and language
        saved_theme = self._settings.value("theme", LIGHT)
        self._apply_theme(saved_theme, animate=False)
        saved_lang = self._settings.value("language", "zh")
        if saved_lang != current_language():
            set_language(saved_lang)
        self.retranslate_ui()

        self._update_window_title()
        self._update_theme_labels()

        # Silent update check
        self._update_checker: StartupUpdateChecker | None = None
        QTimer.singleShot(1500, self._start_update_check)

    def _start_update_check(self):
        self._update_checker = StartupUpdateChecker(self)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.start()

    def _on_update_available(self, latest_tag: str, _url: str):
        """Show a clickable hint in the status bar; clicking opens About."""
        msg = tr("status_update_available").format(tag=latest_tag)
        # Wrap in an <a> so QLabel.linkActivated fires; href is a sentinel.
        self.update_available_label.setText(
            f'<a href="about" style="color:#4A90E2; text-decoration:none;">🔔 {msg}</a>'
        )
        self.update_available_label.setToolTip(tr("status_update_tooltip"))
        self.update_available_label.show()

    def _on_update_banner_clicked(self, _href: str):
        """Open the About dialog when the user clicks the update banner."""
        self._on_show_about()

    def _setup_ui(self):
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        self.toolbar.toggleViewAction().setEnabled(False)
        self.toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

        # ── Menu Bar ──
        self._file_menu   = self.menuBar().addMenu(tr("menu_file"))
        self._edit_menu   = self.menuBar().addMenu(tr("menu_edit"))
        self._layout_menu_ref = None  # set below
        self._view_menu   = self.menuBar().addMenu(tr("menu_view"))
        self._help_menu   = self.menuBar().addMenu(tr("menu_help"))
        # local aliases for building
        file_menu   = self._file_menu
        edit_menu   = self._edit_menu
        help_menu   = self._help_menu

        # ── View menu (theme + language toggles) ──
        self._act_toggle_layers = QAction(tr("action_toggle_layers"), self)
        self._act_toggle_layers.setShortcut(QKeySequence("Ctrl+\\"))
        self._act_toggle_layers.setCheckable(True)
        self._act_toggle_layers.setChecked(True)
        self._act_toggle_layers.triggered.connect(self._on_toggle_layers_panel)
        self._view_menu.addAction(self._act_toggle_layers)
        self._view_menu.addSeparator()

        self._theme_action = QAction(tr("action_switch_light"), self)
        self._theme_action.setShortcut("Ctrl+Shift+T")
        self._theme_action.triggered.connect(self._on_toggle_theme)
        self._view_menu.addAction(self._theme_action)

        self._lang_action = QAction(tr("action_switch_zh"), self)
        self._lang_action.setShortcut("Ctrl+Shift+G")
        self._lang_action.triggered.connect(self._on_toggle_language)
        self._view_menu.addAction(self._lang_action)

        self._about_action = QAction(tr("action_about"), self)
        self._about_action.setMenuRole(QAction.MenuRole.NoRole)
        self._about_action.triggered.connect(self._on_show_about)
        help_menu.addAction(self._about_action)

        self._help_guide_action = QAction(tr("action_user_guide"), self)
        self._help_guide_action.setShortcut("F1")
        self._help_guide_action.setMenuRole(QAction.MenuRole.NoRole)
        self._help_guide_action.triggered.connect(self._on_show_help)
        help_menu.addAction(self._help_guide_action)

        # ── Undo / Redo ──
        self._undo_action = QAction(tr("action_undo"), self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._register_themed_action(self._undo_action, "undo")
        self._undo_action.setEnabled(False)
        self._undo_action.triggered.connect(lambda: self.undo_stack.undo())

        self._redo_action = QAction(tr("action_redo"), self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._register_themed_action(self._redo_action, "redo")
        self._redo_action.setEnabled(False)
        self._redo_action.triggered.connect(lambda: self.undo_stack.redo())

        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)
        edit_menu.addSeparator()

        self.toolbar.addAction(self._undo_action)
        self.toolbar.addAction(self._redo_action)
        self.toolbar.addSeparator()

        # ── File Actions ──
        new_action = QAction(tr("action_new"), self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        self._register_themed_action(new_action, "new")
        new_action.triggered.connect(self._on_new_project)
        self._act_new = new_action

        open_action = QAction(tr("action_open"), self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._register_themed_action(open_action, "open")
        open_action.triggered.connect(self._on_open_project)
        self._act_open = open_action

        save_action = QAction(tr("action_save"), self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._register_themed_action(save_action, "save")
        save_action.triggered.connect(self._on_save_project)
        self._act_save = save_action

        save_as_action = QAction(tr("action_save_as"), self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self._on_save_project_as)
        self._act_save_as = save_as_action

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()

        # File menu — image operations
        import_action = QAction(tr("action_import"), self)
        import_action.triggered.connect(self._on_import_images)
        file_menu.addAction(import_action)
        self._act_import = import_action

        open_images_grid_action = QAction(tr("action_open_grid"), self)
        open_images_grid_action.triggered.connect(self._on_open_images_as_grid)
        file_menu.addAction(open_images_grid_action)
        self._act_open_grid = open_images_grid_action

        reload_images_action = QAction(tr("action_reload"), self)
        reload_images_action.setShortcut(QKeySequence("F5"))
        reload_images_action.triggered.connect(self._on_reload_images)
        file_menu.addAction(reload_images_action)
        self._act_reload = reload_images_action

        file_menu.addSeparator()

        # File menu — export
        export_pdf_action = QAction(tr("action_export_pdf"), self)
        export_pdf_action.triggered.connect(self._on_export_pdf)
        file_menu.addAction(export_pdf_action)
        self._act_export_pdf = export_pdf_action

        export_tiff_action = QAction(tr("action_export_tiff"), self)
        export_tiff_action.triggered.connect(self._on_export_tiff)
        file_menu.addAction(export_tiff_action)
        self._act_export_tiff = export_tiff_action

        export_jpg_action = QAction(tr("action_export_jpg"), self)
        export_jpg_action.triggered.connect(self._on_export_jpg)
        file_menu.addAction(export_jpg_action)
        self._act_export_jpg = export_jpg_action

        # Toolbar — file group (New, Open, Save only)
        self.toolbar.addAction(new_action)
        self.toolbar.addAction(open_action)
        self.toolbar.addAction(save_action)
        self.toolbar.addSeparator()

        # ── Edit menu — text/image/label actions ──
        add_text_action = QAction(tr("action_add_text"), self)
        add_text_action.triggered.connect(self._on_add_text)
        edit_menu.addAction(add_text_action)
        self._act_add_text = add_text_action

        delete_text_action = QAction(tr("action_delete_sel"), self)
        delete_text_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_text_action.triggered.connect(self._on_delete_text)
        edit_menu.addAction(delete_text_action)
        self._act_delete_sel = delete_text_action

        delete_image_action = QAction(tr("action_delete_img"), self)
        delete_image_action.setShortcut(QKeySequence("Ctrl+Delete"))
        delete_image_action.triggered.connect(self._on_delete_image)
        edit_menu.addAction(delete_image_action)
        self._act_delete_img = delete_image_action

        edit_menu.addSeparator()

        auto_label_incell_action = QAction(tr("action_auto_label_incell"), self)
        auto_label_incell_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        auto_label_incell_action.setToolTip(tr("tooltip_auto_label_incell"))
        self._register_themed_action(auto_label_incell_action, "cell_labels")
        auto_label_incell_action.triggered.connect(self._on_auto_label_incell)
        edit_menu.addAction(auto_label_incell_action)
        self._act_auto_label_incell = auto_label_incell_action

        auto_label_outcell_action = QAction(tr("action_auto_label_outcell"), self)
        auto_label_outcell_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
        auto_label_outcell_action.setToolTip(tr("tooltip_auto_label_outcell"))
        self._register_themed_action(auto_label_outcell_action, "row_labels")
        auto_label_outcell_action.triggered.connect(self._on_auto_label_outcell)
        edit_menu.addAction(auto_label_outcell_action)
        self._act_auto_label_outcell = auto_label_outcell_action

        auto_layout_action = QAction(tr("action_auto_layout"), self)
        auto_layout_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self._register_themed_action(auto_layout_action, "auto_layout")
        auto_layout_action.triggered.connect(self._on_auto_layout)
        edit_menu.addAction(auto_layout_action)
        self._act_auto_layout = auto_layout_action

        # ── Layout menu ── (inserted before View in menubar)
        self._layout_menu_ref = QMenu(tr("menu_layout"), self)
        self.menuBar().insertMenu(self._view_menu.menuAction(), self._layout_menu_ref)
        layout_menu = self._layout_menu_ref

        bake_action = QAction(tr("action_bake"), self)
        bake_action.triggered.connect(self._on_bake_to_freeform)
        layout_menu.addAction(bake_action)
        self._act_bake = bake_action

        grid_mode_action = QAction(tr("action_grid_mode"), self)
        grid_mode_action.triggered.connect(self._on_switch_to_grid)
        layout_menu.addAction(grid_mode_action)
        self._act_grid_mode = grid_mode_action

        layout_menu.addSeparator()

        bring_front_action = QAction(tr("action_bring_front"), self)
        bring_front_action.setShortcut(QKeySequence("Ctrl+]"))
        bring_front_action.triggered.connect(self._on_bring_to_front)
        layout_menu.addAction(bring_front_action)
        self._act_bring_front = bring_front_action

        send_back_action = QAction(tr("action_send_back"), self)
        send_back_action.setShortcut(QKeySequence("Ctrl+["))
        send_back_action.triggered.connect(self._on_send_to_back)
        layout_menu.addAction(send_back_action)
        self._act_send_back = send_back_action

        # ── Toolbar — quick actions ──
        self.toolbar.addAction(auto_label_incell_action)
        self.toolbar.addAction(auto_label_outcell_action)
        self.toolbar.addAction(auto_layout_action)
        self.toolbar.addSeparator()

        # ── Right-aligned toolbar group ─────────────────────────────────
        # A stretch spacer pushes the following widgets to the right edge,
        # matching the ``.tb-group.right`` region in the redesign mockups.
        self._toolbar_spacer = QWidget(self)
        self._toolbar_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._toolbar_spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._toolbar_spacer.setStyleSheet("background: transparent;")
        self.toolbar.addWidget(self._toolbar_spacer)

        # Light / Dark segmented pill.
        self._theme_segmented = ThemeSegmented(initial=self._current_theme, parent=self)
        self._theme_segmented.themeChanged.connect(self._apply_theme)
        self.toolbar.addWidget(self._theme_segmented)

        # Primary Export button (accent colour). QToolButton with
        # ``primary=true`` is styled by the QSS in ``theme.py``.
        export_button = QToolButton(self)
        export_button.setText(tr("toolbar_export"))
        export_button.setProperty("primary", True)
        export_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_menu = QMenu(self)
        export_menu.addAction(export_pdf_action)
        export_menu.addAction(export_tiff_action)
        export_menu.addAction(export_jpg_action)
        export_button.setMenu(export_menu)
        self._export_button = export_button  # icon applied via _refresh_toolbar_icons
        self.toolbar.addWidget(export_button)

        # ── Preview-mode toggle ──
        self._act_preview_mode = QAction(tr("action_preview_mode"), self)
        self._act_preview_mode.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self._act_preview_mode.setCheckable(True)
        self._act_preview_mode.triggered.connect(self._on_toggle_preview_mode)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._act_preview_mode)

        # ── History settings ──
        self._act_history_settings = QAction(tr("action_history_settings"), self)
        self._act_history_settings.triggered.connect(self._on_history_settings)
        self._view_menu.addAction(self._act_history_settings)

        # ── Tab actions ──
        self._act_new_tab = QAction(tr("action_new_tab"), self)
        self._act_new_tab.setShortcut(QKeySequence("Ctrl+T"))
        self._act_new_tab.triggered.connect(self._on_new_tab)

        self._act_close_tab = QAction(tr("action_close_tab"), self)
        self._act_close_tab.setShortcut(QKeySequence("Ctrl+W"))
        self._act_close_tab.triggered.connect(self._on_close_current_tab)

        file_menu.addSeparator()
        file_menu.addAction(self._act_new_tab)
        file_menu.addAction(self._act_close_tab)

        # Splitter for Layers+History | Content Tabs | Inspector
        splitter = CollapsibleSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(16)
        self.splitter = splitter
        main_layout.addWidget(splitter)

        # ── Left Panel: Layers + History tabs ──
        self.left_tabs = QTabWidget()
        self.left_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.layers_panel = LayersPanel()
        self.history_view = QUndoView()
        self.history_view.setCleanIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.left_tabs.addTab(self.layers_panel, tr("tab_layers"))
        self.left_tabs.addTab(self.history_view, tr("tab_history"))
        splitter.addWidget(self.left_tabs)

        # ── Centre: Tab widget for multiple open files ──
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabCloseRequested.connect(self._on_close_tab_by_index)
        splitter.addWidget(self.tab_widget)

        # Inspector Area
        self.inspector = Inspector()
        splitter.addWidget(self.inspector)

        # Set initial sizes and stretch factors (3-columns)
        splitter.setSizes([180, 720, 400])
        splitter.setStretchFactor(0, 0)   # Layers keeps its size
        splitter.setStretchFactor(1, 1)   # Canvas stretches
        splitter.setStretchFactor(2, 0)   # Inspector keeps its size
        
        # Status Bar
        self.statusbar = self.statusBar()
        self.mouse_pos_label = QLabel("")
        self.selection_info_label = QLabel("")
        self.canvas_size_label = QLabel("Canvas: -")
        self.zoom_label = QLabel("Zoom: 100%")

        def _status_divider() -> QFrame:
            f = QFrame()
            f.setObjectName("statusDivider")
            f.setFrameShape(QFrame.Shape.VLine)
            f.setFixedSize(1, 12)
            return f

        self.statusbar.addWidget(self.mouse_pos_label)
        self.statusbar.addWidget(_status_divider())
        self.statusbar.addWidget(self.canvas_size_label)
        self.statusbar.addWidget(_status_divider())
        self.statusbar.addWidget(self.selection_info_label)

        # Update-available banner (hidden unless a newer release is detected
        # during the silent startup check). Clicking opens the About dialog.
        self.update_available_label = QLabel("")
        self.update_available_label.setTextFormat(Qt.TextFormat.RichText)
        self.update_available_label.setOpenExternalLinks(False)
        self.update_available_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_available_label.setStyleSheet(
            "color: #4A90E2; font-size: 12px; padding: 0 8px;"
        )
        self.update_available_label.linkActivated.connect(self._on_update_banner_clicked)
        self.update_available_label.hide()
        self.statusbar.addPermanentWidget(self.update_available_label)
        self.statusbar.addPermanentWidget(self.zoom_label)

    def _connect_static_signals(self):
        """Connect once-only signals: inspector, layers panel."""
        self.inspector.cell_property_changed.connect(self._on_cell_property_changed)
        self.inspector.text_property_changed.connect(self._on_text_property_changed)
        self.inspector.row_property_changed.connect(self._on_row_property_changed)
        self.inspector.project_property_changed.connect(self._on_project_property_changed)
        self.inspector.pip_property_changed.connect(self._on_pip_property_changed)
        self.inspector.pip_delete_requested.connect(self._on_inspector_pip_delete)
        self.inspector.corner_label_changed.connect(self._on_corner_label_changed)
        self.inspector.apply_color_to_group.connect(self._on_apply_color_to_group)
        self.inspector.label_text_changed.connect(self._on_label_text_changed)
        self.inspector.subcell_ratio_changed.connect(self._on_subcell_ratio_changed)
        self.layers_panel.items_selected.connect(self._select_cells_by_ids)
        self.layers_panel.context_menu_requested.connect(self._on_layers_context_menu)

    def _connect_tab_signals(self, tab: ProjectTabState):
        """Connect per-tab scene/view/undostack signals."""
        tab.scene.cell_dropped.connect(self._on_cell_image_dropped)
        tab.scene.pip_image_dropped.connect(self._on_pip_image_dropped)
        tab.scene.cell_swapped.connect(self._on_cell_swapped)
        tab.scene.multi_cells_swapped.connect(self._on_multi_cells_swapped)
        tab.scene.new_image_dropped.connect(self._on_new_image_dropped)
        tab.scene.project_file_dropped.connect(self._on_project_file_dropped)
        tab.scene.text_item_changed.connect(self._on_text_item_drag_changed)
        tab.scene.selection_changed_custom.connect(self._on_scene_selection_changed_custom)
        tab.scene.selectionChanged.connect(self._on_selection_changed)
        tab.scene.cell_context_menu.connect(self._on_cell_context_menu)
        tab.scene.cell_crop_committed.connect(self._on_cell_crop_committed)
        tab.scene.crop_mode_active.connect(self._on_crop_mode_active)
        tab.scene.empty_context_menu.connect(self._on_empty_context_menu)
        tab.scene.nested_layout_open_requested.connect(self._on_open_nested_layout)
        tab.scene.insert_row_requested.connect(self._on_insert_row)
        tab.scene.insert_cell_requested.connect(self._on_insert_cell)
        tab.scene.cell_freeform_geometry_changed.connect(self._on_cell_freeform_geometry_changed)
        tab.scene.divider_drag_finished.connect(self._on_divider_drag_finished)
        tab.scene.pip_geometry_changed.connect(self._on_pip_geometry_changed)
        tab.scene.pip_origin_changed.connect(self._on_pip_origin_changed)
        tab.scene.pip_context_menu.connect(self._on_pip_context_menu)
        tab.scene.pip_removed.connect(self._on_pip_removed)
        tab.view.zoom_changed.connect(self._on_zoom_changed)
        tab.view.mouse_scene_pos_changed.connect(self._on_mouse_pos_changed)
        tab.view.navigate_cell.connect(self._on_navigate_cell)
        tab.view.swap_cell.connect(self._on_swap_cell_direction)
        tab.undo_stack.cleanChanged.connect(self._on_undo_clean_changed)
        tab.undo_stack.canUndoChanged.connect(self._undo_action.setEnabled)
        tab.undo_stack.canRedoChanged.connect(self._redo_action.setEnabled)
        tab.undo_stack.undoTextChanged.connect(self._on_undo_text_changed)
        tab.undo_stack.redoTextChanged.connect(self._on_redo_text_changed)

    def _disconnect_tab_signals(self, tab: ProjectTabState):
        """Disconnect per-tab signals before switching away."""
        try:
            tab.scene.cell_dropped.disconnect(self._on_cell_image_dropped)
            tab.scene.pip_image_dropped.disconnect(self._on_pip_image_dropped)
            tab.scene.cell_swapped.disconnect(self._on_cell_swapped)
            tab.scene.multi_cells_swapped.disconnect(self._on_multi_cells_swapped)
            tab.scene.new_image_dropped.disconnect(self._on_new_image_dropped)
            tab.scene.project_file_dropped.disconnect(self._on_project_file_dropped)
            tab.scene.text_item_changed.disconnect(self._on_text_item_drag_changed)
            tab.scene.selection_changed_custom.disconnect(self._on_scene_selection_changed_custom)
            tab.scene.selectionChanged.disconnect(self._on_selection_changed)
            tab.scene.cell_context_menu.disconnect(self._on_cell_context_menu)
            tab.scene.cell_crop_committed.disconnect(self._on_cell_crop_committed)
            tab.scene.crop_mode_active.disconnect(self._on_crop_mode_active)
            tab.scene.empty_context_menu.disconnect(self._on_empty_context_menu)
            tab.scene.nested_layout_open_requested.disconnect(self._on_open_nested_layout)
            tab.scene.insert_row_requested.disconnect(self._on_insert_row)
            tab.scene.insert_cell_requested.disconnect(self._on_insert_cell)
            tab.scene.cell_freeform_geometry_changed.disconnect(self._on_cell_freeform_geometry_changed)
            tab.scene.divider_drag_finished.disconnect(self._on_divider_drag_finished)
            tab.scene.pip_geometry_changed.disconnect(self._on_pip_geometry_changed)
            tab.scene.pip_origin_changed.disconnect(self._on_pip_origin_changed)
            tab.scene.pip_context_menu.disconnect(self._on_pip_context_menu)
            tab.scene.pip_removed.disconnect(self._on_pip_removed)
            tab.view.zoom_changed.disconnect(self._on_zoom_changed)
            tab.view.mouse_scene_pos_changed.disconnect(self._on_mouse_pos_changed)
            tab.view.navigate_cell.disconnect(self._on_navigate_cell)
            tab.view.swap_cell.disconnect(self._on_swap_cell_direction)
            tab.undo_stack.cleanChanged.disconnect(self._on_undo_clean_changed)
            tab.undo_stack.canUndoChanged.disconnect(self._undo_action.setEnabled)
            tab.undo_stack.canRedoChanged.disconnect(self._redo_action.setEnabled)
            tab.undo_stack.undoTextChanged.disconnect(self._on_undo_text_changed)
            tab.undo_stack.redoTextChanged.disconnect(self._on_redo_text_changed)
        except RuntimeError:
            pass  # already disconnected

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    def _tab_title(self, tab: ProjectTabState) -> str:
        if tab.path:
            return os.path.basename(tab.path)
        return "Untitled"

    def _create_tab(self, project: Project, path: Optional[str] = None) -> ProjectTabState:
        """Create a new tab, add it to the tab widget, and activate it."""
        tab = ProjectTabState(project, path)

        # Apply GPU acceleration if available
        if HAS_OPENGL:
            tab.view.setViewport(QOpenGLWidget())

        # Apply current undo limit from settings
        limit = int(self._settings.value("max_history", 200))
        tab.undo_stack.setUndoLimit(limit)

        # Seed canvas colours with the current theme before any content loads.
        tab.scene.apply_theme(get_tokens(self._current_theme))

        self._tabs.append(tab)
        idx = self.tab_widget.addTab(tab.view, self._tab_title(tab))
        self._activate_tab(idx)
        return tab

    def _activate_tab(self, idx: int):
        """Switch to an existing tab by index."""
        if idx < 0 or idx >= len(self._tabs):
            return

        # Disconnect old tab signals
        if self._active_tab_idx >= 0 and self._active_tab_idx < len(self._tabs):
            self._disconnect_tab_signals(self._tabs[self._active_tab_idx])

        self._active_tab_idx = idx
        tab = self._tabs[idx]

        # Sync main-window attribute references to the new active tab
        self.project = tab.project
        self.undo_stack = tab.undo_stack
        self.scene = tab.scene
        self.view = tab.view
        self._current_project_path = tab.path

        # Wire up new tab's project to the scene (first time only)
        if tab.scene.project is None:
            tab.scene.set_project(tab.project)
            self._ensure_cells_exist()
            tab.scene.set_project(tab.project)

        self._connect_tab_signals(tab)

        # Update shared UI panels
        self.layers_panel.set_project(tab.project)
        self.history_view.setStack(tab.undo_stack)
        self._refresh_and_update()
        self._on_selection_changed()
        self._update_window_title()

        # Sync undo/redo action states for this tab
        self._undo_action.setEnabled(tab.undo_stack.canUndo())
        self._redo_action.setEnabled(tab.undo_stack.canRedo())
        self._on_undo_text_changed(tab.undo_stack.undoText())
        self._on_redo_text_changed(tab.undo_stack.redoText())

        # Sync preview mode toggle to this scene's state
        if hasattr(self, '_act_preview_mode'):
            self._act_preview_mode.setChecked(tab.scene.preview_mode)

        # Make sure the tab widget shows the right index (in case we called
        # _activate_tab directly, not via tab click)
        if self.tab_widget.currentIndex() != idx:
            self.tab_widget.blockSignals(True)
            self.tab_widget.setCurrentIndex(idx)
            self.tab_widget.blockSignals(False)

    def _on_tab_changed(self, idx: int):
        """Slot: user clicked a different tab."""
        if idx < 0 or idx >= len(self._tabs):
            return
        if idx == self._active_tab_idx:
            return
        self._activate_tab(idx)

    def _on_new_tab(self):
        """File > New Tab — opens a blank project in a new tab."""
        project = Project()
        project.rows = [
            RowTemplate(index=0, column_count=2, height_ratio=1.0),
            RowTemplate(index=1, column_count=2, height_ratio=1.0)
        ]
        self._create_tab(project, path=None)

    def _on_close_current_tab(self):
        self._on_close_tab_by_index(self._active_tab_idx)

    def _on_close_tab_by_index(self, idx: int):
        """Close a tab; prompt to save if dirty. Don't close the last tab."""
        if len(self._tabs) <= 1:
            # Last tab: just replace with a blank project instead of closing
            if not self._maybe_save():
                return
            self._on_new_tab()
            # Remove the old tab (now at idx 0 if we're closing idx 0)
            old_idx = 0 if idx == 1 else idx
            self._remove_tab(old_idx)
            return

        # Save the active tab if needed before closing
        if idx == self._active_tab_idx:
            old_project = self.project
            old_stack = self.undo_stack
            if not old_stack.isClean():
                ret = self._ask_unsaved(self._tab_title(self._tabs[idx]))
                if ret == "cancel":
                    return
                if ret == "save":
                    if not self._on_save_project():
                        return
        else:
            tab = self._tabs[idx]
            if not tab.undo_stack.isClean():
                ret = self._ask_unsaved(self._tab_title(tab))
                if ret == "cancel":
                    return
                if ret == "save":
                    # Temporarily activate the tab to save it
                    prev = self._active_tab_idx
                    self._activate_tab(idx)
                    if not self._on_save_project():
                        self._activate_tab(prev)
                        return
                    self._activate_tab(prev)

        self._remove_tab(idx)

    def _remove_tab(self, idx: int):
        """Remove tab at idx without save checks."""
        if idx < 0 or idx >= len(self._tabs):
            return
        tab = self._tabs[idx]
        # Only disconnect if this is the currently-connected (active) tab
        if idx == self._active_tab_idx:
            self._disconnect_tab_signals(tab)
        self._tabs.pop(idx)

        # Block QTabWidget.currentChanged during removeTab(): Qt picks a new
        # current index synchronously and emits currentChanged, which would
        # fire _on_tab_changed -> _activate_tab(new_idx), connecting all
        # per-tab signals. The explicit _activate_tab call below would then
        # connect them a SECOND time, doubling every per-tab signal. The
        # visible symptom was drag-and-drop reopening a .figlayout spawning
        # multiple tabs (one extra tab per past close/reopen cycle).
        self.tab_widget.blockSignals(True)
        self.tab_widget.removeTab(idx)
        self.tab_widget.blockSignals(False)

        # Repoint active index
        if len(self._tabs) == 0:
            self._active_tab_idx = -1
            return
        new_idx = min(idx, len(self._tabs) - 1)
        self._active_tab_idx = -1  # force _activate_tab to reconnect
        self._activate_tab(new_idx)

    def _on_toggle_layers_panel(self):
        sizes = self.splitter.sizes()
        if sizes[0] > 0:
            self._layers_panel_saved_width = sizes[0]
            sizes[1] += sizes[0]
            sizes[0] = 0
            self.splitter.setSizes(sizes)
            self._act_toggle_layers.setChecked(False)
        else:
            w = getattr(self, '_layers_panel_saved_width', 200)
            sizes[1] = max(0, sizes[1] - w)
            sizes[0] = w
            self.splitter.setSizes(sizes)
            self._act_toggle_layers.setChecked(True)

    def _on_toggle_theme(self):
        new_theme = LIGHT if self._current_theme == DARK else DARK
        self._apply_theme(new_theme)

    def _apply_theme(self, theme: str, animate: bool = True):
        if theme == self._current_theme and animate:
            return
        changed = theme != self._current_theme
        self._current_theme = theme
        self._settings.setValue("theme", theme)
        app = QApplication.instance()
        app.setPalette(build_palette(theme))
        app.setStyleSheet(get_stylesheet(theme))
        self.layers_panel.apply_theme(get_tokens(theme))

        # Recolour toolbar icons + segmented glyphs to match the new theme.
        self._refresh_toolbar_icons()

        # Keep the segmented pill in sync when the theme was flipped via
        # keyboard or menu (not by the user clicking the pill itself).
        if hasattr(self, "_theme_segmented"):
            self._theme_segmented.set_theme(theme)

        self._update_theme_labels()

        # Apply canvas visuals (background grid, cell colours) to all scenes.
        tokens = get_tokens(theme)
        for tab in self._tabs:
            if tab.scene:
                tab.scene.apply_theme(tokens)

        if animate and changed:
            self._flash_theme_overlay()

    def _flash_theme_overlay(self) -> None:
        """Brief fade-out overlay to smooth the instant theme colour swap."""
        if not hasattr(self, "_theme_overlay"):
            return
        overlay = self._theme_overlay
        overlay.resize(self.size())
        overlay.raise_()
        overlay.show()
        self._overlay_fx.setOpacity(0.28)

        if self._overlay_anim is not None:
            self._overlay_anim.stop()

        anim = QPropertyAnimation(self._overlay_fx, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.28)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(overlay.hide)
        anim.start()
        self._overlay_anim = anim

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_theme_overlay") and self._theme_overlay.isVisible():
            self._theme_overlay.resize(self.size())

    # ------------------------------------------------------------------
    # Themed toolbar icon helpers
    # ------------------------------------------------------------------

    def _register_themed_action(self, action: QAction, icon_name: str) -> None:
        """Mark ``action`` as owning a themed line icon.

        The actual ``QIcon`` is created now so the action looks correct
        before ``_apply_theme`` runs; subsequent theme changes recolour
        it via ``_refresh_toolbar_icons``.
        """
        self._themed_actions[action] = icon_name
        tokens = get_tokens(self._current_theme)
        action.setIcon(make_icon(icon_name, tokens["text"]))

    def _refresh_toolbar_icons(self) -> None:
        """Rebuild every themed icon using the current theme's palette."""
        tokens = get_tokens(self._current_theme)
        text_col = tokens["text"]
        for action, name in self._themed_actions.items():
            action.setIcon(make_icon(name, text_col))

        # Primary Export button uses on_accent (white-ish) since it sits
        # on the filled accent background.
        if hasattr(self, "_export_button"):
            self._export_button.setIcon(make_icon("export", tokens["on_accent"]))

        # Segmented pill: active glyph picks up accent, idle is text_sec.
        if hasattr(self, "_theme_segmented"):
            self._theme_segmented.refresh_icons(tokens["accent"], tokens["text_sec"])

    def _update_theme_labels(self):
        if self._current_theme == DARK:
            self._theme_action.setText(tr("action_switch_light"))
        else:
            self._theme_action.setText(tr("action_switch_dark"))

    def _on_toggle_language(self):
        new_lang = "zh" if current_language() == "en" else "en"
        set_language(new_lang)
        self._settings.setValue("language", new_lang)
        self.retranslate_ui()

    def _on_toggle_preview_mode(self, checked: bool):
        if self.scene:
            self.scene.set_preview_mode(checked)

    def _on_history_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("history_settings_title"))
        dlg.setFixedWidth(320)
        layout = QFormLayout(dlg)
        spin = QSpinBox()
        spin.setRange(100, 1000)
        spin.setSingleStep(50)
        current_limit = int(self._settings.value("max_history", 200))
        spin.setValue(current_limit if current_limit > 0 else 200)
        layout.addRow(tr("history_settings_label"), spin)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            limit = spin.value()
            self._settings.setValue("max_history", limit)
            for tab in self._tabs:
                tab.undo_stack.setUndoLimit(limit)

    def _on_undo_text_changed(self, text: str):
        prefix = tr("action_undo")
        self._undo_action.setText(f"{prefix} {text}" if text else prefix)

    def _on_redo_text_changed(self, text: str):
        prefix = tr("action_redo")
        self._redo_action.setText(f"{prefix} {text}" if text else prefix)

    def retranslate_ui(self):
        """Update all UI text to the current language."""
        if self.undo_stack:
            self._on_undo_text_changed(self.undo_stack.undoText())
            self._on_redo_text_changed(self.undo_stack.redoText())
        self._file_menu.setTitle(tr("menu_file"))
        self._edit_menu.setTitle(tr("menu_edit"))
        self._layout_menu_ref.setTitle(tr("menu_layout"))
        self._view_menu.setTitle(tr("menu_view"))
        self._help_menu.setTitle(tr("menu_help"))

        self._act_new.setText(tr("action_new"))
        self._act_open.setText(tr("action_open"))
        self._act_save.setText(tr("action_save"))
        self._act_save_as.setText(tr("action_save_as"))
        self._act_import.setText(tr("action_import"))
        self._act_open_grid.setText(tr("action_open_grid"))
        self._act_reload.setText(tr("action_reload"))
        self._act_export_pdf.setText(tr("action_export_pdf"))
        self._act_export_tiff.setText(tr("action_export_tiff"))
        self._act_export_jpg.setText(tr("action_export_jpg"))
        self._act_add_text.setText(tr("action_add_text"))
        self._act_delete_sel.setText(tr("action_delete_sel"))
        self._act_delete_img.setText(tr("action_delete_img"))
        self._act_auto_label_incell.setText(tr("action_auto_label_incell"))
        self._act_auto_label_incell.setToolTip(tr("tooltip_auto_label_incell"))
        self._act_auto_label_outcell.setText(tr("action_auto_label_outcell"))
        self._act_auto_label_outcell.setToolTip(tr("tooltip_auto_label_outcell"))
        self._act_auto_layout.setText(tr("action_auto_layout"))
        self._act_bake.setText(tr("action_bake"))
        self._act_grid_mode.setText(tr("action_grid_mode"))
        self._act_bring_front.setText(tr("action_bring_front"))
        self._act_send_back.setText(tr("action_send_back"))
        self._about_action.setText(tr("action_about"))
        self._help_guide_action.setText(tr("action_user_guide"))
        self._export_button.setText(tr("toolbar_export"))

        # Language toggle shows what you'd switch TO
        self._lang_action.setText(tr("action_switch_zh"))

        self._act_toggle_layers.setText(tr("action_toggle_layers"))
        self._act_preview_mode.setText(tr("action_preview_mode"))
        self._act_history_settings.setText(tr("action_history_settings"))
        self._act_new_tab.setText(tr("action_new_tab"))
        self._act_close_tab.setText(tr("action_close_tab"))
        # Update left-panel tab labels
        self.left_tabs.setTabText(0, tr("tab_layers"))
        self.left_tabs.setTabText(1, tr("tab_history"))
        self._update_theme_labels()
        if hasattr(self, "_theme_segmented"):
            self._theme_segmented.retranslate_ui()
        self.inspector.retranslate_ui()
        self.layers_panel.retranslate_ui()

    def _on_zoom_changed(self, zoom_level):
        self.zoom_label.setText(f"Zoom: {int(zoom_level * 100)}%")

    def _on_mouse_pos_changed(self, x_mm, y_mm):
        self.mouse_pos_label.setText(f"  X {x_mm:.1f},  Y {y_mm:.1f} mm")

    # ------------------------------------------------------------------
    # Cell navigation helpers
    # ------------------------------------------------------------------

    def _cell_path_label(self, cell) -> str:
        """Build a compact hierarchical path label for the status bar.
        
        Top-level cell:          "R0C1"
        Sub-cell (depth 1):      "R0C1 › V1"   (vertical split, child index 1)
        Sub-cell (depth 2):      "R0C1 › V1 › H0"
        """
        # Walk up to build path segments from leaf to root
        segments = []
        current = cell
        parent = self.project.find_parent_of(current.id)
        while parent:
            idx = next((i for i, c in enumerate(parent.children) if c.id == current.id), 0)
            direction_char = "V" if parent.split_direction == "vertical" else "H"
            segments.append(f"{direction_char}{idx + 1}")
            current = parent
            parent = self.project.find_parent_of(current.id)
        # current is now the top-level cell
        root_label = f"R{current.row_index + 1}C{current.col_index + 1}"
        segments.reverse()
        if segments:
            return root_label + " › " + " › ".join(segments)
        return root_label

    def _get_selected_cell(self):
        """Return (cell_model, cell_item) for the single selected cell, or (None, None)."""
        items = self.scene.selectedItems()
        if len(items) != 1:
            return None, None
        item = items[0]
        if not hasattr(item, 'cell_id') or getattr(item, 'is_label_cell', False):
            return None, None
        cell = self.project.find_cell_by_id(item.cell_id)
        return cell, item

    def _find_neighbor_cell(self, cell, direction):
        """Find the neighboring cell in the given direction."""
        row_templates = sorted(self.project.rows, key=lambda r: r.index)
        if direction == "left":
            target_row, target_col = cell.row_index, cell.col_index - 1
        elif direction == "right":
            r = next((r for r in row_templates if r.index == cell.row_index), None)
            max_col = (r.column_count - 1) if r else 0
            target_row = cell.row_index
            target_col = min(cell.col_index + 1, max_col)
        elif direction == "up":
            target_row, target_col = cell.row_index - 1, cell.col_index
        elif direction == "down":
            target_row, target_col = cell.row_index + 1, cell.col_index
        elif direction == "next":
            r = next((r for r in row_templates if r.index == cell.row_index), None)
            max_col = (r.column_count - 1) if r else 0
            if cell.col_index < max_col:
                target_row, target_col = cell.row_index, cell.col_index + 1
            else:
                target_row, target_col = cell.row_index + 1, 0
        elif direction == "prev":
            if cell.col_index > 0:
                target_row, target_col = cell.row_index, cell.col_index - 1
            else:
                prev_row = cell.row_index - 1
                r = next((r for r in row_templates if r.index == prev_row), None)
                if r:
                    target_row, target_col = prev_row, r.column_count - 1
                else:
                    return None
        else:
            return None

        return next((c for c in self.project.cells
                     if c.row_index == target_row and c.col_index == target_col), None)

    def _select_cells_by_ids(self, cell_ids: list):
        """Select one or more cells on the canvas by their IDs. Also handles pip_ids from layers panel."""
        # Check if these are pip IDs (not cell IDs)
        if len(cell_ids) == 1:
            pip_id = cell_ids[0]
            for cell in self.project.get_all_leaf_cells():
                pip = next((p for p in getattr(cell, 'pip_items', []) if p.id == pip_id), None)
                if pip:
                    cell_item = self.scene.cell_items.get(cell.id)
                    if cell_item:
                        cell_item.select_pip(pip_id)
                        self.view.centerOn(cell_item)
                    return

        self.scene.blockSignals(True)
        self.scene.clearSelection()
        first_item = None
        for cell_id in cell_ids:
            item = self.scene.cell_items.get(cell_id)
            if item:
                item.setSelected(True)
                if first_item is None:
                    first_item = item
        self.scene.blockSignals(False)
        self._on_selection_changed()  # sync inspector once
        if first_item:
            self.view.centerOn(first_item)

    def _on_navigate_cell(self, direction):
        cell, _ = self._get_selected_cell()
        if not cell:
            # If nothing selected, select the first cell
            if self.project.cells:
                first = sorted(self.project.cells, key=lambda c: (c.row_index, c.col_index))[0]
                self._select_cells_by_ids([first.id])
            return
        neighbor = self._find_neighbor_cell(cell, direction)
        if neighbor:
            self._select_cells_by_ids([neighbor.id])

    def _on_swap_cell_direction(self, direction):
        cell, _ = self._get_selected_cell()
        if not cell:
            return
        neighbor = self._find_neighbor_cell(cell, direction)
        if neighbor and neighbor.id != cell.id:
            cmd = SwapCellsCommand(cell, neighbor, self._refresh_and_update)
            self.undo_stack.push(cmd)
            # Keep the moved cell selected
            self._select_cells_by_ids([cell.id])

    def _ensure_cells_exist(self):
        # Simple logic: ensure every slot in defined rows has a cell
        # Remove cells that are out of bounds
        
        # 1. Keep valid cells
        valid_cells = []
        existing_map = {} # (row, col) -> cell
        
        for c in self.project.cells:
            # Check if row exists
            row_temp = next((r for r in self.project.rows if r.index == c.row_index), None)
            if row_temp and c.col_index < row_temp.column_count:
                valid_cells.append(c)
                existing_map[(c.row_index, c.col_index)] = c
        
        self.project.cells = valid_cells
        
        # 2. Add missing cells
        for r in self.project.rows:
            for col_idx in range(r.column_count):
                if (r.index, col_idx) not in existing_map:
                    new_cell = Cell(row_index=r.index, col_index=col_idx, is_placeholder=True)
                    self.project.cells.append(new_cell)

    def _refresh_and_update(self):
        self.scene.refresh_layout()
        self.layers_panel.set_project(self.project)
        # Update Canvas Size Label
        rect = self.scene.sceneRect()
        self.canvas_size_label.setText(f"Canvas: {int(rect.width())}x{int(rect.height())}")
        # Re-sync inspector so pip/cell spinboxes reflect any model changes
        self._on_selection_changed()
        
        # Check for low-res images

    def _on_undo_clean_changed(self, clean: bool):
        self.setWindowModified(not clean)
        self._update_window_title()
        # Reflect dirty state in tab title
        if 0 <= self._active_tab_idx < len(self._tabs):
            tab = self._tabs[self._active_tab_idx]
            title = self._tab_title(tab)
            if not clean:
                title += " •"
            self.tab_widget.setTabText(self._active_tab_idx, title)

    def _update_window_title(self):
        if self._current_project_path:
            name = os.path.basename(self._current_project_path)
        else:
            name = "Untitled"
        self.setWindowTitle(f"Academic Figure Layout v{self._app_version} - {name}[*]")

    def _mark_dirty(self):
        if self.undo_stack.isClean():
            self.setWindowModified(True)

    def _ask_unsaved(self, name: str) -> str:
        """Show translated Save/Discard/Cancel dialog. Returns 'save', 'discard', or 'cancel'."""
        box = QMessageBox(self)
        box.setWindowTitle(tr("dlg_unsaved_title"))
        box.setText(tr("dlg_unsaved_body").format(name=name))
        box.setIcon(QMessageBox.Icon.Question)
        save_btn    = box.addButton(tr("btn_save"),    QMessageBox.ButtonRole.AcceptRole)
        discard_btn = box.addButton(tr("btn_discard"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("btn_cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_btn:
            return "save"
        if clicked is discard_btn:
            return "discard"
        return "cancel"

    def _maybe_save(self) -> bool:
        """Check active tab for unsaved changes; returns True if safe to proceed."""
        if self.undo_stack is None or self.undo_stack.isClean():
            return True
        tab = self._tabs[self._active_tab_idx]
        ret = self._ask_unsaved(self._tab_title(tab))
        if ret == "save":
            return self._on_save_project()
        if ret == "discard":
            return True
        return False

    def _set_project(self, project: Project, path: Optional[str] = None):
        """Replace the active tab's project (e.g. on open/new)."""
        tab = self._tabs[self._active_tab_idx]
        tab.project = project
        tab.path = path
        self.project = project
        self._current_project_path = path

        self._ensure_cells_exist()
        self.scene.set_project(self.project)
        self.undo_stack.clear()
        self.setWindowModified(False)
        self._update_window_title()
        self._refresh_and_update()
        self._check_image_resolution()
        self._on_selection_changed()

        # Update tab title
        self.tab_widget.setTabText(self._active_tab_idx, self._tab_title(tab))

    def open_file_from_cli(self, path: str):
        """Open a .figlayout file supplied as a command-line argument at startup.

        Called by main.py before the window is shown, so the initial blank tab
        is still clean and untitled — we simply replace it.
        """
        try:
            project = Project.load_from_file(path)
            self._set_project(project, path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open '{os.path.basename(path)}':\n{e}")

    def _build_project_from_images(self, paths):
        project = Project()

        n = len(paths)
        if n <= 0:
            return project

        cols = int(math.ceil(math.sqrt(n)))
        rows = int(math.ceil(n / cols))

        project.rows = [RowTemplate(index=i, column_count=cols, height_ratio=1.0) for i in range(rows)]
        project.cells = []

        idx = 0
        for r in range(rows):
            for c in range(cols):
                cell = Cell(row_index=r, col_index=c, is_placeholder=True)
                if idx < n:
                    cell.image_path = paths[idx]
                    cell.is_placeholder = False
                project.cells.append(cell)
                idx += 1

        return project

    def _check_image_resolution(self):
        """Check if any images are too low resolution for the target DPI"""
        from src.model.layout_engine import LayoutEngine
        from PIL import Image
        import os
        
        warnings = []
        layout = LayoutEngine.calculate_layout(self.project)
        dpi = self.project.dpi
        
        # Guideline 9.4: enforce minimum pixels on the *shorter axis*.
        # To avoid noisy warnings, only warn when the implied upscale factor exceeds this.
        upscale_warn_threshold = 1.2

        for cell in self.project.cells:
            if not cell.image_path or cell.is_placeholder:
                continue
            if not os.path.exists(cell.image_path):
                continue
            if cell.id not in layout.cell_rects:
                continue

            x, y, w_mm, h_mm = layout.cell_rects[cell.id]
            required_w = (w_mm / 25.4) * dpi
            required_h = (h_mm / 25.4) * dpi
            required_short = min(required_w, required_h)

            try:
                with Image.open(cell.image_path) as img:
                    actual_w, actual_h = img.size
            except Exception:
                continue

            actual_short = min(actual_w, actual_h)
            if actual_short <= 0 or required_short <= 0:
                continue

            upscale_factor = required_short / actual_short
            if upscale_factor > upscale_warn_threshold:
                warnings.append(f"Cell({cell.row_index},{cell.col_index})")
        
        if warnings:
            self.statusbar.showMessage(f"⚠ Low-res images: {', '.join(warnings[:3])}{'...' if len(warnings) > 3 else ''}", 5000)
        else:
            self.statusbar.clearMessage()

    def _on_row_count_changed(self, count):
        # Prevent loop if change comes from undo/redo
        if len(self.project.rows) == count:
            return
            
        cmd = ChangeRowCountCommand(self.project, count, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_cell_image_dropped(self, cell_id, file_path):
        cell = self.project.find_cell_by_id(cell_id)
        if cell:
            cmd = DropImageCommand(cell, file_path, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_pip_image_dropped(self, cell_id: str, file_path: str):
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return
        pip = PiPItem(pip_type="external", image_path=file_path, show_origin_box=False)
        cmd = AddPiPItemCommand(cell, pip, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_pip_geometry_changed(self, cell_id: str, pip_id: str, old_geom, new_geom):
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return
        pip = next((p for p in cell.pip_items if p.id == pip_id), None)
        if pip:
            cmd = SetPiPGeometryCommand(pip, old_geom, new_geom, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_pip_origin_changed(self, cell_id: str, pip_id: str, old_crop, new_crop):
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return
        pip = next((p for p in cell.pip_items if p.id == pip_id), None)
        if pip:
            cmd = SetPiPOriginCommand(pip, old_crop, new_crop, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _ctx_remove_pip(self, cell_id: str, pip):
        from src.app.commands import RemovePiPItemCommand
        cell = self.project.find_cell_by_id(cell_id)
        if cell:
            cmd = RemovePiPItemCommand(cell, pip, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_inspector_pip_delete(self):
        """Inspector 'Delete PiP' button pressed — forward to _on_pip_removed."""
        if not self.scene:
            return
        items = self.scene.selectedItems()
        if not items:
            return
        item = items[0]
        cell_id = getattr(item, 'cell_id', None)
        pip_id = getattr(item, '_selected_pip_id', None)
        if cell_id and pip_id:
            self._on_pip_removed(cell_id, pip_id)

    def _on_pip_removed(self, cell_id: str, pip_id: str):
        """Handle Delete key press or Inspector delete button for selected PiP."""
        from src.app.commands import RemovePiPItemCommand
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return
        pip = next((p for p in getattr(cell, 'pip_items', []) if p.id == pip_id), None)
        if pip:
            cmd = RemovePiPItemCommand(cell, pip, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_pip_context_menu(self, cell_id: str, pip_id: str, screen_pos):
        from PyQt6.QtCore import QPoint
        from PyQt6.QtWidgets import QMenu
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return
        pip = next((p for p in cell.pip_items if p.id == pip_id), None)
        if not pip:
            return

        cell_item = self.scene.cell_items.get(cell_id)

        menu = QMenu(self)

        resize_act = menu.addAction(tr("pip_ctx_resize"))
        resize_act.triggered.connect(
            lambda: cell_item.select_pip(pip_id, resize=True) if cell_item else None
        )

        menu.addSeparator()

        remove_act = menu.addAction(tr("pip_ctx_remove"))
        remove_act.triggered.connect(lambda: self._ctx_remove_pip(cell_id, pip))

        menu.exec(QPoint(int(screen_pos.x()), int(screen_pos.y())))

    def _on_new_image_dropped(self, file_path, x, y):
        # Find first placeholder
        target_cell = None
        for cell in self.project.get_all_leaf_cells():
            if cell.is_placeholder:
                target_cell = cell
                break
        
        if target_cell:
            cmd = DropImageCommand(target_cell, file_path, self._refresh_and_update)
            self.undo_stack.push(cmd)
        else:
            print("No placeholder available for new image")

    def _on_cell_swapped(self, id1, id2):
        c1 = self.project.find_cell_by_id(id1)
        c2 = self.project.find_cell_by_id(id2)
        
        if c1 and c2:
            cmd = SwapCellsCommand(c1, c2, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_multi_cells_swapped(self, source_ids, target_ids):
        sources = [self.project.find_cell_by_id(sid) for sid in source_ids]
        targets = [self.project.find_cell_by_id(tid) for tid in target_ids]
        if all(sources) and all(targets) and len(sources) == len(targets):
            cmd = MultiSwapCellsCommand(sources, targets, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_insert_row(self, insert_index):
        # Default to 2 columns for new rows (matching ChangeRowCountCommand default)
        cmd = InsertRowCommand(self.project, insert_index, column_count=2,
                               update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_insert_cell(self, row_index, insert_col):
        cmd = InsertCellCommand(self.project, row_index, insert_col,
                                update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_delete_row(self, row_index):
        if len(self.project.rows) <= 1:
            return
        cmd = DeleteRowCommand(self.project, row_index,
                               update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_delete_cell(self, row_index, col_index):
        row = next((r for r in self.project.rows if r.index == row_index), None)
        if not row or row.column_count <= 1:
            return
        cmd = DeleteCellCommand(self.project, row_index, col_index,
                                update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_selection_changed(self):
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return  # Scene was deleted
        if not items:
            self.selection_info_label.setText("")
            self.inspector.set_selection(None, self.project.to_dict())
            self.layers_panel.select_item(None)
            return

        # Status bar: selection info
        cell_items = [i for i in items if hasattr(i, 'cell_id') and not getattr(i, 'is_label_cell', False)]
        if len(cell_items) > 1:
            self.selection_info_label.setText(f"  {len(cell_items)} cells selected")
        elif len(cell_items) == 1:
            ci = cell_items[0]
            cell = self.project.find_cell_by_id(ci.cell_id)
            if cell:
                info = f"  {self._cell_path_label(cell)}"
                if cell.image_path and not cell.is_placeholder:
                    info += f"  |  {os.path.basename(cell.image_path)}"
                self.selection_info_label.setText(info)
            else:
                self.selection_info_label.setText("")
        else:
            self.selection_info_label.setText("")

        # Multi-cell selection
        if len(cell_items) > 1:
            first_cell = self.project.find_cell_by_id(cell_items[0].cell_id)
            multi_data = {"count": len(cell_items), "layout_mode": getattr(self.project, 'layout_mode', 'grid')}
            if first_cell:
                multi_data.update({
                    "fit_mode": first_cell.fit_mode,
                    "rotation": getattr(first_cell, 'rotation', 0),
                    "padding_top": first_cell.padding_top,
                    "padding_bottom": first_cell.padding_bottom,
                    "padding_left": first_cell.padding_left,
                    "padding_right": first_cell.padding_right,
                })
            self.inspector.set_selection('multi_cell', multi_data)
            return

        item = items[0]
        
        if hasattr(item, 'cell_id'):
            # If a PiP inset inside this cell is selected, PiP becomes the
            # effective selection target for layers highlight + inspector.
            selected_pip_id = getattr(item, '_selected_pip_id', None)
            if selected_pip_id:
                self.layers_panel.select_item(selected_pip_id)
                cell = self.project.find_cell_by_id(item.cell_id)
                if cell:
                    pip = next((p for p in getattr(cell, 'pip_items', []) if p.id == selected_pip_id), None)
                    if pip:
                        self.inspector.set_selection('pip', pip.to_dict())
                        return

            self.layers_panel.select_item(item.cell_id)
            # Check if it's a label cell (id starts with "label_")
            if hasattr(item, 'is_label_cell') and item.is_label_cell:
                # Find the corresponding text item for this label cell
                parent_cell_id = item.cell_id.removeprefix("label_")
                text_obj = next(
                    (t for t in self.project.text_items
                     if t.scope == "cell" and t.subtype != "corner" and t.parent_id == parent_cell_id),
                    None
                )
                label_data = {
                    "text_item_id": text_obj.id if text_obj else None,
                    "label_text": text_obj.text if text_obj else "",
                    "label_scheme": self.project.label_scheme,
                    "label_font_family": self.project.label_font_family,
                    "label_font_size": self.project.label_font_size,
                    "label_font_weight": self.project.label_font_weight,
                    "label_color": self.project.label_color,
                    "label_align": self.project.label_align,
                    "label_offset_x": self.project.label_offset_x,
                    "label_offset_y": self.project.label_offset_y,
                    "label_row_height": getattr(self.project, 'label_row_height', 0.0),
                }
                self.inspector.set_selection('label_cell', label_data)
                return

            cell = self.project.find_cell_by_id(item.cell_id)
            if cell:
                # Find the top-level cell to get row data
                top_cell = cell
                parent = self.project.find_parent_of(cell.id)
                while parent:
                    top_cell = parent
                    parent = self.project.find_parent_of(parent.id)

                # Find Row Data from top-level cell
                row = next((r for r in self.project.rows if r.index == top_cell.row_index), None)
                row_data = row.to_dict() if row else None

                # Populate corner label fields from existing cell-scoped text items
                cell_dict = cell.to_dict()
                cell_dict["layout_mode"] = getattr(self.project, 'layout_mode', 'grid')
                corner_labels = {}
                for t in self.project.text_items:
                    if t.scope == "cell" and t.parent_id == cell.id and t.anchor:
                        corner_labels[t.anchor] = t.text
                cell_dict["corner_labels"] = corner_labels

                # Sub-cell info: if this cell has a parent split container, provide ratio data
                cell_parent = self.project.find_parent_of(cell.id)
                if cell_parent and cell_parent.split_direction != "none":
                    idx = next((i for i, c in enumerate(cell_parent.children) if c.id == cell.id), 0)
                    ratios = cell_parent.split_ratios if cell_parent.split_ratios else [1.0] * len(cell_parent.children)
                    while len(ratios) < len(cell_parent.children):
                        ratios.append(1.0)
                    cell_dict["_subcell"] = {
                        "cell_id": cell.id,
                        "direction": cell_parent.split_direction,
                        "sibling_count": len(cell_parent.children),
                        "sibling_index": idx,
                        "ratio": ratios[idx] if idx < len(ratios) else 1.0,
                        "override_width_mm": getattr(cell, 'override_width_mm', 0.0),
                        "override_height_mm": getattr(cell, 'override_height_mm', 0.0),
                    }

                self.inspector.set_selection('cell', cell_dict, row_data)
                return
                
        if hasattr(item, 'text_item_id'):
             text = next((t for t in self.project.text_items if t.id == item.text_item_id), None)
             if text:
                 self.inspector.set_selection('text', text.to_dict())
                 return
                 
        self.inspector.set_selection(None, self.project.to_dict())

    def _on_scene_selection_changed_custom(self, _ids: list):
        """Scene-level custom selection updates (PiP select/deselect)."""
        self._on_selection_changed()

    def _on_cell_property_changed(self, changes):
        items = self.scene.selectedItems()
        if not items:
            return
        
        # Collect all selected cells
        selected_cells = []
        for item in items:
            if hasattr(item, 'cell_id'):
                cell = self.project.find_cell_by_id(item.cell_id)
                if cell:
                    selected_cells.append(cell)
        
        if not selected_cells:
            return
        
        # Apply changes to all selected cells
        if len(selected_cells) == 1:
            cmd = PropertyChangeCommand(selected_cells[0], changes, self._refresh_and_update, "Change Cell Property")
        else:
            cmd = MultiPropertyChangeCommand(selected_cells, changes, self._refresh_and_update, f"Change {len(selected_cells)} Cells")
        self.undo_stack.push(cmd)

    def _on_pip_property_changed(self, changes: dict):
        """Apply inspector changes to the currently-selected PiP inset."""
        if not self.scene:
            return
        items = self.scene.selectedItems()
        if not items:
            return
        item = items[0]
        cell_id = getattr(item, 'cell_id', None)
        pip_id = getattr(item, '_selected_pip_id', None)
        if not cell_id or not pip_id:
            return

        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return
        pip = next((p for p in getattr(cell, 'pip_items', []) if p.id == pip_id), None)
        if not pip:
            return

        cmd = PropertyChangeCommand(pip, changes, self._refresh_and_update, "Change PiP Property")
        self.undo_stack.push(cmd)

    def _on_corner_label_changed(self, payload: dict):
        """Create/update/delete a corner label (cell-scoped anchored TextItem) for the selected cell."""
        items = self.scene.selectedItems()
        if not items or not hasattr(items[0], 'cell_id'):
            return

        cell_id = items[0].cell_id
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return

        anchor = payload.get("anchor")
        text = (payload.get("text") or "").strip()
        if not anchor:
            return

        existing = next(
            (
                t for t in self.project.text_items
                if t.scope == "cell" and t.parent_id == cell.id and t.anchor == anchor
            ),
            None
        )

        # Empty text means delete the label if it exists
        if text == "":
            if existing:
                cmd = DeleteTextCommand(self.project, existing, self._refresh_and_update)
                self.undo_stack.push(cmd)
            return

        # Otherwise create or update
        if existing:
            cmd = PropertyChangeCommand(existing, {"text": text}, self._refresh_and_update, "Edit Corner Label")
            self.undo_stack.push(cmd)
        else:
            from src.model.data_model import TextItem
            item = TextItem(
                text=text,
                font_family=self.project.corner_label_font_family,
                font_size_pt=self.project.corner_label_font_size,
                font_weight=self.project.corner_label_font_weight,
                color=self.project.corner_label_color,
                scope="cell",
                subtype="corner",
                parent_id=cell.id,
                anchor=anchor,
                offset_x=2.0,
                offset_y=2.0,
            )
            cmd = AddTextCommand(self.project, item, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_label_text_changed(self, text_item_id: str, new_text: str):
        """Handle label text edit from the Label Cell Settings panel."""
        text_obj = next((t for t in self.project.text_items if t.id == text_item_id), None)
        if not text_obj:
            return
        cmd = PropertyChangeCommand(text_obj, {"text": new_text}, self._refresh_and_update, "Edit Label Text")
        self.undo_stack.push(cmd)

    def _on_text_property_changed(self, changes):
        items = self.scene.selectedItems()
        if not items or not hasattr(items[0], 'text_item_id'):
            return
            
        text_id = items[0].text_item_id
        text_obj = next((t for t in self.project.text_items if t.id == text_id), None)
        
        if not text_obj:
            return

        style_keys = {"font_family", "font_size_pt", "font_weight"}
        style_changes = {k: v for k, v in changes.items() if k in style_keys}
        other_changes = {k: v for k, v in changes.items() if k not in style_keys}

        # Cell-scoped labels: style edits propagate globally to the project's label style settings.
        if text_obj.scope == "cell" and style_changes:
            project_style_changes = {}

            prefix = "label_"
            if text_obj.subtype == "corner":
                prefix = "corner_label_"

            if "font_family" in style_changes:
                project_style_changes[f"{prefix}font_family"] = style_changes["font_family"]
            if "font_size_pt" in style_changes:
                project_style_changes[f"{prefix}font_size"] = style_changes["font_size_pt"]
            if "font_weight" in style_changes:
                project_style_changes[f"{prefix}font_weight"] = style_changes["font_weight"]

            if project_style_changes:
                callback = self._refresh_and_sync_labels
                if text_obj.subtype == "corner":
                    callback = self._refresh_and_sync_corner_labels
                cmd = PropertyChangeCommand(
                    self.project, project_style_changes, callback, "Change Label Style"
                )
                self.undo_stack.push(cmd)

        # Floating (global) text items: style changes apply directly to the item.
        elif text_obj.scope == "global" and style_changes:
            cmd = PropertyChangeCommand(text_obj, style_changes, self._refresh_and_update, "Change Text Style")
            self.undo_stack.push(cmd)

        # Non-style changes (color, position, content, etc.) always apply per-item.
        if other_changes:
            cmd = PropertyChangeCommand(text_obj, other_changes, self._refresh_and_update, "Change Text Property")
            self.undo_stack.push(cmd)

    def _on_text_item_drag_changed(self, text_item_id: str, changes: dict):
        """Handle text item changes from dragging or inline editing"""
        text_obj = next((t for t in self.project.text_items if t.id == text_item_id), None)
        if text_obj:
            cmd = PropertyChangeCommand(text_obj, changes, self._refresh_and_update, "Move/Edit Text")
            self.undo_stack.push(cmd)

    def _on_row_property_changed(self, changes):
        items = self.scene.selectedItems()
        if not items or not hasattr(items[0], 'cell_id'):
            return
            
        cell_id = items[0].cell_id
        cell = self.project.find_cell_by_id(cell_id)
        
        if cell:
            row = next((r for r in self.project.rows if r.index == cell.row_index), None)
            if row:
                # Special handling for column count which requires logic
                # For now, let's treat column count change as a PropertyChangeCommand? 
                # No, column count change requires ensuring cells.
                # So we should separate simple property changes from structural changes.
                
                if "column_count" in changes:
                    # Not fully implemented in commands yet for this specific path
                    # Let's fallback to direct set for complex logic or implement a Command.
                    # Since ChangeRowCountCommand does row additions, Column count is different.
                    # We need a ChangeRowColumnsCommand. 
                    # For v1, let's just do it directly without undo for this specific complex property, 
                    # OR use PropertyChangeCommand but add a callback that handles the restructuring.
                    
                    # We'll do direct execution for now to avoid complexity in this step
                    # OR better: use PropertyChangeCommand and in the callback, check structure.
                    
                    # But PropertyChangeCommand.undo needs to restore cells if they were deleted.
                    # Simple property change is insufficient for column count.
                    pass 
                
                cmd = PropertyChangeCommand(row, changes, self._handle_row_change_callback, "Change Row Property")
                self.undo_stack.push(cmd)

    def _handle_row_change_callback(self):
        # Check if we need to restructure
        self._ensure_cells_exist() # This handles column count changes safely
        self._refresh_and_update()

    def _on_project_property_changed(self, changes):
        # We need to handle PageSizePreset conversion for the command to work if we pass raw dict
        # or do it inside the command. PropertyChangeCommand simply sets attributes.
        # So we should convert values before passing to command if needed.

        if "label_scheme" in changes:
            cmd = ChangeLabelSchemeCommand(self.project, changes["label_scheme"], self._refresh_and_update)
            self.undo_stack.push(cmd)
            return

        processed_changes = {}
        for k, v in changes.items():
            if k == "page_size_preset":
                processed_changes[k] = PageSizePreset(v)
            else:
                processed_changes[k] = v
        
        # Check if label font parameters are being changed (excluding color - that's per-label now)
        label_props = {"label_font_family", "label_font_size", "label_font_weight"}
        is_label_change = bool(label_props & set(changes.keys()))

        corner_label_props = {"corner_label_font_family", "corner_label_font_size", "corner_label_font_weight", "corner_label_color"}
        is_corner_label_change = bool(corner_label_props & set(changes.keys()))
        
        if is_label_change:
            # Use callback that also syncs label styles
            cmd = PropertyChangeCommand(self.project, processed_changes, self._refresh_and_sync_labels, "Change Label Settings")
        elif is_corner_label_change:
            cmd = PropertyChangeCommand(self.project, processed_changes, self._refresh_and_sync_corner_labels, "Change Corner Label Settings")
        else:
            cmd = PropertyChangeCommand(self.project, processed_changes, self._refresh_and_update, "Change Project Settings")
        
        self.undo_stack.push(cmd)

    def _refresh_and_sync_labels(self):
        """Refresh and also sync all cell-scoped labels (numbering) to project label settings (excluding color)"""
        for text_item in self.project.text_items:
            # Sync if it's cell-scoped and NOT explicitly a corner label
            if text_item.scope == "cell" and text_item.subtype != "corner":
                text_item.font_family = self.project.label_font_family
                text_item.font_size_pt = self.project.label_font_size
                text_item.font_weight = self.project.label_font_weight
                # Color is now per-label, not auto-synced
        self._refresh_and_update()

    def _refresh_and_sync_corner_labels(self):
        """Refresh and also sync all cell-scoped corner labels to project settings."""
        for text_item in self.project.text_items:
            if text_item.scope == "cell" and text_item.subtype == "corner":
                text_item.font_family = self.project.corner_label_font_family
                text_item.font_size_pt = self.project.corner_label_font_size
                text_item.font_weight = self.project.corner_label_font_weight
                text_item.color = self.project.corner_label_color
        self._refresh_and_update()

    def _on_apply_color_to_group(self, subtype: str, color_hex: str):
        """Apply color to all labels in the same group (numbering or corner)
        as an undoable operation."""
        targets = []
        for text_item in self.project.text_items:
            if text_item.scope != "cell":
                continue
            if subtype == "corner" and text_item.subtype == "corner":
                targets.append(text_item)
            elif subtype == "numbering" and text_item.subtype != "corner":
                targets.append(text_item)

        if not targets:
            return

        # Skip no-ops: all targets already have this color.
        if all(t.color == color_hex for t in targets):
            return

        desc = f"Apply color to {len(targets)} {subtype} label(s)"
        cmd = MultiPropertyChangeCommand(
            targets,
            {"color": color_hex},
            self._refresh_and_update,
            desc,
        )
        self.undo_stack.push(cmd)

    def _on_add_text(self):
        """Create a floating (canvas-anchored) text item. Position is in mm,
        absolute to canvas (0,0), so it survives page/DPI changes."""
        # Default near top-left inside the content margins, stagger each add
        # so consecutive items don't pile up on top of each other.
        base_x = float(getattr(self.project, "margin_left_mm", 10.0)) + 2.0
        base_y = float(getattr(self.project, "margin_top_mm", 10.0)) + 2.0
        existing_floating = sum(
            1 for t in self.project.text_items if t.scope == "global"
        )
        stagger = 4.0  # mm
        item = TextItem(
            text="Text",
            x=base_x + existing_floating * stagger,
            y=base_y + existing_floating * stagger,
            scope="global",
            rotation=0.0,
        )
        cmd = AddTextCommand(self.project, item, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_delete_text(self):
        """Delete selected text item(s), label cell numbering labels, or cell images."""
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return
        
        from src.canvas.cell_item import CellItem

        handled = False
        for item in items:
            if hasattr(item, 'text_item_id'):
                text_obj = next((t for t in self.project.text_items if t.id == item.text_item_id), None)
                if text_obj:
                    cmd = DeleteTextCommand(self.project, text_obj, self._refresh_and_update)
                    self.undo_stack.push(cmd)
                    handled = True
            elif isinstance(item, CellItem) and item.is_label_cell:
                # Label cell ID is "label_{cell_id}" — extract the parent cell_id
                parent_cell_id = item.cell_id.removeprefix("label_")
                text_obj = next(
                    (t for t in self.project.text_items
                     if t.scope == "cell" and t.subtype != "corner" and t.parent_id == parent_cell_id),
                    None
                )
                if text_obj:
                    cmd = DeleteTextCommand(self.project, text_obj, self._refresh_and_update)
                    self.undo_stack.push(cmd)
                    handled = True

        # If nothing text-like was deleted but regular cells are selected, delete their images
        if not handled:
            self._on_delete_image()

    def _on_delete_image(self):
        """Delete image from selected cell(s)"""
        try:
            items = self.scene.selectedItems()
        except RuntimeError:
            return

        from src.canvas.cell_item import CellItem

        selected_cells = [it for it in items if isinstance(it, CellItem)]
        if not selected_cells:
            return

        # One command per cell (keeps undo/redo consistent with existing commands)
        for cell_item in selected_cells:
            cell = self.project.find_cell_by_id(cell_item.cell_id)
            if not cell:
                continue
            if cell.is_placeholder and not cell.image_path:
                continue

            cmd = PropertyChangeCommand(
                cell,
                {"image_path": None, "is_placeholder": True},
                self._refresh_and_update,
                "Delete Image",
            )
            self.undo_stack.push(cmd)

    def _on_layers_context_menu(self, cell_ids: list, global_pos):
        """Right-click context menu from the layers panel tree.

        The layers panel emits raw IDs which may belong to cells, PiP
        insets, or text items — we resolve the kind here and dispatch
        to the matching menu.
        """
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtCore import QPoint

        if not cell_ids:
            return

        if len(cell_ids) == 1:
            target_id = cell_ids[0]

            # PiP items don't live in project.cells, so find_cell_by_id
            # returns None. Scan every leaf cell's pip_items to find the
            # owner and delegate to the PiP-specific menu.
            for cell in self.project.get_all_leaf_cells():
                pip = next(
                    (p for p in getattr(cell, "pip_items", []) if p.id == target_id),
                    None,
                )
                if pip:
                    self._on_pip_context_menu(cell.id, pip.id, global_pos)
                    return

            self._on_cell_context_menu(target_id, False, global_pos)
            return

        menu = QMenu(self)

        cells = [self.project.find_cell_by_id(cid) for cid in cell_ids]
        cells = [c for c in cells if c]

        cells_with_images = [c for c in cells if c.image_path and not c.is_placeholder]
        if cells_with_images:
            def _del_images():
                from src.app.commands import MultiPropertyChangeCommand
                for c in cells_with_images:
                    cmd = PropertyChangeCommand(
                        c, {"image_path": None, "is_placeholder": True},
                        None, "Delete Image"
                    )
                    self.undo_stack.push(cmd)
                self._refresh_and_update()
            act = menu.addAction(f"Delete Images ({len(cells_with_images)} cells)")
            act.triggered.connect(_del_images)
            menu.addSeparator()

        # Label operations
        labeled = [
            c for c in cells
            if any(t for t in self.project.text_items
                   if t.scope == "cell" and t.subtype != "corner" and t.parent_id == c.id)
        ]
        unlabeled = [c for c in cells if c not in labeled]

        if unlabeled:
            def _add_labels():
                for c in unlabeled:
                    self._ctx_add_numbering_label(c.id)
            act = menu.addAction(tr("ctx_add_label_cell_n").format(n=len(unlabeled)))
            act.triggered.connect(_add_labels)

        if labeled:
            def _del_labels():
                for c in labeled:
                    self._ctx_delete_numbering_label(c.id)
            act = menu.addAction(tr("ctx_delete_label_cell_n").format(n=len(labeled)))
            act.triggered.connect(_del_labels)

        # Delete rows/columns for the selected cells
        menu.addSeparator()
        top_cells = []
        seen_ids = set()
        for c in cells:
            top = c
            par = self.project.find_parent_of(c.id)
            while par:
                top = par
                par = self.project.find_parent_of(par.id)
            if top.id not in seen_ids:
                top_cells.append(top)
                seen_ids.add(top.id)

        row_indices = sorted({c.row_index for c in top_cells})
        col_indices = sorted({(c.row_index, c.col_index) for c in top_cells})

        if len(row_indices) > 0 and len(self.project.rows) > len(row_indices):
            def _del_rows():
                for ri in sorted(row_indices, reverse=True):
                    self._on_delete_row(ri)
            act = menu.addAction(f"Delete {len(row_indices)} Row(s)")
            act.triggered.connect(_del_rows)

        def _show():
            menu.exec(global_pos if isinstance(global_pos, QPoint) else
                      QPoint(int(global_pos.x()), int(global_pos.y())))
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, _show)

    def _on_empty_context_menu(self, scene_pos, screen_pos):
        """Right-click on empty canvas area (page background or grey margin).

        The menu is deferred to the next event-loop tick via QTimer.singleShot(0)
        so the synchronous contextMenuEvent handler in CanvasScene finishes and
        the right-click event is fully consumed BEFORE the nested menu loop
        begins. Otherwise Qt can re-dispatch the event after the menu closes,
        causing the context menu to pop up a second time.
        """
        from PyQt6.QtCore import QPoint
        # Clamp the spawn position to the page rect so the new text is always visible.
        page_w = float(getattr(self.project, "page_width_mm", 210.0))
        page_h = float(getattr(self.project, "page_height_mm", 297.0))
        x_mm = max(0.0, min(float(scene_pos.x()), page_w - 5.0))
        y_mm = max(0.0, min(float(scene_pos.y()), page_h - 5.0))
        sx, sy = int(screen_pos.x()), int(screen_pos.y())

        def _show():
            menu = QMenu(self)

            # ── Text ──────────────────────────────────────────────────────
            add_action = menu.addAction(tr("ctx_add_floating_text_here"))
            add_action.triggered.connect(lambda: self._ctx_add_floating_text_at(x_mm, y_mm))

            # ── Export ────────────────────────────────────────────────────
            menu.addSeparator()
            menu.addAction(self._act_export_pdf)
            menu.addAction(self._act_export_tiff)
            menu.addAction(self._act_export_jpg)

            # ── Undo / Redo ───────────────────────────────────────────────
            menu.addSeparator()
            menu.addAction(self._undo_action)
            menu.addAction(self._redo_action)

            menu.exec(QPoint(sx, sy))

        QTimer.singleShot(0, _show)

    def _ctx_add_floating_text_at(self, x_mm: float, y_mm: float):
        """Create a floating text item at the given canvas (mm) position."""
        item = TextItem(
            text="Text",
            x=x_mm,
            y=y_mm,
            scope="global",
            rotation=0.0,
        )
        cmd = AddTextCommand(self.project, item, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_cell_context_menu(self, cell_id: str, is_label_cell: bool, screen_pos):
        """Build and show context menu for a cell or label cell."""
        from PyQt6.QtCore import QPoint

        menu = QMenu(self)

        if is_label_cell:
            # Label cell context menu
            parent_cell_id = cell_id.removeprefix("label_")
            text_obj = next(
                (t for t in self.project.text_items
                 if t.scope == "cell" and t.subtype != "corner" and t.parent_id == parent_cell_id),
                None
            )
            if text_obj:
                delete_label_action = menu.addAction(tr("ctx_delete_label"))
                delete_label_action.triggered.connect(
                    lambda: self._ctx_delete_numbering_label(parent_cell_id)
                )
            menu.exec(QPoint(int(screen_pos.x()), int(screen_pos.y())))
            return

        # Regular cell context menu
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return

        has_image = cell.image_path and not cell.is_placeholder

        # --- Import / Delete Image ---
        has_nested = bool(cell.nested_layout_path)

        import_action = menu.addAction(tr("ctx_import_image"))
        import_action.triggered.connect(lambda: self._ctx_import_image(cell_id))

        if has_image:
            delete_img_action = menu.addAction(tr("action_delete_img"))
            delete_img_action.triggered.connect(lambda: self._ctx_delete_image(cell_id))

        menu.addSeparator()

        # --- Nested Layout ---
        import_layout_action = menu.addAction(tr("ctx_import_layout"))
        import_layout_action.triggered.connect(lambda: self._ctx_import_layout(cell_id))

        if has_nested:
            delete_layout_action = menu.addAction(tr("ctx_delete_layout"))
            delete_layout_action.triggered.connect(lambda: self._ctx_delete_layout(cell_id))

        menu.addSeparator()

        # --- Label submenu ---
        label_menu = menu.addMenu(tr("ctx_labels"))

        # Find the top-level ancestor for this cell
        _top_cell = cell
        _par = self.project.find_parent_of(cell_id)
        while _par:
            _top_cell = _par
            _par = self.project.find_parent_of(_par.id)
        _is_subcell = (_top_cell.id != cell_id)

        # Numbering label — targets this sub-cell directly (label row inside the box)
        has_numbering = any(
            t for t in self.project.text_items
            if t.scope == "cell" and t.subtype != "corner" and t.parent_id == cell_id
        )
        if has_numbering:
            del_num_action = label_menu.addAction(tr("ctx_delete_label_cell"))
            del_num_action.triggered.connect(lambda: self._ctx_delete_numbering_label(cell_id))
        else:
            add_num_action = label_menu.addAction(tr("ctx_add_label_cell"))
            add_num_action.triggered.connect(lambda: self._ctx_add_numbering_label(cell_id))

        # For sub-cells: also offer a label above the whole container box
        if _is_subcell:
            _top_cell_id = _top_cell.id
            has_box_label = any(
                t for t in self.project.text_items
                if t.scope == "cell" and t.subtype != "corner" and t.parent_id == _top_cell_id
            )
            if has_box_label:
                del_box_action = label_menu.addAction(tr("ctx_delete_label_above_box"))
                del_box_action.triggered.connect(
                    lambda: self._ctx_delete_numbering_label(_top_cell_id))
            else:
                add_box_action = label_menu.addAction(tr("ctx_add_label_above_box"))
                add_box_action.triggered.connect(
                    lambda: self._ctx_add_numbering_label(_top_cell_id))

        label_menu.addSeparator()

        # Corner labels
        corner_anchors = [
            ("top_left_inside",     "ctx_corner_top_left"),
            ("top_right_inside",    "ctx_corner_top_right"),
            ("bottom_left_inside",  "ctx_corner_bottom_left"),
            ("bottom_right_inside", "ctx_corner_bottom_right"),
        ]
        for anchor, name_key in corner_anchors:
            existing = next(
                (t for t in self.project.text_items
                 if t.scope == "cell" and getattr(t, 'subtype', None) == 'corner'
                 and t.anchor == anchor and t.parent_id == cell_id),
                None
            )
            if existing:
                action = label_menu.addAction(
                    tr("ctx_delete_corner_label").format(name=tr(name_key)))
                action.triggered.connect(
                    lambda checked=False, a=anchor: self._ctx_delete_corner_label(cell_id, a)
                )
            else:
                action = label_menu.addAction(
                    tr("ctx_add_corner_label").format(name=tr(name_key)))
                action.triggered.connect(
                    lambda checked=False, a=anchor: self._ctx_add_corner_label(cell_id, a)
                )

        # --- Image operations (only if has image) ---
        if has_image:
            menu.addSeparator()

            # Fit Mode submenu
            fit_menu = menu.addMenu(tr("ctx_fit_mode"))
            for mode, key in [("contain", "ctx_fit_contain"), ("cover", "ctx_fit_cover")]:
                action = fit_menu.addAction(tr(key))
                action.setCheckable(True)
                action.setChecked(cell.fit_mode == mode)
                action.triggered.connect(
                    lambda checked=False, m=mode: self._ctx_set_cell_prop(cell_id, {"fit_mode": m})
                )

            # Rotation submenu
            rot_menu = menu.addMenu(tr("ctx_rotation"))
            for deg in [0, 90, 180, 270]:
                action = rot_menu.addAction(f"{deg}°")
                action.setCheckable(True)
                action.setChecked(cell.rotation == deg)
                action.triggered.connect(
                    lambda checked=False, d=deg: self._ctx_set_cell_prop(cell_id, {"rotation": d})
                )

            # Scale Bar toggle
            menu.addSeparator()
            sb_action = menu.addAction(tr("ctx_enable_scale_bar") if not cell.scale_bar_enabled else tr("ctx_disable_scale_bar"))
            sb_action.triggered.connect(
                lambda: self._ctx_set_cell_prop(cell_id, {"scale_bar_enabled": not cell.scale_bar_enabled})
            )

            # --- Crop ---
            menu.addSeparator()
            crop_action = menu.addAction(tr("ctx_crop_image"))
            crop_action.triggered.connect(lambda: self._ctx_crop_image(cell_id))

            crop_ratio_menu = menu.addMenu(tr("ctx_crop_aspect_menu"))
            _PRESETS = [
                (tr("ctx_crop_preset_free"),          0, 0),
                (tr("ctx_crop_preset_square"),         1, 1),
                ("4:3",                                4, 3),
                ("3:2",                                3, 2),
                ("16:9",                              16, 9),
                ("2:1",                                2, 1),
                (tr("ctx_crop_preset_portrait_3_4"),   3, 4),
                (tr("ctx_crop_preset_portrait_2_3"),   2, 3),
                (tr("ctx_crop_preset_portrait_9_16"),  9, 16),
            ]
            for label, aw, ah in _PRESETS:
                act = crop_ratio_menu.addAction(label)
                act.triggered.connect(
                    lambda checked=False, _aw=aw, _ah=ah: self._ctx_crop_to_aspect(cell_id, _aw, _ah)
                )

            if cell.crop_left != 0.0 or cell.crop_top != 0.0 or cell.crop_right != 1.0 or cell.crop_bottom != 1.0:
                reset_crop_act = menu.addAction(tr("ctx_crop_reset"))
                reset_crop_act.triggered.connect(
                    lambda: self._ctx_set_cell_prop(
                        cell_id, {"crop_left": 0.0, "crop_top": 0.0, "crop_right": 1.0, "crop_bottom": 1.0}
                    )
                )

        # --- Insert Row / Cell ---
        menu.addSeparator()
        insert_menu = menu.addMenu(tr("ctx_insert"))

        # Find top-level cell info for row/column operations
        top_cell = cell
        parent = self.project.find_parent_of(cell_id)
        while parent:
            top_cell = parent
            parent = self.project.find_parent_of(parent.id)
        ri = top_cell.row_index
        ci = top_cell.col_index
        row_temp = next((r for r in self.project.rows if r.index == ri), None)
        col_count = row_temp.column_count if row_temp else 1

        act_row_above = insert_menu.addAction(tr("ctx_row_above"))
        act_row_above.triggered.connect(lambda: self._on_insert_row(ri))

        act_row_below = insert_menu.addAction(tr("ctx_row_below"))
        act_row_below.triggered.connect(lambda: self._on_insert_row(ri + 1))

        insert_menu.addSeparator()

        act_cell_left = insert_menu.addAction(tr("ctx_col_left"))
        act_cell_left.triggered.connect(lambda: self._on_insert_cell(ri, ci))

        act_cell_right = insert_menu.addAction(tr("ctx_col_right"))
        act_cell_right.triggered.connect(lambda: self._on_insert_cell(ri, ci + 1))

        # --- Sub-cell operations ---
        # WrapAndInsertCommand handles both cases:
        #   - If parent already splits in the requested direction → insert sibling
        #   - Otherwise → wrap this cell in a new split container
        insert_menu.addSeparator()
        sub_menu = insert_menu.addMenu(tr("ctx_split_subcell"))
        act_sub_above = sub_menu.addAction(tr("ctx_cell_above"))
        act_sub_above.triggered.connect(
            lambda: self._ctx_wrap_and_insert(cell_id, "vertical", "before"))
        act_sub_below = sub_menu.addAction(tr("ctx_cell_below"))
        act_sub_below.triggered.connect(
            lambda: self._ctx_wrap_and_insert(cell_id, "vertical", "after"))
        act_sub_left = sub_menu.addAction(tr("ctx_cell_left"))
        act_sub_left.triggered.connect(
            lambda: self._ctx_wrap_and_insert(cell_id, "horizontal", "before"))
        act_sub_right = sub_menu.addAction(tr("ctx_cell_right"))
        act_sub_right.triggered.connect(
            lambda: self._ctx_wrap_and_insert(cell_id, "horizontal", "after"))

        if cell.is_leaf:
            sub_menu.addSeparator()
            act_split_cols = sub_menu.addAction(tr("ctx_split_n_cols"))
            act_split_cols.triggered.connect(
                lambda: self._ctx_split_into_n(cell_id, "horizontal"))
            act_split_rows = sub_menu.addAction(tr("ctx_split_n_rows"))
            act_split_rows.triggered.connect(
                lambda: self._ctx_split_into_n(cell_id, "vertical"))

        cell_parent = self.project.find_parent_of(cell_id)

        # --- Delete Row / Cell ---
        delete_menu = menu.addMenu(tr("ctx_delete"))

        act_del_row = delete_menu.addAction(tr("ctx_this_row"))
        if len(self.project.rows) <= 1:
            act_del_row.setEnabled(False)
            act_del_row.setToolTip(tr("ctx_cant_delete_last_row"))
        act_del_row.triggered.connect(lambda: self._on_delete_row(ri))

        act_del_cell = delete_menu.addAction(tr("ctx_this_column"))
        if col_count <= 1:
            act_del_cell.setEnabled(False)
            act_del_cell.setToolTip(tr("ctx_cant_delete_last_cell"))
        act_del_cell.triggered.connect(lambda: self._on_delete_cell(ri, ci))

        if cell_parent and len(cell_parent.children) > 1:
            act_del_sub = delete_menu.addAction(tr("ctx_this_subcell"))
            act_del_sub.triggered.connect(
                lambda: self._ctx_delete_subcell(cell_id))

        menu.exec(QPoint(int(screen_pos.x()), int(screen_pos.y())))

    def _ctx_import_image(self, cell_id: str):
        """Context menu: import image into cell."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Image", "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.svg *.pdf *.eps);;All Files (*)"
        )
        if path:
            cell = self.project.find_cell_by_id(cell_id)
            if cell:
                cmd = DropImageCommand(cell, path, self._refresh_and_update)
                self.undo_stack.push(cmd)

    def _ctx_delete_image(self, cell_id: str):
        """Context menu: delete image from cell."""
        cell = self.project.find_cell_by_id(cell_id)
        if cell and (cell.image_path or not cell.is_placeholder):
            cmd = PropertyChangeCommand(
                cell, {"image_path": None, "is_placeholder": True},
                self._refresh_and_update, "Delete Image"
            )
            self.undo_stack.push(cmd)

    def _ctx_import_layout(self, cell_id: str):
        """Context menu: import a .figlayout file into a cell as a nested layout."""
        from src.model.nested_layout_utils import detect_circular_reference

        path, _ = QFileDialog.getOpenFileName(
            self, "Import Layout", "",
            "Figure Layout (*.figlayout);;All Files (*)"
        )
        if not path:
            return

        # Circular reference check
        parent_path = self._current_project_path
        if parent_path and detect_circular_reference(parent_path, path):
            QMessageBox.warning(
                self, "Circular Reference",
                "Cannot import this layout: it would create a circular reference "
                "(the selected file already references this project directly or indirectly)."
            )
            return

        cell = self.project.find_cell_by_id(cell_id)
        if cell:
            cmd = PropertyChangeCommand(
                cell, {"nested_layout_path": path},
                self._refresh_and_update, "Import Layout"
            )
            self.undo_stack.push(cmd)

    def _ctx_delete_layout(self, cell_id: str):
        """Context menu: remove the nested layout from a cell."""
        cell = self.project.find_cell_by_id(cell_id)
        if cell and cell.nested_layout_path:
            cmd = PropertyChangeCommand(
                cell, {"nested_layout_path": None},
                self._refresh_and_update, "Delete Layout"
            )
            self.undo_stack.push(cmd)

    def _ctx_add_numbering_label(self, cell_id: str):
        """Context menu: add a numbering label for a cell."""
        # Ensure label_placement is 'label_row_above' so the label cell row appears
        if self.project.label_placement != "label_row_above":
            cmd = PropertyChangeCommand(
                self.project, {"label_placement": "label_row_above"},
                self._refresh_and_update, "Switch to Label Row"
            )
            self.undo_stack.push(cmd)

        # Determine the next label text based on scheme and existing labels
        scheme = self.project.label_scheme
        existing_labels = [
            t for t in self.project.text_items
            if t.scope == "cell" and t.subtype != "corner" and t.parent_id
        ]
        idx = len(existing_labels)
        if scheme in ["(a)", "a"]:
            letter = chr(ord('a') + idx % 26)
            text = f"({letter})" if scheme == "(a)" else letter
        else:
            letter = chr(ord('A') + idx % 26)
            text = f"({letter})" if scheme == "(A)" else letter

        item = TextItem(
            text=text,
            font_family=self.project.label_font_family,
            font_size_pt=self.project.label_font_size,
            font_weight=self.project.label_font_weight,
            color=self.project.label_color,
            scope="cell",
            parent_id=cell_id,
            anchor="top_left_inside",
            offset_x=2.0,
            offset_y=2.0,
        )
        cmd = AddTextCommand(self.project, item, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_delete_numbering_label(self, cell_id: str):
        """Context menu: delete the numbering label for a cell."""
        text_obj = next(
            (t for t in self.project.text_items
             if t.scope == "cell" and t.subtype != "corner" and t.parent_id == cell_id),
            None
        )
        if text_obj:
            cmd = DeleteTextCommand(self.project, text_obj, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _ctx_add_corner_label(self, cell_id: str, anchor: str):
        """Context menu: add a corner label at the given anchor."""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Corner Label", f"Label text for {anchor}:")
        if ok and text.strip():
            item = TextItem(
                text=text.strip(),
                font_family=self.project.corner_label_font_family,
                font_size_pt=self.project.corner_label_font_size,
                font_weight=self.project.corner_label_font_weight,
                color=self.project.corner_label_color,
                scope="cell",
                subtype="corner",
                parent_id=cell_id,
                anchor=anchor,
                offset_x=2.0,
                offset_y=2.0,
            )
            cmd = AddTextCommand(self.project, item, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _ctx_delete_corner_label(self, cell_id: str, anchor: str):
        """Context menu: delete the corner label at the given anchor."""
        text_obj = next(
            (t for t in self.project.text_items
             if t.scope == "cell" and getattr(t, 'subtype', None) == 'corner'
             and t.anchor == anchor and t.parent_id == cell_id),
            None
        )
        if text_obj:
            cmd = DeleteTextCommand(self.project, text_obj, self._refresh_and_update)
            self.undo_stack.push(cmd)

    def _on_subcell_ratio_changed(self, cell_id: str, new_ratio: float):
        """Inspector: change the size ratio of a sub-cell."""
        cmd = ChangeSubCellRatioCommand(self.project, cell_id, new_ratio,
                                         update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_wrap_and_insert(self, cell_id: str, direction: str, position: str):
        """Context menu: wrap cell in a split and insert a new sibling."""
        cmd = WrapAndInsertCommand(self.project, cell_id, direction, position,
                                    update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_split_into_n(self, cell_id: str, direction: str):
        """Context menu: split a leaf cell into N equal sub-cells at once."""
        from PyQt6.QtWidgets import QInputDialog
        label = tr("ctx_split_n_cols_label") if direction == "horizontal" else tr("ctx_split_n_rows_label")
        count, ok = QInputDialog.getInt(self, tr("ctx_split_dialog_title"), label, value=2, min=2, max=64)
        if not ok:
            return
        cmd = SplitCellCommand(self.project, cell_id, direction, count=count,
                               update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_insert_subcell(self, cell_id: str, position: str):
        """Context menu: insert a sibling sub-cell at the same nesting level."""
        cmd = InsertSubCellCommand(self.project, cell_id, position,
                                    update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_delete_subcell(self, cell_id: str):
        """Context menu: delete a sub-cell."""
        cmd = DeleteSubCellCommand(self.project, cell_id,
                                    update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _ctx_set_cell_prop(self, cell_id: str, changes: dict):
        """Context menu: set properties on a cell."""
        cell = self.project.find_cell_by_id(cell_id)
        if cell:
            cmd = PropertyChangeCommand(cell, changes, self._refresh_and_update, "Change Cell Property")
            self.undo_stack.push(cmd)

    def _ctx_crop_image(self, cell_id: str):
        """Enter interactive crop mode for the given cell."""
        if not self.scene:
            return
        item = self.scene.cell_items.get(cell_id)
        if item:
            item.enter_crop_mode()

    def _ctx_crop_to_aspect(self, cell_id: str, aspect_w: float, aspect_h: float):
        """Apply an aspect-ratio crop preset, undoably."""
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return
        if aspect_w <= 0 or aspect_h <= 0:
            # "Free" — reset crop
            changes = {"crop_left": 0.0, "crop_top": 0.0, "crop_right": 1.0, "crop_bottom": 1.0}
            cmd = PropertyChangeCommand(cell, changes, self._refresh_and_update, "Reset Crop")
            self.undo_stack.push(cmd)
            return
        # Compute crop rect at the requested aspect ratio, centred on the image
        from src.utils.image_proxy import get_image_proxy
        proxy = get_image_proxy()
        pix = proxy.get_pixmap(cell.image_path) if cell.image_path else None
        if pix and not pix.isNull():
            pix_w, pix_h = pix.width(), pix.height()
        else:
            pix_w, pix_h = 1, 1
        # Apply the preset computation via a temporary CellItem helper
        import copy
        tmp_crop = (cell.crop_left, cell.crop_top, cell.crop_right, cell.crop_bottom)
        target_ratio = aspect_w / aspect_h
        cur_w = (cell.crop_right - cell.crop_left) * pix_w
        cur_h = (cell.crop_bottom - cell.crop_top) * pix_h
        if cur_h <= 0 or cur_w <= 0:
            cur_w, cur_h = pix_w, pix_h
        if cur_w / cur_h > target_ratio:
            new_w_frac = (cur_h * target_ratio) / pix_w
            new_h_frac = cur_h / pix_h
        else:
            new_w_frac = cur_w / pix_w
            new_h_frac = (cur_w / target_ratio) / pix_h
        cx = (cell.crop_left + cell.crop_right) * 0.5
        cy = (cell.crop_top + cell.crop_bottom) * 0.5
        new_left = max(0.0, cx - new_w_frac * 0.5)
        new_right = min(1.0, cx + new_w_frac * 0.5)
        new_top = max(0.0, cy - new_h_frac * 0.5)
        new_bottom = min(1.0, cy + new_h_frac * 0.5)
        changes = {
            "crop_left": new_left, "crop_top": new_top,
            "crop_right": new_right, "crop_bottom": new_bottom,
        }
        cmd = PropertyChangeCommand(cell, changes, self._refresh_and_update,
                                    f"Crop {aspect_w}:{aspect_h}")
        self.undo_stack.push(cmd)

    def _on_cell_crop_committed(self, cell_id: str, cl: float, ct: float, cr: float, cb: float):
        """Handle crop committed from interactive crop mode — push undo command."""
        cell = self.project.find_cell_by_id(cell_id)
        if not cell:
            return
        changes = {"crop_left": cl, "crop_top": ct, "crop_right": cr, "crop_bottom": cb}
        cmd = PropertyChangeCommand(cell, changes, self._refresh_and_update, "Crop Image")
        self.undo_stack.push(cmd)

    def _on_crop_mode_active(self, active: bool):
        if active:
            self.statusbar.showMessage(tr("crop_hint"))
        else:
            self.statusbar.clearMessage()

    def _on_auto_label_incell(self):
        cmd = AutoLabelCommand(self.project, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_auto_label_outcell(self):
        cmd = AutoLabelOutCellCommand(self.project, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_auto_layout(self):
        if getattr(self.project, 'layout_mode', 'grid') == 'freeform':
            cmd = AutoLayoutFreeformCommand(self.project, self._refresh_and_update)
            self.undo_stack.push(cmd)
        else:
            cmd = AutoLayoutCommand(self.project, self._refresh_and_update)
            self.undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Freeform layout handlers
    # ------------------------------------------------------------------

    def _on_bake_to_freeform(self):
        """Bake the current grid positions into per-cell freeform coordinates and switch to freeform mode (undoable)."""
        from src.model.layout_engine import LayoutEngine
        layout = LayoutEngine.calculate_layout(self.project)
        baked = {cid: rect for cid, rect in layout.cell_rects.items()}
        cmd = FreeformLayoutModeCommand(self.project, "freeform", baked, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_switch_to_grid(self):
        """Switch back to grid layout mode (undoable)."""
        cmd = FreeformLayoutModeCommand(self.project, "grid", update_callback=self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_cell_freeform_geometry_changed(self, cell_id: str, x: float, y: float, w: float, h: float):
        """Called when user drags/resizes a cell in freeform mode; push undoable command."""
        cell = self.project.find_cell_by_id(cell_id)
        if cell:
            cmd = FreeformGeometryCommand(cell, x, y, w, h)
            # No refresh needed — scene already shows the new geometry from direct manipulation.
            # The command only records state for undo; calling update_callback on undo/redo will resync.
            cmd.update_callback = self._refresh_and_update
            self.undo_stack.push(cmd)

    def _on_divider_drag_finished(self, div):
        """Called when user finishes dragging a row/column divider; push undoable command."""
        cmd = DividerDragCommand(self.project, div, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_bring_to_front(self):
        """Increment z_index of all selected cells (undoable)."""
        cells = [self.project.find_cell_by_id(cid) for cid in self._get_selected_cell_ids()]
        cells = [c for c in cells if c is not None]
        if cells:
            cmd = ZIndexChangeCommand(cells, +1, self._refresh_and_update, "Bring to Front")
            self.undo_stack.push(cmd)

    def _on_send_to_back(self):
        """Decrement z_index of all selected cells (undoable)."""
        cells = [self.project.find_cell_by_id(cid) for cid in self._get_selected_cell_ids()]
        cells = [c for c in cells if c is not None]
        if cells:
            cmd = ZIndexChangeCommand(cells, -1, self._refresh_and_update, "Send to Back")
            self.undo_stack.push(cmd)

    def _get_selected_cell_ids(self):
        """Return list of selected non-label cell IDs from the scene."""
        from src.canvas.cell_item import CellItem
        return [
            item.cell_id for item in self.scene.selectedItems()
            if isinstance(item, CellItem) and not item.is_label_cell
        ]

    def _get_export_default_dir(self) -> str:
        """Return directory of current project file, or empty string if none."""
        if self._current_project_path:
            return os.path.dirname(self._current_project_path)
        return ""

    def _on_export_pdf(self):
        default_dir = self._get_export_default_dir()
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", default_dir, "PDF Files (*.pdf)")
        if path:
            PdfExporter.export(self.project, path)
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _on_export_tiff(self):
        default_dir = self._get_export_default_dir()
        path, _ = QFileDialog.getSaveFileName(self, "Export TIFF", default_dir, "TIFF Files (*.tiff *.tif)")
        if path:
            ImageExporter.export(self.project, path, "TIFF")
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _on_export_jpg(self):
        default_dir = self._get_export_default_dir()
        path, _ = QFileDialog.getSaveFileName(self, "Export JPG", default_dir, "JPEG Files (*.jpg *.jpeg)")
        if path:
            ImageExporter.export(self.project, path, "JPG")
            QMessageBox.information(self, "Export", f"Exported to {path}")

    def _on_show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def _on_show_help(self):
        dlg = HelpDialog(self)
        dlg.exec()

    def _on_open_nested_layout(self, cell_id: str, figlayout_path: str):
        """Open a nested layout in a separate editor window."""
        import os
        if not os.path.exists(figlayout_path):
            QMessageBox.warning(self, "Error", f"Layout file not found:\n{figlayout_path}")
            return
        try:
            project = Project.load_from_file(figlayout_path)
            child_window = MainWindow()
            child_window._set_project(project, figlayout_path)
            child_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            # When child saves, refresh the parent cell's thumbnail
            child_window._parent_cell_id = cell_id
            child_window._parent_window = self
            original_save = child_window._save_project_to_path

            def _save_and_refresh(path):
                result = original_save(path)
                if result:
                    self._refresh_and_update()
                return result

            child_window._save_project_to_path = _save_and_refresh
            child_window.show()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open nested layout: {e}")

    def closeEvent(self, event):
        # Check every tab for unsaved changes
        for i, tab in enumerate(self._tabs):
            if not tab.undo_stack.isClean():
                # Activate the tab so the user sees it
                self._activate_tab(i)
                ret = self._ask_unsaved(self._tab_title(tab))
                if ret == "cancel":
                    event.ignore()
                    return
                if ret == "save":
                    if not self._on_save_project():
                        event.ignore()
                        return
        try:
            get_image_proxy().shutdown()
        except Exception:
            pass
        super().closeEvent(event)

    def _on_new_project(self):
        if not self._maybe_save():
            return

        project = Project()
        project.rows = [
            RowTemplate(index=0, column_count=2, height_ratio=1.0),
            RowTemplate(index=1, column_count=2, height_ratio=1.0)
        ]
        self._set_project(project, None)

    def _on_open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Figure Layout (*.figlayout);;JSON (*.json)")
        if not path:
            return
        # If active tab is clean and untitled, reuse it; otherwise open a new tab
        active_tab = self._tabs[self._active_tab_idx]
        if active_tab.undo_stack.isClean() and active_tab.path is None:
            try:
                project = Project.load_from_file(path)
                self._set_project(project, path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open project: {e}")
        else:
            try:
                project = Project.load_from_file(path)
                self._create_tab(project, path)
                self._check_image_resolution()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open project: {e}")

    def _on_save_project(self):
        if self._current_project_path:
            return self._save_project_to_path(self._current_project_path)
        return self._on_save_project_as()

    def _on_save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save Project As", "", "Figure Layout (*.figlayout);;JSON (*.json)")
        if not path:
            return False
        return self._save_project_to_path(path)

    def _save_project_to_path(self, path: str) -> bool:
        try:
            self.project.name = os.path.splitext(os.path.basename(path))[0]
            self.project.save_to_file(path)
            self._current_project_path = path
            # Keep active tab's path in sync
            if 0 <= self._active_tab_idx < len(self._tabs):
                self._tabs[self._active_tab_idx].path = path
                self.tab_widget.setTabText(self._active_tab_idx,
                                           self._tab_title(self._tabs[self._active_tab_idx]))
            self.undo_stack.setClean()
            self.setWindowModified(False)
            self._update_window_title()
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save project: {e}")
            return False

    def _on_import_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Images", "", 
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.svg *.pdf *.eps);;All Files (*)"
        )
        if paths:
            for file_path in paths:
                # Find first placeholder
                target_cell = None
                for cell in self.project.get_all_leaf_cells():
                    if cell.is_placeholder:
                        target_cell = cell
                        break

                if target_cell:
                    cmd = DropImageCommand(target_cell, file_path, self._refresh_and_update)
                    self.undo_stack.push(cmd)
                else:
                    # No more placeholders
                    QMessageBox.information(
                        self,
                        "Import",
                        f"No more placeholder cells available. {len(paths) - paths.index(file_path)} images not imported."
                    )
                    break

    def _on_open_images_as_grid(self):
        if not self._maybe_save():
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Images as Grid",
            "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp *.svg *.pdf *.eps);;All Files (*)",
        )
        if not paths:
            return

        project = self._build_project_from_images(paths)
        self._set_project(project, None)

        cmd = AutoLayoutCommand(self.project, self._refresh_and_update)
        self.undo_stack.push(cmd)

    def _on_reload_images(self):
        """Clear image cache and refresh canvas to reload all images from disk."""
        get_image_proxy().clear_cache()
        self._refresh_and_update()

    def _on_project_file_dropped(self, file_path: str):
        """Handle drag and drop of .figlayout — opens in a new tab."""
        try:
            project = Project.load_from_file(file_path)
            self._create_tab(project, file_path)
            self._check_image_resolution()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Failed to open project: {e}")
