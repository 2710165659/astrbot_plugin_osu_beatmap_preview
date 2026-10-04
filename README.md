# astrbot_plugin_osu_beatmap_preview

AstrBot 的 osu! 谱面预览插件，渲染内核为 Rust 版 [osu-beatmap-preview](https://github.com/2710165659/osu-beatmap-preview)：在聊天中发送谱面 ID，即可生成 Standard / Taiko / Catch / Mania 四模式的预览长图、GIF 与带原始音频的 MP4 视频。

- 支持 Mod 组合、转谱（`:t` / `:c` / `:m`）、时间点与区间渲染、Taiko 自定义间距。
- MP4 支持背景视频、故事板与打击音，可渲染完整谱面或指定片段。
- 零 Python 依赖，核心是单个二进制文件，Windows / Linux / macOS 均可运行。

## 功能如图

<img src="https://raw.githubusercontent.com/2710165659/astrbot_plugin_osu_beatmap_preview/main/help.png" alt="点击查看使用说明" />

示例：

```text
基本:     /v 123456·/v:3 123456·/vg:3 123456
Mod:      /v 123456+hd+hr
时间:     /vg 123456 t=10+25+60·/vp:3 123456 t=30+60
视频:     /vv 123456·/vv 123456 t=30+60·/vv 123456 --full --bg
GIF单屏:  /vgc 123456·/vgcl 123456 t=-2+10
复杂:     /vg:3 123456+4k+ds+in+dt1.2 t=10+30+50
```

## 核心配置

参考：[这里](https://github.com/2710165659/osu-beatmap-preview/tree/main/crates/osu-beatmap-preview-cli#%E9%85%8D%E7%BD%AE)

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

二进制文件按平台自动选择（上游自 v1.2.0 起 CLI 产物名以 `-cli` 结尾）：

- Windows: `bin/osu-beatmap-preview-windows-amd64-cli.exe`
- Linux: `bin/osu-beatmap-preview-linux-amd64-cli`
- macOS Intel: `bin/osu-beatmap-preview-macos-amd64-cli`
- macOS Apple Silicon: `bin/osu-beatmap-preview-macos-arm64-cli`

插件同时兼容旧命名（`bin/osu-beatmap-preview-windows-amd64.exe` 等），但 `update_core.bat` 只会下载新的 `-cli` 产物。
