"""Download only the host CLI asset, without pinning a release or using GitHub API."""
from __future__ import annotations

import logging
import os
import platform
import re
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from threading import Condition

logger = logging.getLogger(__name__)
MIRRORS = (
    "https://ghfast.top/",
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
)
SOCKET_TIMEOUT = 20
SOURCE_TIMEOUT = 180
MAX_BYTES = 512 * 1024 * 1024


class CoreAccess:
    """Allow simultaneous renders, but wait for all of them before replacement."""

    def __init__(self):
        self.condition = Condition()
        self.readers = 0
        self.writers = 0

    @contextmanager
    def render(self):
        with self.condition:
            self.condition.wait_for(lambda: self.writers == 0)
            self.readers += 1
        try:
            yield
        finally:
            with self.condition:
                self.readers -= 1
                self.condition.notify_all()

    @contextmanager
    def replace(self):
        with self.condition:
            self.writers += 1
            self.condition.wait_for(lambda: self.readers == 0)
            try:
                yield
            finally:
                self.writers -= 1
                self.condition.notify_all()


def _validate_binary(path: Path, asset: str) -> None:
    """Reject HTML/error pages and binaries for a different OS or architecture."""
    with path.open("rb") as file:
        header = file.read(64)
        if len(header) < 64:
            raise ValueError("下载内容过短，不是有效核心")
        if "windows" in asset:
            if header[:2] != b"MZ":
                raise ValueError("下载内容不是 Windows 可执行文件")
            file.seek(struct.unpack_from("<I", header, 60)[0])
            pe = file.read(6)
            if pe != b"PE\0\0\x64\x86":
                raise ValueError("下载内容不是 Windows amd64 核心")
        elif "linux" in asset:
            if (header[:6] != b"\x7fELF\x02\x01"
                    or struct.unpack_from("<H", header, 18)[0] != 62):
                raise ValueError("下载内容不是 Linux amd64 核心")
        elif "macos" in asset:
            cpu = 0x0100000C if "arm64" in asset else 0x01000007
            if (header[:4] != b"\xcf\xfa\xed\xfe"
                    or struct.unpack_from("<I", header, 4)[0] != cpu):
                raise ValueError("下载内容不是对应架构的 macOS 核心")


def _download(url: str, path: Path, asset: str) -> None:
    request = urllib.request.Request(url, headers={
        "User-Agent": "astrbot-osu-beatmap-preview/0.5.0",
        "Accept": "application/octet-stream",
        "Accept-Encoding": "identity",
    })
    deadline = time.monotonic() + SOURCE_TIMEOUT
    with urllib.request.urlopen(request, timeout=SOCKET_TIMEOUT) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/" in content_type or "json" in content_type:
            raise ValueError(f"下载返回了错误页面: {content_type}")
        length = response.headers.get("Content-Length")
        expected = int(length) if length is not None else None
        if expected is not None and not 0 < expected <= MAX_BYTES:
            raise ValueError("核心文件大小异常")
        received = 0
        with path.open("wb") as file:
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError("下载来源超时")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_BYTES:
                    raise ValueError("核心文件过大")
                file.write(chunk)
            file.flush()
            os.fsync(file.fileno())
        if expected is not None and received != expected:
            raise ValueError("核心文件未下载完整")
    _validate_binary(path, asset)


def _core_version(path: Path) -> str:
    result = subprocess.run(
        [str(path), "--version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=15,
    )
    if result.returncode != 0:
        raise ValueError("下载核心无法执行 --version：" + result.stderr.strip())
    matched = re.search(r"\bv?(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)\b", result.stdout)
    if not matched:
        raise ValueError("核心未返回有效版本号：" + result.stdout[:200])
    return "v" + matched[1]


def download_core(repository: str, asset: str, target: Path, access: CoreAccess) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("core_repository 必须是 GitHub 的 owner/repo")
    official = f"https://github.com/{repository}/releases/latest/download/{asset}"
    target.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    # Retry the official source once, then try each independent mirror.
    for url in (official, official, *(prefix + official for prefix in MIRRORS)):
        descriptor, name = tempfile.mkstemp(
            prefix=".core-", suffix=".exe" if os.name == "nt" else ".tmp", dir=target.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        try:
            try:
                _download(url, temporary, asset)
                if os.name != "nt":
                    temporary.chmod(0o755)
                version = _core_version(temporary)
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                logger.warning("核心下载来源失败: %s: %s", url, exc)
                continue
            # Installation failures must not re-download hundreds of MB.
            with access.replace():
                os.replace(temporary, target)
            return version
        finally:
            temporary.unlink(missing_ok=True)
    raise RuntimeError("核心下载失败，GitHub 和镜像均不可用，请稍后使用 /v update 重试。\n"
                       + "\n".join(errors))


def _binary_names() -> tuple[str, ...]:
    """当前平台可能的二进制文件名，按优先级排列。

    上游自 1.2.0 起改为 Cargo workspace，CLI 产物名从 `osu-beatmap-preview-*`
    变成 `osu-beatmap-preview-*-cli`；这里同时接受两种命名，旧核心目录无需改名也能继续使用。
    """
    system = sys.platform
    machine = platform.machine().lower()

    if system == "win32" and machine in {"amd64", "x86_64"}:
        stem = "osu-beatmap-preview-windows-amd64"
    elif system == "darwin" and machine in {"amd64", "x86_64", "arm64", "aarch64"}:
        stem = (
            "osu-beatmap-preview-macos-arm64"
            if machine in {"arm64", "aarch64"}
            else "osu-beatmap-preview-macos-amd64"
        )
    elif system == "linux" and machine in {"amd64", "x86_64"}:
        stem = "osu-beatmap-preview-linux-amd64"
    else:
        raise Exception(f"暂无对应的平台核心: {system}/{machine}")

    suffix = ".exe" if system == "win32" else ""
    return (f"{stem}-cli{suffix}", f"{stem}{suffix}")


def _detect_binary_path(plugin_root: Path) -> Path:
    """Detect the platform and return the path to the appropriate binary."""
    bin_dir = plugin_root / "bin"
    candidates = [bin_dir / name for name in _binary_names()]

    for binary_path in candidates:
        if binary_path.is_file():
            return binary_path

    expected = "\n".join(f"  - {path.name}" for path in candidates)
    raise Exception(
        f"核心二进制文件不存在，已尝试以下文件名:\n{expected}\n"
        f"查找目录: {bin_dir}\n"
        f"请使用 /v update 下载最新核心"
    )


def _ensure_executable(binary_path: Path) -> None:
    """On Unix-like systems, ensure the binary has execute permission."""
    if sys.platform == "win32":
        return

    current_mode = binary_path.stat().st_mode
    if not (current_mode & stat.S_IXUSR):
        try:
            os.chmod(binary_path, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError as exc:
            raise PermissionError(f"无法自动为核心赋予执行权限: {binary_path}: {exc}") from exc


class CoreManager:
    def __init__(self, plugin_root: Path, config=None):
        self.plugin_root = plugin_root
        self.config = config
        self._download_lock = threading.Lock()
        self._execution_lock = CoreAccess()
        self.version: str | None = None

    def has_core(self) -> bool:
        try:
            _detect_binary_path(self.plugin_root)
        except Exception:
            return False
        return True

    def ensure(self, *, force: bool = False) -> Path:
        """Serialize downloads; keep the installed core usable until atomic replacement."""
        with self._download_lock:
            if not force and self.has_core():
                return _detect_binary_path(self.plugin_root)
            names = _binary_names()
            # Replace a legacy-named installation in place as well.
            target = (
                _detect_binary_path(self.plugin_root)
                if self.has_core() else self.plugin_root / "bin" / names[0]
            )
            repository = str((self.config or {}).get(
                "core_repository", "2710165659/osu-beatmap-preview"
            ))
            self.version = download_core(repository, names[0], target, self._execution_lock)
            return target

    @property
    def path(self) -> Path:
        path = self.ensure()
        _ensure_executable(path)
        return path

