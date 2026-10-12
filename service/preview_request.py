"""Translate chat syntax; parameter validity belongs to the CLI core."""
from __future__ import annotations

import re
from dataclasses import dataclass

COMMAND_TO_FMT = {
    "v": None, "预览": None, "vp": "png",
    "vg": "gif", "vgc": "gif", "vgcl": "gif", "vv": "mp4",
}
CONVERT_ALIASES = {
    "1": "taiko", "t": "taiko", "taiko": "taiko",
    "2": "ctb", "c": "ctb", "ctb": "ctb", "catch": "ctb",
    "3": "mania", "m": "mania", "mania": "mania",
}


@dataclass(frozen=True)
class PreviewRequest:
    bid: str | None = None
    fmt: str | None = None
    convert: str | None = None
    mods: tuple[str, ...] = ()
    time_points: tuple[str, ...] = ()
    duration_time: float | None = None
    taiko_gap: str | None = None
    no_cache: bool = False
    bg: bool = False
    full_video: bool = False
    config_profile: str = "default"
    gif_duration_ms: int | float | None = None


def parse_request(command: str, raw_tail: str) -> PreviewRequest:
    command = command.lower()
    fmt = COMMAND_TO_FMT[command]
    profile = command if command in {"vgc", "vgcl"} else "default"
    tail = raw_tail.strip()
    if not tail:
        return PreviewRequest(fmt=fmt, config_profile=profile)

    convert = None
    if tail.startswith((":", "：")):
        spec = tail[1:].lstrip()
        match = re.match(r"(taiko|catch|mania|ctb|[tcm123])", spec, re.I)
        if match:
            convert = CONVERT_ALIASES[match[0].lower()]
            tail = spec[match.end():].lstrip()
        else:
            # Unknown conversion values are still passed through for CLI errors.
            parts = spec.split(maxsplit=1)
            convert = parts[0] if parts else ""
            tail = parts[1] if len(parts) > 1 else ""

    bid_match = re.match(r"[^+\s]+", tail)
    if not bid_match:
        raise ValueError("命令格式不正确，请使用 /v 查看说明")
    bid = bid_match[0]
    suffix = re.sub(r"\s+", "", tail[bid_match.end():]).lower()
    flags = {flag: flag in suffix for flag in ("--no-cache", "--full", "--bg")}
    for flag in flags:
        suffix = suffix.replace(flag, "")

    markers = list(re.finditer(r"-?(?:time|t|gap|g)=", suffix))
    mod_part = suffix[:markers[0].start()] if markers else suffix
    mods = tuple(mod_part.removeprefix("+").split("+")) if mod_part else ()
    params = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(suffix)
        key = "time" if marker[0].lstrip("-") in {"t=", "time="} else "gap"
        params[key] = suffix[marker.end():end]

    times = tuple(params["time"].split("+")) if "time" in params else ()
    duration = None
    gif_duration = None
    is_range = fmt == "mp4" or profile in {"vgc", "vgcl"} or (
        convert is not None and fmt in {None, "png"}
    )
    if is_range and len(times) == 2:
        # Arithmetic converts chat end-times to CLI durations, without checking
        # sign/order. If values aren't numeric, pass them verbatim to the CLI.
        try:
            duration = float(times[1]) - float(times[0])
        except ValueError:
            pass
        else:
            times = (times[0],)
            if profile in {"vgc", "vgcl"}:
                gif_duration = duration * 1000
                try:
                    gif_duration = round(gif_duration)
                except (ValueError, OverflowError):
                    pass
                duration = None
    elif "time" not in params and fmt == "mp4" and not flags["--full"]:
        times, duration = ("preview",), 30.0

    return PreviewRequest(
        bid=bid, fmt=fmt, convert=convert, mods=mods, time_points=times,
        duration_time=duration, taiko_gap=params.get("gap"),
        no_cache=flags["--no-cache"], bg=flags["--bg"],
        full_video=flags["--full"], config_profile=profile,
        gif_duration_ms=gif_duration,
    )
