"""Shared test fixtures."""

import pytest
from unittest.mock import patch


@pytest.fixture
def mock_ibkr_client():
    """Mock IbkrClient to avoid needing a live TWS/IB Gateway connection."""
    with patch("openbb_ibkr.utils.client.IbkrClient") as mock:
        mock.is_connected.return_value = True
        mock.get_positions.return_value = [
            {
                "symbol": "AAPL",
                "sec_type": "STK",
                "currency": "USD",
                "position": 10.0,
                "market_price": 180.0,
                "market_value": 1800.0,
                "average_cost": 150.0,
                "unrealized_pnl": 300.0,
            },
            {
                "symbol": "VTI",
                "sec_type": "ETF",
                "currency": "USD",
                "position": 5.0,
                "market_price": 250.0,
                "market_value": 1250.0,
                "average_cost": 230.0,
                "unrealized_pnl": 100.0,
            },
        ]
        mock.get_account_summary.return_value = [
            {"tag": "NetLiquidation", "value": "5000", "currency": "USD", "account": "TEST"},
            {"tag": "GrossPositionValue", "value": "3050", "currency": "USD", "account": "TEST"},
            {"tag": "TotalCashValue", "value": "1950", "currency": "USD", "account": "TEST"},
            {"tag": "MaintMarginReq", "value": "750", "currency": "USD", "account": "TEST"},
            {"tag": "ExcessLiquidity", "value": "4250", "currency": "USD", "account": "TEST"},
            {"tag": "Cushion", "value": "0.85", "currency": "", "account": "TEST"},
        ]
        mock.get_quote.return_value = {
            "symbol": "AAPL",
            "bid": 179.5,
            "ask": 180.5,
            "last": 180.0,
            "volume": 50000000,
        }
        yield mock
