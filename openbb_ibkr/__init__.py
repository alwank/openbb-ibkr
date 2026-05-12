"""OpenBB IBKR Provider Extension."""

from openbb_core.provider.abstract.provider import Provider

from openbb_ibkr.models.market_data import (
    IbkrEquityHistoricalFetcher,
    IbkrEquityQuoteFetcher,
)

__version__ = "0.1.0"

ibkr_provider = Provider(
    name="ibkr",
    website="https://www.interactivebrokers.com",
    description="Interactive Brokers data provider. "
    "Requires a running TWS or IB Gateway instance with API connections enabled.",
    credentials=["host", "port", "client_id"],
    fetcher_dict={
        "EquityQuote": IbkrEquityQuoteFetcher,
        "EquityHistorical": IbkrEquityHistoricalFetcher,
    },
    repr_name="Interactive Brokers (IBKR)",
    instructions="To use the IBKR provider:\n"
    "1. Ensure TWS or IB Gateway is running with API connections enabled.\n"
    "2. Configure credentials via obb.user.credentials:\n"
    "   obb.user.credentials.ibkr_host = '127.0.0.1'\n"
    "   obb.user.credentials.ibkr_port = '7497'  # 7496 for IB Gateway, 7497 for TWS\n"
    "   obb.user.credentials.ibkr_client_id = '1'\n"
    "3. Use like: obb.equity.price.quote(symbol='AAPL', provider='ibkr')",
)
