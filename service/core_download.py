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
from urllib.parse import quote, unquote, urlsplit
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
    """旧核心在等待替换期间仍可接收渲染，仅原子替换时独占访问。"""

    def __init__(self):
        self.condition = Condition()
        self.readers = 0

    @contextmanager
    def render(self):
        with self.condition:
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
            self.condition.wait_for(lambda: self.readers == 0)
            # wait_for 会释放锁；新请求可以继续用旧核心，替换本身才持锁。
            yield


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


def latest_release_tag(repository: str) -> str:
    """通过 Release 跳转读取 tag，不下载二进制，也不消耗 GitHub API 配额。"""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("core_repository 必须是 GitHub 的 owner/repo")
    official = f"https://github.com/{repository}/releases/latest"
    errors = []
    for url in (official, official, *(prefix + official for prefix in MIRRORS)):
        try:
            request = urllib.request.Request(url, method="HEAD", headers={
                "User-Agent": "astrbot-osu-beatmap-preview/0.5.0",
            })
            with urllib.request.urlopen(request, timeout=SOCKET_TIMEOUT) as response:
                path = urlsplit(response.geturl()).path
                prefix = f"/{repository}/releases/tag/"
                if response.status != 200 or prefix not in path:
                    raise ValueError("无法从 Release 跳转读取版本 tag")
                tag = unquote(path.split(prefix, 1)[1])
                if not re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][\w.-]+)?", tag):
                    raise ValueError(f"不支持的核心版本 tag：{tag}")
                return tag
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            logger.warning("核心版本检查来源失败: %s: %s", url, exc)
    raise RuntimeError("核心版本检查失败，保留现有核心。\n" + "\n".join(errors))


def download_core(
    repository: str, asset: str, target: Path, access: CoreAccess, *, tag: str | None = None
) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("core_repository 必须是 GitHub 的 owner/repo")
    if tag is None:
        tag = latest_release_tag(repository)
    # 固定刚检查的 tag，避免检查和下载期间 latest 变化，或镜像返回旧版本。
    official = f"https://github.com/{repository}/releases/download/{quote(tag, safe='')}/{asset}"
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
                if version != "v" + tag.removeprefix("v"):
                    raise ValueError(f"核心版本 {version} 与 Release tag {tag} 不一致")
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
    def __init__(self, plugin_root: Path, config=None, *, data_dir: Path | None = None):
        self.plugin_root = plugin_root
        self.data_dir = data_dir if data_dir is not None else plugin_root
        self.config = config
        self._download_lock = threading.Lock()
        self._execution_lock = CoreAccess()
        self.version: str | None = None

    def _installed_path(self) -> Path:
        try:
            return _detect_binary_path(self.data_dir)
        except Exception:
            if self.data_dir == self.plugin_root:
                raise
            # 兼容旧安装；后续下载写入插件数据目录，不改动旧文件及其缓存。
            return _detect_binary_path(self.plugin_root)

    def has_core(self) -> bool:
        try:
            self._installed_path()
        except Exception:
            return False
        return True

    def ensure(self, *, force: bool = False) -> Path:
        """force 表示检查最新 tag；相同版本保持文件和修改时间不变。"""
        # 普通渲染必须在下载锁外取得旧核心，否则会等待整段网络下载。
        if not force and self.has_core():
            return self._installed_path()
        with self._download_lock:
            if not force and self.has_core():
                return self._installed_path()
            names = _binary_names()
            repository = str((self.config or {}).get(
                "core_repository", "2710165659/osu-beatmap-preview"
            ))
            tag = latest_release_tag(repository)
            if self.has_core():
                installed = self._installed_path()
                _ensure_executable(installed)
                try:
                    self.version = _core_version(installed)
                except (OSError, ValueError, subprocess.SubprocessError):
                    logger.warning("现有核心无法读取版本，将重新下载", exc_info=True)
                else:
                    if self.version == "v" + tag.removeprefix("v"):
                        logger.info("核心已是最新版本 %s，跳过下载", self.version)
                        return installed
            target = self.data_dir / "bin" / names[0]
            self.version = download_core(
                repository, names[0], target, self._execution_lock, tag=tag
            )
            return target

    @property
    def path(self) -> Path:
        path = self.ensure()
        _ensure_executable(path)
        return path

