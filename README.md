# astrbot_plugin_osu_beatmap_preview

把 Rust 版 `osu-beatmap-preview` core 封装成 AstrBot 插件，通过调用二进制文件渲染谱面预览图。

## 功能如图

![help](help.png)

## 安装

### 方式一：从插件市场安装

在 AstrBot WebUI 中打开插件市场，搜索：`osu!谱面预览` 找到插件后点击安装即可。

### 方式二：手动安装

1. 克隆项目

```bash
git clone https://github.com/2710165659/astrbot_plugin_osu_beatmap_preview.git
```

2. 安装插件

任选一种方式：

* 将项目文件夹压缩为 ZIP 后，在 AstrBot WebUI 中上传安装
* 或将整个 `astrbot_plugin_osu_beatmap_preview` 文件夹复制到 AstrBot 的插件目录中

插件目录一般为：

```text
AstrBot/data/plugins/
```

3. 重启 AstrBot，或在 WebUI 中重载插件

### 方式三：通过github链接安装

在 AstrBot WebUI 中，进入插件管理页面，点击「通过 GitHub 链接安装」，输入以下地址：

```
https://github.com/2710165659/astrbot_plugin_osu_beatmap_preview
```

等待安装完成后重启 AstrBot 即可。

## 更新 core

运行以下脚本，自动从 [osu-beatmap-preview](https://github.com/2710165659/osu-beatmap-preview) 最新 release 下载四个平台的二进制文件到 `bin/` 目录：

```bat
.\update_core.bat
```

二进制文件按平台自动选择：
- Windows: `bin/osu-beatmap-preview-windows-amd64.exe`
- Linux: `bin/osu-beatmap-preview-linux-amd64`
- macOS Intel: `bin/osu-beatmap-preview-macos-amd64`
- macOS Apple Silicon: `bin/osu-beatmap-preview-macos-arm64`
