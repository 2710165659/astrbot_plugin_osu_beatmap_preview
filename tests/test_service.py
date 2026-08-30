from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from service.service_beatmap_preview import BeatmapPreviewService


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class BeatmapPreviewServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BeatmapPreviewService(PLUGIN_ROOT)
        self.service._binary_path = Path("core.exe")

    def test_builds_v108_repeated_cli_arguments(self) -> None:
        args = self.service.build_args(
            "123",
            fmt="mp4",
            convert="mania",
            mods=("4k", "dt1.2"),
            time_points=("-2",),
            duration_time=12,
            no_cache=True,
        )

        self.assertEqual(args[:7], [
            "core.exe",
            "--bid",
            "123",
            "--convert",
            "mania",
            "--fmt",
            "mp4",
        ])
        self.assertEqual(args.count("--mod"), 2)
        self.assertIn("--time-points", args)
        self.assertIn("--duration-time", args)
        self.assertIn("--no-cache", args)
        for retired_flag in (
            "--mods",
            "--time",
            "--gap",
            "--gif-clip",
            "--gif-clip-label",
            "--preview-30s",
        ):
            self.assertNotIn(retired_flag, args)

        config = json.loads(args[args.index("--config") + 1])
        self.assertEqual(config["layout"]["taiko"]["gif"]["FPS"], 30.0)
        self.assertEqual(config["layout"]["mania"]["mp4"]["FPS"], 30)

    def test_core_timeouts_use_fixed_defaults(self) -> None:
        schema = json.loads((PLUGIN_ROOT / "_conf_schema.json").read_text("utf-8"))
        config = self.service.build_config("default")["timeouts"]["render"]

        self.assertNotIn("image_timeout_seconds", schema)
        self.assertNotIn("video_timeout_seconds", schema)
        self.assertEqual(config["PNG_TIMEOUT"], 60)
        self.assertEqual(config["GIF_TIMEOUT"], 60)
        self.assertEqual(config["MP4_TIMEOUT"], 120)

    def test_vgc_and_vgcl_profiles_are_single_cell(self) -> None:
        default = self.service.build_config("default")
        vgc = self.service.build_config("vgc")
        vgcl = self.service.build_config("vgcl")

        self.assertEqual(default["layout"]["mania"]["gif"]["DURATION_MS"], 5000)
        for mode in ("standard", "taiko", "catch", "mania"):
            self.assertFalse(vgc["layout"][mode]["gif"]["SHOW_TIME_LABEL"])
            self.assertTrue(vgcl["layout"][mode]["gif"]["SHOW_TIME_LABEL"])
            self.assertEqual(vgc["layout"][mode]["gif"]["DURATION_MS"], 10000)
        for mode in ("standard", "catch"):
            self.assertEqual(vgc["layout"][mode]["gif"]["ROW_COUNT"], 1)
            self.assertEqual(vgc["layout"][mode]["gif"]["IMAGES_PER_ROW"], 1)
        self.assertEqual(vgc["layout"]["taiko"]["gif"]["ROW_COUNT"], 1)
        self.assertEqual(vgc["layout"]["mania"]["gif"]["IMAGES_PER_ROW"], 1)

    def test_dynamic_gap_and_clip_duration_merge_with_profile(self) -> None:
        config = self.service.build_config(
            "vgcl",
            taiko_gap=500,
            gif_duration_ms=12500,
        )

        self.assertEqual(
            config["layout"]["taiko"]["png"]["SPACING_PER_BPM"],
            500,
        )
        for mode in ("standard", "taiko", "catch", "mania"):
            self.assertEqual(config["layout"][mode]["gif"]["DURATION_MS"], 12500)
            self.assertTrue(config["layout"][mode]["gif"]["SHOW_TIME_LABEL"])

    def test_schema_json_defaults_are_valid(self) -> None:
        schema = json.loads((PLUGIN_ROOT / "_conf_schema.json").read_text("utf-8"))

        for key in ("default_json",):
            with self.subTest(key=key):
                self.assertIsInstance(json.loads(schema[key]["default"]), dict)

    def test_webui_json_changes_apply_to_next_build(self) -> None:
        live_config = {
            "default_json": '{"layout":{"standard":{"gif":{"FPS":45}}}}',
        }
        service = BeatmapPreviewService(PLUGIN_ROOT, config=live_config)

        self.assertEqual(
            service.build_config("vgc")["layout"]["standard"]["gif"]["FPS"],
            45,
        )
        live_config["default_json"] = '{"layout":{"standard":{"gif":{"FPS":60}}}}'
        self.assertEqual(
            service.build_config("vgc")["layout"]["standard"]["gif"]["FPS"],
            60,
        )

    def test_invalid_webui_json_reports_config_key(self) -> None:
        service = BeatmapPreviewService(
            PLUGIN_ROOT,
            config={"default_json": "{\"layout\":["},
        )

        with self.assertRaisesRegex(ValueError, "default_json JSON 格式错误"):
            service.build_config("default")

    def test_rejects_invalid_gap_values(self) -> None:
        self.service.build_args("123", taiko_gap=0)
        self.service.build_args("123", taiko_gap=500)
        for gap in (-0.1, 500.1, float("nan"), float("inf")):
            with self.subTest(gap=gap), self.assertRaisesRegex(ValueError, "gap"):
                self.service.build_args("123", taiko_gap=gap)

    def test_parses_success_and_error_results(self) -> None:
        success = subprocess.CompletedProcess(
            [],
            0,
            stdout='{"status":"success","preview-img":"out.gif"}',
            stderr="diagnostic",
        )
        self.assertEqual(
            self.service._parse_process_result(success)["status"],
            "success",
        )

        json_error = subprocess.CompletedProcess(
            [],
            1,
            stdout='{"status":"error","msg":"render failed"}',
            stderr="",
        )
        with self.assertRaisesRegex(Exception, "render failed"):
            self.service._parse_process_result(json_error)

        cli_error = subprocess.CompletedProcess(
            [],
            2,
            stdout="",
            stderr="error: unknown argument",
        )
        with self.assertRaisesRegex(Exception, "unknown argument"):
            self.service._parse_process_result(cli_error)

    def test_translates_subprocess_timeout(self) -> None:
        with patch(
            "service.service_beatmap_preview.subprocess.run",
            side_effect=subprocess.TimeoutExpired("core", 1),
        ):
            with self.assertRaisesRegex(TimeoutError, "预览生成超时"):
                self.service.generate_from_bid("123", timeout=1)


if __name__ == "__main__":
    unittest.main()
