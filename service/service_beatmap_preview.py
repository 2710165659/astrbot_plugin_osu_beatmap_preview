from __future__ import annotations

import json
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


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
            # chmod may fail if we don't own the file; let the subprocess
            # call fail with its own PermissionError for a clear message.
            pass


class BeatmapPreviewService:
    """通过调用 Rust 二进制文件生成 osu! 谱面预览图"""

    def __init__(self, plugin_root: Path) -> None:
        self.plugin_root = plugin_root
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
        mod_text: str | None = None,
        time_text: str | None = None,
    ) -> dict[str, Any]:
        # 命令层只允许纯数字 bid。
        bid = bid.strip()
        if not bid.isdigit():
            raise Exception("只支持纯数字 bid，例如：/v 5199917")

        # 构建命令行参数
        args = [str(self.binary_path), "--bid", bid]

        if convert:
            args += ["--convert", convert]
        if fmt:
            args += ["--fmt", fmt]
        if mod_text:
            args += ["--mods", mod_text]
        if time_text:
            args += ["--time", time_text]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            raise Exception("预览生成超时，请稍后再试")
        except (FileNotFoundError, PermissionError) as exc:
            hint = ""
            if sys.platform != "win32":
                hint = "\n如果刚下载了核心，请运行 chmod +x {} 赋予执行权限".format(
                    self.binary_path
                )
            raise Exception(
                f"无法执行核心二进制文件: {self.binary_path}\n"
                f"{exc}{hint}"
            )

        if result.returncode != 0:
            # 尝试从 JSON 提取 msg，回退到 stderr/stdout
            try:
                err_payload = json.loads(result.stdout or result.stderr)
                error_msg = err_payload.get("msg", "未知错误")
            except json.JSONDecodeError:
                error_msg = result.stderr.strip() or result.stdout.strip() or "未知错误"
            raise Exception(error_msg)

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise Exception(f"核心返回了无效的 JSON：{result.stdout[:200]}")

        if payload.get("status") == "error":
            raise Exception(payload.get("msg", "未知错误"))

        # 统一预览图路径
        preview_img = payload.get("preview-img", "")
        if preview_img:
            payload["preview-img"] = str(Path(preview_img).resolve())

        return payload
