from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core_config import CoreConfig
from .core_download import CoreManager

PYTHON_RENDER_TIMEOUT_SECONDS = 60 * 60
DEFAULT_CORE_ENV = "OSU_CLIENT_ID=''\nOSU_CLIENT_SECRET=''\n"


class BeatmapPreviewService:
    """通过调用 Rust 二进制文件生成 osu! 谱面预览图和视频。"""

    def __init__(
        self, plugin_root: Path, config: Mapping[str, Any] | None = None,
        *, data_dir: Path | None = None,
    ) -> None:
        self.core = CoreManager(plugin_root, config, data_dir=data_dir)
        self.config = config
        self.config_loader = CoreConfig(config)

    def has_core(self) -> bool:
        return self.core.has_core()

    def ensure_core(self, *, force: bool = False) -> Path:
        return self.core.ensure(force=force)

    @property
    def binary_path(self) -> Path:
        return self.core.path

    def generate_from_bid(
        self, bid: str, *, timeout: int = PYTHON_RENDER_TIMEOUT_SECONDS, **options: Any
    ) -> dict[str, Any]:
        return self._render(self.build_args(bid, **options), timeout)

    def generate_custom(
        self, args: Sequence[str], *, timeout: int = PYTHON_RENDER_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        return self._render([str(self.binary_path), *args], timeout)

    def _render(self, args: list[str], timeout: int) -> dict[str, Any]:
        # Read immediately before execution, without changing AstrBot's environment.
        env = self._build_core_env()
        try:
            with self.core._execution_lock.render():
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    env=env,
                )
        except subprocess.TimeoutExpired:
            raise TimeoutError("预览生成超时，请稍后再试")
        except (FileNotFoundError, PermissionError) as exc:
            raise Exception(f"无法执行核心二进制文件: {self.binary_path}\n{exc}")

        payload = self._parse_process_result(result)
        preview_img = payload.get("preview-img", "")
        if preview_img:
            payload["preview-img"] = str(Path(preview_img).resolve())
        return payload

    def _build_core_env(self) -> dict[str, str]:
        env = os.environ.copy()
        contents = (self.config or {}).get("core_env", DEFAULT_CORE_ENV)
        if not isinstance(contents, str):
            raise ValueError("核心环境变量配置必须为文本，每行一个 KEY=VALUE")
        for line_number, line in enumerate(contents.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not separator or not key:
                raise ValueError(f"核心环境变量配置第 {line_number} 行应为 KEY=VALUE")
            if value.startswith(("'", '"')):
                if len(value) < 2 or value[-1] != value[0]:
                    raise ValueError(f"核心环境变量配置第 {line_number} 行引号未闭合")
                value = value[1:-1]
            env[key] = value
        return env

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
        bg: bool = False,
        config_profile: str = "default",
        taiko_gap: str | float | None = None,
        gif_duration_ms: int | None = None,
    ) -> list[str]:
        bid = bid.strip()
        args = [str(self.binary_path), "--bid", bid]
        if convert is not None:
            args += ["--convert", convert]
        if fmt:
            args += ["--fmt", fmt]
        for mod in mods:
            mod = mod.strip()
            args += ["--mod", mod]
        for time_point in time_points:
            time_point = str(time_point).strip()
            args += ["--time-points", time_point]
        if duration_time is not None:
            args += ["--duration-time", str(duration_time)]
        if no_cache:
            args.append("--no-cache")

        config = self.config_loader.build(
            config_profile,
            taiko_gap=taiko_gap,
            gif_duration_ms=gif_duration_ms,
            bg=bg,
        )
        args += [
            "--config",
            json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        ]
        return args

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
