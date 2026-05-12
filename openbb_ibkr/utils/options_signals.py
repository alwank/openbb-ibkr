"""Option-chain decision signal helpers."""

from __future__ import annotations

import math
from typing import Any


TRADING_DAYS = 252


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def realized_vol_from_bars(bars: list[dict[str, Any]], window: int = 63) -> float | None:
    """Compute close-to-close annualized realized volatility from historical bars."""
    closes = [_to_float(row.get("close")) for row in bars]
    closes = [value for value in closes if value is not None and value > 0]
    if len(closes) < 2:
        return None

    selected = closes[-(window + 1) :] if window > 0 else closes
    returns = [math.log(selected[index] / selected[index - 1]) for index in range(1, len(selected))]
    if len(returns) < 2:
        return None

    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS)


def _option_iv(row: dict[str, Any]) -> float | None:
    iv = _to_float(row.get("implied_vol"))
    return iv if iv is not None and iv > 0 else None


def _right(row: dict[str, Any]) -> str:
    return str(row.get("right") or "").upper()[:1]


def _dte(row: dict[str, Any]) -> float | None:
    dte = _to_float(row.get("dte"))
    return dte if dte is not None and dte >= 0 else None


def _moneyness_distance(row: dict[str, Any]) -> float:
    moneyness = _to_float(row.get("moneyness"))
    if moneyness is not None and moneyness > 0:
        return abs(moneyness - 1.0)
    strike = _to_float(row.get("strike"))
    underlying = _to_float(row.get("underlying_price"))
    if strike is not None and underlying is not None and underlying > 0:
        return abs((strike / underlying) - 1.0)
    return 999.0


def _candidate_rows(rows: list[dict[str, Any]], min_dte: int = 60, max_dte: int = 120) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        dte = _dte(row)
        if dte is None or dte < min_dte or dte > max_dte or _option_iv(row) is None:
            continue
        candidates.append(row)
    return candidates


def _nearest_atm_rows(rows: list[dict[str, Any]], target_dte: int = 90) -> list[dict[str, Any]]:
    candidates = _candidate_rows(rows)
    if not candidates:
        return []
    ranked = sorted(candidates, key=lambda row: (abs((_dte(row) or target_dte) - target_dte), _moneyness_distance(row)))
    best_dte = _dte(ranked[0])
    best_distance = _moneyness_distance(ranked[0])
    return [
        row
        for row in ranked
        if _dte(row) == best_dte and abs(_moneyness_distance(row) - best_distance) < 1e-9
    ]


def select_3m_atm_iv(rows: list[dict[str, Any]]) -> float | None:
    atm_rows = _nearest_atm_rows(rows)
    ivs = [_option_iv(row) for row in atm_rows]
    ivs = [iv for iv in ivs if iv is not None]
    if not ivs:
        return None
    return sum(ivs) / len(ivs)


def _nearest_delta_iv(rows: list[dict[str, Any]], right: str, target_abs_delta: float = 0.25) -> float | None:
    candidates = [
        row
        for row in _candidate_rows(rows)
        if _right(row) == right and _to_float(row.get("delta")) is not None
    ]
    if not candidates:
        return None
    row = min(
        candidates,
        key=lambda item: (
            abs((_dte(item) or 90) - 90),
            abs(abs(_to_float(item.get("delta")) or 0.0) - target_abs_delta),
            _moneyness_distance(item),
        ),
    )
    return _option_iv(row)


def _atm_side_iv(rows: list[dict[str, Any]], right: str) -> float | None:
    atm_rows = [row for row in _nearest_atm_rows(rows) if _right(row) == right]
    if not atm_rows:
        return None
    ivs = [_option_iv(row) for row in atm_rows]
    ivs = [iv for iv in ivs if iv is not None]
    if not ivs:
        return None
    return sum(ivs) / len(ivs)


def _flow_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    call_volume = put_volume = 0.0
    call_oi = put_oi = 0.0
    call_premium = put_premium = 0.0
    net_delta = 0.0
    call_vega = put_vega = 0.0

    for row in rows:
        right = _right(row)
        volume = _to_float(row.get("volume")) or 0.0
        open_interest = _to_float(row.get("open_interest")) or 0.0
        multiplier = _to_float(row.get("multiplier")) or 100.0
        price = _to_float(row.get("mid"))
        if price is None:
            price = _to_float(row.get("last")) or 0.0
        premium = volume * price * multiplier
        delta = _to_float(row.get("delta")) or 0.0
        vega = abs(_to_float(row.get("vega")) or 0.0) * volume * multiplier
        net_delta += volume * multiplier * delta

        if right == "C":
            call_volume += volume
            call_oi += open_interest
            call_premium += premium
            call_vega += vega
        elif right == "P":
            put_volume += volume
            put_oi += open_interest
            put_premium += premium
            put_vega += vega

    total_vega = call_vega + put_vega
    return {
        "call_volume": call_volume,
        "put_volume": put_volume,
        "put_call_volume_ratio": _ratio(put_volume, call_volume),
        "call_put_volume_ratio": _ratio(call_volume, put_volume),
        "put_call_oi_ratio": _ratio(put_oi, call_oi),
        "call_put_premium_ratio": _ratio(call_premium, put_premium),
        "net_option_delta_bias": net_delta,
        "net_option_vega_bias": ((call_vega - put_vega) / total_vega) if total_vega > 0 else None,
    }


def build_option_decision_signal(
    rows: list[dict[str, Any]],
    historical_bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize option-chain rows into Decision Layer metrics and labels."""
    bars = historical_bars or []
    symbol = None
    for row in rows:
        symbol = row.get("underlying_symbol") or row.get("symbol")
        if symbol:
            break

    implied_vol_3m = select_3m_atm_iv(rows)
    realized_vol_3m = realized_vol_from_bars(bars)
    iv_rv_spread = implied_vol_3m - realized_vol_3m if implied_vol_3m is not None and realized_vol_3m is not None else None
    iv_rv_ratio = _ratio(implied_vol_3m, realized_vol_3m)

    put_25d_iv = _nearest_delta_iv(rows, "P")
    call_25d_iv = _nearest_delta_iv(rows, "C")
    atm_put_iv = _atm_side_iv(rows, "P")
    atm_call_iv = _atm_side_iv(rows, "C")
    put_call_skew = put_25d_iv - call_25d_iv if put_25d_iv is not None and call_25d_iv is not None else None
    atm_put_call_skew = atm_put_iv - atm_call_iv if atm_put_iv is not None and atm_call_iv is not None else None
    skew_for_decision = put_call_skew if put_call_skew is not None else atm_put_call_skew

    flow = _flow_metrics(rows)
    labels: list[str] = []
    vol_pricing_score = 0.0
    skew_risk_score = 0.0
    flow_bias_score = 0.0

    if iv_rv_ratio is not None:
        if iv_rv_ratio >= 1.25:
            labels.append("expensive_vol")
            vol_pricing_score = min(5.0, 2.0 + (iv_rv_ratio - 1.25) / 0.75 * 3.0)
        elif iv_rv_ratio <= 0.85:
            labels.append("cheap_vol")

    if skew_for_decision is not None:
        if skew_for_decision >= 0.05:
            labels.append("downside_fear_priced")
            skew_risk_score = min(5.0, 2.0 + skew_for_decision / 0.10 * 3.0)
        elif skew_for_decision <= -0.03:
            labels.append("upside_chase")
            skew_risk_score = min(5.0, 2.0 + abs(skew_for_decision) / 0.08 * 3.0)

    put_call_volume_ratio = flow["put_call_volume_ratio"]
    call_put_volume_ratio = flow["call_put_volume_ratio"]
    call_put_premium_ratio = flow["call_put_premium_ratio"]
    if put_call_volume_ratio is not None and put_call_volume_ratio >= 1.25:
        labels.append("bearish_flow")
        flow_bias_score = min(5.0, 2.0 + (put_call_volume_ratio - 1.25) / 1.75 * 3.0)
    elif (
        call_put_volume_ratio is not None
        and call_put_volume_ratio >= 1.25
        and (call_put_premium_ratio is None or call_put_premium_ratio >= 1.0)
    ):
        labels.append("bullish_flow")
        flow_bias_score = min(3.0, 1.0 + (call_put_volume_ratio - 1.25) / 1.75 * 2.0)

    if not labels:
        labels.append("neutral_options")

    trade_suitability = "monitor"
    if "expensive_vol" in labels and "downside_fear_priced" not in labels:
        trade_suitability = "sell_premium_candidate"
    if "cheap_vol" in labels and "bullish_flow" in labels:
        trade_suitability = "buy_convexity_candidate"
    if "downside_fear_priced" in labels or "bearish_flow" in labels:
        trade_suitability = "hedge_or_size_down"
    if "upside_chase" in labels and "expensive_vol" in labels:
        trade_suitability = "avoid_chasing_calls"

    iv_sources = sorted({str(r.get("iv_source")) for r in rows if r.get("iv_source")})

    return {
        "symbol": str(symbol or "").upper() or None,
        "implied_vol_3m": round(implied_vol_3m, 6) if implied_vol_3m is not None else None,
        "realized_vol_3m": round(realized_vol_3m, 6) if realized_vol_3m is not None else None,
        "iv_rv_spread": round(iv_rv_spread, 6) if iv_rv_spread is not None else None,
        "iv_rv_ratio": round(iv_rv_ratio, 6) if iv_rv_ratio is not None else None,
        "put_25d_iv": round(put_25d_iv, 6) if put_25d_iv is not None else None,
        "call_25d_iv": round(call_25d_iv, 6) if call_25d_iv is not None else None,
        "put_call_skew": round(put_call_skew, 6) if put_call_skew is not None else None,
        "atm_put_call_skew": round(atm_put_call_skew, 6) if atm_put_call_skew is not None else None,
        "call_put_premium_ratio": round(flow["call_put_premium_ratio"], 6) if flow["call_put_premium_ratio"] is not None else None,
        "put_call_oi_ratio": round(flow["put_call_oi_ratio"], 6) if flow["put_call_oi_ratio"] is not None else None,
        "put_call_volume_ratio": round(flow["put_call_volume_ratio"], 6) if flow["put_call_volume_ratio"] is not None else None,
        "call_put_volume_ratio": round(flow["call_put_volume_ratio"], 6) if flow["call_put_volume_ratio"] is not None else None,
        "net_option_delta_bias": round(flow["net_option_delta_bias"] or 0.0, 6),
        "net_option_vega_bias": round(flow["net_option_vega_bias"], 6) if flow["net_option_vega_bias"] is not None else None,
        "vol_pricing_score": round(vol_pricing_score, 2),
        "skew_risk_score": round(skew_risk_score, 2),
        "flow_bias_score": round(flow_bias_score, 2),
        "option_decision_labels": ", ".join(labels),
        "trade_suitability": trade_suitability,
        "iv_sources_used": ", ".join(iv_sources) if iv_sources else None,
    }
