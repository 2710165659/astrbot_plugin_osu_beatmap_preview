from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


class BeatmapPreviewService:
    """把谱面预览 core 隔离在本地 service 层"""

    def __init__(self, plugin_root: Path) -> None:
        self.plugin_root = plugin_root
        self.skill_root = plugin_root / "osu-beatmap-preview"

    def generate_from_bid(
        self,
        bid: str,
        *,
        fmt: str | None = None,
        convert: str | None = None,
        mod_text: str | None = None,
        time_text: str | None = None,
    ) -> dict[str, Any]:
        # 命令层只允许纯数字 bid。
        bid = bid.strip()
        if not bid.isdigit():
            raise Exception("只支持纯数字 bid，例如：/v 5199917")

        # core skill 的 import 入口是 `scripts.beatmap_preview...`。
        # 在这里处理导入细节，main.py 不需要感知 core 目录结构。
        if str(self.skill_root) not in sys.path:
            sys.path.insert(0, str(self.skill_root))

        from scripts.beatmap_preview.errors import PreviewError
        from scripts.beatmap_preview.mods import parse_mods
        from scripts.beatmap_preview.service import generate_preview

        try:
            mod_settings = parse_mods(mod_text) if mod_text else None
            times = self._parse_times(time_text) if time_text else None
            payload = generate_preview(
                bid,
                fmt=fmt,
                convert=convert,
                mods=mod_settings,
                times=times,
            )
        except PreviewError as exc:
            raise Exception(f"谱面预览生成失败：{exc}") from exc

        payload["preview-img"] = str(Path(str(payload["preview-img"])).resolve())
        return payload

    @staticmethod
    def _parse_times(raw: str) -> list[float]:
        parts = [part.strip() for part in raw.split("+") if part.strip()]
        if not parts:
            raise Exception("命令格式不正确，请检查时间参数")
        if len(parts) > 4:
            raise Exception("命令格式不正确，请检查时间参数")

        result: list[float] = []
        for part in parts:
            try:
                value = float(part)
            except ValueError as exc:
                raise Exception("命令格式不正确，请检查时间参数") from exc
            if value < 0:
                raise Exception("命令格式不正确，请检查时间参数")
            result.append(value)
        return result
