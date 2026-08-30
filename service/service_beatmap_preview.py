from __future__ import annotations

import copy
import json
import math
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

CONFIG_PROFILE_KEYS = {
    "default": ("default_json",),
    "vgc": ("default_json",),
    "vgcl": ("default_json",),
}
GIF_MODES = ("standard", "taiko", "catch", "mania")
PYTHON_RENDER_TIMEOUT_SECONDS = 10 * 60
VGC_CONFIG = {
    "layout": {
        "standard": {"gif": {"ROW_COUNT": 1, "IMAGES_PER_ROW": 1, "SHOW_TIME_LABEL": False, "DURATION_MS": 10000}},
        "taiko": {"gif": {"ROW_COUNT": 1, "SHOW_TIME_LABEL": False, "DURATION_MS": 10000}},
        "catch": {"gif": {"ROW_COUNT": 1, "IMAGES_PER_ROW": 1, "SHOW_TIME_LABEL": False, "DURATION_MS": 10000}},
        "mania": {"gif": {"IMAGES_PER_ROW": 1, "SHOW_TIME_LABEL": False, "DURATION_MS": 10000}},
    }
}
VGCL_CONFIG = {
    "layout": {
        mode: {"gif": {"SHOW_TIME_LABEL": True}}
        for mode in GIF_MODES
    }
}


def _detect_binary_path(plugin_root: Path) -> Path:
    """Detect the platform and return the path to the appropriate binary."""
    system = sys.platform
    machine = platform.machine().lower()

    if system == "win32":
        binary_name = "osu-beatmap-preview-windows-amd64.exe"
    elif system == "darwin":
        if machine == "arm64":
            binary_name = "osu-beatmap-preview-macos-arm64"
        else:
            binary_name = "osu-beatmap-preview-macos-amd64"
    elif system == "linux":
        binary_name = "osu-beatmap-preview-linux-amd64"
    else:
        raise Exception(f"不支持的平台: {system}")

    binary_path = plugin_root / "bin" / binary_name
    if not binary_path.exists():
        update_script = "update_core.bat"
        raise Exception(
            f"核心二进制文件不存在: {binary_path}\n"
            f"请运行 {update_script} 下载最新核心"
        )
    return binary_path


def _ensure_executable(binary_path: Path) -> None:
    """On Unix-like systems, ensure the binary has execute permission."""
    if sys.platform == "win32":
        return

    current_mode = binary_path.stat().st_mode
    if not (current_mode & stat.S_IXUSR):
        try:
            os.chmod(binary_path, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            # Let subprocess report a clearer permission error if chmod is unavailable.
            pass


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    for key, value in overlay.items():
        current = base.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            _deep_merge(current, value)
        else:
            base[key] = copy.deepcopy(value)


def _set_nested(config: dict[str, Any], path: Sequence[str], value: Any) -> None:
    current = config
    for key in path[:-1]:
        child = current.setdefault(key, {})
        if not isinstance(child, dict):
            raise ValueError(f"配置路径 {'.'.join(path)} 与现有标量冲突")
        current = child
    current[path[-1]] = value


class BeatmapPreviewService:
    """通过调用 Rust 二进制文件生成 osu! 谱面预览图和视频。"""

    def __init__(self, plugin_root: Path, config: Mapping[str, Any] | None = None) -> None:
        self.plugin_root = plugin_root
        # Keep the AstrBot config object, not a copied snapshot.  AstrBot may
        # update this object when plugin settings are edited; reading it for
        # every request makes JSON changes effective immediately.
        self.config = config
        self._binary_path: Path | None = None

    @property
    def binary_path(self) -> Path:
        if self._binary_path is None:
            self._binary_path = _detect_binary_path(self.plugin_root)
            _ensure_executable(self._binary_path)
        return self._binary_path

    def generate_from_bid(
        self,
        bid: str,
        *,
        fmt: str | None = None,
        convert: str | None = None,
        mods: Sequence[str] = (),
        time_points: Sequence[str] = (),
        duration_time: float | None = None,
        no_cache: bool = False,
        config_profile: str = "default",
        taiko_gap: float | None = None,
        gif_duration_ms: int | None = None,
        timeout: int = PYTHON_RENDER_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        args = self.build_args(
            bid,
            fmt=fmt,
            convert=convert,
            mods=mods,
            time_points=time_points,
            duration_time=duration_time,
            no_cache=no_cache,
            config_profile=config_profile,
            taiko_gap=taiko_gap,
            gif_duration_ms=gif_duration_ms,
        )

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError("预览生成超时，请稍后再试")
        except (FileNotFoundError, PermissionError) as exc:
            hint = ""
            if sys.platform != "win32":
                hint = f"\n如果刚下载了核心，请运行 chmod +x {self.binary_path} 赋予执行权限"
            raise Exception(f"无法执行核心二进制文件: {self.binary_path}\n{exc}{hint}")

        payload = self._parse_process_result(result)
        preview_img = payload.get("preview-img", "")
        if preview_img:
            payload["preview-img"] = str(Path(preview_img).resolve())
        return payload

    def build_args(
        self,
        bid: str,
        *,
        fmt: str | None = None,
        convert: str | None = None,
        mods: Sequence[str] = (),
        time_points: Sequence[str] = (),
        duration_time: float | None = None,
        no_cache: bool = False,
        config_profile: str = "default",
        taiko_gap: float | None = None,
        gif_duration_ms: int | None = None,
    ) -> list[str]:
        bid = bid.strip()
        if not bid.isdigit():
            raise ValueError("只支持纯数字 bid，例如：/v 5199917")
        if duration_time is not None and (
            not math.isfinite(duration_time) or duration_time <= 0
        ):
            raise ValueError("视频时长必须是有限正数")
        if taiko_gap is not None and (
            not math.isfinite(taiko_gap) or not 0 <= taiko_gap <= 500
        ):
            raise ValueError("gap 必须是 0 到 500 之间的数字")
        if gif_duration_ms is not None and gif_duration_ms <= 0:
            raise ValueError("GIF 片段时长必须大于 0 毫秒")

        args = [str(self.binary_path), "--bid", bid]
        if convert:
            args += ["--convert", convert]
        if fmt:
            args += ["--fmt", fmt]
        for mod in mods:
            mod = mod.strip()
            if not mod:
                raise ValueError("Mod 不能为空")
            args += ["--mod", mod]
        for time_point in time_points:
            time_point = str(time_point).strip()
            if not time_point:
                raise ValueError("时间点不能为空")
            args += ["--time-points", time_point]
        if duration_time is not None:
            args += ["--duration-time", self._format_number(duration_time)]
        if no_cache:
            args.append("--no-cache")

        config = self.build_config(
            config_profile,
            taiko_gap=taiko_gap,
            gif_duration_ms=gif_duration_ms,
        )
        args += [
            "--config",
            json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        ]
        return args

    def build_config(
        self,
        profile: str,
        *,
        taiko_gap: float | None = None,
        gif_duration_ms: int | None = None,
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
            _set_nested(
                merged,
                ("layout", "taiko", "png", "SPACING_PER_BPM"),
                taiko_gap,
            )
        if gif_duration_ms is not None:
            for mode in GIF_MODES:
                _set_nested(
                    merged,
                    ("layout", mode, "gif", "DURATION_MS"),
                    gif_duration_ms,
                )
        return merged

    def _load_config_document(self, key: str) -> Any:
        """Load a JSON document from AstrBot settings or schema defaults."""
        sentinel = object()
        raw: Any = sentinel
        if self.config is not None and key is not None:
            getter = getattr(self.config, "get", None)
            if getter is not None:
                raw = getter(key, sentinel)

        if raw is sentinel:
            # AstrBot populates schema defaults for new installations.  The
            # explicit fallback also keeps direct service users/tests working
            # when no AstrBot config object is supplied.
            schema_path = self.plugin_root / "_conf_schema.json"
            try:
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                raw = schema[key]["default"]
            except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(f"无法读取配置默认值 {schema_path}: {exc}") from exc

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

    @staticmethod
    def _format_number(value: float) -> str:
        return format(value, ".15g")

    @staticmethod
    def _parse_process_result(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        payload: dict[str, Any] | None = None
        if result.stdout:
            try:
                parsed = json.loads(result.stdout)
                if isinstance(parsed, dict):
                    payload = parsed
            except json.JSONDecodeError:
                payload = None

        if result.returncode != 0:
            if payload is not None:
                error_msg = payload.get("msg", "未知错误")
            else:
                error_msg = (
                    (result.stderr or "").strip()
                    or (result.stdout or "").strip()
                    or "未知错误"
                )
            raise Exception(error_msg)

        if payload is None:
            if not result.stdout:
                raise Exception("核心未返回任何输出")
            raise Exception(f"核心返回了无效的 JSON：{result.stdout[:200]}")
        if payload.get("status") == "error":
            raise Exception(payload.get("msg", "未知错误"))
        return payload
