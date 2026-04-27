from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


class BeatmapPreviewService:
    """把谱面预览 core 隔离在本地 service 层"""

    def __init__(self, plugin_root: Path) -> None:
        self.plugin_root = plugin_root
        self.skill_root = plugin_root / "osu-beatmap-preview"

    def generate_from_bid(self, bid: str) -> dict[str, Any]:
        # 命令层只允许纯数字 bid。
        bid = bid.strip()
        if not bid.isdigit():
            raise Exception("只支持纯数字 bid，例如：/预览 5199917")

        # core skill 的 import 入口是 `scripts.beatmap_preview...`。
        # 在这里处理导入细节，main.py 不需要感知 core 目录结构。
        if str(self.skill_root) not in sys.path:
            sys.path.insert(0, str(self.skill_root))

        from scripts.beatmap_preview.errors import PreviewError
        from scripts.beatmap_preview.service import generate_preview

        try:
            payload = generate_preview(bid, self.skill_root)
        except PreviewError as exc:
            raise Exception(f"谱面预览生成失败：{exc}") from exc

        payload["preview-img"] = str(Path(str(payload["preview-img"])).resolve())
        return payload
