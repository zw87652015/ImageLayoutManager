import json
import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QApplication, QMessageBox, QMenu,
)
from PyQt6.QtCore import Qt
from src.app.i18n import tr, current_language


_CLAUDE_DESKTOP_CONFIG = "claude_desktop_config.json"


def _mcp_command_and_args() -> tuple[str, list[str]]:
    """Return (command, args) for the MCP server config.

    Frozen exe: ``imagelayout-cli.exe mcp`` (ships alongside the GUI exe).
    Source:     ``python src/cli/main.py mcp``.
    """
    if getattr(sys, "frozen", False):
        cli_exe = str(Path(sys.executable).parent / "imagelayout-cli.exe")
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


# ── guide HTML ────────────────────────────────────────────────────────

_HTML_EN = """\
<h2 style="margin-top:0">MCP Setup Guide</h2>

<p>Connect any MCP-compatible AI host
(<b>Claude Desktop</b>, <b>Claude Code</b>, <b>Cursor</b>,
<b>Windsurf</b>, <b>Cline</b>, etc.)
to ImageLayoutManager so the AI can build and edit
multi-panel figures for you.</p>

<hr>

<h3>How it works</h3>
<pre style="background:#f4f4f4; padding:10px; border-radius:4px; font-size:12px;">\
AI host  ── stdio (MCP) ──►  ImageLayoutManager --mcp  ── WebSocket ──►  ILM (this app)</pre>

<p>Your AI host launches this app with <code>--mcp</code> as a subprocess.
In that mode the app acts as a lightweight MCP adapter — no extra
Python install or packages needed.</p>

<hr>

<h3>Step 1 — Enable MCP Server in this app</h3>
<p><b>Tools → Enable MCP Server</b> (in this menu).</p>

<hr>

<h3>Step 2 — Register in your AI host</h3>

<p><b>Easiest:</b> click <b>"Auto Register…"</b> below — it detects
installed hosts and writes the config for you.</p>

<p><b>Manual:</b> click <b>"Copy MCP Config JSON"</b> and paste the
snippet into your host's MCP server configuration. Most hosts store
this in a JSON file with the same format:</p>
<pre style="background:#f4f4f4; padding:10px; border-radius:4px; font-size:12px;">\
{{
  "mcpServers": {{
    "imagelayout": {entry_json}
  }}
}}</pre>

<p><b>Common config file locations:</b></p>
<table cellpadding="4" cellspacing="0" style="border-collapse:collapse; font-size:12px;">
<tr style="background:#f4f4f4;">
  <td style="border:1px solid #ddd;"><b>Claude Desktop</b></td>
  <td style="border:1px solid #ddd;"><code>Settings → Developer → Edit Config</code></td></tr>
<tr>
  <td style="border:1px solid #ddd;"><b>Claude Code</b></td>
  <td style="border:1px solid #ddd;"><code>claude mcp add imagelayout -- …</code> (use "Copy mcp add" button)</td></tr>
<tr style="background:#f4f4f4;">
  <td style="border:1px solid #ddd;"><b>Cursor</b></td>
  <td style="border:1px solid #ddd;"><code>~/.cursor/mcp.json</code></td></tr>
<tr>
  <td style="border:1px solid #ddd;"><b>Windsurf</b></td>
  <td style="border:1px solid #ddd;"><code>~/.codeium/windsurf/mcp_config.json</code></td></tr>
</table>

<hr>

<h3>Step 3 — Use it</h3>
<ol>
  <li>Make sure this app is running with MCP Server enabled.</li>
  <li>Start your AI host and ask the AI to work with your figure:
    <ul>
      <li><i>"Create a 2×3 figure from the images in D:\\data\\panels"</i></li>
      <li><i>"Make the top row taller"</i></li>
      <li><i>"Make all panel labels 10 pt bold with a little padding"</i></li>
      <li><i>"Add 10 µm scale bars to the microscopy panels"</i></li>
      <li><i>"Add a zoom inset to panel b and give it a white border"</i></li>
      <li><i>"Save the project as figure.figlayout"</i></li>
    </ul>
  </li>
</ol>
<p>Every change appears live in this window. Undo any step with <b>Ctrl+Z</b>.</p>

<p><b>Current MCP capabilities:</b> AI can create/open/save/export projects,
reshape rows and cells, import images, split panels, switch to freeform
layout, crop/rotate/pad/align images, style labels and text, add scale bars,
add PiP insets, manage size groups, set export regions, auto-layout, and
request canvas screenshots.</p>

<hr>

<h3>Troubleshooting</h3>
<table cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
<tr style="background:#f4f4f4;">
  <td style="border:1px solid #ddd;"><b>Connection refused</b></td>
  <td style="border:1px solid #ddd;">MCP Server is not running. Enable it in Tools menu.</td>
</tr>
<tr>
  <td style="border:1px solid #ddd;"><b>Authentication failed</b></td>
  <td style="border:1px solid #ddd;">Token regenerates on each restart. Start a new AI session.</td>
</tr>
<tr style="background:#f4f4f4;">
  <td style="border:1px solid #ddd;"><b>"no tool named …"</b></td>
  <td style="border:1px solid #ddd;">After updating, restart both this app and your AI host so the GUI server and MCP subprocess load the same tool list.</td>
</tr>
</table>
"""

_HTML_ZH = """\
<h2 style="margin-top:0">MCP 配置指南</h2>

<p>通过本指南，你可以将兼容 MCP 的 AI 助手
（<b>Claude Desktop</b>、<b>Claude Code</b>、<b>Cursor</b>、
<b>Windsurf</b>、<b>Cline</b> 等）
接入 ImageLayoutManager，让 AI 帮你自动排版和编辑多图版组图。</p>

<hr>

<h3>工作原理</h3>
<pre style="background:#f4f4f4; padding:10px; border-radius:4px; font-size:12px;">\
AI 助手  ── stdio (MCP) ──►  ImageLayoutManager --mcp  ── WebSocket ──►  ILM（本应用）</pre>

<p>AI 助手会以 <code>--mcp</code> 参数启动本应用的一个轻量副本，
作为 MCP 适配器运行——无需额外安装 Python 或任何依赖。</p>

<hr>

<h3>第一步：在软件内启用 MCP 服务</h3>
<p>点击菜单栏中的 <b>工具 → 启用 MCP 服务</b>（就在当前菜单下）。</p>

<hr>

<h3>第二步：在 AI 助手中注册</h3>

<p><b>最简方式：</b>点击下方 <b>"一键注册…"</b> 按钮，
软件会自动检测已安装的 AI 工具并写入配置。</p>

<p><b>手动方式：</b>点击 <b>"复制 MCP 配置"</b>，将以下 JSON 片段粘贴到
你的 AI 工具的 MCP 服务配置中。大多数工具使用相同的格式：</p>
<pre style="background:#f4f4f4; padding:10px; border-radius:4px; font-size:12px;">\
{{
  "mcpServers": {{
    "imagelayout": {entry_json}
  }}
}}</pre>

<p><b>常见配置文件位置：</b></p>
<table cellpadding="4" cellspacing="0" style="border-collapse:collapse; font-size:12px;">
<tr style="background:#f4f4f4;">
  <td style="border:1px solid #ddd;"><b>Claude Desktop</b></td>
  <td style="border:1px solid #ddd;"><code>Settings → Developer → Edit Config</code></td></tr>
<tr>
  <td style="border:1px solid #ddd;"><b>Claude Code</b></td>
  <td style="border:1px solid #ddd;"><code>claude mcp add imagelayout -- …</code>（使用"复制 mcp add 命令"按钮）</td></tr>
<tr style="background:#f4f4f4;">
  <td style="border:1px solid #ddd;"><b>Cursor</b></td>
  <td style="border:1px solid #ddd;"><code>~/.cursor/mcp.json</code></td></tr>
<tr>
  <td style="border:1px solid #ddd;"><b>Windsurf</b></td>
  <td style="border:1px solid #ddd;"><code>~/.codeium/windsurf/mcp_config.json</code></td></tr>
</table>

<hr>

<h3>第三步：开始使用</h3>
<ol>
  <li>确保本应用正在运行且 MCP 服务已启用。</li>
  <li>启动 AI 助手，直接向 AI 下达排版指令，例如：
    <ul>
      <li><i>"用 D:\\data\\panels 里的图片拼一个 2×3 的图版"</i></li>
      <li><i>"把第一行调高一些"</i></li>
      <li><i>"把所有面板标签改成 10 pt 粗体，并留一点边距"</i></li>
      <li><i>"给显微图加 10 µm 比例尺"</i></li>
      <li><i>"给 b 面板加一个放大插图，并设置白色边框"</i></li>
      <li><i>"保存为 figure.figlayout"</i></li>
    </ul>
  </li>
</ol>
<p>每次操作都会实时显示在本窗口中，随时 <b>Ctrl+Z</b> 撤销。</p>

<p><b>当前 MCP 能力：</b>AI 可以新建/打开/保存/导出项目，调整行列与单元格，
导入图片，分割面板，切换自由布局，裁剪/旋转/加边距/对齐图片，调整标签和文本样式，
添加比例尺，添加 PiP 放大插图，管理尺寸组，设置导出区域，自动排版，并请求画布截图。</p>

<hr>

<h3>常见问题</h3>
<table cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
<tr style="background:#f4f4f4;">
  <td style="border:1px solid #ddd;"><b>连接被拒绝</b></td>
  <td style="border:1px solid #ddd;">MCP 服务未启动，请在"工具"菜单中启用。</td>
</tr>
<tr>
  <td style="border:1px solid #ddd;"><b>认证失败</b></td>
  <td style="border:1px solid #ddd;">令牌在每次重启时刷新，请重新开启 AI 会话。</td>
</tr>
<tr style="background:#f4f4f4;">
  <td style="border:1px solid #ddd;"><b>"no tool named …"</b></td>
  <td style="border:1px solid #ddd;">更新后请同时重启本应用和 AI 工具，确保 GUI 服务与 MCP 子进程加载同一套工具列表。</td>
</tr>
</table>
"""


def _format_html(html: str) -> str:
    if getattr(sys, "frozen", False):
        cli = str(Path(sys.executable).parent / "imagelayout-cli.exe")
        cli = cli.replace("\\", "/")
    else:
        cli = "&lt;install-path&gt;/imagelayout-cli.exe"
    example = {"command": cli, "args": ["mcp"]}
    entry_json = json.dumps(example, indent=6, ensure_ascii=False)
    return html.format(entry_json=entry_json)


class MCPGuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            "MCP 配置指南" if current_language() == "zh" else "MCP Setup Guide"
        )
        self.resize(640, 580)
        self.setModal(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        raw = _HTML_ZH if current_language() == "zh" else _HTML_EN
        html = _format_html(raw)

        lbl = QLabel(html)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lbl.setOpenExternalLinks(True)
        lbl.setContentsMargins(16, 16, 16, 16)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        # Qt builds QLabel's right-click "Copy / Select All" menu through
        # a private platform-style path that ignores our QSS-styled QMenu,
        # producing a dark-on-dark popup in light mode.  Suppress it; the
        # bottom-row buttons cover the useful copy actions and Ctrl+C
        # still works on any selected text.
        lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        scroll.setWidget(lbl)
        root.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 0)

        auto_btn = QPushButton(tr("btn_auto_register"))
        auto_btn.clicked.connect(self._on_auto_register)
        btn_row.addWidget(auto_btn)

        copy_config_btn = QPushButton(tr("btn_copy_mcp_config"))
        copy_config_btn.clicked.connect(self._copy_config_json)
        btn_row.addWidget(copy_config_btn)

        copy_cmd_btn = QPushButton(
            "复制 mcp add 命令" if current_language() == "zh"
            else "Copy mcp add command"
        )
        copy_cmd_btn.clicked.connect(self._copy_claude_code_command)
        btn_row.addWidget(copy_cmd_btn)

        btn_row.addStretch()

        close_btn = QPushButton(
            "关闭" if current_language() == "zh" else "Close"
        )
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

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

    def _copy_claude_code_command(self):
        """Copy the `claude mcp add` CLI command."""
        command, args = _mcp_command_and_args()
        parts = [f'"{command}"'] + [f'"{a}"' for a in args]
        cmd = f'claude mcp add imagelayout -- {" ".join(parts)}'
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(cmd)

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

        QMessageBox.information(
            self, "OK",
            tr("msg_registered").format(path=config_path, host=host_name),
        )
