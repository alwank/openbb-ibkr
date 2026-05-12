# openbb-ibkr

[![PyPI](https://img.shields.io/pypi/v/openbb-ibkr)](https://pypi.org/project/openbb-ibkr/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

Interactive Brokers (IBKR) provider extension for the [OpenBB Platform](https://openbb.co). Connects your IBKR portfolio data — positions, account summary, margin, orders, trades, and market data — directly into OpenBB.

## Features

- **Portfolio positions** — Symbol, quantity, market value, average cost, unrealized/realized P&L
- **Account summary** — Net liquidation, cash balances, buying power
- **Margin data** — Initial/maintenance margin, available funds, excess liquidity, cushion
- **Leverage analysis** — Compare pro-rata vs targeted leverage-up scenarios with shock tables and carry estimates
- **Orders & trades** — Open/completed orders and full trade history with fill-level detail
- **Market data** — Real-time/delayed quotes and historical bars
- **Multi-asset quotes** — FX, bonds, mutual funds, crypto, CFDs, commodities via IBKR-specific routes
- **Options** — Chain lookup, screener with Greeks, and decision signals (IV/RV, skew, flow)
- **Riskfolio optimization** *(optional)* — Mean-variance optimization, risk contribution, drawdown analysis

## Requirements

- **OpenBB Platform v4** installed
- **TWS** or **IB Gateway** running with API connections enabled
- Python 3.10+

## Installation

```bash
pip install openbb-ibkr
```

With Riskfolio portfolio optimization:

```bash
pip install openbb-ibkr[riskfolio]
```

Then rebuild the OpenBB package to register the extension:

```bash
openbb-build
```

> **Important:** The `openbb-build` step is required after installing any new OpenBB extension.

## Configuration

```python
from openbb import obb

obb.user.credentials.ibkr_host = "127.0.0.1"
obb.user.credentials.ibkr_port = "7497"   # 7496 for IB Gateway, 7497 for TWS
obb.user.credentials.ibkr_client_id = "1"
```

## Usage

### Portfolio & Account

```python
from openbb import obb

# Current positions with P&L
positions = obb.ibkr.positions()
print(positions.to_dataframe())

# Account summary
summary = obb.ibkr.account_summary().to_dataframe()

# Margin details
margin = obb.ibkr.margin_summary()
```

### Orders & Trades

```python
orders = obb.ibkr.open_orders().to_dataframe()
completed = obb.ibkr.completed_orders().to_dataframe()
trades = obb.ibkr.trades().to_dataframe()
```

### Market Data

```python
# Via IBKR router
obb.ibkr.quote(symbol="AAPL")
obb.ibkr.historical(symbol="AAPL", duration="1 M")

# Via OpenBB standard routers (provider="ibkr")
obb.equity.price.quote(symbol="AAPL", provider="ibkr")
obb.equity.price.historical(symbol="AAPL", provider="ibkr")

# Multi-asset
obb.ibkr.fx_quote(symbol="EUR.USD")
obb.ibkr.bond_quote(symbol="US912828Z864")
obb.ibkr.crypto_quote(symbol="BTC")
```

### Options

```python
# Option chain
chain = obb.ibkr.option_chain(symbol="AAPL")

# Screener with Greeks and signals
screener = obb.ibkr.option_screener(symbol="AAPL", min_dte=7, max_dte=45)

# Decision signals (IV/RV, skew, flow bias)
signals = obb.ibkr.option_decision_signals(symbols="AAPL,MSFT,SPY")
```

### Riskfolio Optimization (optional)

Requires `pip install openbb-ibkr[riskfolio]`.

```python
# Current vs optimized weights
weights = obb.ibkr.riskfolio_optimized_weights(duration="1 Y")

# Risk metrics comparison
metrics = obb.ibkr.riskfolio_metrics(duration="1 Y")

# Risk contribution by symbol
contrib = obb.ibkr.riskfolio_risk_contribution(duration="1 Y")
```

## API Reference

| Command | Description |
|---|---|
| `configure(host, port, client_id)` | Set IBKR connection parameters |
| `account_summary()` | All account tags |
| `margin_summary()` | Margin requirements |
| `account_values()` | Account tags by currency |
| `positions()` | Portfolio positions with P&L |
| `position_detail(symbol)` | Single position detail |
| `leverage_analysis(...)` | Leverage scenario analysis |
| `open_orders()` | Open orders |
| `completed_orders()` | Completed orders |
| `trades()` | Trade history with fills |
| `quote(symbol)` | Real-time/delayed quote |
| `historical(symbol, duration, bar_size)` | Historical bars |
| `market_quote(symbol, sec_type, ...)` | Multi-asset quote |
| `market_historical(symbol, sec_type, ...)` | Multi-asset history |
| `contract_search(symbol)` | Contract lookup |
| `contract_details(symbol)` | Contract metadata |
| `fx_quote(symbol)` | FX spot quote |
| `bond_quote(symbol)` | Bond quote |
| `fund_quote(symbol)` | Mutual fund quote |
| `crypto_quote(symbol)` | Crypto quote |
| `cfd_quote(symbol)` | CFD quote |
| `commodity_quote(symbol)` | Commodity quote |
| `option_chain(symbol)` | Option chain contracts |
| `option_screener(symbol, ...)` | Option screener with Greeks |
| `option_decision_signals(symbols)` | IV/RV and flow signals |
| `riskfolio_leverage_target(...)` | Constrained optimization target |
| `riskfolio_holdings()` | Holdings with inclusion status |
| `riskfolio_metrics(...)` | Risk metrics comparison |
| `riskfolio_optimized_weights(...)` | Current vs optimized weights |
| `riskfolio_risk_contribution(...)` | Volatility risk contribution |
| `is_connected()` | Connection status |

## Package Structure

```
openbb_ibkr/
├── __init__.py              # Provider registration
├── ibkr_router.py           # Router commands
├── models/
│   ├── market_data.py       # OpenBB fetchers (EquityQuote, EquityHistorical)
│   └── response_models.py   # Response data models
└── utils/
    ├── client.py            # IBKR connection manager (ib_insync wrapper)
    ├── options_signals.py   # Option decision signal computation
    └── iv_fallback.py       # IV gap-filling via yFinance fallback
```

## Development

```bash
git clone https://github.com/alwanalkautsar/openbb-ibkr.git
cd openbb-ibkr
pip install -e .[dev]
pytest tests/ -v
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — see [LICENSE](LICENSE).
