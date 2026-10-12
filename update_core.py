"""Optional local updater; uses the same platform detection and mirrors as the plugin."""
from pathlib import Path

from service.core_download import CoreManager


if __name__ == "__main__":
    try:
        path = CoreManager(Path(__file__).resolve().parent).ensure(force=True)
    except Exception as exc:
        raise SystemExit(f"Core update failed: {exc}") from exc
    print(f"Core updated: {path}")
