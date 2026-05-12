from typing import Any, List, Optional, Union

import pandas as pd

from openbb_core.app.model.abstract.warning import Warning_
from openbb_core.app.model.obbject import OBBject
from openbb_core.app.router import Router

from openbb_ibkr.models.response_models import (
    AccountSummaryItem,
    ContractDetails,
    ContractSearchResult,
    HistoricalBar,
    MarginRequirement,
    MarketQuote,
    OptionChainContract,
    OptionDecisionSignal,
    OptionScreenerContract,
    Order,
    Position,
    Quote,
    RiskfolioAllocation,
    RiskfolioAssetRiskReturn,
    RiskfolioCumulativeReturn,
    RiskfolioDistributionBin,
    RiskfolioDrawdown,
    RiskfolioHolding,
    RiskfolioMetric,
    RiskfolioRiskContribution,
    RiskfolioTailRiskContribution,
    RiskfolioWeight,
    Trade,
)
from openbb_ibkr.utils.client import IbkrClient, IbkrConnectionError

router = Router(prefix="", description="Interactive Brokers account, portfolio, and trading data.")

_ERR_MSG = (
    "Cannot connect to IBKR. Ensure TWS or IB Gateway is running "
    "with API enabled on the configured host:port."
)
_RISKFOLIO_SUPPORTED_SEC_TYPES = {"STK", "ETF"}
_DEFAULT_LEVERAGE_TARGET_SYMBOLS = ("VTI", "QQQM", "SCHD", "SPMO", "USMV", "AVUV")
_DEFAULT_LEVERAGE_SHOCKS = (0.05, 0.10, 0.15, 0.20, 0.30)
_DEFAULT_FUNDING_RATES = (0.05, 0.06, 0.07, 0.08)
_DEFAULT_SLEEVE_MAP = {
    "VTI": "us_equity",
    "QQQM": "us_equity",
    "SCHD": "us_equity",
    "SPMO": "us_equity",
    "USMV": "us_equity",
    "AVUV": "us_equity",
    "VXUS": "international_equity",
    "VWO": "international_equity",
    "AVDV": "international_equity",
    "VGIT": "bonds_cash",
    "STIP": "bonds_cash",
    "SGOV": "bonds_cash",
    "DBMF": "alternatives_real_assets",
    "PDBC": "alternatives_real_assets",
    "GLDM": "alternatives_real_assets",
}
_DEFAULT_SLEEVE_BOUNDS = {
    "us_equity": (0.40, 0.50),
    "international_equity": (0.20, 0.30),
    "bonds_cash": (0.15, 0.25),
    "alternatives_real_assets": (0.10, 0.20),
}


def _column(
    field: str,
    header_name: str,
    cell_data_type: str,
    formatter_fn: Optional[str] = None,
    chart_data_type: Optional[str] = None,
    pinned: Optional[str] = None,
) -> dict[str, Any]:
    column: dict[str, Any] = {
        "field": field,
        "headerName": header_name,
        "cellDataType": cell_data_type,
    }
    if formatter_fn:
        column["formatterFn"] = formatter_fn
    if chart_data_type:
        column["chartDataType"] = chart_data_type
    if pinned:
        column["pinned"] = pinned
    return column


def _riskfolio_widget_config(
    chart_type: str,
    cell_range_cols: list[str],
    columns: list[dict[str, Any]],
    sub_category: str,
    name: Optional[str] = None,
    widget_id: Optional[str] = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "source": ["IBKR", "Riskfolio"],
        "category": "IBKR",
        "subCategory": sub_category,
        "data": {
            "table": {
                "showAll": True,
                "enableAdvanced": True,
                "enableCharts": True,
                "chartView": {
                    "enabled": True,
                    "chartType": chart_type,
                    "cellRangeCols": {
                        chart_type: cell_range_cols,
                    },
                    "ignoreCellRange": True,
                },
                "columnsDefs": columns,
            }
        },
    }
    if name:
        config["name"] = name
    if widget_id:
        config["widgetId"] = widget_id
    return config


_RISKFOLIO_HOLDING_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "category"),
    _column("sec_type", "Security Type", "text", chart_data_type="excluded"),
    _column("currency", "Currency", "text", chart_data_type="excluded"),
    _column("position", "Position", "number", chart_data_type="series"),
    _column("market_value", "Market Value", "number", chart_data_type="series"),
    _column("current_weight", "Current Weight", "number", "normalizedPercent", "series"),
    _column("market_price", "Market Price", "number", chart_data_type="series"),
    _column("average_cost", "Average Cost", "number", chart_data_type="series"),
    _column("unrealized_pnl", "Unrealized P&L", "number", chart_data_type="series"),
    _column("included", "Included", "text", chart_data_type="excluded"),
    _column("exclusion_reason", "Exclusion Reason", "text", chart_data_type="excluded"),
]
_RISKFOLIO_ALLOCATION_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "category"),
    _column("market_value", "Market Value", "number", chart_data_type="series"),
    _column("current_weight", "Current Weight", "number", "normalizedPercent", "series"),
    _column("unrealized_pnl", "Unrealized P&L", "number", chart_data_type="series"),
    _column("unrealized_pnl_percent", "Unrealized P&L %", "number", "normalizedPercent", "series"),
]
_RISKFOLIO_METRIC_COLUMNS = [
    _column("metric", "Metric", "text", "none", "category"),
    _column("current", "Current", "number", chart_data_type="series"),
    _column("optimized", "Optimized", "number", chart_data_type="series"),
    _column("delta", "Delta", "number", chart_data_type="series"),
]
_RISKFOLIO_WEIGHT_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "category"),
    _column("current_weight", "Current Weight", "number", "normalizedPercent", "series"),
    _column("optimized_weight", "Optimized Weight", "number", "normalizedPercent", "series"),
    _column("rebalance_delta", "Rebalance Delta", "number", "normalizedPercent", "series"),
]
_RISKFOLIO_CONTRIBUTION_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "excluded", "left"),
    _column("ticker", "Ticker", "text", "none", "category"),
    _column("current_weight", "Current Weight", "number", "normalizedPercent", "series"),
    _column("risk_contribution", "Risk Contribution", "number", "normalizedPercent", "series"),
    _column("risk_weight_gap", "Risk Weight Gap", "number", "normalizedPercent", "series"),
    _column("bubble_size", "Bubble Size", "number", chart_data_type="excluded"),
]
_RISKFOLIO_ASSET_RISK_RETURN_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "category"),
    _column("expected_return", "Expected Return", "number", "normalizedPercent", "series"),
    _column("volatility", "Volatility", "number", "normalizedPercent", "series"),
    _column("sharpe_ratio", "Sharpe Ratio", "number", chart_data_type="series"),
    _column("current_weight", "Current Weight", "number", "normalizedPercent", "series"),
]
_RISKFOLIO_TAIL_RISK_CONTRIBUTION_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "category"),
    _column("current_weight", "Current Weight", "number", "normalizedPercent", "series"),
    _column("cvar_contribution", "CVaR Contribution", "number", "normalizedPercent", "series"),
    _column("cvar_weight_gap", "CVaR - Weight Gap", "number", "normalizedPercent", "series"),
]
_RISKFOLIO_DRAWDOWN_COLUMNS = [
    _column("date", "Date", "text", chart_data_type="category"),
    _column("drawdown", "Drawdown", "number", "normalizedPercent", "series"),
]
_RISKFOLIO_CUMULATIVE_RETURN_COLUMNS = [
    _column("date", "Date", "text", chart_data_type="category"),
    _column("symbol", "Symbol", "text", "none", "category"),
    _column("cumulative_return", "Cumulative Return", "number", "normalizedPercent", "series"),
]
_RISKFOLIO_DISTRIBUTION_COLUMNS = [
    _column("bin_center", "Bin Center", "number", chart_data_type="category"),
    _column("frequency", "Frequency", "number", chart_data_type="series"),
]
_OPTION_SCREENER_COLUMNS = [
    _column("underlying_symbol", "Underlying", "text", "none", "category", "left"),
    _column("con_id", "Con ID", "number", chart_data_type="category"),
    _column("expiry", "Expiry", "text", chart_data_type="category"),
    _column("strike", "Strike", "number", chart_data_type="series"),
    _column("right", "Right", "text", "none", "category"),
    _column("dte", "DTE", "number", chart_data_type="series"),
    _column("moneyness", "Moneyness", "number", chart_data_type="series"),
    _column("bid", "Bid", "number", chart_data_type="series"),
    _column("ask", "Ask", "number", chart_data_type="series"),
    _column("mid", "Mid", "number", chart_data_type="series"),
    _column("last", "Last", "number", chart_data_type="series"),
    _column("volume", "Volume", "number", chart_data_type="series"),
    _column("open_interest", "Open Interest", "number", chart_data_type="series"),
    _column("implied_vol", "IV", "number", "normalizedPercent", "series"),
    _column("delta", "Delta", "number", chart_data_type="series"),
    _column("gamma", "Gamma", "number", chart_data_type="series"),
    _column("theta", "Theta", "number", chart_data_type="series"),
    _column("vega", "Vega", "number", chart_data_type="series"),
    _column("spread_percent", "Spread %", "number", "normalizedPercent", "series"),
    _column("volume_oi_ratio", "Vol/OI", "number", chart_data_type="series"),
    _column("iv_rv_ratio", "IV/RV", "number", chart_data_type="series"),
    _column("iv_rv_spread", "IV-RV", "number", "normalizedPercent", "series"),
    _column("put_call_skew", "25D Put-Call Skew", "number", "normalizedPercent", "series"),
    _column("option_decision_labels", "Option Labels", "text", chart_data_type="category"),
    _column("trade_suitability", "Trade Suitability", "text", chart_data_type="category"),
    _column("liquidity_score", "Liquidity Score", "number", chart_data_type="series"),
    _column("strategy_score", "Strategy Score", "number", chart_data_type="series"),
]
_OPTION_DECISION_SIGNAL_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "category", "left"),
    _column("implied_vol_3m", "3M IV", "number", "normalizedPercent", "series"),
    _column("realized_vol_3m", "3M RV", "number", "normalizedPercent", "series"),
    _column("iv_rv_ratio", "IV/RV", "number", chart_data_type="series"),
    _column("iv_rv_spread", "IV-RV", "number", "normalizedPercent", "series"),
    _column("put_call_skew", "25D Put-Call Skew", "number", "normalizedPercent", "series"),
    _column("atm_put_call_skew", "ATM Put-Call Skew", "number", "normalizedPercent", "series"),
    _column("call_put_premium_ratio", "Call/Put Premium", "number", chart_data_type="series"),
    _column("put_call_oi_ratio", "Put/Call OI", "number", chart_data_type="series"),
    _column("net_option_delta_bias", "Net Delta Bias", "number", chart_data_type="series"),
    _column("net_option_vega_bias", "Net Vega Bias", "number", chart_data_type="series"),
    _column("vol_pricing_score", "Vol Pricing", "number", chart_data_type="series"),
    _column("skew_risk_score", "Skew Risk", "number", chart_data_type="series"),
    _column("flow_bias_score", "Flow Bias", "number", chart_data_type="series"),
    _column("option_decision_labels", "Labels", "text", chart_data_type="category"),
    _column("trade_suitability", "Trade Suitability", "text", chart_data_type="category"),
]
_MARKET_QUOTE_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "category", "left"),
    _column("sec_type", "Security Type", "text", "none", "category"),
    _column("exchange", "Exchange", "text", "none", "category"),
    _column("currency", "Currency", "text", "none", "category"),
    _column("bid", "Bid", "number", chart_data_type="series"),
    _column("ask", "Ask", "number", chart_data_type="series"),
    _column("last", "Last", "number", chart_data_type="series"),
    _column("close", "Close", "number", chart_data_type="series"),
    _column("volume", "Volume", "number", chart_data_type="series"),
    _column("timestamp", "Timestamp", "text", chart_data_type="category"),
    _column("delayed", "Delayed", "text", chart_data_type="excluded"),
    _column("con_id", "Con ID", "number", chart_data_type="category"),
]
_CONTRACT_COLUMNS = [
    _column("symbol", "Symbol", "text", "none", "category", "left"),
    _column("sec_type", "Security Type", "text", "none", "category"),
    _column("exchange", "Exchange", "text", "none", "category"),
    _column("primary_exchange", "Primary Exchange", "text", "none", "category"),
    _column("currency", "Currency", "text", "none", "category"),
    _column("con_id", "Con ID", "number", chart_data_type="category"),
    _column("local_symbol", "Local Symbol", "text", chart_data_type="category"),
    _column("trading_class", "Trading Class", "text", chart_data_type="category"),
    _column("description", "Description", "text", chart_data_type="excluded"),
]


def _market_quote_widget_config(name: str, sub_category: str, widget_id: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": "Normalized read-only IBKR market quote for subscribed asset classes.",
        "type": "table",
        "source": ["IBKR"],
        "category": "IBKR",
        "subCategory": sub_category,
        "widgetId": widget_id,
        "gridData": {"w": 20, "h": 8},
        "data": {
            "table": {
                "showAll": True,
                "enableAdvanced": True,
                "enableCharts": True,
                "chartView": {
                    "enabled": True,
                    "chartType": "bar",
                    "cellRangeCols": {"bar": ["symbol", "last"]},
                    "ignoreCellRange": True,
                },
                "columnsDefs": _MARKET_QUOTE_COLUMNS,
            }
        },
    }


def _contract_widget_config(name: str, widget_id: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": "IBKR contract lookup metadata for resolving symbols and conIds.",
        "type": "table",
        "source": ["IBKR"],
        "category": "IBKR",
        "subCategory": "Contracts",
        "widgetId": widget_id,
        "gridData": {"w": 40, "h": 12},
        "data": {
            "table": {
                "showAll": True,
                "enableAdvanced": True,
                "enableCharts": False,
                "columnsDefs": _CONTRACT_COLUMNS,
            }
        },
    }


def _option_widget_config(
    chart_type: str = "bar",
    cell_range_cols: Optional[list[str]] = None,
    name: str = "IBKR Option Screener",
    description: str = "IBKR option contracts with quotes, Greeks, and screening metrics.",
    widget_id: str = "ibkr_option_screener",
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "type": "table",
        "source": ["IBKR"],
        "category": "IBKR",
        "subCategory": "Options",
        "widgetId": widget_id,
        "gridData": {"w": 40, "h": 20},
        "data": {
            "table": {
                "showAll": True,
                "enableAdvanced": True,
                "enableCharts": True,
                "chartView": {
                    "enabled": True,
                    "chartType": chart_type,
                    "cellRangeCols": {
                        chart_type: cell_range_cols or ["expiry", "strategy_score"],
                    },
                    "ignoreCellRange": True,
                },
                "columnsDefs": _OPTION_SCREENER_COLUMNS,
            }
        },
    }


def _riskfolio_chart_widget_config(
    name: str,
    description: str,
    widget_id: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "type": "chart",
        "source": ["IBKR", "Riskfolio"],
        "category": "IBKR",
        "subCategory": "Riskfolio",
        "widgetId": widget_id,
        "gridData": {"w": 40, "h": 20},
        "params": [
            {
                "paramName": "duration",
                "label": "Duration",
                "description": "Historical lookback window used to compute returns.",
                "type": "text",
                "value": "1 Y",
                "show": True,
            },
            {
                "paramName": "delayed",
                "label": "Delayed",
                "description": "Request delayed market data from IBKR.",
                "type": "boolean",
                "value": True,
                "show": True,
            },
            {"paramName": "host", "show": True},
            {"paramName": "port", "show": True},
            {"paramName": "client_id", "show": True},
            {"paramName": "theme", "value": "dark", "show": False},
        ],
    }


def _configure_from_query(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> None:
    """Override client configuration from per-request query parameters."""
    host = _clean_query_value(host)
    port = _clean_query_value(port)
    client_id = _clean_query_value(client_id)
    if host is not None or port is not None or client_id is not None:
        IbkrClient.configure(host=host, port=port, client_id=client_id)


def _clean_query_value(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() in {"none", "null", "undefined"}:
        return None
    return value


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_rate(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        text = str(value).strip().replace("%", "")
        if not text:
            return None
        rate = float(text)
    except (TypeError, ValueError):
        return None
    if abs(rate) > 1:
        rate = rate / 100
    return rate


def _parse_symbol_list(value: Optional[str], default: tuple[str, ...] = ()) -> list[str]:
    raw = value if value is not None else ",".join(default)
    symbols: list[str] = []
    for item in str(raw).replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def _parse_rate_list(value: Optional[str], default: tuple[float, ...]) -> list[float]:
    raw = value if value is not None else ",".join(str(item) for item in default)
    rates: list[float] = []
    for item in str(raw).replace(";", ",").split(","):
        rate = _normalize_rate(item)
        if rate is not None:
            rates.append(rate)
    if not rates:
        rates = list(default)
    return sorted(dict.fromkeys(rates))


def _parse_distribution_yield_overrides(value: Optional[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    if not value:
        return overrides

    for item in str(value).replace(";", ",").split(","):
        if "=" not in item:
            continue
        symbol, raw_rate = item.split("=", 1)
        rate = _normalize_rate(raw_rate)
        clean_symbol = symbol.strip().upper()
        if clean_symbol and rate is not None:
            overrides[clean_symbol] = rate
    return overrides


def _parse_sleeve_memberships(value: Optional[str]) -> dict[str, str]:
    memberships = dict(_DEFAULT_SLEEVE_MAP)
    if not value:
        return memberships

    for group in str(value).split(";"):
        if "=" not in group:
            continue
        sleeve, raw_symbols = group.split("=", 1)
        sleeve_name = sleeve.strip().lower()
        for symbol in raw_symbols.replace("|", ",").split(","):
            clean_symbol = symbol.strip().upper()
            if clean_symbol:
                memberships[clean_symbol] = sleeve_name
    return memberships


def _parse_sleeve_bounds(value: Optional[str]) -> dict[str, tuple[float, float]]:
    bounds = dict(_DEFAULT_SLEEVE_BOUNDS)
    if not value:
        return bounds

    for group in str(value).split(","):
        if "=" not in group:
            continue
        sleeve, raw_bounds = group.split("=", 1)
        sleeve_name = sleeve.strip().lower()
        if ":" not in raw_bounds:
            continue
        min_raw, max_raw = raw_bounds.split(":", 1)
        min_weight = _normalize_rate(min_raw)
        max_weight = _normalize_rate(max_raw)
        if min_weight is None or max_weight is None:
            continue
        bounds[sleeve_name] = (min_weight, max_weight)
    return bounds


def _daily_series_metrics(daily_returns: pd.Series, risk_free_rate: float = 0.0) -> dict[str, float]:
    import numpy as np

    expected_return = float(daily_returns.mean() * 252)
    volatility = float(daily_returns.std(ddof=1) * np.sqrt(252))
    sharpe = (expected_return - risk_free_rate) / volatility if volatility else 0.0
    cumulative = (1 + daily_returns).cumprod()
    drawdown = cumulative / cumulative.cummax() - 1
    var_95 = float(daily_returns.quantile(0.05))
    cvar_95 = float(daily_returns[daily_returns <= var_95].mean()) if len(daily_returns) else 0.0
    return {
        "expected_return": expected_return,
        "volatility": volatility,
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
        "var_95": var_95,
        "cvar_95": cvar_95,
    }


def _summary_metric(items: list[dict[str, Any]], tag: str) -> Optional[float]:
    priorities = (
        lambda item: item.get("account") not in {"All", None, ""},
        lambda item: item.get("currency") in {"USD", "BASE", ""},
    )
    for rule in priorities:
        for item in items:
            if item.get("tag") == tag and rule(item):
                return _to_float(item.get("value"))
    for item in items:
        if item.get("tag") == tag:
            return _to_float(item.get("value"))
    return None


def _supported_long_positions(positions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    included: list[dict[str, Any]] = []
    excluded_symbols: list[str] = []

    for position in positions:
        sec_type = str(position.get("sec_type") or "").upper()
        market_value = _to_float(position.get("market_value"))
        quantity = _to_float(position.get("position"))
        if quantity <= 0 or market_value <= 0:
            continue
        if sec_type not in _RISKFOLIO_SUPPORTED_SEC_TYPES:
            symbol = str(position.get("symbol") or sec_type or "UNKNOWN").upper()
            if symbol not in excluded_symbols:
                excluded_symbols.append(symbol)
            continue
        included.append(
            {
                "symbol": str(position.get("symbol") or "").upper(),
                "market_value": market_value,
                "current_weight": 0.0,
            }
        )

    total_market_value = sum(item["market_value"] for item in included)
    for item in included:
        if total_market_value > 0:
            item["current_weight"] = item["market_value"] / total_market_value

    return included, excluded_symbols


def _fetch_distribution_yields(symbols: list[str]) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    try:
        import yfinance as yf
    except ImportError:
        return {}, ["Distribution-yield estimates are unavailable because yfinance is not installed."]

    yields: dict[str, float] = {}
    for symbol in symbols:
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception as exc:
            warnings.append(f"Could not fetch distribution yield for {symbol}: {exc}")
            continue

        for key in ("yield", "dividendYield", "trailingAnnualDividendYield"):
            rate = _normalize_rate(info.get(key))
            if rate is not None and rate >= 0:
                yields[symbol] = rate
                break

    return yields, warnings


def _weight_series(rows: list[dict[str, Any]], key: str) -> pd.Series:
    return pd.Series({row["symbol"]: float(row.get(key, 0.0)) for row in rows}, dtype=float)


def _riskfolio_optimize_constrained(
    returns: pd.DataFrame,
    risk_free_rate: float,
    max_weight: float,
    sleeve_map: dict[str, str],
    sleeve_bounds: dict[str, tuple[float, float]],
) -> pd.Series:
    import riskfolio as rp

    port = rp.Portfolio(returns=returns)
    port.assets_stats(method_mu="hist", method_cov="hist")
    port.upperlng = max_weight

    ordered_assets = list(returns.columns)
    asset_classes = pd.DataFrame(
        {
            "Assets": ordered_assets,
            "Sleeve": [sleeve_map.get(symbol, "unassigned") for symbol in ordered_assets],
        }
    )

    constraint_rows: list[dict[str, Any]] = []
    for sleeve, (min_weight, max_weight_bound) in sleeve_bounds.items():
        constraint_rows.append(
            {
                "Disabled": False,
                "Type": "Classes",
                "Set": "Sleeve",
                "Position": sleeve,
                "Sign": ">=",
                "Weight": min_weight,
                "Type Relative": "",
                "Relative Set": "",
                "Relative": "",
                "Factor": "",
            }
        )
        constraint_rows.append(
            {
                "Disabled": False,
                "Type": "Classes",
                "Set": "Sleeve",
                "Position": sleeve,
                "Sign": "<=",
                "Weight": max_weight_bound,
                "Type Relative": "",
                "Relative Set": "",
                "Relative": "",
                "Factor": "",
            }
        )

    constraints = pd.DataFrame(constraint_rows)
    A, B = rp.assets_constraints(constraints, asset_classes)
    port.ainequality = A
    port.binequality = B

    weights = port.optimization(
        model="Classic",
        rm="MV",
        obj="Sharpe",
        rf=risk_free_rate,
        l=0,
        hist=True,
    )
    if weights is None or weights.empty:
        raise ValueError("Riskfolio optimizer did not produce constrained weights.")
    series = weights.iloc[:, 0].astype(float).clip(lower=0)
    total = float(series.sum())
    if total <= 0:
        raise ValueError("Riskfolio optimizer returned zero total weight.")
    return series / total


def _build_constrained_leverage_target(
    positions: list[dict[str, Any]],
    account_summary_items: list[dict[str, Any]],
    returns: pd.DataFrame,
    target_leverage: float,
    risk_free_rate: float,
    max_weight: float,
    sleeve_map: dict[str, str],
    sleeve_bounds: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    supported_rows, excluded_symbols = _supported_long_positions(positions)
    if not supported_rows:
        raise ValueError("No supported long stock/ETF positions were found.")

    net_liquidation = _summary_metric(account_summary_items, "NetLiquidation") or 0.0
    gross_position_value = _summary_metric(account_summary_items, "GrossPositionValue") or 0.0
    total_cash_value = _summary_metric(account_summary_items, "TotalCashValue") or 0.0
    maint_margin_req = _summary_metric(account_summary_items, "MaintMarginReq") or 0.0
    if net_liquidation <= 0 or gross_position_value <= 0:
        raise ValueError("Net liquidation or gross position value is missing.")

    ordered_assets = [symbol for symbol in returns.columns if symbol in {row["symbol"] for row in supported_rows}]
    if not ordered_assets:
        raise ValueError("No overlapping assets between positions and return history.")

    filtered_returns = returns[ordered_assets]
    current_weights = _weight_series(supported_rows, "current_weight").reindex(ordered_assets).fillna(0)
    current_weights = current_weights / float(current_weights.sum())

    optimized_weights = _riskfolio_optimize_constrained(
        filtered_returns,
        risk_free_rate=risk_free_rate,
        max_weight=max_weight,
        sleeve_map=sleeve_map,
        sleeve_bounds=sleeve_bounds,
    ).reindex(ordered_assets).fillna(0)
    optimized_weights = optimized_weights / float(optimized_weights.sum())

    target_gross = net_liquidation * target_leverage
    current_leverage = gross_position_value / net_liquidation
    incremental_exposure = target_gross - gross_position_value
    maintenance_ratio = maint_margin_req / gross_position_value if gross_position_value > 0 else 0.25
    estimated_margin_debit = max(-(total_cash_value - incremental_exposure), 0.0)
    estimated_maintenance_margin = target_gross * maintenance_ratio
    estimated_excess_liquidity = net_liquidation - estimated_maintenance_margin

    per_symbol: list[dict[str, Any]] = []
    current_market_values = {row["symbol"]: row["market_value"] for row in supported_rows}
    for symbol in ordered_assets:
        current_weight = float(current_weights.get(symbol, 0.0))
        optimized_weight = float(optimized_weights.get(symbol, 0.0))
        target_market_value = optimized_weight * target_gross
        per_symbol.append(
            {
                "symbol": symbol,
                "sleeve": sleeve_map.get(symbol, "unassigned"),
                "current_weight": current_weight,
                "optimized_weight": optimized_weight,
                "rebalance_delta": optimized_weight - current_weight,
                "current_market_value": current_market_values.get(symbol, 0.0),
                "target_market_value": target_market_value,
                "trade_delta": target_market_value - current_market_values.get(symbol, 0.0),
            }
        )

    sleeve_rows: list[dict[str, Any]] = []
    sleeve_names = sorted({sleeve_map.get(symbol, "unassigned") for symbol in ordered_assets})
    for sleeve in sleeve_names:
        current_weight = float(sum(row["current_weight"] for row in per_symbol if row["sleeve"] == sleeve))
        optimized_weight = float(sum(row["optimized_weight"] for row in per_symbol if row["sleeve"] == sleeve))
        target_market_value = float(sum(row["target_market_value"] for row in per_symbol if row["sleeve"] == sleeve))
        lower_bound, upper_bound = sleeve_bounds.get(sleeve, (0.0, 1.0))
        sleeve_rows.append(
            {
                "sleeve": sleeve,
                "current_weight": current_weight,
                "optimized_weight": optimized_weight,
                "target_market_value": target_market_value,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
            }
        )

    current_daily = filtered_returns @ current_weights
    optimized_daily = filtered_returns @ optimized_weights * target_leverage
    current_metrics = _daily_series_metrics(current_daily, risk_free_rate=risk_free_rate)
    optimized_metrics = _daily_series_metrics(optimized_daily, risk_free_rate=risk_free_rate)

    warnings: list[str] = []
    if excluded_symbols:
        warnings.append(
            "Excluded unsupported long positions from constrained target: "
            + ", ".join(excluded_symbols)
        )

    return {
        "summary": {
            "net_liquidation": net_liquidation,
            "current_gross_exposure": gross_position_value,
            "target_gross_exposure": target_gross,
            "current_leverage": current_leverage,
            "target_leverage": target_leverage,
            "incremental_exposure": incremental_exposure,
            "estimated_margin_debit": estimated_margin_debit,
            "estimated_maintenance_margin": estimated_maintenance_margin,
            "estimated_excess_liquidity": estimated_excess_liquidity,
            "estimated_cushion": (
                estimated_excess_liquidity / net_liquidation if net_liquidation else 0.0
            ),
        },
        "constraints": {
            "max_weight": max_weight,
            "risk_free_rate": risk_free_rate,
            "sleeve_bounds": [
                {"sleeve": sleeve, "min_weight": bounds[0], "max_weight": bounds[1]}
                for sleeve, bounds in sleeve_bounds.items()
            ],
        },
        "per_symbol": per_symbol,
        "per_sleeve": sleeve_rows,
        "metrics": {
            "current": current_metrics,
            "optimized_target": optimized_metrics,
        },
        "warnings": warnings,
    }


def _build_leverage_analysis(
    positions: list[dict[str, Any]],
    account_summary_items: list[dict[str, Any]],
    target_leverage: float,
    target_symbols: list[str],
    funding_rates: list[float],
    shock_magnitudes: list[float],
    tax_rate: float,
    distribution_yields: Optional[dict[str, float]] = None,
    returns: Optional[pd.DataFrame] = None,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if target_leverage <= 0:
        raise ValueError("target_leverage must be positive.")

    supported_rows, excluded_symbols = _supported_long_positions(positions)
    if not supported_rows:
        raise ValueError("No supported long stock/ETF positions were found.")
    if excluded_symbols:
        warnings.append(
            "Excluded unsupported long positions from leverage analysis: "
            + ", ".join(excluded_symbols)
        )

    net_liquidation = _summary_metric(account_summary_items, "NetLiquidation") or 0.0
    gross_position_value = _summary_metric(account_summary_items, "GrossPositionValue") or 0.0
    total_cash_value = _summary_metric(account_summary_items, "TotalCashValue") or 0.0
    maint_margin_req = _summary_metric(account_summary_items, "MaintMarginReq") or 0.0
    excess_liquidity = _summary_metric(account_summary_items, "ExcessLiquidity") or 0.0
    cushion = _summary_metric(account_summary_items, "Cushion")

    modeled_gross = sum(row["market_value"] for row in supported_rows)
    if gross_position_value <= 0:
        gross_position_value = modeled_gross
    if net_liquidation <= 0:
        raise ValueError("Net liquidation value is missing or non-positive.")

    current_leverage = gross_position_value / net_liquidation if net_liquidation else 0.0
    if target_leverage < current_leverage:
        raise ValueError(
            f"target_leverage {target_leverage:.2f}x is below the current leverage {current_leverage:.2f}x."
        )
    if abs(modeled_gross - gross_position_value) > max(25.0, gross_position_value * 0.01):
        warnings.append(
            "Supported long stock/ETF exposure differs from GrossPositionValue. "
            "Scenario weights are based on supported positions only."
        )

    maintenance_ratio = maint_margin_req / gross_position_value if gross_position_value > 0 else 0.25
    if maintenance_ratio <= 0:
        maintenance_ratio = 0.25
        warnings.append("Maintenance margin ratio was unavailable. Falling back to 25%.")

    if distribution_yields is None:
        distribution_yields = {}
    fetched_yields, yield_warnings = _fetch_distribution_yields([row["symbol"] for row in supported_rows])
    warnings.extend(yield_warnings)
    yield_lookup = {**fetched_yields, **distribution_yields}

    current_weights = _weight_series(supported_rows, "current_weight")
    current_target_weight = float(current_weights.reindex(target_symbols).fillna(0).sum())
    current_debit = max(-total_cash_value, 0.0)
    target_gross = net_liquidation * target_leverage
    incremental_exposure = target_gross - gross_position_value
    target_debit = max(-(total_cash_value - incremental_exposure), 0.0)
    target_maint_margin = maintenance_ratio * target_gross
    target_excess_liquidity = net_liquidation - target_maint_margin
    target_cushion = target_excess_liquidity / net_liquidation if net_liquidation else 0.0
    drawdown_to_maintenance = (
        (1 - maintenance_ratio * target_leverage) / (target_leverage * (1 - maintenance_ratio))
        if target_leverage * (1 - maintenance_ratio)
        else 0.0
    )

    symbol_market_values = {row["symbol"]: row["market_value"] for row in supported_rows}
    target_pool_total = sum(symbol_market_values.get(symbol, 0.0) for symbol in target_symbols)
    if target_pool_total <= 0:
        warnings.append("Target symbols did not match supported positions. Targeted variant falls back to pro rata.")

    variants: list[dict[str, Any]] = []
    weight_changes: list[dict[str, Any]] = []
    shock_rows: list[dict[str, Any]] = []
    carry_rows: list[dict[str, Any]] = []
    historical_rows: list[dict[str, Any]] = []

    variant_specs = [
        ("current", 0.0, {}),
        ("pro_rata", incremental_exposure, {symbol: weight for symbol, weight in current_weights.items()}),
    ]
    if target_pool_total > 0:
        target_mix = {
            symbol: symbol_market_values.get(symbol, 0.0) / target_pool_total
            for symbol in target_symbols
            if symbol_market_values.get(symbol, 0.0) > 0
        }
    else:
        target_mix = {symbol: weight for symbol, weight in current_weights.items()}
    variant_specs.append(("targeted_symbols", incremental_exposure, target_mix))

    for variant_name, variant_increment, allocation_mix in variant_specs:
        rows: list[dict[str, Any]] = []
        for row in supported_rows:
            symbol = row["symbol"]
            added_market_value = variant_increment * allocation_mix.get(symbol, 0.0)
            target_market_value = row["market_value"] + added_market_value
            target_weight = (
                target_market_value / (gross_position_value + variant_increment)
                if gross_position_value + variant_increment > 0
                else 0.0
            )
            rows.append(
                {
                    "symbol": symbol,
                    "current_market_value": row["market_value"],
                    "added_market_value": added_market_value,
                    "target_market_value": target_market_value,
                    "current_weight": row["current_weight"],
                    "target_weight": target_weight,
                }
            )

        variant_target_weight = float(sum(row["target_weight"] for row in rows if row["symbol"] in target_symbols))
        incremental_income_yield = sum(
            allocation_mix.get(row["symbol"], 0.0) * yield_lookup.get(row["symbol"], 0.0)
            for row in rows
        )
        portfolio_income_yield_after = sum(
            row["target_weight"] * yield_lookup.get(row["symbol"], 0.0) for row in rows
        )

        variants.append(
            {
                "variant": variant_name,
                "target_leverage": target_leverage if variant_name != "current" else current_leverage,
                "gross_exposure": gross_position_value + variant_increment,
                "incremental_exposure": variant_increment,
                "estimated_margin_debit": current_debit if variant_name == "current" else target_debit,
                "estimated_maintenance_margin": (
                    maint_margin_req if variant_name == "current" else target_maint_margin
                ),
                "estimated_excess_liquidity": (
                    excess_liquidity if variant_name == "current" else target_excess_liquidity
                ),
                "estimated_cushion": (
                    cushion if variant_name == "current" and cushion is not None else (
                        (excess_liquidity / net_liquidation) if variant_name == "current" else target_cushion
                    )
                ),
                "target_symbol_weight_before": current_target_weight,
                "target_symbol_weight_after": variant_target_weight,
                "incremental_income_yield": incremental_income_yield,
                "portfolio_income_yield_after": portfolio_income_yield_after,
                "drawdown_to_maintenance": (
                    (1 - maintenance_ratio * current_leverage) / (current_leverage * (1 - maintenance_ratio))
                    if variant_name == "current" and current_leverage * (1 - maintenance_ratio)
                    else drawdown_to_maintenance
                ),
            }
        )

        for row in rows:
            weight_changes.append(
                {
                    "variant": variant_name,
                    "symbol": row["symbol"],
                    "current_market_value": row["current_market_value"],
                    "added_market_value": row["added_market_value"],
                    "target_market_value": row["target_market_value"],
                    "current_weight": row["current_weight"],
                    "target_weight": row["target_weight"],
                    "weight_delta": row["target_weight"] - row["current_weight"],
                }
            )

        if variant_name != "current":
            for rate in funding_rates:
                gross_distribution_income = variant_increment * incremental_income_yield
                post_tax_distribution_income = gross_distribution_income * (1 - tax_rate)
                annual_margin_interest = target_debit * rate
                carry_rows.append(
                    {
                        "variant": variant_name,
                        "funding_rate": rate,
                        "annual_margin_interest": annual_margin_interest,
                        "gross_distribution_income": gross_distribution_income,
                        "post_tax_distribution_income": post_tax_distribution_income,
                        "net_annual_carry": annual_margin_interest - post_tax_distribution_income,
                        "net_annual_carry_on_nav": (
                            (annual_margin_interest - post_tax_distribution_income) / net_liquidation
                            if net_liquidation
                            else 0.0
                        ),
                    }
                )

        variant_gross = gross_position_value + variant_increment
        variant_leverage = variant_gross / net_liquidation if net_liquidation else 0.0
        for shock in shock_magnitudes:
            loss_all = variant_gross * shock
            gross_after_all = variant_gross - loss_all
            nav_after_all = net_liquidation - loss_all
            maint_after_all = maintenance_ratio * gross_after_all
            excess_after_all = nav_after_all - maint_after_all
            shock_rows.append(
                {
                    "variant": variant_name,
                    "shock_scope": "portfolio",
                    "shock": shock,
                    "gross_after_shock": gross_after_all,
                    "nav_after_shock": nav_after_all,
                    "nav_return": (-loss_all / net_liquidation) if net_liquidation else 0.0,
                    "maintenance_margin_after_shock": maint_after_all,
                    "excess_liquidity_after_shock": excess_after_all,
                    "cushion_after_shock": (excess_after_all / nav_after_all) if nav_after_all > 0 else None,
                    "maintenance_breach": excess_after_all < 0,
                }
            )

            target_loss = variant_gross * variant_target_weight * shock
            gross_after_target = variant_gross - target_loss
            nav_after_target = net_liquidation - target_loss
            maint_after_target = maintenance_ratio * gross_after_target
            excess_after_target = nav_after_target - maint_after_target
            shock_rows.append(
                {
                    "variant": variant_name,
                    "shock_scope": "target_symbols_only",
                    "shock": shock,
                    "gross_after_shock": gross_after_target,
                    "nav_after_shock": nav_after_target,
                    "nav_return": (-target_loss / net_liquidation) if net_liquidation else 0.0,
                    "maintenance_margin_after_shock": maint_after_target,
                    "excess_liquidity_after_shock": excess_after_target,
                    "cushion_after_shock": (
                        (excess_after_target / nav_after_target) if nav_after_target > 0 else None
                    ),
                    "maintenance_breach": excess_after_target < 0,
                }
            )

        if returns is not None and not returns.empty:
            weights_after = pd.Series(
                {row["symbol"]: row["target_weight"] for row in rows},
                dtype=float,
            ).reindex(returns.columns).fillna(0)
            daily = (returns @ weights_after) * variant_leverage
            metrics = _daily_series_metrics(daily)
            historical_rows.append(
                {
                    "variant": variant_name,
                    "gross_exposure": variant_gross,
                    "nav_leverage": variant_leverage,
                    **metrics,
                }
            )

    diversifier_correlations: list[dict[str, Any]] = []
    if returns is not None and not returns.empty:
        available_target_symbols = [symbol for symbol in target_symbols if symbol in returns.columns]
        if available_target_symbols:
            target_weights = current_weights.reindex(available_target_symbols).fillna(0)
            if float(target_weights.sum()) > 0:
                target_weights = target_weights / float(target_weights.sum())
                target_daily = returns[available_target_symbols] @ target_weights
                current_daily = returns @ current_weights.reindex(returns.columns).fillna(0)
                for symbol in returns.columns:
                    if symbol in available_target_symbols:
                        continue
                    asset_daily = returns[symbol]
                    variance = float(target_daily.var(ddof=1))
                    covariance = float(asset_daily.cov(target_daily))
                    diversifier_correlations.append(
                        {
                            "symbol": symbol,
                            "current_weight": float(current_weights.get(symbol, 0.0)),
                            "correlation_to_target_symbols": float(asset_daily.corr(target_daily)),
                            "correlation_to_current_portfolio": float(asset_daily.corr(current_daily)),
                            "beta_to_target_symbols": (covariance / variance) if variance else 0.0,
                        }
                    )

    result = {
        "assumptions": {
            "target_leverage": target_leverage,
            "target_symbols": target_symbols,
            "shock_magnitudes": shock_magnitudes,
            "funding_rates": funding_rates,
            "tax_rate": tax_rate,
            "maintenance_ratio": maintenance_ratio,
            "distribution_yield_source": "yfinance info fields with optional user overrides",
        },
        "baseline": {
            "net_liquidation": net_liquidation,
            "gross_position_value": gross_position_value,
            "current_leverage": current_leverage,
            "total_cash_value": total_cash_value,
            "current_margin_debit": current_debit,
            "maint_margin_req": maint_margin_req,
            "excess_liquidity": excess_liquidity,
            "cushion": cushion if cushion is not None else (excess_liquidity / net_liquidation),
            "modeled_supported_gross": modeled_gross,
        },
        "variants": variants,
        "weight_changes": weight_changes,
        "shock_scenarios": shock_rows,
        "carry_scenarios": carry_rows,
        "historical_variant_metrics": historical_rows,
        "diversifier_correlations": diversifier_correlations,
        "distribution_yields": [
            {"symbol": symbol, "distribution_yield": rate}
            for symbol, rate in sorted(yield_lookup.items())
        ],
    }
    return result, warnings


def _clean_plotly_json(value: Any) -> Any:
    import numpy as np
    import pandas as pd

    if isinstance(value, dict):
        return {key: _clean_plotly_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_plotly_json(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_plotly_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return _clean_plotly_json(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _riskfolio_holding_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    positions = IbkrClient.get_positions()
    total_value = 0.0
    rows: list[dict[str, Any]] = []

    for position in positions:
        sec_type = str(position.get("sec_type") or "").upper()
        market_value = _to_float(position.get("market_value"))
        quantity = _to_float(position.get("position"))
        included = True
        exclusion_reason = None

        if sec_type not in _RISKFOLIO_SUPPORTED_SEC_TYPES:
            included = False
            exclusion_reason = f"Unsupported sec_type: {sec_type or 'unknown'}"
        elif quantity <= 0:
            included = False
            exclusion_reason = "Only long positions are included."
        elif market_value <= 0:
            included = False
            exclusion_reason = "Market value is missing or non-positive."

        row = {
            "symbol": position.get("symbol"),
            "sec_type": sec_type,
            "currency": position.get("currency"),
            "position": quantity,
            "market_value": market_value,
            "current_weight": 0.0,
            "market_price": position.get("market_price"),
            "average_cost": position.get("average_cost"),
            "unrealized_pnl": position.get("unrealized_pnl"),
            "included": included,
            "exclusion_reason": exclusion_reason,
        }
        if included:
            total_value += market_value
        rows.append(row)

    for row in rows:
        if row["included"] and total_value:
            row["current_weight"] = row["market_value"] / total_value

    return rows, [row for row in rows if row["included"]]


def _riskfolio_returns(duration: str, delayed: bool) -> tuple[Any, Any]:
    import pandas as pd

    _, holdings = _riskfolio_holding_rows()
    if len(holdings) < 2:
        raise ValueError("At least two long stock/ETF holdings are required.")

    prices = {}
    for holding in holdings:
        symbol = holding["symbol"]
        bars = IbkrClient.get_historical(
            symbol=symbol,
            duration=duration,
            bar_size="1 day",
            what_to_show="TRADES",
            use_rth=True,
            delayed=delayed,
        )
        df = pd.DataFrame(bars)
        if df.empty or "date" not in df or "close" not in df:
            raise ValueError(f"Missing historical prices for {symbol}.")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date", "close"]).sort_values("date")
        prices[symbol] = pd.Series(df["close"].astype(float).values, index=df["date"])

    price_df = pd.concat(prices, axis=1).ffill().dropna()
    if len(price_df) < 30:
        raise ValueError("At least 30 aligned daily price observations are required.")

    returns = price_df.pct_change(fill_method=None).dropna()
    weights = pd.Series({row["symbol"]: row["current_weight"] for row in holdings})
    weights = weights.reindex(returns.columns).fillna(0)
    weights = weights / weights.sum()
    return returns, weights


def _riskfolio_historical_nav_exposure(duration: str, delayed: bool) -> Any:
    import pandas as pd

    _, holdings = _riskfolio_holding_rows()
    if len(holdings) < 2:
        raise ValueError("At least two long stock/ETF holdings are required.")

    prices = {}
    for holding in holdings:
        symbol = holding["symbol"]
        bars = IbkrClient.get_historical(
            symbol=symbol,
            duration=duration,
            bar_size="1 day",
            what_to_show="TRADES",
            use_rth=True,
            delayed=delayed,
        )
        df = pd.DataFrame(bars)
        if df.empty or "date" not in df or "close" not in df:
            raise ValueError(f"Missing historical prices for {symbol}.")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date", "close"]).sort_values("date")
        prices[symbol] = pd.Series(df["close"].astype(float).values, index=df["date"])

    price_df = pd.concat(prices, axis=1).ffill().dropna()
    if len(price_df) < 30:
        raise ValueError("At least 30 aligned daily price observations are required.")

    returns = price_df.pct_change(fill_method=None).dropna()
    if returns.empty:
        raise ValueError("Historical prices did not produce usable returns.")

    weights = pd.Series({row["symbol"]: row["current_weight"] for row in holdings})
    weights = weights.reindex(returns.columns).fillna(0)
    weights = weights / weights.sum()
    total_value = sum(_to_float(row.get("market_value")) for row in holdings)
    if total_value <= 0:
        raise ValueError("Included portfolio market value is missing or non-positive.")

    daily = returns @ weights
    growth = pd.concat([pd.Series([1.0], index=[price_df.index.min()]), (1 + daily).cumprod()])
    nav = growth / growth.iloc[-1] * total_value
    return pd.DataFrame(
        {
            "historical_nav": nav,
            "historical_exposure": nav,
        }
    ).sort_index()


def _riskfolio_optimize(returns: Any, risk_free_rate: float, max_weight: float) -> Any:
    import riskfolio as rp

    port = rp.Portfolio(returns=returns)
    port.assets_stats(method_mu="hist", method_cov="hist")
    port.upperlng = max_weight
    weights = port.optimization(
        model="Classic",
        rm="MV",
        obj="Sharpe",
        rf=risk_free_rate,
        l=0,
        hist=True,
    )
    if weights is None or weights.empty:
        raise ValueError("Riskfolio optimizer did not produce weights.")
    series = weights.iloc[:, 0].astype(float).clip(lower=0)
    total = series.sum()
    if total <= 0:
        raise ValueError("Riskfolio optimizer returned zero total weight.")
    return series / total


def _portfolio_metrics(returns: Any, weights: Any, risk_free_rate: float) -> dict[str, float]:
    import numpy as np

    weights = weights.reindex(returns.columns).fillna(0)
    daily = returns @ weights
    expected_return = float(daily.mean() * 252)
    volatility = float(daily.std(ddof=1) * np.sqrt(252))
    downside = daily[daily < 0].std(ddof=1) * np.sqrt(252)
    sharpe = (expected_return - risk_free_rate) / volatility if volatility else 0.0
    sortino = (expected_return - risk_free_rate) / downside if downside else 0.0
    cumulative = (1 + daily).cumprod()
    drawdown = cumulative / cumulative.cummax() - 1
    var_95 = daily.quantile(0.05)
    return {
        "expected_return": expected_return,
        "volatility": volatility,
        "sharpe_ratio": float(sharpe),
        "sortino_ratio": float(sortino),
        "max_drawdown": float(drawdown.min()),
        "var_95": float(var_95),
        "cvar_95": float(daily[daily <= var_95].mean()),
    }


def _riskfolio_risk_contribution_rows(duration: str, delayed: bool) -> list[dict[str, Any]]:
    returns, weights = _riskfolio_returns(duration=duration, delayed=delayed)
    cov = returns.cov() * 252
    marginal = cov @ weights
    variance = float(weights.T @ cov @ weights)
    contributions = weights * marginal / variance if variance > 0 else weights * 0
    return [
        {
            "symbol": symbol,
            "ticker": symbol,
            "current_weight": float(weights.get(symbol, 0)),
            "risk_contribution": float(value),
            "risk_weight_gap": float(value - weights.get(symbol, 0)),
            "bubble_size": float(abs(value - weights.get(symbol, 0)) + 0.01),
        }
        for symbol, value in contributions.fillna(0).items()
    ]


def _riskfolio_allocation_rows() -> list[dict[str, Any]]:
    _, included = _riskfolio_holding_rows()
    rows: list[dict[str, Any]] = []
    for row in included:
        unrealized_pnl = _to_float(row.get("unrealized_pnl"))
        cost_basis = row["market_value"] - unrealized_pnl
        unrealized_pnl_percent = (
            unrealized_pnl / cost_basis
            if row.get("unrealized_pnl") is not None and cost_basis
            else 0.0
        )
        rows.append(
            {
                "symbol": row["symbol"],
                "market_value": row["market_value"],
                "current_weight": row["current_weight"],
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_percent": unrealized_pnl_percent,
            }
        )
    return rows


def _riskfolio_asset_risk_return_rows(
    duration: str, delayed: bool, risk_free_rate: float
) -> list[dict[str, Any]]:
    returns, weights = _riskfolio_returns(duration=duration, delayed=delayed)
    rows: list[dict[str, Any]] = []
    for symbol in returns.columns:
        expected_return = float(returns[symbol].mean() * 252)
        volatility = float(returns[symbol].std(ddof=1) * np.sqrt(252))
        sharpe = (expected_return - risk_free_rate) / volatility if volatility else 0.0
        rows.append(
            {
                "symbol": symbol,
                "expected_return": expected_return,
                "volatility": volatility,
                "sharpe_ratio": sharpe,
                "current_weight": float(weights.get(symbol, 0)),
            }
        )
    return rows


def _riskfolio_tail_risk_contribution_rows(duration: str, delayed: bool) -> list[dict[str, Any]]:
    returns, weights = _riskfolio_returns(duration=duration, delayed=delayed)
    weights = weights.reindex(returns.columns).fillna(0)
    daily = returns @ weights
    var_95 = daily.quantile(0.05)
    portfolio_cvar = float(daily[daily <= var_95].mean())
    tail_mask = daily <= var_95
    rows: list[dict[str, Any]] = []
    for symbol in returns.columns:
        weight = float(weights.get(symbol, 0))
        asset_tail_mean = float(returns[symbol][tail_mask].mean())
        contribution = weight * asset_tail_mean / portfolio_cvar if portfolio_cvar else 0.0
        rows.append(
            {
                "symbol": symbol,
                "current_weight": weight,
                "cvar_contribution": contribution,
                "cvar_weight_gap": contribution - weight,
            }
        )
    return rows


def _riskfolio_drawdown_data(duration: str, delayed: bool) -> pd.DataFrame:
    returns, weights = _riskfolio_returns(duration=duration, delayed=delayed)
    weights = weights.reindex(returns.columns).fillna(0)
    daily = returns @ weights
    cumulative = (1 + daily).cumprod()
    drawdown = cumulative / cumulative.cummax() - 1
    return pd.DataFrame({"date": drawdown.index.astype(str), "drawdown": drawdown.values})


def _riskfolio_cumulative_returns_data(duration: str, delayed: bool) -> pd.DataFrame:
    returns, weights = _riskfolio_returns(duration=duration, delayed=delayed)
    weights = weights.reindex(returns.columns).fillna(0)
    cumulative = (1 + returns).cumprod() - 1
    rows: list[dict[str, Any]] = []
    for date, row in cumulative.iterrows():
        for symbol, value in row.items():
            rows.append({"date": str(date), "symbol": symbol, "cumulative_return": float(value)})
    return pd.DataFrame(rows)


def _riskfolio_returns_distribution_data(duration: str, delayed: bool) -> pd.DataFrame:
    import numpy as np

    returns, weights = _riskfolio_returns(duration=duration, delayed=delayed)
    weights = weights.reindex(returns.columns).fillna(0)
    daily = returns @ weights
    counts, bin_edges = np.histogram(daily.dropna(), bins=40)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    return pd.DataFrame({"bin_center": bin_centers, "frequency": counts.astype(float)})


def _option_chain_decision_signal(
    *,
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
    min_dte: int = 7,
    max_dte: int = 120,
    max_contracts: int = 160,
    delayed: bool = True,
) -> dict[str, Any]:
    from openbb_ibkr.utils.options_signals import build_option_decision_signal

    rows = IbkrClient.get_option_screener(
        symbol=symbol,
        exchange=exchange,
        currency=currency,
        min_dte=min_dte,
        max_dte=max_dte,
        right="both",
        min_volume=0,
        min_open_interest=0,
        max_spread_percent=None,
        min_delta=None,
        max_delta=None,
        max_contracts=max_contracts,
        delayed=delayed,
    )
    bars = IbkrClient.get_historical(symbol=symbol, duration="6 M", delayed=delayed)
    signal = build_option_decision_signal(rows, bars)
    signal["symbol"] = signal.get("symbol") or symbol.upper()
    return signal


def _option_chain_signal_rows(*, symbols: list[str], delayed: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        signal = _option_chain_decision_signal(symbol=symbol, delayed=delayed)
        if signal.get("symbol"):
            rows.append(signal)
    return rows


@router.command(methods=["POST"])
def configure(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    read_only: Optional[bool] = None,
    delayed: Optional[bool] = None,
) -> OBBject[dict[str, Any]]:
    """Configure IBKR connection parameters.

    Parameters
    ----------
    host : str, optional
        TWS/IB Gateway host address. Default: 127.0.0.1
    port : int, optional
        API port. Default: 7497 (TWS) or 7496 (IB Gateway)
    client_id : int, optional
        API client ID. Default: 1
    read_only : bool, optional
        Ignored. IBKR connections are always opened in read-only mode.
    delayed : bool, optional
        Use delayed market data for quotes and historical data
    """
    IbkrClient.configure(
        host=_clean_query_value(host),
        port=_clean_query_value(port),
        client_id=_clean_query_value(client_id),
        read_only=True,
        delayed=delayed,
    )
    return OBBject(
        results={
            "host": IbkrClient._host,
            "port": IbkrClient._port,
            "client_id": IbkrClient._client_id,
            "read_only": IbkrClient._read_only,
            "delayed": IbkrClient._delayed,
            "connected": IbkrClient.is_connected(),
        }
    )


@router.command(methods=["GET"])
def account_summary(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[AccountSummaryItem]]:
    """Get IBKR account summary including net liquidation value, cash balances, buying power, and margin data.

    Returns account tags such as NetLiquidation, TotalCashValue, BuyingPower,
    GrossPositionValue, EquityWithLoanValue, InitMarginReq, MaintMarginReq,
    AvailableFunds, ExcessLiquidity, Cushion, and Full* margin variants.

    Parameters
    ----------
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_account_summary()
    except IbkrConnectionError as e:
        return OBBject(results=[], warnings=[Warning_(category="IBKR", message=str(e))])
    results = [AccountSummaryItem(**item) for item in items]
    return OBBject(results=results)


@router.command(methods=["GET"])
def margin_summary(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[MarginRequirement]:
    """Get IBKR account-level margin requirement summary.

    Returns init margin req, maint margin req, available funds, excess liquidity,
    cushion, SMA, and lookahead/full variants.

    Parameters
    ----------
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        data = IbkrClient.get_margin_summary()
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=MarginRequirement(**data))


@router.command(methods=["GET"])
def account_values(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[dict[str, Any]]:
    """Get IBKR account values organized by currency.

    Returns a nested dict keyed by currency, where each entry contains tags
    like NetLiquidation, TotalCashValue, BuyingPower, InitMarginReq, etc.

    Parameters
    ----------
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        values = IbkrClient.get_account_values()
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=values)


@router.command(methods=["GET"])
def positions(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[Position]]:
    """Get current IBKR portfolio positions with P&L.

    Returns symbol, position size, market price, market value, average cost,
    unrealized P&L, and realized P&L for each holding. Includes contract
    details (conId, strike, right, multiplier, expiry) for options/futures.

    Parameters
    ----------
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_positions()
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    results = [Position(**item) for item in items]
    return OBBject(results=results)


@router.command(methods=["GET"])
def leverage_analysis(
    target_leverage: float = 1.4,
    target_symbols: Optional[str] = None,
    funding_rates: Optional[str] = None,
    shocks: Optional[str] = None,
    tax_rate: float = 0.24,
    distribution_yields: Optional[str] = None,
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[dict[str, Any]]:
    """Analyze raising IBKR gross leverage from the current level to a target level.

    Returns a decision-oriented analysis object with:
    - baseline account leverage and margin state
    - target vs current exposure and debit estimates
    - allocation deltas for pro-rata vs targeted leverage
    - margin shock tables for portfolio-wide and target-sleeve-only shocks
    - carry tables across multiple funding-rate assumptions
    - optional historical variant metrics and diversifier correlations

    The default `target_symbols` assumption reflects the current U.S. equity sleeve:
    `VTI,QQQM,SCHD,SPMO,USMV,AVUV`. Override it for other portfolios.
    """
    _configure_from_query(host, port, client_id)
    warning_messages: list[str] = []
    rates = _parse_rate_list(funding_rates, _DEFAULT_FUNDING_RATES)
    shock_magnitudes = _parse_rate_list(shocks, _DEFAULT_LEVERAGE_SHOCKS)
    symbols = _parse_symbol_list(target_symbols, _DEFAULT_LEVERAGE_TARGET_SYMBOLS)
    yield_overrides = _parse_distribution_yield_overrides(distribution_yields)
    returns: Optional[pd.DataFrame] = None

    try:
        positions_data = IbkrClient.get_positions()
        account_summary_data = IbkrClient.get_account_summary()
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])

    try:
        returns, _ = _riskfolio_returns(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        warning_messages.append(
            f"Historical-return analytics were skipped: {e}"
        )

    try:
        result, helper_warnings = _build_leverage_analysis(
            positions=positions_data,
            account_summary_items=account_summary_data,
            target_leverage=target_leverage,
            target_symbols=symbols,
            funding_rates=rates,
            shock_magnitudes=shock_magnitudes,
            tax_rate=tax_rate,
            distribution_yields=yield_overrides,
            returns=returns,
        )
    except ValueError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])

    warning_messages.extend(helper_warnings)
    warnings = [Warning_(category="IBKR", message=message) for message in warning_messages]
    return OBBject(results=result, warnings=warnings)


@router.command(methods=["GET"])
def riskfolio_leverage_target(
    target_leverage: float = 1.4,
    risk_free_rate: float = 0.0,
    max_weight: float = 0.2,
    sleeve_bounds: Optional[str] = None,
    sleeve_memberships: Optional[str] = None,
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[dict[str, Any]]:
    """Optimize a target levered allocation with Riskfolio under sleeve constraints.

    The optimizer solves for invested weights that sum to 100%, then scales the
    result to `target_leverage * net_liquidation` to produce dollar targets.

    Default sleeve assumptions are tailored to the current portfolio:
    - us_equity: VTI, QQQM, SCHD, SPMO, USMV, AVUV
    - international_equity: VXUS, VWO, AVDV
    - bonds_cash: VGIT, STIP, SGOV
    - alternatives_real_assets: DBMF, PDBC, GLDM

    Override `sleeve_bounds` as:
    `us_equity=0.40:0.50,international_equity=0.20:0.30,bonds_cash=0.15:0.25,alternatives_real_assets=0.10:0.20`

    Override `sleeve_memberships` as:
    `us_equity=VTI|QQQM;international_equity=VXUS|VWO`
    """
    _configure_from_query(host, port, client_id)
    warning_messages: list[str] = []
    memberships = _parse_sleeve_memberships(sleeve_memberships)
    bounds = _parse_sleeve_bounds(sleeve_bounds)

    try:
        positions_data = IbkrClient.get_positions()
        account_summary_data = IbkrClient.get_account_summary()
        returns, _ = _riskfolio_returns(duration=duration, delayed=delayed)
        result = _build_constrained_leverage_target(
            positions=positions_data,
            account_summary_items=account_summary_data,
            returns=returns,
            target_leverage=target_leverage,
            risk_free_rate=risk_free_rate,
            max_weight=max_weight,
            sleeve_map=memberships,
            sleeve_bounds=bounds,
        )
        warning_messages.extend(result.pop("warnings", []))
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=None, warnings=[Warning_(category="Riskfolio", message=str(e))])

    warnings = [Warning_(category="Riskfolio", message=message) for message in warning_messages]
    return OBBject(results=result, warnings=warnings)


@router.command(methods=["GET"])
def position_detail(
    symbol: str,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[Optional[Position]]:
    """Get details for a specific IBKR portfolio position.

    Parameters
    ----------
    symbol : str
        Stock or instrument symbol (e.g., 'AAPL')
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        item = IbkrClient.get_position_detail(symbol)
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    if item is None:
        return OBBject(
            results=None,
            warnings=[Warning_(category="IBKR", message=f"No position found for symbol: {symbol}")],
        )
    return OBBject(results=Position(**item))


@router.command(methods=["GET"])
def open_orders(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[Order]]:
    """Get all open orders.

    Returns order ID, symbol, action (BUY/SELL), quantity, order type,
    limit/aux price, status, filled/remaining quantities, and timestamps.

    Parameters
    ----------
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_open_orders()
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    results = [Order(**item) for item in items]
    return OBBject(results=results)


@router.command(methods=["GET"])
def completed_orders(
    api_only: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[Order]]:
    """Get completed orders from the IBKR API session.

    Parameters
    ----------
    api_only : bool, default=True
        If True, returns only orders completed during this API session.
        If False, returns all completed orders (may be slow).
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_completed_orders(api_only=api_only)
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    results = [Order(**item) for item in items]
    return OBBject(results=results)


@router.command(methods=["GET"])
def trades(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[Trade]]:
    """Get all trades from the current IBKR API session.

    Returns trade details including symbol, action, quantity, fill price,
    commission, exchange, and individual fill executions.

    Parameters
    ----------
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_trades()
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    results = [Trade(**item) for item in items]
    return OBBject(results=results)


@router.command(methods=["GET"])
def quote(
    symbol: str,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[Quote]:
    """Get a market data quote for a symbol via IBKR.

    Parameters
    ----------
    symbol : str
        Stock ticker symbol (e.g., 'AAPL')
    delayed : bool, default=False
        Request delayed data. Required if TWS/IB Gateway API is in read-only mode.
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        item = IbkrClient.get_quote(symbol, delayed=delayed)
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=Quote(**item))


@router.command(methods=["GET"])
def historical(
    symbol: str,
    duration: str = "1 M",
    bar_size: str = "1 day",
    what_to_show: str = "TRADES",
    use_rth: bool = True,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[HistoricalBar]]:
    """Get historical price data for a symbol via IBKR.

    Parameters
    ----------
    symbol : str
        Stock ticker symbol
    duration : str, default='1 M'
        Time span (e.g., '1 D', '1 W', '1 M', '1 Y', '10 Y')
    bar_size : str, default='1 day'
        Bar size (e.g., '1 min', '5 mins', '1 hour', '1 day', '1 week')
    what_to_show : str, default='TRADES'
        Data type: 'TRADES', 'MIDPOINT', 'BID', 'ASK', 'ADJUSTED_LAST'
    use_rth : bool, default=True
        If True, use regular trading hours only. If False, include extended hours.
    delayed : bool, default=False
        Request delayed data. Required if TWS/IB Gateway API is in read-only mode.
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_historical(
            symbol=symbol,
            duration=duration,
            bar_size=bar_size,
            what_to_show=what_to_show,
            use_rth=use_rth,
            delayed=delayed,
        )
    except IbkrConnectionError as e:
        return OBBject(results=None, warnings=[Warning_(category="IBKR", message=str(e))])
    results = [HistoricalBar(**item) for item in items]
    return OBBject(results=results)


@router.command(
    methods=["GET"],
    widget_config=_market_quote_widget_config(
        name="IBKR Market Quote",
        sub_category="Market Data",
        widget_id="ibkr_market_quote_custom_obb",
    ),
)
def market_quote(
    symbol: str,
    sec_type: str = "STK",
    exchange: str = "SMART",
    currency: str = "USD",
    primary_exchange: Optional[str] = None,
    con_id: Optional[int] = None,
    local_symbol: Optional[str] = None,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[MarketQuote]]:
    """Get a normalized IBKR quote for supported subscribed asset classes."""
    _configure_from_query(host, port, client_id)
    try:
        item = IbkrClient.get_market_quote(
            symbol=symbol,
            sec_type=sec_type,
            exchange=exchange,
            currency=currency,
            primary_exchange=_clean_query_value(primary_exchange),
            con_id=con_id,
            local_symbol=_clean_query_value(local_symbol),
            delayed=delayed,
        )
    except Exception as e:
        return OBBject(results=[], warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=[MarketQuote(**item)])


@router.command(methods=["GET"])
def market_historical(
    symbol: str,
    sec_type: str = "STK",
    exchange: str = "SMART",
    currency: str = "USD",
    primary_exchange: Optional[str] = None,
    con_id: Optional[int] = None,
    local_symbol: Optional[str] = None,
    duration: str = "1 M",
    bar_size: str = "1 day",
    what_to_show: str = "TRADES",
    use_rth: bool = True,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[HistoricalBar]]:
    """Get historical bars for an IBKR contract built from explicit asset-class fields."""
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_market_historical(
            symbol=symbol,
            sec_type=sec_type,
            exchange=exchange,
            currency=currency,
            primary_exchange=_clean_query_value(primary_exchange),
            con_id=con_id,
            local_symbol=_clean_query_value(local_symbol),
            duration=duration,
            bar_size=bar_size,
            what_to_show=what_to_show,
            use_rth=use_rth,
            delayed=delayed,
        )
    except Exception as e:
        return OBBject(results=[], warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=[HistoricalBar(**item) for item in items])


@router.command(
    methods=["GET"],
    widget_config=_contract_widget_config(
        name="IBKR Contract Search",
        widget_id="ibkr_contract_search_custom_obb",
    ),
)
def contract_search(
    symbol: str,
    sec_type: Optional[str] = None,
    exchange: str = "SMART",
    currency: str = "USD",
    primary_exchange: Optional[str] = None,
    con_id: Optional[int] = None,
    local_symbol: Optional[str] = None,
    limit: int = 50,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[ContractSearchResult]]:
    """Search IBKR contracts or resolve details for an explicit contract request."""
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.search_contracts(
            symbol=symbol,
            sec_type=_clean_query_value(sec_type),
            exchange=exchange,
            currency=currency,
            primary_exchange=_clean_query_value(primary_exchange),
            con_id=con_id,
            local_symbol=_clean_query_value(local_symbol),
            limit=limit,
        )
    except Exception as e:
        return OBBject(results=[], warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=[ContractSearchResult(**item) for item in items])


@router.command(
    methods=["GET"],
    widget_config=_contract_widget_config(
        name="IBKR Contract Details",
        widget_id="ibkr_contract_details_custom_obb",
    ),
)
def contract_details(
    symbol: str,
    sec_type: str = "STK",
    exchange: str = "SMART",
    currency: str = "USD",
    primary_exchange: Optional[str] = None,
    con_id: Optional[int] = None,
    local_symbol: Optional[str] = None,
    limit: int = 25,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[ContractDetails]]:
    """Get detailed IBKR contract metadata."""
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_contract_details(
            symbol=symbol,
            sec_type=sec_type,
            exchange=exchange,
            currency=currency,
            primary_exchange=_clean_query_value(primary_exchange),
            con_id=con_id,
            local_symbol=_clean_query_value(local_symbol),
            limit=limit,
        )
    except Exception as e:
        return OBBject(results=[], warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=[ContractDetails(**item) for item in items])


@router.command(
    methods=["GET"],
    widget_config=_market_quote_widget_config(
        name="IBKR FX Spot Quote",
        sub_category="FX",
        widget_id="ibkr_fx_quote_custom_obb",
    ),
)
def fx_quote(
    symbol: str = "EUR.USD",
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[MarketQuote]]:
    """Get an IDEALPRO FX spot quote, for example EUR.USD."""
    return market_quote(
        symbol=symbol,
        sec_type="CASH",
        exchange="IDEALPRO",
        currency="USD",
        delayed=delayed,
        host=host,
        port=port,
        client_id=client_id,
    )


@router.command(
    methods=["GET"],
    widget_config=_market_quote_widget_config(
        name="IBKR Bond Quote",
        sub_category="Bonds",
        widget_id="ibkr_bond_quote_custom_obb",
    ),
)
def bond_quote(
    symbol: str = "",
    exchange: str = "SMART",
    currency: str = "USD",
    con_id: Optional[int] = None,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[MarketQuote]]:
    """Get a bond quote. Use con_id when ticker resolution is ambiguous."""
    return market_quote(
        symbol=symbol,
        sec_type="BOND",
        exchange=exchange,
        currency=currency,
        con_id=con_id,
        delayed=delayed,
        host=host,
        port=port,
        client_id=client_id,
    )


@router.command(
    methods=["GET"],
    widget_config=_market_quote_widget_config(
        name="IBKR Mutual Fund Quote",
        sub_category="Funds",
        widget_id="ibkr_fund_quote_custom_obb",
    ),
)
def fund_quote(
    symbol: str,
    exchange: str = "FUNDSERV",
    currency: str = "USD",
    con_id: Optional[int] = None,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[MarketQuote]]:
    """Get a U.S. mutual fund quote."""
    return market_quote(
        symbol=symbol,
        sec_type="FUND",
        exchange=exchange,
        currency=currency,
        con_id=con_id,
        delayed=delayed,
        host=host,
        port=port,
        client_id=client_id,
    )


@router.command(
    methods=["GET"],
    widget_config=_market_quote_widget_config(
        name="IBKR Crypto/Paxos Quote",
        sub_category="Crypto",
        widget_id="ibkr_crypto_quote_custom_obb",
    ),
)
def crypto_quote(
    symbol: str = "BTC",
    exchange: str = "PAXOS",
    currency: str = "USD",
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[MarketQuote]]:
    """Get a Paxos crypto quote."""
    return market_quote(
        symbol=symbol,
        sec_type="CRYPTO",
        exchange=exchange,
        currency=currency,
        delayed=delayed,
        host=host,
        port=port,
        client_id=client_id,
    )


@router.command(
    methods=["GET"],
    widget_config=_market_quote_widget_config(
        name="IBKR CFD Quote",
        sub_category="CFDs",
        widget_id="ibkr_cfd_quote_custom_obb",
    ),
)
def cfd_quote(
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
    con_id: Optional[int] = None,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[MarketQuote]]:
    """Get an index CFD quote. Use con_id when ticker resolution is ambiguous."""
    return market_quote(
        symbol=symbol,
        sec_type="CFD",
        exchange=exchange,
        currency=currency,
        con_id=con_id,
        delayed=delayed,
        host=host,
        port=port,
        client_id=client_id,
    )


@router.command(
    methods=["GET"],
    widget_config=_market_quote_widget_config(
        name="IBKR Metals/Commodity Quote",
        sub_category="Commodities",
        widget_id="ibkr_commodity_quote_custom_obb",
    ),
)
def commodity_quote(
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
    con_id: Optional[int] = None,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[MarketQuote]]:
    """Get a physical metals or commodity quote."""
    return market_quote(
        symbol=symbol,
        sec_type="CMDTY",
        exchange=exchange,
        currency=currency,
        con_id=con_id,
        delayed=delayed,
        host=host,
        port=port,
        client_id=client_id,
    )


@router.command(methods=["GET"])
def option_chain(
    symbol: str,
    exchange: str = "SMART",
    sec_type: str = "STK",
    currency: str = "USD",
    min_dte: int = 0,
    max_dte: int = 60,
    max_strikes: int = 80,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[OptionChainContract]]:
    """Discover IBKR option contract definitions for a U.S. equity or ETF."""
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_option_chain(
            symbol=symbol,
            exchange=exchange,
            sec_type=sec_type,
            currency=currency,
            min_dte=min_dte,
            max_dte=max_dte,
            max_strikes=max_strikes,
            delayed=delayed,
        )
    except IbkrConnectionError as e:
        return OBBject(results=[], warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=[OptionChainContract(**item) for item in items])


@router.command(
    methods=["GET"],
    widget_config=_option_widget_config(),
)
def option_screener(
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
    min_dte: int = 7,
    max_dte: int = 60,
    right: str = "both",
    min_volume: float = 0,
    min_open_interest: float = 0,
    max_spread_percent: Optional[float] = None,
    min_delta: Optional[float] = None,
    max_delta: Optional[float] = None,
    max_contracts: int = 80,
    expiry: Optional[str] = None,
    min_strike: Optional[float] = None,
    max_strike: Optional[float] = None,
    delayed: bool = False,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[OptionScreenerContract]]:
    """Screen IBKR option contracts with live or delayed snapshot data."""
    _configure_from_query(host, port, client_id)
    try:
        items = IbkrClient.get_option_screener(
            symbol=symbol,
            exchange=exchange,
            currency=currency,
            min_dte=min_dte,
            max_dte=max_dte,
            right=right,
            min_volume=min_volume,
            min_open_interest=min_open_interest,
            max_spread_percent=max_spread_percent,
            min_delta=min_delta,
            max_delta=max_delta,
            max_contracts=max_contracts,
            expiry=expiry,
            min_strike=min_strike,
            max_strike=max_strike,
            delayed=delayed,
        )
    except IbkrConnectionError as e:
        return OBBject(results=[], warnings=[Warning_(category="IBKR", message=str(e))])
    return OBBject(results=[OptionScreenerContract(**item) for item in items])


@router.command(
    methods=["GET"],
    widget_config={
        "name": "IBKR Option Decision Signals",
        "description": "3M IV/RV, skew, calls-vs-puts, and decision labels for an optionable underlying.",
        "type": "table",
        "source": ["IBKR"],
        "category": "IBKR",
        "subCategory": "Options",
        "widgetId": "ibkr_option_decision_signals_custom_obb",
        "gridData": {"w": 40, "h": 10},
        "data": {
            "table": {
                "showAll": True,
                "enableAdvanced": True,
                "enableCharts": True,
                "chartView": {
                    "enabled": True,
                    "chartType": "bar",
                    "cellRangeCols": {"bar": ["symbol", "iv_rv_ratio"]},
                    "ignoreCellRange": True,
                },
                "columnsDefs": _OPTION_DECISION_SIGNAL_COLUMNS,
            }
        },
    },
)
def option_decision_signals(
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
    min_dte: int = 7,
    max_dte: int = 120,
    max_contracts: int = 160,
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[OptionDecisionSignal]]:
    """Summarize option-chain IV/RV, skew, and calls-vs-puts into decision labels."""
    _configure_from_query(host, port, client_id)
    try:
        signal = _option_chain_decision_signal(
            symbol=symbol,
            exchange=exchange,
            currency=currency,
            min_dte=min_dte,
            max_dte=max_dte,
            max_contracts=max_contracts,
            delayed=delayed,
        )
    except IbkrConnectionError as e:
        return OBBject(results=[], warnings=[Warning_(category="IBKR", message=str(e))])
    except ValueError as e:
        return OBBject(results=[], warnings=[Warning_(category="Options", message=str(e))])
    return OBBject(results=[OptionDecisionSignal(**signal)])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="bar",
        cell_range_cols=["symbol", "market_value", "current_weight"],
        columns=_RISKFOLIO_HOLDING_COLUMNS,
        sub_category="Riskfolio",
    ),
)
def riskfolio_holdings(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioHolding]]:
    """Get IBKR holdings prepared for Riskfolio portfolio analysis.

    Filters current IBKR positions into supported long stock/ETF holdings,
    normalizes market-value weights, and reports excluded instruments with
    a reason.
    """
    _configure_from_query(host, port, client_id)
    try:
        rows, _ = _riskfolio_holding_rows()
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioHolding(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="treemap",
        cell_range_cols=["symbol", "market_value"],
        columns=_RISKFOLIO_ALLOCATION_COLUMNS,
        sub_category="Riskfolio",
        name="Riskfolio Allocation Table",
        widget_id="ibkr_riskfolio_allocation_table_custom_obb",
    ),
)
def riskfolio_allocation(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioAllocation]]:
    """Get chart-friendly current IBKR allocation for Riskfolio analysis.

    Returns included long stock/ETF positions with market value and current
    normalized portfolio weight.
    """
    _configure_from_query(host, port, client_id)
    try:
        rows = _riskfolio_allocation_rows()
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioAllocation(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config={
        "name": "Riskfolio Allocation Treemap",
        "description": (
            "Plotly treemap of current portfolio allocation sized by market value "
            "and colored by unrealized P&L percent."
        ),
        "type": "chart",
        "source": ["IBKR", "Riskfolio"],
        "category": "IBKR",
        "subCategory": "Riskfolio",
        "widgetId": "ibkr_riskfolio_allocation_treemap_custom_obb",
        "gridData": {"w": 40, "h": 20},
        "params": [
            {"paramName": "host", "show": True},
            {"paramName": "port", "show": True},
            {"paramName": "client_id", "show": True},
            {"paramName": "theme", "value": "dark", "show": False},
        ],
    },
)
def riskfolio_allocation_treemap(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a labeled Plotly treemap for current Riskfolio allocation."""
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        rows = _riskfolio_allocation_rows()
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 30, "r": 30, "t": 30, "b": 30},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return _clean_plotly_json(fig.to_plotly_json())

    labels = [row["symbol"] for row in rows]
    values = [row["market_value"] for row in rows]
    colors = [row["unrealized_pnl_percent"] for row in rows]
    customdata = [
        [
            row["current_weight"],
            row["unrealized_pnl"],
            row["unrealized_pnl_percent"],
        ]
        for row in rows
    ]
    max_abs_color = max([abs(value) for value in colors] + [0.01])

    fig = go.Figure(
        go.Treemap(
            labels=labels,
            parents=[""] * len(labels),
            values=values,
            branchvalues="total",
            customdata=customdata,
            marker={
                "colors": colors,
                "colorscale": [
                    [0, "#b91c1c"],
                    [0.5, "#f8fafc"],
                    [1, "#15803d"],
                ],
                "cmin": -max_abs_color,
                "cmax": max_abs_color,
                "colorbar": {"title": "Unrealized P&L %", "tickformat": ".0%"},
                "line": {"color": "#f8fafc", "width": 2},
            },
            texttemplate=(
                "<b>%{label}</b><br>"
                "%{customdata[0]:.1%}<br>"
                "$%{value:,.0f}"
            ),
            textfont={"color": "#111827", "size": 18},
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Weight: %{customdata[0]:.2%}<br>"
                "Market Value: $%{value:,.2f}<br>"
                "Unrealized P&L: $%{customdata[1]:,.2f}<br>"
                "Unrealized P&L %: %{customdata[2]:+.2%}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        template=template,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        uniformtext={"minsize": 11, "mode": "hide"},
    )
    return _clean_plotly_json(fig.to_plotly_json())


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_chart_widget_config(
        name="Historical NAV and Exposure",
        description=(
            "Plotly line chart of synthetic current-holdings historical NAV "
            "and long gross exposure."
        ),
        widget_id="ibkr_riskfolio_equity_curve_plotly_custom_obb",
    ),
)
def riskfolio_equity_curve(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a Plotly line chart for synthetic historical NAV and exposure."""
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        curve = _riskfolio_historical_nav_exposure(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 40, "r": 40, "t": 40, "b": 40},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return _clean_plotly_json(fig.to_plotly_json())

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[item.isoformat() for item in curve.index],
            y=curve["historical_nav"].astype(float).tolist(),
            mode="lines",
            name="Historical NAV",
            hovertemplate="Date: %{x|%Y-%m-%d}<br>NAV: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[item.isoformat() for item in curve.index],
            y=curve["historical_exposure"].astype(float).tolist(),
            mode="lines",
            name="Historical Exposure",
            line={"dash": "dash"},
            hovertemplate="Date: %{x|%Y-%m-%d}<br>Exposure: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        template=template,
        title="Historical NAV and Exposure",
        yaxis_title="Value",
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        hovermode="x unified",
        margin={"l": 70, "r": 30, "t": 50, "b": 60},
    )
    return _clean_plotly_json(fig.to_plotly_json())


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="groupedBar",
        cell_range_cols=["metric", "current", "optimized"],
        columns=_RISKFOLIO_METRIC_COLUMNS,
        sub_category="Riskfolio",
    ),
)
def riskfolio_metrics(
    duration: str = "1 Y",
    delayed: bool = True,
    risk_free_rate: float = 0.0,
    max_weight: float = 1.0,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioMetric]]:
    """Get current vs Riskfolio-optimized portfolio risk metrics.

    Returns expected return, volatility, Sharpe, Sortino, max drawdown,
    daily VaR 95%, and daily CVaR 95% for the current and optimized
    allocations.
    """
    _configure_from_query(host, port, client_id)
    try:
        returns, current = _riskfolio_returns(duration=duration, delayed=delayed)
        optimized = _riskfolio_optimize(returns, risk_free_rate, max_weight)
        current_metrics = _portfolio_metrics(returns, current, risk_free_rate)
        optimized_metrics = _portfolio_metrics(returns, optimized, risk_free_rate)
        rows = [
            {
                "metric": metric,
                "current": current_value,
                "optimized": optimized_metrics[metric],
                "delta": optimized_metrics[metric] - current_value,
            }
            for metric, current_value in current_metrics.items()
        ]
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioMetric(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="groupedBar",
        cell_range_cols=["symbol", "current_weight", "optimized_weight", "rebalance_delta"],
        columns=_RISKFOLIO_WEIGHT_COLUMNS,
        sub_category="Riskfolio",
    ),
)
def riskfolio_optimized_weights(
    duration: str = "1 Y",
    delayed: bool = True,
    risk_free_rate: float = 0.0,
    max_weight: float = 1.0,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioWeight]]:
    """Get current vs Riskfolio-optimized portfolio weights."""
    _configure_from_query(host, port, client_id)
    try:
        returns, current = _riskfolio_returns(duration=duration, delayed=delayed)
        optimized = _riskfolio_optimize(returns, risk_free_rate, max_weight)
        rows = [
            {
                "symbol": symbol,
                "current_weight": float(current.get(symbol, 0)),
                "optimized_weight": float(optimized.get(symbol, 0)),
                "rebalance_delta": float(optimized.get(symbol, 0) - current.get(symbol, 0)),
            }
            for symbol in current.index
        ]
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioWeight(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="scatter",
        cell_range_cols=["ticker", "current_weight", "risk_contribution"],
        columns=_RISKFOLIO_CONTRIBUTION_COLUMNS,
        sub_category="Riskfolio",
    ),
)
def riskfolio_risk_contribution(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioRiskContribution]]:
    """Get current portfolio volatility risk contribution by symbol."""
    _configure_from_query(host, port, client_id)
    try:
        rows = _riskfolio_risk_contribution_rows(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioRiskContribution(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_chart_widget_config(
        name="Riskfolio Risk Contribution Scatter",
        description=(
            "Plotly scatter chart of current portfolio weight versus volatility risk "
            "contribution, with ticker labels shown on points and in hover text."
        ),
        widget_id="ibkr_riskfolio_risk_contribution_scatter_plotly_custom_obb",
    ),
)
def riskfolio_risk_contribution_scatter(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a labeled Plotly scatter chart for Riskfolio risk contribution."""
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        rows = _riskfolio_risk_contribution_rows(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 40, "r": 40, "t": 40, "b": 40},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return fig.to_plotly_json()

    tickers = [row["ticker"] for row in rows]
    current_weights = [row["current_weight"] for row in rows]
    risk_contributions = [row["risk_contribution"] for row in rows]
    risk_weight_gaps = [row["risk_weight_gap"] for row in rows]
    text_positions = [
        "top center",
        "bottom center",
        "middle right",
        "middle left",
    ]

    fig = go.Figure(
        data=[
            go.Scatter(
                x=current_weights,
                y=risk_contributions,
                customdata=[[gap] for gap in risk_weight_gaps],
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Current Weight: %{x:.2%}<br>"
                    "Risk Contribution: %{y:.2%}<br>"
                    "Risk - Weight Gap: %{customdata[0]:+.2%}"
                    "<extra></extra>"
                ),
                marker={
                    "color": risk_weight_gaps,
                    "colorscale": "RdBu",
                    "line": {"color": "#1f2937", "width": 1},
                    "opacity": 0.78,
                    "showscale": True,
                    "size": 13,
                    "colorbar": {"title": "Risk - Weight"},
                },
                mode="markers+text",
                name="Risk Contribution vs Current Weight",
                text=tickers,
                textfont={"size": 12},
                textposition=[
                    text_positions[index % len(text_positions)]
                    for index in range(len(tickers))
                ],
                type="scatter",
            )
        ]
    )
    fig.add_shape(
        type="line",
        x0=0,
        y0=0,
        x1=max(current_weights + risk_contributions, default=0.1),
        y1=max(current_weights + risk_contributions, default=0.1),
        line={"color": "#9ca3af", "dash": "dash", "width": 1},
    )
    fig.update_layout(
        template=template,
        margin={"l": 70, "r": 40, "t": 30, "b": 60},
        xaxis={"title": "Current Portfolio Weight", "tickformat": ".0%"},
        yaxis={"title": "Risk Contribution", "tickformat": ".0%"},
        hovermode="closest",
        showlegend=False,
    )
    return fig.to_plotly_json()


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_chart_widget_config(
        name="Riskfolio Correlation",
        description="Plotly heatmap of pairwise daily return correlations for included holdings.",
        widget_id="ibkr_riskfolio_correlation_heatmap_plotly_custom_obb",
    ),
)
def riskfolio_correlation(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a Plotly heatmap of pairwise return correlations for included IBKR holdings."""
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        returns, _ = _riskfolio_returns(duration=duration, delayed=delayed)
        corr = returns.corr()
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 40, "r": 40, "t": 40, "b": 40},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return _clean_plotly_json(fig.to_plotly_json())

    symbols = corr.index.astype(str).tolist()
    compared_symbols = corr.columns.astype(str).tolist()
    z_values = corr.astype(float).values.tolist()
    text_values = [[f"{value:.2f}" for value in row] for row in z_values]
    fig = go.Figure(
        data=[
            go.Heatmap(
                z=z_values,
                x=compared_symbols,
                y=symbols,
                zmin=-1,
                zmax=1,
                colorscale="RdBu",
                reversescale=True,
                colorbar={"title": "Correlation"},
                text=text_values,
                texttemplate="%{text}",
                hovertemplate=(
                    "<b>%{y}</b> vs <b>%{x}</b><br>"
                    "Correlation: %{z:.2f}"
                    "<extra></extra>"
                ),
                type="heatmap",
            )
        ]
    )
    fig.update_layout(
        template=template,
        title="Riskfolio Correlation",
        margin={"l": 80, "r": 40, "t": 50, "b": 80},
        xaxis={"title": "Compared Symbol", "side": "bottom"},
        yaxis={"title": "Symbol", "autorange": "reversed"},
    )
    return _clean_plotly_json(fig.to_plotly_json())


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="scatter",
        cell_range_cols=["volatility", "expected_return"],
        columns=_RISKFOLIO_ASSET_RISK_RETURN_COLUMNS,
        sub_category="Riskfolio",
        name="Asset Risk-Return",
        widget_id="ibkr_riskfolio_asset_risk_return_custom_obb",
    ),
)
def riskfolio_asset_risk_return(
    duration: str = "1 Y",
    delayed: bool = True,
    risk_free_rate: float = 0.0,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioAssetRiskReturn]]:
    """Get asset-level risk-return scatter data for current IBKR holdings."""
    _configure_from_query(host, port, client_id)
    try:
        rows = _riskfolio_asset_risk_return_rows(duration=duration, delayed=delayed, risk_free_rate=risk_free_rate)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioAssetRiskReturn(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_chart_widget_config(
        name="Asset Risk-Return Scatter",
        description="Plotly scatter chart of expected return versus volatility, sized by current weight and colored by Sharpe ratio.",
        widget_id="ibkr_riskfolio_asset_risk_return_scatter_plotly_custom_obb",
    ),
)
def riskfolio_asset_risk_return_scatter(
    duration: str = "1 Y",
    delayed: bool = True,
    risk_free_rate: float = 0.0,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a labeled Plotly scatter chart for asset risk-return profile."""
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        rows = _riskfolio_asset_risk_return_rows(duration=duration, delayed=delayed, risk_free_rate=risk_free_rate)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 40, "r": 40, "t": 40, "b": 40},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return _clean_plotly_json(fig.to_plotly_json())

    symbols = [row["symbol"] for row in rows]
    volatilities = [row["volatility"] for row in rows]
    expected_returns = [row["expected_return"] for row in rows]
    sharpe_ratios = [row["sharpe_ratio"] for row in rows]
    current_weights = [row["current_weight"] for row in rows]

    fig = go.Figure(
        data=[
            go.Scatter(
                x=volatilities,
                y=expected_returns,
                mode="markers+text",
                text=symbols,
                textfont={"size": 11},
                textposition="top center",
                marker={
                    "size": [max(8, min(40, w * 1000)) for w in current_weights],
                    "color": sharpe_ratios,
                    "colorscale": "Viridis",
                    "showscale": True,
                    "colorbar": {"title": "Sharpe Ratio"},
                    "line": {"color": "#1f2937", "width": 1},
                    "opacity": 0.85,
                },
                customdata=[[w, s] for w, s in zip(current_weights, sharpe_ratios)],
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Volatility: %{x:.2%}<br>"
                    "Expected Return: %{y:.2%}<br>"
                    "Weight: %{customdata[0]:.2%}<br>"
                    "Sharpe: %{customdata[1]:.2f}"
                    "<extra></extra>"
                ),
            )
        ]
    )
    fig.update_layout(
        template=template,
        title="Asset Risk-Return Profile",
        xaxis_title="Annualized Volatility",
        yaxis_title="Annualized Expected Return",
        xaxis_tickformat=".1%",
        yaxis_tickformat=".1%",
        margin={"l": 60, "r": 40, "t": 50, "b": 60},
        hovermode="closest",
    )
    return _clean_plotly_json(fig.to_plotly_json())


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="bar",
        cell_range_cols=["symbol", "cvar_contribution"],
        columns=_RISKFOLIO_TAIL_RISK_CONTRIBUTION_COLUMNS,
        sub_category="Riskfolio",
        name="Tail Risk Contribution",
        widget_id="ibkr_riskfolio_tail_risk_contribution_custom_obb",
    ),
)
def riskfolio_tail_risk_contribution(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioTailRiskContribution]]:
    """Get CVaR-based tail risk contribution by symbol for current IBKR holdings."""
    _configure_from_query(host, port, client_id)
    try:
        rows = _riskfolio_tail_risk_contribution_rows(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioTailRiskContribution(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_chart_widget_config(
        name="Tail Risk Contribution Bar",
        description="Plotly bar chart of CVaR-based tail risk contribution by symbol, colored by CVaR-weight gap.",
        widget_id="ibkr_riskfolio_tail_risk_contribution_bar_plotly_custom_obb",
    ),
)
def riskfolio_tail_risk_contribution_bar(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a Plotly bar chart for CVaR-based tail risk contribution."""
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        rows = _riskfolio_tail_risk_contribution_rows(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 40, "r": 40, "t": 40, "b": 40},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return _clean_plotly_json(fig.to_plotly_json())

    symbols = [row["symbol"] for row in rows]
    contributions = [row["cvar_contribution"] for row in rows]
    gaps = [row["cvar_weight_gap"] for row in rows]

    fig = go.Figure(
        data=[
            go.Bar(
                x=symbols,
                y=contributions,
                marker={
                    "color": gaps,
                    "colorscale": "RdBu",
                    "line": {"color": "#1f2937", "width": 1},
                },
                customdata=[[g] for g in gaps],
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "CVaR Contribution: %{y:.2%}<br>"
                    "CVaR - Weight Gap: %{customdata[0]:+.2%}"
                    "<extra></extra>"
                ),
            )
        ]
    )
    fig.update_layout(
        template=template,
        title="Tail Risk Contribution (CVaR 95%)",
        yaxis_tickformat=".1%",
        margin={"l": 60, "r": 40, "t": 50, "b": 60},
        showlegend=False,
    )
    return _clean_plotly_json(fig.to_plotly_json())


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="line",
        cell_range_cols=["date", "drawdown"],
        columns=_RISKFOLIO_DRAWDOWN_COLUMNS,
        sub_category="Riskfolio",
        name="Drawdown Table",
        widget_id="ibkr_riskfolio_drawdown_table_custom_obb",
    ),
)
def riskfolio_drawdown_table(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioDrawdown]]:
    """Get portfolio drawdown time series as a table for current IBKR holdings."""
    _configure_from_query(host, port, client_id)
    try:
        df = _riskfolio_drawdown_data(duration=duration, delayed=delayed)
        rows = df.to_dict(orient="records")
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioDrawdown(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_chart_widget_config(
        name="Portfolio Drawdown",
        description="Plotly area chart of portfolio peak-to-trough drawdown over time.",
        widget_id="ibkr_riskfolio_drawdown_plotly_custom_obb",
    ),
)
def riskfolio_drawdown(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a Plotly area chart for portfolio drawdown."""
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        df = _riskfolio_drawdown_data(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 40, "r": 40, "t": 40, "b": 40},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return _clean_plotly_json(fig.to_plotly_json())

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"].astype(str).tolist(),
            y=df["drawdown"].astype(float).tolist(),
            mode="lines",
            name="Drawdown",
            fill="tozeroy",
            line={"color": "#dc2626", "width": 1.5},
            fillcolor="rgba(220, 38, 38, 0.25)",
            hovertemplate="Date: %{x|%Y-%m-%d}<br>Drawdown: %{y:.2%}<extra></extra>",
        )
    )
    fig.update_layout(
        template=template,
        title="Portfolio Drawdown (Underwater Curve)",
        yaxis_title="Drawdown",
        yaxis_tickformat=".1%",
        hovermode="x unified",
        margin={"l": 60, "r": 30, "t": 50, "b": 60},
        showlegend=False,
    )
    return _clean_plotly_json(fig.to_plotly_json())


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="line",
        cell_range_cols=["date", "symbol", "cumulative_return"],
        columns=_RISKFOLIO_CUMULATIVE_RETURN_COLUMNS,
        sub_category="Riskfolio",
        name="Cumulative Returns by Asset",
        widget_id="ibkr_riskfolio_cumulative_returns_table_custom_obb",
    ),
)
def riskfolio_cumulative_returns_table(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioCumulativeReturn]]:
    """Get cumulative returns per asset per date as a table for current IBKR holdings."""
    _configure_from_query(host, port, client_id)
    try:
        df = _riskfolio_cumulative_returns_data(duration=duration, delayed=delayed)
        rows = df.to_dict(orient="records")
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioCumulativeReturn(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_chart_widget_config(
        name="Cumulative Returns by Asset",
        description="Plotly multi-line chart of cumulative returns for each included holding.",
        widget_id="ibkr_riskfolio_cumulative_returns_plotly_custom_obb",
    ),
)
def riskfolio_cumulative_returns(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a Plotly multi-line chart of cumulative returns by asset."""
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        df = _riskfolio_cumulative_returns_data(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 40, "r": 40, "t": 40, "b": 40},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return _clean_plotly_json(fig.to_plotly_json())

    fig = go.Figure()
    for symbol in df["symbol"].unique():
        symbol_df = df[df["symbol"] == symbol]
        fig.add_trace(
            go.Scatter(
                x=symbol_df["date"].astype(str).tolist(),
                y=symbol_df["cumulative_return"].astype(float).tolist(),
                mode="lines",
                name=symbol,
                hovertemplate="%{fullData.name}: %{y:.2%}<extra></extra>",
            )
        )
    fig.update_layout(
        template=template,
        title="Cumulative Returns by Asset",
        yaxis_title="Cumulative Return",
        yaxis_tickformat=".0%",
        hovermode="x unified",
        margin={"l": 60, "r": 30, "t": 50, "b": 60},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.25, "xanchor": "center", "x": 0.5},
    )
    return _clean_plotly_json(fig.to_plotly_json())


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_widget_config(
        chart_type="bar",
        cell_range_cols=["bin_center", "frequency"],
        columns=_RISKFOLIO_DISTRIBUTION_COLUMNS,
        sub_category="Riskfolio",
        name="Returns Distribution Table",
        widget_id="ibkr_riskfolio_returns_distribution_table_custom_obb",
    ),
)
def riskfolio_returns_distribution_table(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[List[RiskfolioDistributionBin]]:
    """Get portfolio daily returns histogram bins as a table for current IBKR holdings."""
    _configure_from_query(host, port, client_id)
    try:
        df = _riskfolio_returns_distribution_data(duration=duration, delayed=delayed)
        rows = df.to_dict(orient="records")
    except (IbkrConnectionError, ImportError, ValueError) as e:
        return OBBject(results=[], warnings=[Warning_(category="Riskfolio", message=str(e))])
    return OBBject(results=[RiskfolioDistributionBin(**row) for row in rows])


@router.command(
    methods=["GET"],
    widget_config=_riskfolio_chart_widget_config(
        name="Returns Distribution",
        description="Plotly histogram of daily portfolio returns with normal distribution overlay and VaR/CVaR markers.",
        widget_id="ibkr_riskfolio_returns_distribution_plotly_custom_obb",
    ),
)
def riskfolio_returns_distribution(
    duration: str = "1 Y",
    delayed: bool = True,
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
    theme: str = "dark",
) -> dict:
    """Get a Plotly histogram of portfolio daily returns with normal overlay and VaR/CVaR markers."""
    import numpy as np
    import plotly.graph_objects as go

    _configure_from_query(host, port, client_id)
    template = "plotly_dark" if theme == "dark" else "plotly_white"
    try:
        returns, weights = _riskfolio_returns(duration=duration, delayed=delayed)
    except (IbkrConnectionError, ImportError, ValueError) as e:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            margin={"l": 40, "r": 40, "t": 40, "b": 40},
            annotations=[
                {
                    "text": str(e),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "align": "center",
                }
            ],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return _clean_plotly_json(fig.to_plotly_json())

    weights = weights.reindex(returns.columns).fillna(0)
    daily = returns @ weights
    mean = float(daily.mean())
    std = float(daily.std(ddof=1))
    var_95 = float(daily.quantile(0.05))
    cvar_95 = float(daily[daily <= var_95].mean())

    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=daily.astype(float).tolist(),
            nbinsx=40,
            name="Daily Returns",
            marker={"color": "#3b82f6", "line": {"color": "#1f2937", "width": 1}},
            opacity=0.75,
            histnorm="probability density",
            hovertemplate="Bin: %{x:.4f}<br>Density: %{y:.4f}<extra></extra>",
        )
    )

    if std > 0:
        x_min = float(daily.min()) - 3 * std
        x_max = float(daily.max()) + 3 * std
        x_norm = np.linspace(x_min, x_max, 200)
        y_norm = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_norm - mean) / std) ** 2)
        fig.add_trace(
            go.Scatter(
                x=x_norm.tolist(),
                y=y_norm.tolist(),
                mode="lines",
                name="Normal Fit",
                line={"color": "#fbbf24", "width": 2, "dash": "dash"},
                hovertemplate="Normal: %{x:.4f}<br>Density: %{y:.4f}<extra></extra>",
            )
        )

    for x_val, color, label in [
        (var_95, "#ef4444", "VaR 95%"),
        (cvar_95, "#b91c1c", "CVaR 95%"),
        (mean, "#9ca3af", "Mean"),
    ]:
        fig.add_vline(
            x=x_val,
            line={"color": color, "width": 2, "dash": "dash"},
            annotation_text=label,
            annotation_position="top",
            annotation={"font": {"color": color, "size": 12}},
        )

    fig.update_layout(
        template=template,
        title="Portfolio Daily Returns Distribution",
        xaxis_title="Daily Return",
        yaxis_title="Probability Density",
        xaxis_tickformat=".2%",
        yaxis_tickformat=".4f",
        hovermode="x unified",
        margin={"l": 60, "r": 30, "t": 50, "b": 60},
        bargap=0.05,
    )
    return _clean_plotly_json(fig.to_plotly_json())


@router.command(methods=["GET"])
def is_connected(
    host: Optional[str] = None,
    port: Optional[str] = None,
    client_id: Optional[str] = None,
) -> OBBject[dict[str, bool]]:
    """Check if the IBKR client is currently connected to TWS/IB Gateway.

    Parameters
    ----------
    host : str, optional
        Override TWS/IB Gateway host for this request
    port : int, optional
        Override API port for this request
    client_id : int, optional
        Override API client ID for this request
    """
    _configure_from_query(host, port, client_id)
    return OBBject(results={"connected": IbkrClient.is_connected()})

