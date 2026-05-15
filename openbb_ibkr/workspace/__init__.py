"""OpenBB Workspace App bundle for openbb-ibkr."""

from pathlib import Path


def get_apps_json_path() -> str:
    """Return the absolute path to the bundled apps.json."""
    return str(Path(__file__).parent / "apps.json")
