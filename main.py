from __future__ import annotations

import asyncio
import base64
import inspect
import os
import re
import sys
import time
from dataclasses import dataclass
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
    r"^\s*/(?P<command>预览|vgcl|vgc|vv|vp|vg|v)(?P<tail>.*)\s*$",
    re.IGNORECASE,
)

HELP_IMG = PLUGIN_ROOT / "help.png"

COMMAND_TO_FMT = {
    "v": None,
    "vp": "png",
    "vg": "gif",
    "vgc": "gif",
    "vgcl": "gif",
    "vv": "mp4",
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


@dataclass(frozen=True)
class PreviewRequest:
    """解析后的聊天请求，避免在新增模式时扩展位置元组。"""

    bid: str | None
    fmt: str | None
    convert: str | None
    mod_text: str | None
    time_text: str | None
    gap_text: str | None
    no_cache: bool
    full_video: bool = False
    gif_clip: bool = False
    gif_clip_label: bool = False


@register(
    "astrbot_plugin_osu_beatmap_preview",
    "xuan_yuan",
    "Generate osu! beatmap preview images and videos from beatmap id via osu-beatmap-preview Rust core.",
    "0.2.5",
)
class BeatmapPreviewPlugin(Star):
    """AstrBot 插件入口"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.preview_service = BeatmapPreviewService(plugin_root=PLUGIN_ROOT)
        legacy_timeout_seconds = config.get("preview_timeout_seconds", None)
        image_timeout_seconds = config.get(
            "image_timeout_seconds", legacy_timeout_seconds or 60
        )
        video_timeout_seconds = config.get(
            "video_timeout_seconds", legacy_timeout_seconds or 120
        )
        legacy_image_queue_length = config.get("max_concurrency", 10)
        self.image_timeout_seconds = max(1, int(image_timeout_seconds))
        self.video_timeout_seconds = max(1, int(video_timeout_seconds))
        self.max_image_queue_length = max(
            1, int(config.get("max_image_queue_length", legacy_image_queue_length))
        )
        self.max_video_queue_length = max(
            1, int(config.get("max_video_queue_length", 3))
        )
        self._image_render_semaphore = asyncio.Semaphore(1)
        self._video_render_semaphore = asyncio.Semaphore(1)
        self._image_queue_lock = asyncio.Lock()
        self._image_queue_size = 0
        self._video_queue_lock = asyncio.Lock()
        self._video_queue_size = 0

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def preview_beatmap(self, event: AstrMessageEvent):
        """统一处理 /v、/vp、/vg、/vgc、/vgcl、/vv 指令"""

        raw_text = event.message_obj.message_str
        matched = V_REQUEST_RE.match(raw_text)
        if not matched:
            return

        try:
            request = self._parse_request(
                command=matched.group("command"),
                raw_tail=matched.group("tail"),
            )
        except ValueError as exc:
            yield self._reply_text(event, str(exc))
            return

        if request.bid is None:
            yield event.chain_result([
                Comp.Reply(id=event.message_obj.message_id),
                Comp.Image.fromFileSystem(str(HELP_IMG)),
            ])
            return

        is_video = request.fmt == "mp4"
        queue_position = None
        if is_video:
            async with self._video_queue_lock:
                if self._video_queue_size < self.max_video_queue_length:
                    self._video_queue_size += 1
                    queue_position = self._video_queue_size

            if queue_position is None:
                yield self._reply_text(event, "视频渲染队列已满，请稍后再试")
                return
        else:
            async with self._image_queue_lock:
                if self._image_queue_size < self.max_image_queue_length:
                    self._image_queue_size += 1
                    queue_position = self._image_queue_size

            if queue_position is None:
                yield self._reply_text(event, "图片渲染队列已满，请稍后再试")
                return

        try:
            if is_video and request.full_video:
                yield self._reply_text(
                    event,
                    f"已加入视频渲染队列（{queue_position}/{self.max_video_queue_length}）",
                )

            t0 = time.monotonic()
            render_semaphore = (
                self._video_render_semaphore if is_video else self._image_render_semaphore
            )
            timeout_seconds = (
                self.video_timeout_seconds if is_video else self.image_timeout_seconds
            )
            try:
                async with render_semaphore:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._generate_from_bid,
                            request.bid,
                            fmt=request.fmt,
                            convert=request.convert,
                            mod_text=request.mod_text,
                            time_text=request.time_text,
                            gap_text=request.gap_text,
                            no_cache=request.no_cache,
                            gif_clip=request.gif_clip,
                            gif_clip_label=request.gif_clip_label,
                            preview_30s=(
                                is_video
                                and request.time_text is None
                                and not request.full_video
                            ),
                            timeout=timeout_seconds,
                        ),
                        timeout=timeout_seconds,
                    )
                preview_path = result["preview-img"]
                if not preview_path or not Path(preview_path).exists():
                    raise FileNotFoundError("生成的预览文件不存在")
            except asyncio.TimeoutError:
                logger.warning(f"[{request.bid}] 生成失败：超时（>{timeout_seconds}s）")
                yield self._reply_text(event, "谱面预览生成超时，请稍后再试")
                return
            except TimeoutError:
                logger.warning(f"[{request.bid}] 生成失败：超时（>{timeout_seconds}s）")
                yield self._reply_text(event, "谱面预览生成超时，请稍后再试")
                return
            except Exception as exc:
                logger.error(f"[{request.bid}] 生成失败：{exc}", exc_info=True)
                yield self._reply_text(event, "谱面预览生成失败：" + str(exc))
                return

            elapsed = time.monotonic() - t0
            size_kb = os.path.getsize(preview_path) / 1024
            logger.info(f"[{request.bid}] 生成成功，耗时 {elapsed:.1f} s，文件：{Path(preview_path).name}（{size_kb:.1f} KB）")

            if is_video:
                video_data = await asyncio.to_thread(
                    self._encode_video_base64,
                    preview_path,
                )
                preview_component = Comp.Video(file=f"base64://{video_data}")
            else:
                preview_component = Comp.Image.fromFileSystem(preview_path)

            if is_video:
                yield event.chain_result([preview_component])
            else:
                yield event.chain_result([
                    Comp.Reply(id=event.message_obj.message_id),
                    preview_component,
                ])
        finally:
            if queue_position is not None and is_video:
                async with self._video_queue_lock:
                    self._video_queue_size -= 1
            elif queue_position is not None:
                async with self._image_queue_lock:
                    self._image_queue_size -= 1

    @staticmethod
    def _reply_text(event: AstrMessageEvent, text: str):
        return event.chain_result(
            [
                Comp.Reply(id=event.message_obj.message_id),
                Comp.Plain(text=text),
            ]
        )

    @staticmethod
    def _encode_video_base64(path: str) -> str:
        return base64.b64encode(Path(path).read_bytes()).decode("ascii")

    def _generate_from_bid(
        self,
        bid: str,
        *,
        fmt: str | None,
        convert: str | None,
        mod_text: str | None,
        time_text: str | None,
        gap_text: str | None,
        no_cache: bool,
        gif_clip: bool,
        gif_clip_label: bool,
        preview_30s: bool,
        timeout: int,
    ):
        kwargs = {
            "fmt": fmt,
            "convert": convert,
            "mod_text": mod_text,
            "time_text": time_text,
            "gap_text": gap_text,
            "no_cache": no_cache,
        }
        signature = inspect.signature(self.preview_service.generate_from_bid)
        parameters = signature.parameters
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        for name, value in (
            ("gif_clip", gif_clip),
            ("gif_clip_label", gif_clip_label),
            ("preview_30s", preview_30s),
            ("timeout", timeout),
        ):
            if name in parameters or accepts_kwargs:
                kwargs[name] = value
        return self.preview_service.generate_from_bid(bid, **kwargs)

    def _parse_request(
        self,
        command: str,
        raw_tail: str,
    ) -> PreviewRequest:
        command_key = command.lower()
        fmt = COMMAND_TO_FMT[command_key]
        gif_clip = command_key == "vgc"
        gif_clip_label = command_key == "vgcl"
        tail = raw_tail.strip()
        if not tail:
            return PreviewRequest(
                None,
                fmt,
                None,
                None,
                None,
                None,
                False,
                gif_clip=gif_clip,
                gif_clip_label=gif_clip_label,
            )

        convert = None
        if tail.startswith((":", "：")):
            convert, tail = self._parse_convert_spec(tail[1:].lstrip())

        tail = tail.lstrip()
        bid_match = re.match(r"^\d+", tail)
        if bid_match is None:
            raise ValueError("命令格式不正确")

        bid = bid_match.group(0)
        suffix = tail[bid_match.end():]
        mod_text, time_text, gap_text, no_cache, full_video = self._parse_suffix(suffix)
        if full_video and fmt != "mp4":
            raise ValueError("--full 仅适用于 /vv 视频命令")
        if full_video and time_text is not None:
            raise ValueError("--full 不能与视频时间范围同时使用")
        if fmt == "mp4" and time_text is not None:
            time_points = [part for part in time_text.split("+") if part]
            if len(time_points) != 2:
                raise ValueError("视频时间范围需要两个时间点，例如：t=30+60")
        if (gif_clip or gif_clip_label) and time_text is not None:
            time_points = [part for part in time_text.split("+") if part]
            if len(time_points) != 2:
                raise ValueError("GIF 单屏模式的时间范围需要两个时间点，例如：t=30+40")
        return PreviewRequest(
            bid,
            fmt,
            convert,
            mod_text,
            time_text,
            gap_text,
            no_cache,
            full_video=full_video,
            gif_clip=gif_clip,
            gif_clip_label=gif_clip_label,
        )

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

    def _parse_suffix(
        self,
        raw_suffix: str,
    ) -> tuple[str | None, str | None, str | None, bool, bool]:
        normalized = re.sub(r"\s+", "", raw_suffix).lower()
        if not normalized:
            return None, None, None, False, False

        # 独立解析尾部开关，允许 --full 与 --no-cache 以任意顺序组合。
        no_cache = False
        full_video = False
        if "--no-cache" in normalized:
            no_cache = True
            normalized = normalized.replace("--no-cache", "")
        if "--full" in normalized:
            full_video = True
            normalized = normalized.replace("--full", "")
        if not normalized:
            return None, None, None, no_cache, full_video

        gap_match = re.search(r"(?:gap|g)=", normalized)
        time_match = re.search(r"-?(?:time|t)=", normalized)

        # mod_part 截止于第一个 = 参数之前
        cut = len(normalized)
        if gap_match is not None:
            cut = min(cut, gap_match.start())
        if time_match is not None:
            cut = min(cut, time_match.start())

        mod_part = normalized[:cut]
        param_part = normalized[cut:]

        # 依次解析 param_part 中的 gap=/g= 和 t=/time=
        gap_text = None
        time_text = None
        pos = 0
        while pos < len(param_part):
            m_gap = re.match(r"(?:gap|g)=", param_part[pos:])
            m_time = re.match(r"-?(?:time|t)=", param_part[pos:])
            if m_gap:
                pos += m_gap.end()
                n_gap = re.search(r"(?:gap|g)=", param_part[pos:])
                n_time = re.search(r"-?(?:time|t)=", param_part[pos:])
                end = len(param_part)
                if n_gap is not None:
                    end = min(end, pos + n_gap.start())
                if n_time is not None:
                    end = min(end, pos + n_time.start())
                gap_text = param_part[pos:end]
                pos = end
                if not gap_text:
                    raise ValueError("命令格式不正确")
                try:
                    float(gap_text)
                except ValueError:
                    raise ValueError("命令格式不正确")
            elif m_time:
                pos += m_time.end()
                n_gap = re.search(r"(?:gap|g)=", param_part[pos:])
                n_time = re.search(r"-?(?:time|t)=", param_part[pos:])
                end = len(param_part)
                if n_gap is not None:
                    end = min(end, pos + n_gap.start())
                if n_time is not None:
                    end = min(end, pos + n_time.start())
                time_text = param_part[pos:end]
                pos = end
                if not time_text:
                    raise ValueError("命令格式不正确")
            else:
                raise ValueError("命令格式不正确")

        mod_text = None
        if mod_part:
            if not mod_part.startswith("+") or mod_part.endswith("+"):
                raise ValueError("命令格式不正确")
            mod_text = mod_part[1:]
            if not mod_text:
                raise ValueError("命令格式不正确")

        return mod_text, time_text, gap_text, no_cache, full_video
