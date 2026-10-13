"""Optional local updater; uses the same platform detection and mirrors as the plugin."""
from pathlib import Path
import os

from service.core_download import CoreManager


if __name__ == "__main__":
    try:
        # 独立脚本也使用 AstrBot 数据路径；未安装 AstrBot 时遵循相同的根目录约定。
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path
            data_root = Path(get_astrbot_plugin_data_path())
        except ModuleNotFoundError as exc:
            if exc.name != "astrbot":
                raise
            data_root = Path(os.environ.get("ASTRBOT_ROOT", os.getcwd())) / "data" / "plugin_data"
        path = CoreManager(
            Path(__file__).resolve().parent,
            data_dir=data_root / "astrbot_plugin_osu_beatmap_preview",
        ).ensure(force=True)
    except Exception as exc:
        raise SystemExit(f"Core update failed: {exc}") from exc
    print(f"Core updated: {path}")
