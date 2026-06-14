# Changelog

## [0.2.0] - 2026-06-14

### 破坏性变更

- **核心迁移至 Rust**：底层渲染引擎由 Python 重写为 Rust 单可执行文件，皮肤资源编译期嵌入，零运行时依赖。
- 旧的 `osu-beatmap-preview/` Python core 目录已移除，不再通过 `import` 调用，改为通过 `subprocess` 调用平台对应的二进制文件。

### 新增

- `bin/` 目录：存放各平台二进制文件，由 `update_core.bat` 从 [osu-beatmap-preview](https://github.com/2710165659/osu-beatmap-preview) 最新 release 自动下载。
- 多平台支持：Windows (amd64)、Linux (amd64)、macOS (amd64 / arm64)，服务层自动检测平台选择对应二进制。
- `.gitignore` 新增 `bin/`，二进制不入库。
- 非 Windows 平台自动 `chmod +x` 赋予二进制执行权限。

### 变更

- `update_core.bat`：不再从 `osu-agent-skills` 仓库 clone Python 代码，改为从 GitHub API 拉取最新 tag 并下载四个平台的二进制文件。
- `service/service_beatmap_preview.py`：移除所有 Python import 逻辑，改用 `subprocess.run` 调用 Rust 二进制，解析 stdout JSON。非 Windows 平台自动 `chmod +x`，捕获 `PermissionError` 并给出修复提示。
- `requirements.txt`：移除 `Pillow>=10.0.0`，插件不再需要任何 Python 第三方依赖。
- `metadata.yaml`、`main.py`、`README.md`：更新描述文案，指向新 Rust core 仓库。

### 移除

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
