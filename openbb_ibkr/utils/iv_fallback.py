"""IV gap-filling fallback utilities: yFinance → IBKR calculateImpliedVolatility."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)

_IV_COVERAGE_THRESHOLD = 0.50  # proactive fetch if < 50% have IV


def fetch_yfinance_iv_chain(symbol: str) -> Dict[Tuple[str, float, str], float]:
    """Fetch full yFinance option chain and return IV lookup keyed by (expiry_YYYYMMDD, strike, right)."""
    try:
        import yfinance as yf
    except ImportError:
        _logger.warning("yfinance not installed; skipping yFinance IV fallback")
        return {}

    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return {}
    except Exception as e:
        _logger.warning("yFinance option chain fetch failed for %s: %s", symbol, e)
        return {}

    lookup: Dict[Tuple[str, float, str], float] = {}
    for exp_str in expirations:
        try:
            exp_yyyymmdd = datetime.strptime(exp_str, "%Y-%m-%d").strftime("%Y%m%d")
            chain = ticker.option_chain(exp_str)
            for _, row in chain.calls.iterrows():
                iv = row.get("impliedVolatility")
                strike = row.get("strike")
                if iv and iv > 0 and strike:
                    lookup[(exp_yyyymmdd, float(strike), "C")] = float(iv)
            for _, row in chain.puts.iterrows():
                iv = row.get("impliedVolatility")
                strike = row.get("strike")
                if iv and iv > 0 and strike:
                    lookup[(exp_yyyymmdd, float(strike), "P")] = float(iv)
        except Exception as e:
            _logger.debug("yFinance chain parse error for %s exp %s: %s", symbol, exp_str, e)
            continue
    return lookup


def _best_option_price(
    bid: Optional[float], ask: Optional[float], last: Optional[float]
) -> Optional[float]:
    """Select best available option price: mid if spread < 10%, else last, else None."""
    if bid is not None and ask is not None and ask >= bid and bid > 0:
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid
        if spread_pct < 0.10:
            return mid
    if last is not None and last > 0:
        return last
    return None


def _calculate_iv_ibkr(
    rows: List[Dict[str, Any]], underlying_price: float
) -> None:
    """Fill IV gaps using IBKR calculateImpliedVolatility for rows still missing IV (in-place)."""
    from openbb_ibkr.utils.client import IbkrClient

    needs_calc = [r for r in rows if r.get("implied_vol") is None and r.get("con_id")]
    if not needs_calc:
        return

    def _do_calc() -> None:
        from ib_insync import Option

        ib = IbkrClient._ensure_connected()
        for row in needs_calc:
            option_price = _best_option_price(row.get("bid"), row.get("ask"), row.get("last"))
            if option_price is None:
                continue
            contract = Option(conId=int(row["con_id"]))
            try:
                qualified = ib.qualifyContracts(contract)
                if not qualified:
                    continue
                computation = ib.calculateImpliedVolatility(
                    qualified[0], option_price, underlying_price
                )
                iv = getattr(computation, "impliedVol", None)
                if iv is not None and iv > 0:
                    row["implied_vol"] = float(iv)
                    row["iv_source"] = "calculated"
            except Exception as e:
                _logger.debug("IBKR calculateIV failed for conId %s: %s", row["con_id"], e)

    IbkrClient._run(_do_calc)


def fill_iv_gaps(
    rows: List[Dict[str, Any]], symbol: str, underlying_price: Optional[float]
) -> List[Dict[str, Any]]:
    """Fill IV gaps: yFinance first, then IBKR calculateImpliedVolatility. Annotates iv_source."""
    if not rows:
        return rows

    # Determine which expiries need proactive fetch
    expiry_counts: Dict[str, List[int]] = {}  # expiry -> [total, with_iv]
    for row in rows:
        exp = row.get("expiry", "")
        counts = expiry_counts.setdefault(exp, [0, 0])
        counts[0] += 1
        if row.get("implied_vol") is not None:
            counts[1] += 1

    proactive_expiries = {
        exp for exp, (total, with_iv) in expiry_counts.items()
        if total > 0 and (with_iv / total) < _IV_COVERAGE_THRESHOLD
    }

    # Collect rows needing fill: individual Nones + all in proactive expiries
    needs_fill = [
        r for r in rows
        if r.get("implied_vol") is None or r.get("expiry") in proactive_expiries
    ]
    needs_fill_none = [r for r in needs_fill if r.get("implied_vol") is None]

    if not needs_fill_none:
        return rows

    # Step 1: yFinance fallback
    yf_lookup = fetch_yfinance_iv_chain(symbol)
    if yf_lookup:
        for row in needs_fill_none:
            key = (str(row.get("expiry", "")), float(row.get("strike", 0)), str(row.get("right", "")))
            iv = yf_lookup.get(key)
            if iv is not None:
                row["implied_vol"] = iv
                row["iv_source"] = "yfinance"

    # Step 2: IBKR calculateImpliedVolatility for remaining gaps
    if underlying_price and underlying_price > 0:
        _calculate_iv_ibkr(rows, underlying_price)

    return rows
