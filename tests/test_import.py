"""Smoke tests: verify the package imports and registers correctly."""

import ast
from pathlib import Path


def test_router_parses():
    """The stripped router file is syntactically valid Python."""
    source = Path(__file__).resolve().parent.parent / "openbb_ibkr" / "ibkr_router.py"
    ast.parse(source.read_text())


def test_response_models_parse():
    """The response models file is syntactically valid Python."""
    source = Path(__file__).resolve().parent.parent / "openbb_ibkr" / "models" / "response_models.py"
    ast.parse(source.read_text())


def test_no_research_imports():
    """The router does not reference research utilities."""
    source = Path(__file__).resolve().parent.parent / "openbb_ibkr" / "ibkr_router.py"
    content = source.read_text()
    assert "from openbb_ibkr.utils.research" not in content
    assert "from openbb_ibkr.utils.risk_radar" not in content


def test_core_models_importable():
    """Core response models can be imported."""
    from openbb_ibkr.models.response_models import (
        AccountSummaryItem,
        ContractDetails,
        HistoricalBar,
        MarginRequirement,
        MarketQuote,
        OptionChainContract,
        OptionDecisionSignal,
        OptionScreenerContract,
        Order,
        Position,
        Quote,
        RiskfolioMetric,
        RiskfolioWeight,
        Trade,
    )
    assert Position is not None
    assert RiskfolioMetric is not None


def test_client_importable():
    """The IBKR client class can be imported."""
    from openbb_ibkr.utils.client import IbkrClient, IbkrConnectionError
    assert IbkrClient._host == "127.0.0.1"
    assert IbkrClient._port == 7497


def test_options_signals_importable():
    """Option signal utilities can be imported."""
    from openbb_ibkr.utils.options_signals import realized_vol_from_bars
    assert callable(realized_vol_from_bars)


def test_iv_fallback_importable():
    """IV fallback utilities can be imported."""
    from openbb_ibkr.utils.iv_fallback import fill_iv_gaps
    assert callable(fill_iv_gaps)
