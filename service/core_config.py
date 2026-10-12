from __future__ import annotations

import copy
import json
from typing import Any, Mapping

CONFIG_PROFILE_KEYS = {
    "default": ("default_json",),
    "vgc": ("default_json",),
    "vgcl": ("default_json",),
}
GIF_MODES = ("standard", "taiko", "catch", "mania")
VGC_CONFIG = {
    "render": {
        "standard": {"gif": {"structure": {"ROW_COUNT": 1, "IMAGES_PER_ROW": 1}, "style": {"SHOW_TIME_LABEL": False, "DURATION_MS": 10000}}},
        "taiko": {"gif": {"structure": {"ROW_COUNT": 1}, "style": {"SHOW_TIME_LABEL": False, "DURATION_MS": 10000}}},
        "catch": {"gif": {"structure": {"ROW_COUNT": 1, "IMAGES_PER_ROW": 1}, "style": {"SHOW_TIME_LABEL": False, "DURATION_MS": 10000}}},
        "mania": {"gif": {"structure": {"IMAGES_PER_ROW": 1}, "style": {"SHOW_TIME_LABEL": False, "SHOW_SV_LABEL": False, "DURATION_MS": 10000}}},
    }
}
VGCL_CONFIG = {
    "render": {
        mode: {"gif": {"style": {"SHOW_TIME_LABEL": True}}}
        for mode in GIF_MODES
    }
}
# --bg：渲染背景视频与故事板（上游 v1.4.0 起四模式 mp4 各带这两个开关，默认关闭）。
BG_CONFIG = {
    "render": {
        mode: {
            "mp4": {
                "style": {
                    "ENABLE_BACKGROUND_VIDEO": True,
                    "ENABLE_STORYBOARD": True,
                }
            }
        }
        for mode in GIF_MODES
    }
}


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    for key, value in overlay.items():
        current = base.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            _deep_merge(current, value)
        else:
            base[key] = copy.deepcopy(value)


class CoreConfig:
    def __init__(self, config: Mapping[str, Any] | None):
        self.config = config

    def build(
        self,
        profile: str,
        *,
        taiko_gap: str | float | None = None,
        gif_duration_ms: int | None = None,
        bg: bool = False,
    ) -> dict[str, Any]:
        try:
            config_keys = CONFIG_PROFILE_KEYS[profile]
        except KeyError:
            raise ValueError(f"未知配置 profile: {profile}") from None

        merged: dict[str, Any] = {}
        for key in config_keys:
            loaded = self._load_config_document(key)
            if loaded is None:
                continue
            if not isinstance(loaded, Mapping):
                raise ValueError(f"配置项顶层必须是对象: {key}")
            _deep_merge(merged, loaded)

        if profile == "vgc":
            _deep_merge(merged, VGC_CONFIG)
        elif profile == "vgcl":
            _deep_merge(merged, VGC_CONFIG)
            _deep_merge(merged, VGCL_CONFIG)

        if taiko_gap is not None:
            _deep_merge(
                merged,
                {"render": {"taiko": {"png": {"style": {"SPACING_PER_BPM": taiko_gap}}}}},
            )
        if gif_duration_ms is not None:
            for mode in GIF_MODES:
                _deep_merge(
                    merged,
                    {"render": {mode: {"gif": {"style": {"DURATION_MS": gif_duration_ms}}}}},
                )
        if bg:
            # --bg 开启背景视频与故事板渲染，覆盖 default_json 中的同名开关。
            _deep_merge(merged, BG_CONFIG)
        return merged

    def _load_config_document(self, key: str) -> Any:
        """Load a JSON document from the current AstrBot settings."""
        sentinel = object()
        raw: Any = sentinel
        if self.config is not None and key is not None:
            getter = getattr(self.config, "get", None)
            if getter is not None:
                raw = getter(key, sentinel)

        if raw is sentinel:
            return None

        if isinstance(raw, Mapping):
            return raw
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        if not isinstance(raw, str):
            raise ValueError(f"配置项 {key} 必须是 JSON 文本")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"配置项 {key} JSON 格式错误: {exc}") from exc

