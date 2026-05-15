"""Integration tests for the OpenBB Workspace App bundle."""

import json
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "openbb_ibkr" / "workspace"
APPS_JSON_PATH = WORKSPACE_DIR / "apps.json"
ROUTER_PATH = Path(__file__).resolve().parent.parent / "openbb_ibkr" / "ibkr_router.py"


def test_apps_json_exists():
    """The apps.json file exists in the workspace directory."""
    assert APPS_JSON_PATH.exists()


def test_apps_json_valid():
    """The apps.json is valid JSON."""
    data = json.loads(APPS_JSON_PATH.read_text())
    assert isinstance(data, list)
    assert len(data) >= 1


def test_apps_json_structure():
    """The app has required top-level keys."""
    apps = json.loads(APPS_JSON_PATH.read_text())
    app = apps[0]
    assert app["name"] == "IBKR Connection"
    assert "tabs" in app
    assert "groups" in app
    assert "prompts" in app
    assert app["allowCustomization"] is True


def test_apps_json_tabs():
    """The app has the expected 3 tabs with layouts."""
    apps = json.loads(APPS_JSON_PATH.read_text())
    tabs = apps[0]["tabs"]
    assert "portfolio" in tabs
    assert "market-data" in tabs
    assert "options" in tabs
    for tab_id, tab in tabs.items():
        assert "layout" in tab
        assert len(tab["layout"]) > 0


def test_apps_json_widget_ids_in_router():
    """All widget IDs referenced in apps.json exist in the router source."""
    apps = json.loads(APPS_JSON_PATH.read_text())
    router_content = ROUTER_PATH.read_text()

    widget_ids = set()
    for tab in apps[0]["tabs"].values():
        for widget in tab["layout"]:
            widget_ids.add(widget["i"])

    # Widget IDs either appear as explicit widgetId strings in widget_config,
    # or are auto-generated from function names (function_name_custom_obb)
    for wid in widget_ids:
        # Check if it's explicitly defined or derivable from a function name
        if wid.endswith("_custom_obb"):
            # Could be auto-generated: strip suffix and check function exists
            func_name = wid.removesuffix("_custom_obb")
            has_explicit = f'"{wid}"' in router_content
            has_function = f"def {func_name}(" in router_content
            assert has_explicit or has_function, (
                f"Widget ID '{wid}' not found as explicit widgetId or function name in router"
            )
        else:
            # Non-standard ID — must be explicitly defined
            assert f'"{wid}"' in router_content, (
                f"Widget ID '{wid}' not found in router"
            )


def test_workspace_init_exists():
    """The workspace __init__.py exists with get_apps_json_path."""
    init_path = WORKSPACE_DIR / "__init__.py"
    assert init_path.exists()
    content = init_path.read_text()
    assert "get_apps_json_path" in content
