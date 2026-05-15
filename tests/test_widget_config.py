"""Tests for widget_config presence on core portfolio endpoints."""

import ast
import re
from pathlib import Path

ROUTER_PATH = Path(__file__).resolve().parent.parent / "openbb_ibkr" / "ibkr_router.py"

EXPECTED_WIDGET_CONFIGS = {
    "account_summary": "ibkr_account_summary_custom_obb",
    "positions": "ibkr_positions_custom_obb",
    "margin_summary": "ibkr_margin_summary_custom_obb",
}


def test_router_parses_with_widget_configs():
    """Router file is syntactically valid after widget_config additions."""
    ast.parse(ROUTER_PATH.read_text())


def test_widget_ids_present_in_source():
    """All expected widgetId strings exist in the router source."""
    content = ROUTER_PATH.read_text()
    for endpoint, widget_id in EXPECTED_WIDGET_CONFIGS.items():
        assert widget_id in content, f"widgetId '{widget_id}' not found for {endpoint}"


def test_widget_config_has_columns_defs():
    """Each core endpoint's widget_config contains columnsDefs."""
    content = ROUTER_PATH.read_text()
    for endpoint, widget_id in EXPECTED_WIDGET_CONFIGS.items():
        idx = content.find(f'"{widget_id}"')
        assert idx != -1, f"widgetId '{widget_id}' not found"
        # columnsDefs appears after widgetId in the same widget_config block
        block = content[max(0, idx - 500):idx + 2000]
        assert "columnsDefs" in block, f"columnsDefs missing near {widget_id}"


def test_widget_config_has_required_keys():
    """Each core widget_config contains name, type, category, subCategory."""
    content = ROUTER_PATH.read_text()
    for endpoint, widget_id in EXPECTED_WIDGET_CONFIGS.items():
        idx = content.find(f'"{widget_id}"')
        block = content[max(0, idx - 1500):idx + 500]
        for key in ['"name"', '"type"', '"category"', '"subCategory"']:
            assert key in block, f"{key} missing near {widget_id}"
