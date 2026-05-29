# MCP 配置指南

将兼容 MCP 的 AI 助手（Claude Desktop、Claude Code、Cursor、Windsurf、Cline 等）接入正在运行的 ImageLayoutManager，让 AI 代替你创建、排版、标注和导出多面板学术图。

---

## 工作原理

```text
AI 助手  ── stdio (MCP) ──►  imagelayout-cli mcp  ── WebSocket ──►  ILM (GUI)
```

AI 工具会把 `imagelayout-cli mcp` 作为子进程启动。CLI 只是一个轻量 MCP 适配器，不需要用户额外安装 Python 或 `mcp` 包；它会通过本地 WebSocket 连接到正在运行的 ILM GUI。

服务只绑定到 `127.0.0.1`，不会暴露到外部网络。

---

## 第一步：在应用内启用 MCP 服务

打开 ImageLayoutManager，然后点击：**Tools → Enable MCP Server**。

---

## 第二步：在 AI 工具中注册

### 一键注册（推荐）

在应用内点击：**Tools → MCP Setup Guide… → Auto Register…**。软件会检测常见 AI 工具并自动写入配置。

### Claude Desktop

Settings → Developer → Edit Config：

```json
{
  "mcpServers": {
    "imagelayout": {
      "command": "C:/Program Files/ImageLayoutManager/imagelayout-cli.exe",
      "args": ["mcp"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add imagelayout -- "C:/.../imagelayout-cli.exe" "mcp"
```

也可以使用应用内 MCP 设置向导中的 **Copy mcp add command** 按钮。

### Cursor

编辑 `~/.cursor/mcp.json`，格式同上。

### Windsurf

编辑 `~/.codeium/windsurf/mcp_config.json`，格式同上。

### 其他 MCP 工具

任意支持 stdio MCP server 的工具都可以使用：

- **command**：`imagelayout-cli.exe` 的绝对路径
- **args**：`["mcp"]`
- **transport**：stdio

---

## 第三步：开始使用

1. 确保 ILM 正在运行，且 MCP Server 已启用。
2. 打开 AI 工具并直接下达任务，例如：
   - *"用 D:\data\panels 里的图片拼一个 2×3 的图版"*
   - *"把第一行调高一些"*
   - *"把所有面板标签改成 10 pt 粗体，并留一点边距"*
   - *"给显微图加 10 µm 比例尺"*
   - *"给 b 面板加一个放大插图，并设置白色边框"*
   - *"保存为 figure.figlayout"*
   - *"导出为 figure.png"*

所有操作都会实时显示在 ILM 窗口中。任何一步都可以用 Ctrl+Z 撤销。

---

## AI 当前能控制什么

当前 MCP 暴露 36 个工具。概括来说，AI 可以：

- 新建、打开、保存、检查、导出项目。
- 调整行、列、嵌套分割、网格比例和自由布局几何。
- 导入图片，并调整 fit mode、裁剪、旋转、边距、对齐、z-order、SVG 文本归一化。
- 自动生成标签，批量调整标签样式，单独调整某个文本/标签，添加或删除自由文本。
- 添加并配置显微比例尺。
- 添加、删除、调整 PiP 放大插图。
- 管理尺寸组，让多个单元格共享宽度/高度。
- 设置或清除持久导出区域。
- 请求画布截图用于视觉检查。

LLM 侧的概念指南可通过 MCP 资源 `ilm://concepts` 读取；源码对应文件为 `docs/agent_concepts.md`。

---

## 源码/开发环境

```bash
claude mcp add imagelayout -- python "cli_main.py" "mcp"
```

源码模式需要当前 Python 环境已安装 `websockets`。

---

## 常见问题

| 问题 | 解决方法 |
|---|---|
| Connection refused / 连接被拒绝 | ILM 的 MCP Server 未启动，请在 Tools 菜单中启用。 |
| Authentication failed / 认证失败 | Token 每次重启都会刷新。重启 AI 会话。 |
| "no tool named …" | 更新后同时重启 ILM 和 AI 工具，确保 GUI 服务与 `imagelayout-cli mcp` 子进程加载同一套工具列表。 |
