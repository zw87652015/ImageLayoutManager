# ImageLayoutManager — 学术图像排版工具

[English README](README.en.md)

## 简介

ImageLayoutManager 是一款基于 PyQt6 的桌面应用，专为学术写作场景设计，帮助研究者快速排列多面板图，保证统一的间距、对齐、标签与导出质量，满足期刊投稿要求。

## 功能亮点

- **多面板图组装**
  将多张图片放入同一布局，统一设置边距与间隔。
- **布局可复现**
  支持保存和重新加载布局文件，随时重新生成同一张图。
- **面向论文的导出**
  导出为 PDF、TIFF、JPG 等格式，适配学术写作工作流。
- **层级分割**
  单元格可无限纵向/横向分割，支持按比例调节子单元格大小，并可在子单元格组上方添加标签行而不破坏整体布局。
- **所见即所得导出（WYSIWYG）**
  PDF、栅格与 SVG 导出严格对应画布中的布局与标签位置。
- **矢量图导入（SVG）**
  SVG 文件可置入单元格，PDF 与 SVG 导出时以矢量方式渲染。
- **标签编辑**
  每个标签均可单独编辑；可通过"应用到全部"按钮将颜色同步到同组所有标签。
- **可移植项目包（.figpack）**
  将项目及其所有引用图片打包为单个 `.figpack` 文件，便于分享或归档，无需担心图片路径失效。
- **文件锁定**
  打开项目文件时会自动加锁，同一文件无法在同一实例或另一实例中重复打开，防止并发编辑。

## 下载

预编译文件附在每个 [GitHub Release](../../releases) 页面中。

| 文件 | 平台 | 说明 |
|---|---|---|
| `ImageLayoutManager_版本_Windows_Setup.exe` | Windows | **推荐。** 安装包版本 — 安装时解压一次，之后每次启动均为即时打开。 |
| `ImageLayoutManager_版本_Windows.exe` | Windows | 免安装单文件版 — 无需安装，但每次启动需 5–10 秒自解压。 |
| `ImageLayoutManager_版本_MacOS.zip` | macOS | App Bundle — 解压后拖入"应用程序"文件夹即可。 |

## 快速开始

### 环境要求

- Python 3.9 及以上
- 通过 pip 安装 PyQt6

### 安装

```bash
pip install -r requirements.txt
```

如需使用干净的独立环境（推荐用于打包构建），可通过提供的 conda 环境文件创建：

```bash
conda env create -f environment.yml
conda activate imagelayout
```

## 使用方法

启动应用：

```bash
python main.py
```

典型工作流：

1. **新建布局**
2. **向单元格中添加图片**
3. **右键菜单分割单元格**（纵向/横向，支持自定义比例）
4. **在检查器中调整间距、对齐方式及子单元格比例**
5. **保存布局文件**（便于后续复现）
6. **导出**为目标格式

## 命令行界面（CLI）

Windows 安装包中包含无头 CLI 工具（`imagelayout-cli.exe`），用于自动化工作流。其输出与 GUI 导出功能保持像素级完全一致。

### 命令

| 命令      | 用途                                                         |
| --------- | --------------------------------------------------------------- |
| `render`  | `.figpack` / `.figlayout` → `pdf` / `tiff` / `jpg` / `png`      |
| `pack`    | `.figlayout` → `.figpack`（打包布局 + 引用的资源）   |
| `unpack`  | `.figpack` → 包含资源 + 侧边 `.figlayout` 的文件夹    |
| `inspect` | 打印页面尺寸、DPI、单元格数量等（文本或 `--json`）      |

### 示例

```powershell
# 按项目保存的 DPI 进行像素级精确的 PDF 渲染
imagelayout-cli.exe render figure_4.figpack -f pdf -o figure_4.pdf

# 覆盖 DPI 以生成快速预览 PNG
imagelayout-cli.exe render figure_4.figlayout -f png --dpi 150

# 使用指定 ICC 配置文件的印刷级 CMYK TIFF
imagelayout-cli.exe render figure_4.figpack -f tiff --cmyk `
    --icc-profile "C:\ICC\USWebCoatedSWOP.icc" --icc-intent 1 -o fig.tiff

# 将 .figlayout 及其所有引用图片打包为 .figpack
imagelayout-cli.exe pack figure_4.figlayout -o figure_4.figpack

# 解包 .figpack 以便手动编辑 JSON / 图片
imagelayout-cli.exe unpack figure_4.figpack -o ./extracted/

# 快速摘要
imagelayout-cli.exe inspect figure_4.figpack
imagelayout-cli.exe inspect figure_4.figpack --json
```

### 访问方式

安装 Windows 版本后，可通过以下方式使用 CLI：
- **开始菜单**："ImageLayoutManager CLI (shell)" — 打开已预配置 CLI 路径的 PowerShell
- **安装目录**：`C:\Program Files\ImageLayoutManager\imagelayout-cli.exe`

运行 `imagelayout-cli.exe --help` 查看完整用法信息。

## 文件格式

### 项目文件

| 后缀 | 说明 |
|---|---|
| `*.figlayout` | 默认项目格式。以 JSON 存储布局，图片文件通过路径引用，保持独立存放。轻量，适合版本控制。 |
| `*.figpack` | 可移植包格式。ZIP 归档，包含布局 JSON 与所有引用图片。通过 **文件 → 转换为 .figpack…** 将已打开的 `.figlayout` 项目打包，适合分享或归档已完成的图表。 |

项目文件打开时，会在其旁边写入一个隐藏的存在文件（`~$文件名`）。若另一实例尝试打开同一文件，应用将拒绝并显示当前持有者的用户名。关闭标签页后锁定自动释放。

### 图片导入

支持的栅格格式：PNG、JPG、TIFF、BMP、GIF、WebP。  
SVG 文件同样支持，在 PDF 与 SVG 导出时以矢量方式渲染。

### 导出格式

| 格式 | 说明 |
|---|---|
| `*.pdf` | 文本保持矢量；图片按项目 DPI 嵌入。 |
| `*.tif` / `*.tiff` | 栅格；输出像素尺寸 = 物理尺寸 × DPI。 |
| `*.jpg` / `*.jpeg` | 栅格；与 TIFF 相同但有损压缩。 |
| `*.png` | 栅格；无损压缩。 |
| `*.svg` | 矢量；文字与布局为矢量，栅格图片以嵌入方式保存。 |

**DPI** 控制栅格导出的输出像素尺寸，以及 PDF 的内部渲染分辨率，不影响版面物理尺寸。

## 支持开发

如果这个项目对您有帮助，欢迎通过支付宝打赏支持：

<img src="assets/Alipay.jpg" alt="支付宝收款码" width="200"/>

## 许可证

Apache-2.0 许可证，详见 `LICENSE`。
