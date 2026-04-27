from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

# AstrBot 会直接加载插件根目录下的 main.py。
# 这里主动把插件根目录放进 sys.path，确保 service/ 目录的导入行为稳定。
PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from service.service_beatmap_preview import BeatmapPreviewService


@register(
    "astrbot_plugin_osu_beatmap_preview",
    "xuan_yuan",
    "Generate osu! beatmap preview images from beatmap id via osu-agent-skills.",
    "0.1.0",
)
class BeatmapPreviewPlugin(Star):
    """AstrBot 插件入口"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.preview_service = BeatmapPreviewService(plugin_root=PLUGIN_ROOT)
        self.max_concurrency = config.get("max_concurrency", 10)
        self.preview_timeout_seconds = config.get("preview_timeout_seconds", 60)
        self._preview_semaphore = asyncio.Semaphore(self.max_concurrency)

    @filter.command("预览", alias={"谱面预览"})
    async def preview_beatmap(self, event: AstrMessageEvent, bid: str):
        """按 beatmap id 生成 osu! 谱面预览图"""

        # 如果当前执行中的预览任务已达到最大并发数，直接拒绝新请求，避免过载。
        if self._preview_semaphore.locked():
            yield event.plain_result("当前谱面预览任务较多，请稍后再试")
            return

        try:
            async with self._preview_semaphore:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self.preview_service.generate_from_bid, bid),
                    timeout=self.preview_timeout_seconds,
                )
            preview_img = result["preview-img"]
            if not preview_img or not Path(preview_img).exists():
                raise FileNotFoundError("生成的预览图文件不存在")
        except asyncio.TimeoutError:
            yield event.plain_result("谱面预览生成超时，请稍后再试")
            return
        except Exception as exc:
            # 统一异常日志记录，方便排查问题
            logger.exception("osu beatmap preview plugin failed while generating preview")
            yield event.plain_result("谱面预览生成失败：" + str(exc))
            return

        chain = [
            Comp.Reply(id=event.message_obj.message_id),
            Comp.Image.fromFileSystem(preview_img),
        ]
        yield event.chain_result(chain)
