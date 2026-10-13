# astrbot_plugin_osu_beatmap_preview

AstrBot 的 osu! 谱面预览插件，默认使用兼容的 Rust CLI 核心 [osu-beatmap-preview](https://github.com/2710165659/osu-beatmap-preview)：在聊天中发送谱面 ID，即可生成 Standard / Taiko / Catch / Mania 四模式的预览长图、GIF 与带原始音频的 MP4 视频。

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

## 核心下载与更新

插件不绑定具体核心版本，插件版本与核心版本独立更新，仓库和安装包不包含二进制核心。默认从 [osu-beatmap-preview Releases](https://github.com/2710165659/osu-beatmap-preview/releases/latest) 获取最新 CLI；也可以手动放置兼容相同命令行参数、配置和 JSON 输出协议的核心。使用其他 GitHub 仓库时，可在插件配置中修改 `core_repository`（产物须采用下表中的命名）。

- 插件安装、启动加载或重载时通过 AstrBot 的 `initialize()` 钩子后台检查最新 Release tag，不阻塞插件加载。与已安装核心的 `--version` 相同时跳过下载，保留文件修改时间和预览缓存；版本不同时下载对应 tag 的核心。成功后日志打印核心版本及耗时（秒），失败记录日志并保留旧核心。
- 首次发送 `/v`、`/vp`、`/vg`、`/vgc`、`/vgcl`、`/vv` 或 `/预览`，缺核心时会提示「核心正在下载」，并在后台只下载当前平台的文件。完成后不主动通知，请稍后重新发送渲染命令。
- 已有核心时普通命令跳过下载；发送 `/v update` 可手动检查并更新核心，返回当前版本。配置 `core_update_users` 可限制此命令的用户 ID，默认空列表允许所有人使用；普通预览不受影响。
- 核心通过 AstrBot 的 `StarTools.get_data_dir()` 保存至 `data/plugin_data/astrbot_plugin_osu_beatmap_preview/bin/`，避免随插件重装丢失。仍可读取旧的插件根目录 `bin/`，后续下载统一写入新目录。
- 优先访问 GitHub 官方，失败后重试并依次尝试 ghfast.top、gh-proxy.com、ghproxy.net 镜像。镜像可用性会变化，全部失败时可稍后重试或手动安装。
- 新文件先下载至同目录临时文件，检查文件完整性、可执行格式、架构与版本 tag 后才替换旧核心。下载和等待替换期间，新请求仍可使用旧核心；仅原子替换时短暂独占访问。失败会保留旧核心并清理临时文件。

### 手动下载和放置核心

1. 在 [Release 页面](https://github.com/2710165659/osu-beatmap-preview/releases) 的 Assets 中下载当前 **AstrBot 运行环境**对应的 CLI，Docker 部署请按容器平台选择。无需下载其他平台；若下载的是压缩包，先解压出可执行文件。
2. 在 `AstrBot/data/plugin_data/astrbot_plugin_osu_beatmap_preview/` 下创建 `bin/`，将文件放入其中，保持以下文件名：

| 运行平台 | 相对插件数据目录的路径 |
| --- | --- |
| Windows x86_64 / amd64 | `bin/osu-beatmap-preview-windows-amd64-cli.exe` |
| Linux x86_64 / amd64 | `bin/osu-beatmap-preview-linux-amd64-cli` |
| macOS Intel | `bin/osu-beatmap-preview-macos-amd64-cli` |
| macOS Apple Silicon | `bin/osu-beatmap-preview-macos-arm64-cli` |

例如 Windows 核心路径为 `AstrBot/data/plugin_data/astrbot_plugin_osu_beatmap_preview/bin/osu-beatmap-preview-windows-amd64-cli.exe`。AstrBot 根目录以运行环境为准，并支持 `ASTRBOT_ROOT`；插件不自行假定根目录。旧插件目录下的 `bin/` 仍兼容，但新数据目录优先。

3. Linux/macOS 请赋予执行权限，例如 Linux：

```bash
chmod +x AstrBot/data/plugin_data/astrbot_plugin_osu_beatmap_preview/bin/osu-beatmap-preview-linux-amd64-cli
```

4. 发送渲染命令即可使用。也兼容去掉 `-cli` 的旧文件名，但优先使用新文件名。当前上游未提供 Linux ARM、Windows ARM 或 32 位产物，插件不会下载错误架构的核心。

仍可从 AstrBot 根目录运行 `python data/plugins/astrbot_plugin_osu_beatmap_preview/update_core.py`，或设置 `ASTRBOT_ROOT` 后运行脚本；Windows 的 `update_core.bat` 调用同一套版本检查和下载逻辑，只更新当前平台。

### 预览缓存

核心要求预览产物的修改时间不早于核心可执行文件与谱面文件，因此重复下载同一版本核心也会使旧预览失效。本插件在 tag 相同时跳过下载，避免无故重渲染。真正更新核心后，同一请求第一次重渲染是正常行为；后续相同参数和配置可复用缓存。核心默认输出和谱面缓存仍由核心配置决定，`--no-cache` 会显式禁用复用。

### 参数处理

插件只解析聊天语法并转换 CLI 参数，Mod、时间正负/顺序和其他渲染参数的合法性由核心判断，核心报错直接反馈。不再按错误文案重试渲染或迁移旧缓存；`--no-cache` 仍会直接传给核心。

Taiko/Catch/Mania PNG 的 `t=起点+终点` 区间转换请显式使用 `:t`、`:c` 或 `:m`。原生谱面未指定模式时，时间点原样交给核心，插件不再猜测模式并重试。
