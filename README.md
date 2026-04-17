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
  PDF 与栅格导出严格对应画布中的布局与标签位置。
- **矢量图导入（SVG）**
  SVG 文件可置入单元格，PDF 导出时以矢量方式渲染。
- **标签编辑**
  每个标签均可单独编辑；可通过"应用到全部"按钮将颜色同步到同组所有标签。

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

## 文件格式

- 布局文件后缀为 `*.figlayout`（本仓库 `.gitignore` 中已默认忽略）。
- 支持导入的图片格式：PNG、JPG、TIFF 等常见栅格格式，以及 SVG。
- 支持导出格式：
  - `*.pdf`
  - `*.tif` / `*.tiff`
  - `*.jpg` / `*.jpeg`

> **DPI 说明**：DPI 主要影响栅格导出（TIFF/JPG）的输出像素尺寸；PDF 导出以页面尺寸为准，DPI 影响内部渲染分辨率，不影响版面物理尺寸。

## 支持开发

如果这个项目对您有帮助，欢迎通过支付宝打赏支持：

<img src="assets/Alipay.jpg" alt="支付宝收款码" width="200"/>

## 许可证

Apache-2.0 许可证，详见 `LICENSE`。
