from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
import time
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
from service.preview_request import parse_request

V_REQUEST_RE = re.compile(
    r"^\s*/(?P<command>预览|vgcl|vgc|vv|vp|vg|v)(?P<tail>.*)\s*$",
    re.IGNORECASE,
)

HELP_IMG = PLUGIN_ROOT / "help.png"

PYTHON_RENDER_TIMEOUT_SECONDS = 10 * 60


@register(
    "astrbot_plugin_osu_beatmap_preview",
    "xuan_yuan",
    "Generate osu! beatmap preview images and videos from beatmap id via osu-beatmap-preview Rust core.",
    "0.5.0",
)
class BeatmapPreviewPlugin(Star):
    """AstrBot 插件入口"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.preview_service = BeatmapPreviewService(
            plugin_root=PLUGIN_ROOT,
            config=config,
        )
        self.max_image_queue_length = max(
            1, int(config.get("max_image_queue_length", 10))
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
        self._core_download_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """AstrBot calls this after installation, load and reload; don't block it."""
        self._start_core_download(force=True)

    async def _download_core(self, *, force: bool) -> Path:
        start = time.monotonic()
        path = await asyncio.to_thread(self.preview_service.ensure_core, force=force)
        version = self.preview_service.core.version
        logger.info(f"核心更新成功：{version}，耗时 {time.monotonic() - start:.1f} s")
        return path

    def _start_core_download(self, *, force: bool = False) -> asyncio.Task:
        if self._core_download_task is None or self._core_download_task.done():
            self._core_download_task = asyncio.create_task(
                self._download_core(force=force)
            )
            self._core_download_task.add_done_callback(self._log_core_download)
        return self._core_download_task

    @staticmethod
    def _log_core_download(task: asyncio.Task) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error(f"核心下载/更新失败：{error}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def preview_beatmap(self, event: AstrMessageEvent):
        """统一处理 /v、/vp、/vg、/vgc、/vgcl、/vv 指令"""

        raw_text = event.message_obj.message_str
        matched = V_REQUEST_RE.match(raw_text)
        if not matched:
            return

        if matched.group("command").lower() == "v" and matched.group("tail").strip().lower() == "update":
            task = self._start_core_download(force=True)
            yield self._reply_text(event, "核心正在更新，完成前仍可使用旧核心" if self.preview_service.has_core() else "核心正在下载")
            try:
                await asyncio.shield(task)
            except Exception as exc:
                yield self._reply_text(event, f"核心更新失败：{exc}")
            else:
                version = self.preview_service.core.version
                yield self._reply_text(event, f"核心已更新至 {version}")
            return

        core_missing = not self.preview_service.has_core()
        if core_missing:
            self._start_core_download()

        try:
            request = parse_request(
                command=matched.group("command"),
                raw_tail=matched.group("tail"),
            )
        except ValueError as exc:
            yield self._reply_text(event, str(exc) + ("\n核心正在下载" if core_missing else ""))
            return

        if request.bid is None:
            yield event.chain_result([
                Comp.Reply(id=event.message_obj.message_id),
                Comp.Image.fromFileSystem(str(HELP_IMG)),
                *([Comp.Plain(text="核心正在下载")] if core_missing else []),
            ])
            return

        if core_missing:
            yield self._reply_text(event, "暂时无法渲染谱面，核心正在下载，请稍后重新发送命令")
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
            timeout_seconds = PYTHON_RENDER_TIMEOUT_SECONDS
            try:
                async with render_semaphore:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.preview_service.generate_from_bid,
                            request.bid,
                            fmt=request.fmt,
                            convert=request.convert,
                            mods=request.mods,
                            time_points=request.time_points,
                            duration_time=request.duration_time,
                            no_cache=request.no_cache,
                            bg=request.bg,
                            config_profile=request.config_profile,
                            taiko_gap=request.taiko_gap,
                            gif_duration_ms=request.gif_duration_ms,
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
