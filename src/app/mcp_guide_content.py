"""User text for the MCP setup guide. Every entry is an (en, zh) pair."""

TITLE = ("Connect an AI assistant", "连接 AI 助手")
SUBTITLE = ("Let Claude, Cursor or Windsurf build and edit figures here. Optional.",
            "让 Claude、Cursor 或 Windsurf 在这里排版和编辑组图。可选功能。")
FLOW = (("AI app", "AI 工具"), ("MCP adapter", "MCP 适配器"), ("This window", "本窗口"))
STEPS = (
    (("Turn on the MCP server", "开启 MCP 服务"),
     ("Your AI app talks to this window through it.", "AI 工具通过它与本窗口通信。")),
    (("Register your AI app", "在 AI 工具中注册"),
     ("One click writes the config for apps found on this computer.", "一键为本机已安装的 AI 工具写入配置。")),
    (("Ask in your AI app", "在 AI 工具中提问"),
     ("Keep this window open, then try:", "保持本窗口打开，然后试试：")),
)
STATUS_ON = ("Server on", "服务已开启")
STATUS_OFF = ("Server off", "服务未开启")
HOST_FOUND = ("found", "已检测到")
HOST_MISSING = ("not found", "未检测到")
COPY_CONFIG = ("Copy Config JSON", "复制配置 JSON")
COPY_CLAUDE_CODE = ("Copy Claude Code Command", "复制 Claude Code 命令")
COPIED = ("Copied to clipboard", "已复制到剪贴板")
REGISTERED = ("Registered in {host}. Restart it to connect.", "已注册到 {host}，重启它即可连接。")
PROMPTS = (
    ("Make a 2×3 figure from the images in my folder", "用我文件夹里的图片拼一个 2×3 组图"),
    ("Make the panel letters bold", "把面板编号改成粗体"),
    ("Add a zoom inset to panel b", "给 b 面板加一个放大插图"),
)
PROMPT_TIP = ("Click to copy", "点击复制")
SAFETY = ("Save a copy first — not every AI edit can be undone.", "请先另存副本——并非所有 AI 修改都能撤销。")
DETAILS = {
    "manual": ("Manual setup", "手动配置"),
    "abilities": ("What the AI can do", "AI 能做什么"),
    "trouble": ("Troubleshooting", "常见问题"),
}
MANUAL_HINT = ("Paste this into your AI app's MCP settings:", "将以下内容粘贴到 AI 工具的 MCP 设置中：")
CONFIG_LOCATIONS = (
    ("Claude Desktop", ("Settings → Developer → Edit Config", "设置 → 开发者 → 编辑配置")),
    ("Claude Code", ("Use “Copy Claude Code Command”", "使用“复制 Claude Code 命令”")),
    ("Cursor", ("~/.cursor/mcp.json", "~/.cursor/mcp.json")),
    ("Windsurf", ("~/.codeium/windsurf/mcp_config.json", "~/.codeium/windsurf/mcp_config.json")),
)
ABILITIES = (("Projects", "工程"), ("Rows & cells", "行与单元格"), ("Images", "图片"),
             ("Crop & rotate", "裁剪与旋转"), ("Labels & text", "标注与文字"), ("Scale bars", "比例尺"),
             ("Insets", "插图"), ("Size groups", "尺寸组"), ("Auto layout", "自动布局"),
             ("Export", "导出"), ("Canvas screenshots", "画布截图"))
TROUBLE = (
    (("Connection refused", "连接被拒绝"), ("Turn on the server in step 1.", "在第 1 步开启服务。")),
    (("Authentication failed", "认证失败"),
     ("The token changes on restart — start a new AI chat.", "令牌在重启后会变化——请新开一个 AI 会话。")),
    (("“no tool named …”", "“no tool named …”"),
     ("After updating, restart this app and the AI app.", "更新后请同时重启本应用和 AI 工具。")),
)
CLOSE = ("Close", "关闭")


def text(pair, lang):
    return pair[1] if lang == "zh" else pair[0]
