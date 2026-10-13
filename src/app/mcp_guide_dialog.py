import json
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, QRectF, Qt, QTimer
from PyQt6.QtGui import QFontDatabase, QFontMetrics, QGuiApplication, QPainter, QPalette
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)
from src.app.i18n import tr, current_language
from src.app.mcp_guide_content import (
    TITLE, SUBTITLE, FLOW, STEPS, STATUS_ON, STATUS_OFF, HOST_MISSING, COPY_CONFIG,
    COPY_CLAUDE_CODE, COPIED, REGISTERED, PROMPTS, PROMPT_TIP, SAFETY, DETAILS,
    MANUAL_HINT, CONFIG_LOCATIONS, ABILITIES, TROUBLE, CLOSE, text,
)
from src.app.mcp_guide_paint import paint_flow
from src.app.theme import DARK, LIGHT, get_tokens


_CLAUDE_DESKTOP_CONFIG = "claude_desktop_config.json"

# Bundled CLI executable name: ``imagelayout-cli.exe`` on Windows,
# plain ``imagelayout-cli`` inside the macOS app bundle's Contents/MacOS.
_CLI_NAME = "imagelayout-cli.exe" if sys.platform == "win32" else "imagelayout-cli"


def _mcp_command_and_args() -> tuple[str, list[str]]:
    """Return (command, args) for the MCP server config.

    Frozen exe: ``<cli> mcp`` — ``imagelayout-cli.exe`` on Windows,
    ``imagelayout-cli`` on macOS (ships alongside the GUI exe).
    Source:     ``python src/cli/main.py mcp``.
    """
    if getattr(sys, "frozen", False):
        cli_exe = str(Path(sys.executable).parent / _CLI_NAME)
        return cli_exe, ["mcp"]
    cli_main = str(Path(__file__).resolve().parents[2] / "src" / "cli" / "main.py")
    return sys.executable, [cli_main, "mcp"]


def _mcp_entry() -> dict:
    command, args = _mcp_command_and_args()
    return {
        "command": command.replace("\\", "/"),
        "args": [a.replace("\\", "/") for a in args],
    }


# ── known MCP host config paths ──────────────────────────────────────

def _claude_desktop_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "Claude"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude"
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "Claude"


_KNOWN_HOSTS = [
    ("Claude Desktop", lambda: _claude_desktop_dir() / _CLAUDE_DESKTOP_CONFIG),
    ("Cursor",         lambda: Path.home() / ".cursor" / "mcp.json"),
    ("Windsurf",       lambda: Path.home() / ".codeium" / "windsurf" / "mcp_config.json"),
]


def _host_configs() -> list[tuple[str, Path]]:
    """Return [(display_name, config_path), ...] for detected MCP hosts."""
    hosts = []
    for name, path_fn in _KNOWN_HOSTS:
        path = path_fn()
        if path.parent.exists() or path.exists():
            hosts.append((name, path))
    return hosts


def _flow_colors() -> dict:
    window = QGuiApplication.palette().color(QPalette.ColorRole.Window)
    tokens = get_tokens(DARK if window.lightness() < 128 else LIGHT)
    return {"surface": tokens["surface"], "border": tokens["border_strong"],
            "accent": tokens["accent"], "text": tokens["text"], "muted": tokens["text_tert"]}


class _FlowWidget(QWidget):
    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self._labels = labels
        self.setFixedHeight(64)

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_flow(painter, QRectF(self.rect()), self._labels, _flow_colors())
        painter.end()


class MCPGuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lang = current_language()
        self.setObjectName("mcpGuide")
        self.setWindowTitle(text(TITLE, self._lang))
        self.resize(560, 600)
        self.setModal(False)

        self._feedbacks = []
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._hide_feedback)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(18, 18, 18, 18)
        col.setSpacing(12)

        title = QLabel(text(TITLE, self._lang))
        title.setObjectName("mcpTitle")
        title.setWordWrap(True)
        subtitle = QLabel(text(SUBTITLE, self._lang))
        subtitle.setObjectName("mcpSubtitle")
        subtitle.setWordWrap(True)
        col.addWidget(title)
        col.addWidget(subtitle)
        col.addWidget(_FlowWidget([text(item, self._lang) for item in FLOW]))
        col.addWidget(self._step_one())
        col.addWidget(self._step_two())
        col.addWidget(self._step_three())

        safety = QLabel("ⓘ " + text(SAFETY, self._lang))
        safety.setObjectName("mcpSafety")
        safety.setWordWrap(True)
        col.addWidget(safety)

        col.addWidget(self._details_section("manual", self._manual_body()))
        col.addWidget(self._details_section("abilities", self._abilities_body()))
        col.addWidget(self._details_section("trouble", self._trouble_body()))
        col.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(12, 0, 12, 12)
        footer.addStretch()
        close_btn = QPushButton(text(CLOSE, self._lang))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._refresh_server()

    # ── building blocks ───────────────────────────────────────────────

    def _body_label(self, pair):
        label = QLabel(text(pair, self._lang))
        label.setObjectName("mcpStepBody")
        label.setWordWrap(True)
        return label

    def _feedback_label(self):
        label = QLabel()
        label.setObjectName("mcpFeedback")
        label.setWordWrap(True)
        label.hide()
        self._feedbacks.append(label)
        return label

    def _card(self, number, title_pair):
        card = QFrame()
        card.setObjectName("mcpStepCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(8)
        badge = QLabel(str(number))
        badge.setObjectName("mcpStepBadge")
        badge.setFixedSize(22, 22)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading = QLabel(text(title_pair, self._lang))
        heading.setObjectName("mcpStepTitle")
        heading.setWordWrap(True)
        header.addWidget(badge)
        header.addWidget(heading, 1)
        layout.addLayout(header)
        return card, layout

    def _details_section(self, key, body):
        toggle = QToolButton()
        toggle.setObjectName("mcpDetailsToggle")
        toggle.setCheckable(True)
        toggle.setText(text(DETAILS[key], self._lang))
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        body.setVisible(False)

        def _toggled(checked, button=toggle, panel=body):
            button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
            panel.setVisible(checked)

        toggle.toggled.connect(_toggled)
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(toggle)
        layout.addWidget(body)
        return wrapper

    # ── step 1: server ────────────────────────────────────────────────

    def _step_one(self):
        card, layout = self._card(1, STEPS[0][0])
        layout.addWidget(self._body_label(STEPS[0][1]))
        row = QHBoxLayout()
        self._pill = QLabel()
        self._pill.setObjectName("mcpStatusPill")
        row.addWidget(self._pill)
        row.addStretch()
        self._server_button = QPushButton()
        self._server_button.clicked.connect(self._on_server_button)
        row.addWidget(self._server_button)
        layout.addLayout(row)
        action = self._server_action()
        if action is not None:
            action.toggled.connect(self._on_server_toggled)
        return card

    def _server_action(self):
        return getattr(self.parent(), "_act_enable_agent_server", None)

    def _server_running(self):
        controller = getattr(self.parent(), "_agent_server_controller", None)
        return bool(controller is not None and controller.is_running())

    def _refresh_server(self):
        running = self._server_running()
        self._pill.setText(text(STATUS_ON if running else STATUS_OFF, self._lang))
        self._pill.setProperty("on", "true" if running else "false")
        self._repolish(self._pill)
        self._server_button.setText(
            tr("action_disable_agent_server") if running else tr("action_enable_agent_server"))
        self._server_button.setProperty("accent", not running)
        self._repolish(self._server_button)
        self._server_button.setEnabled(self._server_action() is not None)

    def _repolish(self, widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _on_server_button(self):
        action = self._server_action()
        if action is not None:
            action.trigger()

    def _on_server_toggled(self, _checked):
        QTimer.singleShot(0, self._refresh_server)

    # ── step 2: register ──────────────────────────────────────────────

    def _step_two(self):
        card, layout = self._card(2, STEPS[1][0])
        layout.addWidget(self._body_label(STEPS[1][1]))
        hosts_row = QHBoxLayout()
        found = {name for name, _path in _host_configs()}
        for name, _path_fn in _KNOWN_HOSTS:
            is_found = name in found
            label = QLabel(f"✓ {name}" if is_found
                           else f"{name} · {text(HOST_MISSING, self._lang)}")
            label.setObjectName("mcpHost")
            label.setProperty("found", "true" if is_found else "false")
            hosts_row.addWidget(label)
        hosts_row.addStretch()
        layout.addLayout(hosts_row)

        buttons = QHBoxLayout()
        auto_btn = QPushButton(tr("btn_auto_register"))
        auto_btn.setProperty("accent", True)
        auto_btn.clicked.connect(self._on_auto_register)
        copy_config_btn = QPushButton(text(COPY_CONFIG, self._lang))
        copy_config_btn.clicked.connect(self._copy_config_json)
        copy_cmd_btn = QPushButton(text(COPY_CLAUDE_CODE, self._lang))
        copy_cmd_btn.clicked.connect(self._copy_claude_code_command)
        buttons.addWidget(auto_btn)
        buttons.addWidget(copy_config_btn)
        buttons.addWidget(copy_cmd_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self._step_two_feedback = self._feedback_label()
        layout.addWidget(self._step_two_feedback)
        return card

    # ── step 3: ask ───────────────────────────────────────────────────

    def _step_three(self):
        card, layout = self._card(3, STEPS[2][0])
        layout.addWidget(self._body_label(STEPS[2][1]))
        for prompt in PROMPTS:
            prompt_text = text(prompt, self._lang)
            chip = QPushButton(prompt_text)
            chip.setObjectName("mcpPrompt")
            chip.setToolTip(text(PROMPT_TIP, self._lang))
            chip.clicked.connect(lambda checked=False, t=prompt_text: self._copy_prompt(t))
            layout.addWidget(chip)
        self._prompt_feedback = self._feedback_label()
        layout.addWidget(self._prompt_feedback)
        return card

    # ── details ───────────────────────────────────────────────────────

    def _manual_body(self):
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._body_label(MANUAL_HINT))
        snippet = json.dumps({"mcpServers": {"imagelayout": _mcp_entry()}},
                             indent=2, ensure_ascii=False)
        code = QPlainTextEdit(snippet)
        code.setObjectName("mcpCode")
        code.setReadOnly(True)
        code.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        lines = snippet.count("\n") + 1
        code.setFixedHeight(min(lines, 12) * QFontMetrics(code.font()).lineSpacing() + 16)
        layout.addWidget(code)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for row, (host, where) in enumerate(CONFIG_LOCATIONS):
            host_label = QLabel(host)
            host_label.setObjectName("mcpLocHost")
            where_label = QLabel(text(where, self._lang))
            where_label.setObjectName("mcpLocPath")
            where_label.setWordWrap(True)
            where_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(host_label, row, 0)
            grid.addWidget(where_label, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return body

    def _abilities_body(self):
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        for index, item in enumerate(ABILITIES):
            chip = QLabel(text(item, self._lang))
            chip.setObjectName("mcpChip")
            grid.addWidget(chip, index // 3, index % 3)
        return body

    def _trouble_body(self):
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for problem, fix in TROUBLE:
            heading = QLabel(text(problem, self._lang))
            heading.setObjectName("mcpStepTitle")
            heading.setWordWrap(True)
            layout.addWidget(heading)
            layout.addWidget(self._body_label(fix))
        return body

    # ── feedback ──────────────────────────────────────────────────────

    def _show_feedback(self, label, message):
        for other in self._feedbacks:
            other.hide()
        label.setText(message)
        label.show()
        self._feedback_timer.start(3000)

    def _hide_feedback(self):
        for label in self._feedbacks:
            label.hide()

    def _copy_prompt(self, prompt_text):
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(prompt_text)
        self._show_feedback(self._prompt_feedback, text(COPIED, self._lang))

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_server()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            self._refresh_server()

    # ── button handlers ───────────────────────────────────────────────

    def _copy_config_json(self):
        """Copy the universal MCP server JSON snippet to clipboard."""
        snippet = json.dumps(
            {"mcpServers": {"imagelayout": _mcp_entry()}},
            indent=2, ensure_ascii=False,
        )
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(snippet)
        self._show_feedback(self._step_two_feedback, text(COPIED, self._lang))

    def _copy_claude_code_command(self):
        """Copy the `claude mcp add` CLI command."""
        command, args = _mcp_command_and_args()
        parts = [f'"{command}"'] + [f'"{a}"' for a in args]
        cmd = f'claude mcp add imagelayout -- {" ".join(parts)}'
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(cmd)
        self._show_feedback(self._step_two_feedback, text(COPIED, self._lang))

    def _on_auto_register(self):
        """Show a dropdown of detected hosts, then write to the chosen one."""
        hosts = _host_configs()
        if not hosts:
            QMessageBox.information(self, "MCP", tr("msg_no_hosts_found"))
            return

        menu = QMenu(self)
        for name, path in hosts:
            action = menu.addAction(name)
            action.setData((name, str(path)))

        chosen = menu.exec(self.sender().mapToGlobal(
            self.sender().rect().bottomLeft()
        ))
        if chosen is None:
            return

        host_name, config_path_str = chosen.data()
        config_path = Path(config_path_str)
        self._write_host_config(host_name, config_path)

    def _write_host_config(self, host_name: str, config_path: Path):
        config: dict = {}
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                config = {}

        config.setdefault("mcpServers", {})
        config["mcpServers"]["imagelayout"] = _mcp_entry()

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Error",
                tr("msg_register_failed").format(error=e),
            )
            return

        self._show_feedback(self._step_two_feedback,
                            text(REGISTERED, self._lang).format(host=host_name))
