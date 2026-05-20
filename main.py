from __future__ import annotations

import asyncio
import re
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

V_REQUEST_RE = re.compile(
    r"^\s*/(?P<command>预览|v(?:p|g)?)(?P<tail>.*)\s*$",
    re.IGNORECASE,
)

HELP_IMG = PLUGIN_ROOT / "help.png"

COMMAND_TO_FMT = {
    "v": None,
    "vp": "png",
    "vg": "gif",
    "预览": None,
}

CONVERT_ALIAS_TO_TARGET = {
    "1": "taiko",
    "t": "taiko",
    "taiko": "taiko",
    "2": "ctb",
    "c": "ctb",
    "ctb": "ctb",
    "catch": "ctb",
    "3": "mania",
    "m": "mania",
    "mania": "mania",
}

TEXT_CONVERT_ALIASES = (
    "taiko",
    "catch",
    "mania",
    "ctb",
    "t",
    "c",
    "m",
)


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

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def preview_beatmap(self, event: AstrMessageEvent):
        """统一处理 /v、/vp、/vg 指令"""

        raw_text = event.message_obj.message_str
        matched = V_REQUEST_RE.match(raw_text)
        if not matched:
            return

        try:
            bid, fmt, convert, mod_text, time_text = self._parse_request(
                command=matched.group("command"),
                raw_tail=matched.group("tail"),
            )
        except ValueError as exc:
            yield self._reply_text(event, str(exc))
            return

        if bid is None:
            yield event.chain_result([
                Comp.Reply(id=event.message_obj.message_id),
                Comp.Image.fromFileSystem(str(HELP_IMG)),
            ])
            return

        # 如果当前执行中的预览任务已达到最大并发数，直接拒绝新请求，避免过载。
        if self._preview_semaphore.locked():
            yield self._reply_text(event, "当前谱面预览任务较多，请稍后再试")
            return

        try:
            async with self._preview_semaphore:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.preview_service.generate_from_bid,
                        bid,
                        fmt=fmt,
                        convert=convert,
                        mod_text=mod_text,
                        time_text=time_text,
                    ),
                    timeout=self.preview_timeout_seconds,
                )
            preview_img = result["preview-img"]
            if not preview_img or not Path(preview_img).exists():
                raise FileNotFoundError("生成的预览图文件不存在")
        except asyncio.TimeoutError:
            yield self._reply_text(event, "谱面预览生成超时，请稍后再试")
            return
        except Exception as exc:
            # 统一异常日志记录，方便排查问题
            logger.exception("osu beatmap preview plugin failed while generating preview")
            yield self._reply_text(event, "谱面预览生成失败：" + str(exc))
            return

        chain = [
            Comp.Reply(id=event.message_obj.message_id),
            Comp.Image.fromFileSystem(preview_img),
        ]
        yield event.chain_result(chain)

    @staticmethod
    def _reply_text(event: AstrMessageEvent, text: str):
        return event.chain_result(
            [
                Comp.Reply(id=event.message_obj.message_id),
                Comp.Plain(text=text),
            ]
        )

    def _parse_request(
        self,
        command: str,
        raw_tail: str,
    ) -> tuple[str | None, str | None, str | None, str | None, str | None]:
        fmt = COMMAND_TO_FMT[command.lower()]
        tail = raw_tail.strip()
        if not tail:
            return None, fmt, None, None, None

        convert = None
        if tail.startswith((":", "：")):
            convert, tail = self._parse_convert_spec(tail[1:].lstrip())

        tail = tail.lstrip()
        bid_match = re.match(r"^\d+", tail)
        if bid_match is None:
            raise ValueError("命令格式不正确")

        bid = bid_match.group(0)
        suffix = tail[bid_match.end():]
        mod_text, time_text = self._parse_suffix(suffix)
        return bid, fmt, convert, mod_text, time_text

    def _parse_convert_spec(self, raw_spec: str) -> tuple[str, str]:
        if not raw_spec:
            raise ValueError("命令格式不正确")

        lowered = raw_spec.lower()
        for alias in TEXT_CONVERT_ALIASES:
            if lowered.startswith(alias):
                return CONVERT_ALIAS_TO_TARGET[alias], raw_spec[len(alias):]

        numeric_alias = lowered[0]
        if numeric_alias in {"1", "2", "3"}:
            if len(raw_spec) == 1 or raw_spec[1].isdigit():
                raise ValueError("命令格式不正确")
            return CONVERT_ALIAS_TO_TARGET[numeric_alias], raw_spec[1:]

        raise ValueError("命令格式不正确")

    def _parse_suffix(self, raw_suffix: str) -> tuple[str | None, str | None]:
        normalized = re.sub(r"\s+", "", raw_suffix).lower()
        if not normalized:
            return None, None

        time_match = re.search(r"-?(?:time|t)=", normalized)
        mod_part = normalized
        time_text = None
        if time_match is not None:
            mod_part = normalized[:time_match.start()]
            time_text = normalized[time_match.end():]
            if not time_text:
                raise ValueError("命令格式不正确")

        mod_text = None
        if mod_part:
            if not mod_part.startswith("+") or mod_part.endswith("+"):
                raise ValueError("命令格式不正确")
            mod_text = mod_part[1:]
            if not mod_text:
                raise ValueError("命令格式不正确")

        return mod_text, time_text
