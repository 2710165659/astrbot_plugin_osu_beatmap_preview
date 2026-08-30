from __future__ import annotations

import sys
import types
import unittest


def _identity_decorator(*_args, **_kwargs):
    def decorate(value):
        return value

    return decorate


astrbot = types.ModuleType("astrbot")
api = types.ModuleType("astrbot.api")
components = types.ModuleType("astrbot.api.message_components")
event = types.ModuleType("astrbot.api.event")
star = types.ModuleType("astrbot.api.star")
event.filter = types.SimpleNamespace(
    EventMessageType=types.SimpleNamespace(ALL="all"),
    event_message_type=_identity_decorator,
)
event.AstrMessageEvent = object
star.Context = object
star.Star = object
star.register = _identity_decorator
api.AstrBotConfig = dict
api.logger = types.SimpleNamespace()
sys.modules.update({
    "astrbot": astrbot,
    "astrbot.api": api,
    "astrbot.api.message_components": components,
    "astrbot.api.event": event,
    "astrbot.api.star": star,
})

from main import BeatmapPreviewPlugin


class PreviewRequestParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(BeatmapPreviewPlugin)

    def test_regular_gif_keeps_multiple_time_points_and_splits_mods(self) -> None:
        request = self.plugin._parse_request(
            "vg",
            "123+4k+ds+in+dt1.2 t=10+30+50 --no-cache",
        )

        self.assertEqual(request.mods, ("4k", "ds", "in", "dt1.2"))
        self.assertEqual(request.time_points, ("10", "30", "50"))
        self.assertIsNone(request.duration_time)
        self.assertTrue(request.no_cache)
        self.assertEqual(request.config_profile, "default")

    def test_default_video_uses_preview_for_thirty_seconds(self) -> None:
        request = self.plugin._parse_request("vv", "123")

        self.assertEqual(request.time_points, ("preview",))
        self.assertEqual(request.duration_time, 30.0)
        self.assertFalse(request.full_video)

    def test_video_range_becomes_start_and_duration(self) -> None:
        request = self.plugin._parse_request("vv", "123 t=-2+10")

        self.assertEqual(request.time_points, ("-2",))
        self.assertEqual(request.duration_time, 12.0)

    def test_full_video_has_no_explicit_time_options(self) -> None:
        request = self.plugin._parse_request("vv", "123 --full")

        self.assertEqual(request.time_points, ())
        self.assertIsNone(request.duration_time)
        self.assertTrue(request.full_video)

    def test_clip_profiles_and_custom_duration(self) -> None:
        vgc = self.plugin._parse_request("vgc", "123")
        vgcl = self.plugin._parse_request("vgcl", "123 t=-2+10")

        self.assertEqual(vgc.config_profile, "vgc")
        self.assertIsNone(vgc.gif_duration_ms)
        self.assertEqual(vgcl.config_profile, "vgcl")
        self.assertEqual(vgcl.time_points, ("-2",))
        self.assertEqual(vgcl.gif_duration_ms, 12000)

    def test_taiko_gap_boundaries_and_conversion_alias(self) -> None:
        lower = self.plugin._parse_request("vp", ":t 123 gap=0")
        upper = self.plugin._parse_request("vp", ":taiko 123 g=500")

        self.assertEqual(lower.convert, "taiko")
        self.assertEqual(lower.taiko_gap, 0)
        self.assertEqual(upper.convert, "taiko")
        self.assertEqual(upper.taiko_gap, 500)

    def test_rejects_invalid_ranges_flags_and_numbers(self) -> None:
        cases = (
            ("vv", "123 t=10+10", "终点必须大于起点"),
            ("vv", "123 t=20+10", "终点必须大于起点"),
            ("vv", "123 t=10", "需要两个时间点"),
            ("vgc", "123 t=nan+10", "有限数字"),
            ("vp", "123 gap=-1", "gap"),
            ("vp", "123 gap=501", "gap"),
            ("vv", "123 t=1+2 --full", "不能与视频时间范围"),
            ("vg", "123 --full", "仅适用于 /vv"),
            ("vg", "123+hd++hr", "命令格式不正确"),
        )
        for command, tail, message in cases:
            with self.subTest(command=command, tail=tail):
                with self.assertRaisesRegex(ValueError, message):
                    self.plugin._parse_request(command, tail)


if __name__ == "__main__":
    unittest.main()
