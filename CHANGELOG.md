# Changelog

## [0.2.x]

### [0.2.8] - 2026-09-05

#### 破坏性变更

- 同步上游 osu-beatmap-preview v1.1.1 的配置结构，`default_json` 改用 `timeout` 和 `render.*.*.structure/style` 字段。
- 移除旧版配置、队列和参数兼容逻辑；参数合法性统一交给 Rust 核心校验，核心错误直接返回插件。
- 新版不迁移旧版输出缓存或下载缓存。升级后请清理 osu-beatmap-preview 缓存，再使用新版插件。

#### 修复

- 修复 `/vgc` 和 `/vgcl` 的 Mania GIF 仍显示 SV 标签的问题。

### [0.2.6] - 2026-08-30

- 同步上游 osu-beatmap-preview [v1.0.8](https://github.com/2710165659/osu-beatmap-preview/releases/tag/v1.0.8)，适配新的 `--mod`、`--time-points`、`--duration-time` 和 `--config` 命令行接口。
- 保留现有聊天命令语法：复合 Mod 和多时间点会转换为可重复的上游参数，`/vv` 时间范围会转换为起点与时长。
- Taiko 和 Mania 的 GIF/MP4 默认使用 30 FPS。
- `/vgc` 改为通过配置生成四模式无时间标签的单屏 GIF；`/vgcl` 在同一布局上开启时间标签。
- Taiko PNG 的 `gap=` 保持兼容，改为动态覆盖 `layout.taiko.png.SPACING_PER_BPM`。
- 核心 PNG/GIF/MP4 默认超时设为 55/55/115 秒，比 Python 外层默认的图片 60 秒和视频 120 秒各少 5 秒。

### [0.2.5] - 2026-08-02

- `/vv <BID>` 默认使用 `--preview-30s` 渲染 `PreviewTime` 附近约 30 秒；追加 `--full` 可渲染完整视频，`t=<起点>+<终点>` 仍可指定视频范围。
- 新增 `/vgc <BID>` 无时间标签和 `/vgcl <BID>` 带时间标签的单屏连续 GIF 命令，对应核心的 `--gif-clip` 与 `--gif-clip-label`。
- 默认视频和指定范围视频完成后只发送最终视频；完整视频保留入队提示。

### [0.2.4] - 2026-07-31

- 同步上游 osu-beatmap-preview [v1.0.6](https://github.com/2710165659/osu-beatmap-preview/releases/tag/v1.0.6)。
- 新增 `/vv <BID>` MP4 视频渲染，视频包含谱面原始音频；可用 `t=<起点>+<终点>` 指定两个时间点，省略时渲染整张谱面。
- 新增视频渲染队列长度配置，默认最多容纳 3 个等待中或渲染中的视频任务；入队和队满时均会立即反馈。
- Taiko PNG 的 `gap=` 参数改为调用上游 `--gap`，匹配上游参数重命名。
- 更新帮助文档。

### [0.2.3] - 2026-06-23

- 同步上游 osu-beatmap-preview [v1.0.3](https://github.com/2710165659/osu-beatmap-preview/releases/tag/v1.0.3)。
- 新增 taiko PNG `gap=` 参数支持，可自定义 BPM 间距（对应上游 `--bpm`）。
- 新增 `--no-cache` 后缀支持，强制重新下载 .osu 文件并跳过输出缓存（对应上游 `--no-cache`）。
- Standard 模式新增 TC (Traceable) mod 支持（GIF / PNG）。
- 更新 help 文档。

### [0.2.2]

- 修复windows环境因编码问题导致的渲染失败问题。
- 增加日志输出。

### [0.2.1] - 2026-06-14

修复错误提示信息。

### [0.2.0] - 2026-06-14

#### 破坏性变更

- **核心迁移至 Rust**：底层渲染引擎由 Python 重写为 Rust 单可执行文件，皮肤资源编译期嵌入，零运行时依赖。
- 旧的 `osu-beatmap-preview/` Python core 目录已移除，不再通过 `import` 调用，改为通过 `subprocess` 调用平台对应的二进制文件。

#### 新增

- `bin/` 目录：存放各平台二进制文件，由 `update_core.bat` 从 [osu-beatmap-preview](https://github.com/2710165659/osu-beatmap-preview) 最新 release 自动下载。
- 多平台支持：Windows (amd64)、Linux (amd64)、macOS (amd64 / arm64)，服务层自动检测平台选择对应二进制。
- 非 Windows 平台自动 `chmod +x` 赋予二进制执行权限。

#### 变更

- `update_core.bat`：不再从 `osu-agent-skills` 仓库 clone Python 代码，改为从 GitHub API 拉取最新 tag 并下载四个平台的二进制文件。
- `service/service_beatmap_preview.py`：移除所有 Python import 逻辑，改用 `subprocess.run` 调用 Rust 二进制，解析 stdout JSON。非 Windows 平台自动 `chmod +x`，捕获 `PermissionError` 并给出修复提示。
- `requirements.txt`：移除 `Pillow>=10.0.0`，插件不再需要任何 Python 第三方依赖。
- `metadata.yaml`、`main.py`、`README.md`：更新描述文案，指向新 Rust core 仓库。

#### 移除

- `osu-beatmap-preview/`（Python 版 core 全部代码）。

## [0.1.x]

### 0.1.8
- 同步上游修复：taiko 谱面渲染问题。

### 0.1.7
- 修复首次运行报错。

### 0.1.6
- 增加 mania / ctb / taiko GIF 预览。
- 全模式 mod 支持。
- 指定时间点、转谱等大量功能。

### 0.1.5 及更早
- osu! 四模式谱面预览基础功能。
- 同步上游渲染与内存优化更新。
- `update_core.sh` 改为 `update_core.bat`。
