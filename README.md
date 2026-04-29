# astrbot_plugin_osu_beatmap_preview

把 `osu-beatmap-preview` core 封装成 AstrBot 插件，并把上游代码直接放在仓库内，方便部署和发布。

## 功能

- 指令：`/预览 <bid>` or `/谱面预览 <bid>`
- osu!standard：随机选取谱面中的四个时间段进行局部预览，不渲染完整谱面。
- osu!taiko：生成完整谱面的纵向预览图，用于查看鼓点分布和整体节奏密度。暂不支持 10 分钟以上的长谱。
- osu!catch：生成完整谱面的纵向预览图，用于查看水果、滑条路径和整体物件分布。暂不支持 10 分钟以上的长谱。
- osu!mania：生成完整谱面的纵向预览图，用于查看各轨道物件分布和长条配置。暂不支持 10 分钟以上的长谱。

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

## 更新 core

仓库里附带了一个手动更新脚本，会从上游仓库拉取最新的 `osu-beatmap-preview` 子目录并覆盖本地 core。

```bat
.\update_core.bat
```
