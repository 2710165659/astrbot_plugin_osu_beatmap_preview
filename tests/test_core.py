import logging
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from service import core_download as download
from service.core_config import CoreConfig
from service.preview_request import parse_request
from service.service_beatmap_preview import BeatmapPreviewService


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.asset = download._binary_names()[0]
        self.target = self.root / "bin" / self.asset
        self.target.parent.mkdir()
        tag_patch = patch.object(download, "latest_release_tag", return_value="v1.4.1")
        tag_patch.start()
        self.addCleanup(tag_patch.stop)
        version_patch = patch.object(download, "_core_version", return_value="v1.4.0")
        version_patch.start()
        self.addCleanup(version_patch.stop)

    def test_official_then_mirror_and_atomic_replace(self):
        self.target.write_bytes(b"old core")
        sources = []

        def fetch(url, temporary, asset):
            sources.append(url)
            self.assertEqual(self.target.read_bytes(), b"old core")
            temporary.write_bytes(b"new core")
            if len(sources) <= 2:
                raise TimeoutError("offline")

        with patch.object(download, "_download", side_effect=fetch), patch.object(
            download, "_core_version",
            side_effect=lambda path: "v1.4.0" if path == self.target else "v1.4.1",
        ), self.assertLogs(download.logger, logging.WARNING):
            manager = download.CoreManager(self.root)
            manager.ensure(force=True)
        self.assertEqual(sources[:2], [sources[0]] * 2)
        self.assertTrue(sources[2].startswith(download.MIRRORS[0]))
        self.assertEqual(self.target.read_bytes(), b"new core")
        self.assertEqual(manager.version, "v1.4.1")
        self.assertIn("/releases/download/v1.4.1/", sources[0])
        self.assertEqual(list(self.target.parent.iterdir()), [self.target])

    def test_failure_preserves_old_core(self):
        self.target.write_bytes(b"old core")
        with patch.object(download, "_download", side_effect=ValueError("HTML")), self.assertLogs(
            download.logger, logging.WARNING
        ), self.assertRaises(RuntimeError):
            download.CoreManager(self.root).ensure(force=True)
        self.assertEqual(self.target.read_bytes(), b"old core")
        self.assertEqual(list(self.target.parent.iterdir()), [self.target])

    def test_concurrent_missing_core_downloads_once(self):
        def fetch(repository, asset, target, access, *, tag):
            target.write_bytes(b"installed")
            return "v1.4.1"

        manager = download.CoreManager(self.root)
        with patch.object(download, "download_core", side_effect=fetch) as mocked:
            with ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(lambda _: manager.ensure(), range(5)))
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(results, [self.target] * 5)

    def test_same_tag_skips_download_and_preserves_mtime(self):
        self.target.write_bytes(b"existing core")
        before = self.target.stat().st_mtime_ns
        with patch.object(download, "_core_version", return_value="v1.4.1"), patch.object(
            download, "download_core"
        ) as fetch:
            manager = download.CoreManager(self.root)
            self.assertEqual(manager.ensure(force=True), self.target)
        fetch.assert_not_called()
        self.assertEqual(manager.version, "v1.4.1")
        self.assertEqual(self.target.stat().st_mtime_ns, before)

    def test_render_can_use_old_core_during_download(self):
        self.target.write_bytes(b"existing core")
        downloading = threading.Event()
        release = threading.Event()
        manager = download.CoreManager(self.root)

        def fetch(*args, **kwargs):
            downloading.set()
            if not release.wait(3):
                raise TimeoutError("test download timed out")
            return "v1.4.1"

        with patch.object(download, "download_core", side_effect=fetch):
            with ThreadPoolExecutor(max_workers=2) as pool:
                update = pool.submit(manager.ensure, force=True)
                try:
                    self.assertTrue(downloading.wait(1))
                    self.assertEqual(pool.submit(lambda: manager.path).result(1), self.target)
                finally:
                    release.set()
                update.result(1)

    def test_pending_replacement_allows_new_render(self):
        access = download.CoreAccess()
        waiting = threading.Event()
        acquired = threading.Event()
        original_wait = access.condition.wait_for

        def wait(predicate):
            waiting.set()
            return original_wait(predicate)

        def writer():
            with access.replace():
                acquired.set()

        def render():
            with access.render():
                return True

        with patch.object(access.condition, "wait_for", side_effect=wait):
            with ThreadPoolExecutor(max_workers=2) as pool:
                with access.render():
                    update = pool.submit(writer)
                    self.assertTrue(waiting.wait(1))
                    self.assertTrue(pool.submit(render).result(1))
                    self.assertFalse(acquired.is_set())
                update.result(1)
        self.assertTrue(acquired.is_set())

    def test_download_goes_to_data_dir_with_legacy_fallback(self):
        self.target.write_bytes(b"legacy core")
        data_dir = self.root / "plugin_data"
        manager = download.CoreManager(self.root, data_dir=data_dir)
        self.assertEqual(manager.path, self.target)

        def fetch(repository, asset, target, access, *, tag):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"new core")
            return "v1.4.1"

        with patch.object(download, "download_core", side_effect=fetch):
            target = manager.ensure(force=True)
        self.assertEqual(target, data_dir / "bin" / self.asset)
        self.assertEqual(manager.path, target)
        self.assertEqual(self.target.read_bytes(), b"legacy core")

    def test_wrong_release_version_is_not_installed(self):
        self.target.write_bytes(b"old core")

        def fetch(url, temporary, asset):
            temporary.write_bytes(b"wrong release")

        with patch.object(download, "_download", side_effect=fetch), self.assertLogs(
            download.logger, logging.WARNING
        ), self.assertRaises(RuntimeError):
            download.CoreManager(self.root).ensure(force=True)
        self.assertEqual(self.target.read_bytes(), b"old core")

    def test_tag_check_failure_preserves_old_core(self):
        self.target.write_bytes(b"old core")
        with patch.object(download, "latest_release_tag", side_effect=RuntimeError("offline")), patch.object(
            download, "download_core"
        ) as fetch, self.assertRaisesRegex(RuntimeError, "offline"):
            download.CoreManager(self.root).ensure(force=True)
        fetch.assert_not_called()
        self.assertEqual(self.target.read_bytes(), b"old core")

    def test_replacement_waits_for_active_render(self):
        access = download.CoreAccess()
        acquired = threading.Event()
        attempted = threading.Event()

        def writer():
            attempted.set()
            with access.replace():
                acquired.set()

        with access.render():
            thread = threading.Thread(target=writer)
            thread.start()
            self.assertTrue(attempted.wait(1))
            self.assertFalse(acquired.is_set())
        thread.join(1)
        self.assertTrue(acquired.is_set())

    def test_invalid_binary_rejected(self):
        self.target.write_bytes(b"<html>error</html>" * 10)
        with self.assertRaises(ValueError):
            download._validate_binary(self.target, self.asset)

    def test_manually_installed_core_gets_execute_permissions(self):
        self.target.write_bytes(b"existing")
        with patch.object(download.sys, "platform", "linux"), patch.object(
            download.platform, "machine", return_value="x86_64"
        ), patch.object(download.os, "chmod") as chmod:
            path = self.target.parent / "osu-beatmap-preview-linux-amd64-cli"
            path.write_bytes(b"manual core")
            with patch.object(download.Path, "stat") as stat_result:
                stat_result.return_value.st_mode = 0o644
                # Stat mocking would hide is_file; verify the permission helper directly.
                download._ensure_executable(path)
            chmod.assert_called_once_with(path, 0o755)

    def test_invalid_params_reach_cli(self):
        self.target.write_bytes(b"existing")
        request = parse_request("vv", "123+notamod t=30+-10")
        service = BeatmapPreviewService(self.root)
        args = service.build_args(request.bid, mods=request.mods,
                                  time_points=request.time_points,
                                  duration_time=request.duration_time)
        self.assertIn("notamod", args)
        self.assertIn("-40.0", args)
        self.assertEqual(parse_request("vp", "123 t=-5+0").time_points, ("-5", "0"))
        self.assertEqual(parse_request("vgc", "123 t=10+5").gif_duration_ms, -5000)
        self.assertEqual(parse_request("vv", "123 t=bad+other").time_points, ("bad", "other"))

    def test_configuration_is_live_and_does_not_mutate_source(self):
        source = {"default_json": {"render": {"mania": {"gif": {"style": {"X": 1}}}}}}
        loader = CoreConfig(source)
        output = loader.build("vgcl", gif_duration_ms=2000)
        style = output["render"]["mania"]["gif"]["style"]
        self.assertTrue(style["SHOW_TIME_LABEL"])
        self.assertEqual(style["DURATION_MS"], 2000)
        self.assertEqual(source["default_json"]["render"]["mania"]["gif"]["style"], {"X": 1})
        source["default_json"] = '{"timeout":{"PNG_TIMEOUT":12}}'
        self.assertEqual(loader.build("default")["timeout"]["PNG_TIMEOUT"], 12)


if __name__ == "__main__":
    unittest.main()
