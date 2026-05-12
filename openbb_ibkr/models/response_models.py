from typing import List, Optional

from openbb_core.provider.abstract.data import Data


class AccountSummaryItem(Data):
    """A single account summary item from IBKR."""

    tag: str
    value: str
    currency: str
    account: str


class MarginRequirement(Data):
    """IBKR account-level margin requirement summary."""

    account: str
    currency: str
    init_margin_req: Optional[float] = None
    maint_margin_req: Optional[float] = None
    available_funds: Optional[float] = None
    excess_liquidity: Optional[float] = None
    cushion: Optional[float] = None
    sma: Optional[float] = None
    full_init_margin_req: Optional[float] = None
    full_maint_margin_req: Optional[float] = None
    full_available_funds: Optional[float] = None
    full_excess_liquidity: Optional[float] = None
    look_ahead_init_margin_req: Optional[float] = None
    look_ahead_maint_margin_req: Optional[float] = None
    look_ahead_available_funds: Optional[float] = None
    look_ahead_excess_liquidity: Optional[float] = None


class Position(Data):
    """An IBKR portfolio position."""

    symbol: str
    sec_type: str
    currency: str
    exchange: Optional[str] = None
    position: float
    market_price: Optional[float] = None
    market_value: Optional[float] = None
    average_cost: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    account: Optional[str] = None
    con_id: Optional[int] = None
    strike: Optional[float] = None
    right: Optional[str] = None
    multiplier: Optional[str] = None
    expiry: Optional[str] = None


class Order(Data):
    """An IBKR order."""

    order_id: int
    symbol: str
    sec_type: Optional[str] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None
    action: str
    total_quantity: float
    order_type: str
    limit_price: Optional[float] = None
    aux_price: Optional[float] = None
    status: str
    filled: float
    remaining: float
    avg_fill_price: Optional[float] = None
    last_fill_price: Optional[float] = None
    parent_id: Optional[int] = None
    perm_id: Optional[int] = None
    submitted: Optional[str] = None


class TradeFill(Data):
    """A single fill within an IBKR trade."""

    exec_id: str
    time: Optional[str] = None
    side: Optional[str] = None
    shares: float
    price: float
    cum_qty: float
    avg_price: float
    exchange: Optional[str] = None
    commission: Optional[float] = None
    currency: Optional[str] = None


class Trade(Data):
    """An IBKR trade with its fills."""

    trade_id: Optional[int] = None
    contract_symbol: str
    contract_sec_type: Optional[str] = None
    contract_currency: Optional[str] = None
    action: str
    order_type: str
    limit_price: Optional[float] = None
    total_quantity: float
    status: str
    filled: float
    remaining: float
    avg_fill_price: Optional[float] = None
    perm_id: Optional[int] = None
    fills: List[TradeFill] = []


class Quote(Data):
    """A market data quote from IBKR."""

    symbol: str
    delayed: bool = False
    bid: Optional[float] = None
    bid_size: Optional[float] = None
    ask: Optional[float] = None
    ask_size: Optional[float] = None
    last: Optional[float] = None
    last_size: Optional[float] = None
    last_time: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    prev_close: Optional[float] = None
    change: Optional[float] = None
    implied_vol: Optional[float] = None
    hist_vol: Optional[float] = None


class HistoricalBar(Data):
    """A historical price bar from IBKR."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    wap: Optional[float] = None
    bar_count: Optional[int] = None


class MarketQuote(Data):
    """A normalized market quote from IBKR."""

    symbol: str
    sec_type: str
    exchange: Optional[str] = None
    currency: Optional[str] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    timestamp: Optional[str] = None
    delayed: bool = False
    con_id: Optional[int] = None


class ContractSearchResult(Data):
    """A contract search result from IBKR."""

    symbol: str
    sec_type: str
    exchange: Optional[str] = None
    primary_exchange: Optional[str] = None
    currency: Optional[str] = None
    con_id: Optional[int] = None
    local_symbol: Optional[str] = None
    trading_class: Optional[str] = None
    description: Optional[str] = None


class ContractDetails(Data):
    """Detailed IBKR contract metadata."""

    symbol: str
    sec_type: str
    exchange: Optional[str] = None
    primary_exchange: Optional[str] = None
    currency: Optional[str] = None
    con_id: Optional[int] = None
    local_symbol: Optional[str] = None
    trading_class: Optional[str] = None
    long_name: Optional[str] = None
    market_name: Optional[str] = None
    min_tick: Optional[float] = None
    order_types: Optional[str] = None
    valid_exchanges: Optional[str] = None
    price_magnifier: Optional[int] = None
    under_con_id: Optional[int] = None


class OptionChainContract(Data):
    """An IBKR option contract definition."""

    underlying_symbol: str
    trading_class: Optional[str] = None
    exchange: Optional[str] = None
    expiry: str
    strike: float
    right: str
    multiplier: Optional[str] = None
    currency: str = "USD"


class OptionScreenerContract(Data):
    """A quote and screening row for an IBKR option contract."""

    underlying_symbol: str
    con_id: Optional[int] = None
    expiry: str
    strike: float
    right: str
    dte: Optional[int] = None
    moneyness: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    implied_vol: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    spread: Optional[float] = None
    spread_percent: Optional[float] = None
    volume_oi_ratio: Optional[float] = None
    implied_vol_3m: Optional[float] = None
    realized_vol_3m: Optional[float] = None
    iv_rv_spread: Optional[float] = None
    iv_rv_ratio: Optional[float] = None
    put_25d_iv: Optional[float] = None
    call_25d_iv: Optional[float] = None
    put_call_skew: Optional[float] = None
    atm_put_call_skew: Optional[float] = None
    call_put_premium_ratio: Optional[float] = None
    put_call_oi_ratio: Optional[float] = None
    put_call_volume_ratio: Optional[float] = None
    call_put_volume_ratio: Optional[float] = None
    net_option_delta_bias: Optional[float] = None
    net_option_vega_bias: Optional[float] = None
    vol_pricing_score: Optional[float] = None
    skew_risk_score: Optional[float] = None
    flow_bias_score: Optional[float] = None
    option_decision_labels: Optional[str] = None
    trade_suitability: Optional[str] = None
    liquidity_score: Optional[float] = None
    strategy_score: Optional[float] = None
    underlying_price: Optional[float] = None
    trading_class: Optional[str] = None
    exchange: Optional[str] = None
    multiplier: Optional[str] = None
    currency: str = "USD"
    iv_source: Optional[str] = None


class OptionDecisionSignal(Data):
    """Option-chain decision signal summary for an underlying."""

    symbol: Optional[str] = None
    implied_vol_3m: Optional[float] = None
    realized_vol_3m: Optional[float] = None
    iv_rv_spread: Optional[float] = None
    iv_rv_ratio: Optional[float] = None
    put_25d_iv: Optional[float] = None
    call_25d_iv: Optional[float] = None
    put_call_skew: Optional[float] = None
    atm_put_call_skew: Optional[float] = None
    call_put_premium_ratio: Optional[float] = None
    put_call_oi_ratio: Optional[float] = None
    put_call_volume_ratio: Optional[float] = None
    call_put_volume_ratio: Optional[float] = None
    net_option_delta_bias: Optional[float] = None
    net_option_vega_bias: Optional[float] = None
    vol_pricing_score: float = 0.0
    skew_risk_score: float = 0.0
    flow_bias_score: float = 0.0
    option_decision_labels: str
    trade_suitability: str
    iv_sources_used: Optional[str] = None


class RiskfolioHolding(Data):
    """A Riskfolio-ready IBKR holding row."""

    symbol: str
    sec_type: str
    currency: Optional[str] = None
    position: float
    market_value: float
    current_weight: float
    market_price: Optional[float] = None
    average_cost: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    included: bool
    exclusion_reason: Optional[str] = None


class RiskfolioAllocation(Data):
    """Chart-friendly Riskfolio allocation row."""

    symbol: str
    market_value: float
    current_weight: float
    unrealized_pnl: float
    unrealized_pnl_percent: float


class RiskfolioMetric(Data):
    """Portfolio risk metric for current and optimized allocations."""

    metric: str
    current: Optional[float] = None
    optimized: Optional[float] = None
    delta: Optional[float] = None


class RiskfolioWeight(Data):
    """Current vs optimized Riskfolio weight."""

    symbol: str
    current_weight: float
    optimized_weight: float
    rebalance_delta: float


class RiskfolioRiskContribution(Data):
    """Volatility risk contribution by symbol."""

    symbol: str
    ticker: str
    current_weight: float
    risk_contribution: float
    risk_weight_gap: float
    bubble_size: float


class RiskfolioCorrelation(Data):
    """Pairwise return correlation."""

    symbol: str
    compared_symbol: str
    correlation: float


class RiskfolioAssetRiskReturn(Data):
    """Asset-level risk-return scatter data."""

    symbol: str
    expected_return: float
    volatility: float
    sharpe_ratio: float
    current_weight: float


class RiskfolioTailRiskContribution(Data):
    """CVaR-based tail risk contribution by symbol."""

    symbol: str
    current_weight: float
    cvar_contribution: float
    cvar_weight_gap: float


class RiskfolioDrawdown(Data):
    """Portfolio drawdown at a single date."""

    date: str
    drawdown: float


class RiskfolioCumulativeReturn(Data):
    """Cumulative return per asset per date."""

    date: str
    symbol: str
    cumulative_return: float


class RiskfolioDistributionBin(Data):
    """Histogram bin for portfolio returns distribution."""

    bin_center: float
    frequency: float
