import asyncio
import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar


T = TypeVar("T")
_logger = logging.getLogger(__name__)
_MAX_CLIENT_ID = 10


class IbkrConnectionError(Exception):
    """Raised when unable to connect to IBKR TWS/IB Gateway."""


class IbkrClient:
    _ib: Any = None
    _host: str = "127.0.0.1"
    _port: int = 7497
    _client_id: int = 1
    _read_only: bool = True
    _delayed: bool = True
    _executor: Optional[ThreadPoolExecutor] = None
    _worker_loop: Optional[asyncio.AbstractEventLoop] = None
    _worker_thread_id: Optional[int] = None
    _option_flow_subscriptions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def configure(
        cls,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
        read_only: Optional[bool] = None,
        delayed: Optional[bool] = None,
    ) -> None:
        if host is not None:
            cls._host = host
        if port is not None:
            cls._port = int(port)
        if client_id is not None:
            cls._client_id = int(client_id)
        cls._read_only = True
        if delayed is not None:
            cls._delayed = bool(delayed)

    @classmethod
    def _thread_init(cls) -> None:
        cls._worker_thread_id = threading.get_ident()
        cls._worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls._worker_loop)

    @classmethod
    def _run(cls, func: Callable[[], T]) -> T:
        """Run all ib_insync work on one persistent thread/event loop."""
        if threading.get_ident() == cls._worker_thread_id:
            return func()

        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="openbb-ibkr",
                initializer=cls._thread_init,
            )

        future = cls._executor.submit(func)
        return future.result()

    @classmethod
    def _ensure_connected(cls) -> Any:
        from ib_insync import IB

        if cls._ib is not None and cls._ib.isConnected():
            return cls._ib

        first_id = cls._client_id
        last_error = None

        for attempt in range(_MAX_CLIENT_ID):
            cls._ib = IB()
            try:
                cls._ib.connect(
                    cls._host,
                    cls._port,
                    cls._client_id,
                    readonly=True,
                )
                ib_logger = logging.getLogger("ib_insync")
                ib_logger.setLevel(logging.WARNING)
                if cls._delayed:
                    cls._ib.reqMarketDataType(3)
                else:
                    cls._ib.reqMarketDataType(1)

                if attempt > 0:
                    _logger.info(
                        "Connected to IBKR with clientId=%d (was rejected on earlier IDs)",
                        cls._client_id,
                    )
                return cls._ib
            except ConnectionRefusedError:
                cls._ib = None
                raise IbkrConnectionError(
                    f"Cannot connect to IBKR at {cls._host}:{cls._port} "
                    f"(clientId={cls._client_id}). "
                    f"Ensure TWS or IB Gateway is running with API enabled."
                ) from None
            except Exception as e:
                last_error = e
                cls._ib = None
                # ib_insync wraps client-ID-conflict errors as TimeoutError with
                # an empty message — the "Peer closed connection" text is only
                # logged internally. Retry with the next client ID.
                cls._client_id += 1
                continue

        raise IbkrConnectionError(
            f"Cannot connect to IBKR at {cls._host}:{cls._port} "
            f"(tried clientIds {first_id}–{cls._client_id - 1}). "
            f"All client IDs are in use. Restart TWS/IB Gateway or configure a free client ID. "
            f"Last error: {last_error}"
        ) from last_error

    @classmethod
    def disconnect(cls) -> None:
        if cls._executor is None:
            cls._ib = None
            return

        def _disconnect() -> None:
            if cls._ib and cls._ib.isConnected():
                cls._ib.disconnect()
            cls._ib = None

        cls._run(_disconnect)

    @classmethod
    def is_connected(cls) -> bool:
        if cls._ib is None:
            return False
        return cls._run(lambda: cls._ib is not None and cls._ib.isConnected())

    @classmethod
    def get_account_summary(cls) -> List[Dict[str, Any]]:
        def _get_account_summary() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            results = []
            for item in ib.accountSummary():
                results.append({
                    "tag": item.tag,
                    "value": item.value,
                    "currency": item.currency,
                    "account": item.account,
                })
            return results

        return cls._run(_get_account_summary)

    @classmethod
    def get_account_values(cls) -> Dict[str, Dict[str, str]]:
        def _get_account_values() -> Dict[str, Dict[str, str]]:
            ib = cls._ensure_connected()
            result: Dict[str, Dict[str, str]] = {}
            for item in ib.accountSummary():
                if item.currency not in result:
                    result[item.currency] = {}
                result[item.currency][item.tag] = item.value
            return result

        return cls._run(_get_account_values)

    @classmethod
    def get_margin_summary(cls) -> Dict[str, Any]:
        def _get_margin_summary() -> Dict[str, Any]:
            ib = cls._ensure_connected()
            margin_tags = {
                "InitMarginReq": "init_margin_req",
                "MaintMarginReq": "maint_margin_req",
                "AvailableFunds": "available_funds",
                "ExcessLiquidity": "excess_liquidity",
                "Cushion": "cushion",
                "SMA": "sma",
                "FullInitMarginReq": "full_init_margin_req",
                "FullMaintMarginReq": "full_maint_margin_req",
                "FullAvailableFunds": "full_available_funds",
                "FullExcessLiquidity": "full_excess_liquidity",
                "LookAheadInitMarginReq": "look_ahead_init_margin_req",
                "LookAheadMaintMarginReq": "look_ahead_maint_margin_req",
                "LookAheadAvailableFunds": "look_ahead_available_funds",
                "LookAheadExcessLiquidity": "look_ahead_excess_liquidity",
            }
            result: Dict[str, Any] = {
                "account": "",
                "currency": "",
            }
            result.update({v: None for v in margin_tags.values()})

            for item in ib.accountSummary():
                if item.tag in margin_tags:
                    key = margin_tags[item.tag]
                    try:
                        result[key] = float(item.value)
                    except (ValueError, TypeError):
                        result[key] = item.value
                    if not result["account"]:
                        result["account"] = item.account
                    if not result["currency"]:
                        result["currency"] = item.currency
            return result

        return cls._run(_get_margin_summary)

    @classmethod
    def get_positions(cls) -> List[Dict[str, Any]]:
        def _get_positions() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            results = []
            for item in ib.portfolio():
                contract = item.contract
                position_data = {
                    "symbol": contract.symbol,
                    "sec_type": contract.secType,
                    "currency": contract.currency,
                    "exchange": contract.exchange,
                    "position": float(item.position),
                    "market_price": item.marketPrice,
                    "market_value": item.marketValue,
                    "average_cost": item.averageCost,
                    "unrealized_pnl": item.unrealizedPNL,
                    "realized_pnl": item.realizedPNL,
                    "account": item.account,
                }
                # Add contract details for options/futures
                if hasattr(contract, "conId") and contract.conId:
                    position_data["con_id"] = contract.conId
                if hasattr(contract, "strike") and contract.strike:
                    position_data["strike"] = contract.strike
                if hasattr(contract, "right") and contract.right:
                    position_data["right"] = contract.right
                if hasattr(contract, "multiplier") and contract.multiplier:
                    position_data["multiplier"] = contract.multiplier
                if hasattr(contract, "lastTradeDateOrContractMonth") and contract.lastTradeDateOrContractMonth:
                    position_data["expiry"] = contract.lastTradeDateOrContractMonth
                results.append(position_data)
            return results

        return cls._run(_get_positions)

    @classmethod
    def get_position_detail(cls, symbol: str) -> Optional[Dict[str, Any]]:
        positions = cls.get_positions()
        for pos in positions:
            if pos.get("symbol") == symbol:
                return pos
        return None

    @classmethod
    def get_open_orders(cls) -> List[Dict[str, Any]]:
        def _get_open_orders() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            results = []
            orders = ib.openOrders()
            for order_obj in orders:
                results.append({
                    "order_id": order_obj.order.orderId,
                    "symbol": order_obj.contract.symbol,
                    "sec_type": order_obj.contract.secType,
                    "currency": order_obj.contract.currency,
                    "exchange": order_obj.contract.exchange,
                    "action": order_obj.order.action,
                    "total_quantity": float(order_obj.order.totalQuantity),
                    "order_type": order_obj.order.orderType,
                    "limit_price": order_obj.order.lmtPrice,
                    "aux_price": order_obj.order.auxPrice,
                    "status": order_obj.orderStatus.status,
                    "filled": float(order_obj.orderStatus.filled),
                    "remaining": float(order_obj.orderStatus.remaining),
                    "avg_fill_price": order_obj.orderStatus.avgFillPrice,
                    "last_fill_price": order_obj.orderStatus.lastFillPrice,
                    "parent_id": order_obj.orderStatus.parentId,
                    "perm_id": order_obj.order.permId,
                    "submitted": (
                        str(order_obj.orderStatus.submitted)
                        if order_obj.orderStatus.submitted else None
                    ),
                })
            return results

        return cls._run(_get_open_orders)

    @classmethod
    def get_completed_orders(cls, api_only: bool = True) -> List[Dict[str, Any]]:
        def _get_completed_orders() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            results = []
            for item in ib.reqCompletedOrders(api_only=api_only):
                results.append({
                    "order_id": item.order.orderId,
                    "symbol": item.contract.symbol,
                    "sec_type": item.contract.secType,
                    "currency": item.contract.currency,
                    "action": item.order.action,
                    "total_quantity": float(item.order.totalQuantity),
                    "order_type": item.order.orderType,
                    "limit_price": item.order.lmtPrice,
                    "status": item.orderStatus.status,
                    "filled": float(item.orderStatus.filled),
                    "remaining": float(item.orderStatus.remaining),
                    "avg_fill_price": item.orderStatus.avgFillPrice,
                    "perm_id": item.order.permId,
                })
            return results

        return cls._run(_get_completed_orders)

    @classmethod
    def get_trades(cls) -> List[Dict[str, Any]]:
        def _get_trades() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            results = []
            for trade in ib.trades():
                fills = []
                for fill in trade.fills:
                    fills.append({
                        "exec_id": fill.execution.execId,
                        "time": str(fill.execution.time),
                        "side": fill.execution.side,
                        "shares": float(fill.execution.shares),
                        "price": fill.execution.price,
                        "cum_qty": float(fill.execution.cumQty),
                        "avg_price": fill.execution.avgPrice,
                        "exchange": fill.execution.exchange,
                        "commission": (
                            float(fill.commissionReport.commission)
                            if fill.commissionReport else None
                        ),
                        "currency": (
                            fill.commissionReport.currency
                            if fill.commissionReport else None
                        ),
                    })
                results.append({
                    "trade_id": trade.permId if trade.tradeLog else None,
                    "contract_symbol": trade.contract.symbol,
                    "contract_sec_type": trade.contract.secType,
                    "contract_currency": trade.contract.currency,
                    "action": trade.order.action,
                    "order_type": trade.order.orderType,
                    "limit_price": trade.order.lmtPrice,
                    "total_quantity": float(trade.order.totalQuantity),
                    "status": trade.orderStatus.status,
                    "filled": float(trade.orderStatus.filled),
                    "remaining": float(trade.orderStatus.remaining),
                    "avg_fill_price": trade.orderStatus.avgFillPrice,
                    "perm_id": _get_perm_id(trade),
                    "fills": fills,
                })
            return results

        return cls._run(_get_trades)

    @classmethod
    def get_quote(cls, symbol: str, delayed: bool = False) -> Dict[str, Any]:
        def _get_quote() -> Dict[str, Any]:
            ib = cls._ensure_connected()
            if delayed or cls._delayed:
                ib.reqMarketDataType(3)
            else:
                ib.reqMarketDataType(1)
            contract = cls.build_contract(symbol=symbol, sec_type="STK", exchange="SMART", currency="USD")
            contract = cls._qualify_contract(ib, contract)
            ticker = ib.reqMktData(contract, "", False, False)
            ib.sleep(0.5)
            last = cls._clean_float(getattr(ticker, "last", None))
            close = cls._clean_float(getattr(ticker, "close", None))
            result = {
                "symbol": symbol,
                "delayed": delayed or cls._delayed,
                "bid": cls._clean_float(getattr(ticker, "bid", None)),
                "bid_size": cls._clean_float(getattr(ticker, "bidSize", None)),
                "ask": cls._clean_float(getattr(ticker, "ask", None)),
                "ask_size": cls._clean_float(getattr(ticker, "askSize", None)),
                "last": last,
                "last_size": cls._clean_float(getattr(ticker, "lastSize", None)),
                "last_time": str(ticker.time) if ticker.time else None,
                "open": cls._clean_float(getattr(ticker, "open", None)),
                "high": cls._clean_float(getattr(ticker, "high", None)),
                "low": cls._clean_float(getattr(ticker, "low", None)),
                "close": close,
                "volume": cls._clean_float(getattr(ticker, "volume", None)),
                "prev_close": cls._clean_float(getattr(ticker, "prevLast", None)),
                "change": last - close if last is not None and close is not None else None,
                "implied_vol": cls._clean_float(getattr(ticker, "impliedVolatility", None)),
                "hist_vol": cls._clean_float(getattr(ticker, "histVolatility", None)),
            }
            ib.cancelMktData(contract)
            return result

        return cls._run(_get_quote)

    @classmethod
    def get_historical(
        cls,
        symbol: str,
        duration: str = "1 M",
        bar_size: str = "1 day",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        delayed: bool = False,
    ) -> List[Dict[str, Any]]:
        return cls.get_market_historical(
            symbol=symbol,
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            duration=duration,
            bar_size=bar_size,
            what_to_show=what_to_show,
            use_rth=use_rth,
            delayed=delayed,
        )

    @classmethod
    def get_historical_multi(
        cls,
        symbols: List[str],
        duration: str = "1 M",
        bar_size: str = "1 day",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        delayed: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
        def _get_multi() -> Dict[str, List[Dict[str, Any]]]:
            from ib_insync import Stock
            import asyncio

            ib = cls._ensure_connected()
            if delayed or cls._delayed:
                ib.reqMarketDataType(3)
            else:
                ib.reqMarketDataType(1)

            async def _fetch_one(symbol: str) -> tuple[str, list]:
                contract = Stock(symbol, "SMART", "USD")
                try:
                    bars = await ib.reqHistoricalDataAsync(
                        contract,
                        endDateTime="",
                        durationStr=duration,
                        barSizeSetting=bar_size,
                        whatToShow=what_to_show,
                        useRTH=use_rth,
                        formatDate=1,
                    )
                    records = []
                    for bar in bars:
                        records.append({
                            "date": str(bar.date),
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "volume": bar.volume,
                            "wap": getattr(bar, "wap", getattr(bar, "average", None)),
                            "bar_count": bar.barCount,
                        })
                    return symbol, records
                except Exception:
                    return symbol, []

            loop = asyncio.get_event_loop()
            tasks = [_fetch_one(symbol) for symbol in symbols]
            results = loop.run_until_complete(asyncio.gather(*tasks))
            return {symbol: records for symbol, records in results}

        return cls._run(_get_multi)

    @classmethod
    def get_iv_history(
        cls,
        symbol: str,
        duration: str = "1 Y",
        bar_size: str = "1 day",
        delayed: bool = True,
    ) -> List[Dict[str, Any]]:
        """Fetch historical implied volatility bars from IBKR."""
        return cls.get_market_historical(
            symbol=symbol,
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            duration=duration,
            bar_size=bar_size,
            what_to_show="OPTION_IMPLIED_VOLATILITY",
            use_rth=True,
            delayed=delayed,
        )

    @classmethod
    def get_hv_history(
        cls,
        symbol: str,
        duration: str = "1 Y",
        bar_size: str = "1 day",
        delayed: bool = True,
    ) -> List[Dict[str, Any]]:
        """Fetch historical (realized) volatility bars from IBKR."""
        return cls.get_market_historical(
            symbol=symbol,
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            duration=duration,
            bar_size=bar_size,
            what_to_show="HISTORICAL_VOLATILITY",
            use_rth=True,
            delayed=delayed,
        )

    @staticmethod
    def _clean_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            value = float(value)
            if math.isnan(value) or math.isinf(value):
                return None
            return value
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_ibkr_expiry(value: str) -> Optional[date]:
        value = str(value or "").strip()
        for fmt in ("%Y%m%d", "%Y%m"):
            try:
                parsed = datetime.strptime(value, fmt).date()
                if fmt == "%Y%m":
                    return parsed.replace(day=1)
                return parsed
            except ValueError:
                continue
        return None

    @staticmethod
    def _safe_exchange(value: Any) -> str:
        value = str(value or "").strip()
        return value or "SMART"

    @staticmethod
    def _clean_text(value: Any) -> Optional[str]:
        value = str(value or "").strip()
        return value or None

    @staticmethod
    def _contract_field(contract: Any, name: str) -> Any:
        try:
            return getattr(contract, name)
        except Exception:
            return None

    @staticmethod
    def _fx_pair(symbol: str, currency: str) -> str:
        value = str(symbol or "").replace("/", ".").replace("-", ".").replace("_", ".").upper()
        if "." in value:
            base, quote = value.split(".", 1)
            return f"{base}{quote}"
        if len(value) == 6:
            return value
        return f"{value}{str(currency or 'USD').upper()}"

    @classmethod
    def build_contract(
        cls,
        symbol: str,
        sec_type: str = "STK",
        exchange: str = "SMART",
        currency: str = "USD",
        primary_exchange: Optional[str] = None,
        con_id: Optional[int] = None,
        local_symbol: Optional[str] = None,
    ) -> Any:
        """Build an ib_insync contract for the subscribed IBKR asset classes."""
        from ib_insync import Bond, CFD, Commodity, Contract, Crypto, Forex, MutualFund, Stock

        sec_type = str(sec_type or "STK").upper()
        exchange = cls._safe_exchange(exchange)
        currency = str(currency or "USD").upper()
        kwargs = {}
        if primary_exchange:
            kwargs["primaryExchange"] = str(primary_exchange)
        if local_symbol:
            kwargs["localSymbol"] = str(local_symbol)
        if con_id:
            kwargs["conId"] = int(con_id)

        if sec_type in {"STK", "ETF"}:
            contract = Stock(str(symbol).upper(), exchange, currency, **kwargs)
            if sec_type == "ETF":
                contract.secType = "ETF"
        elif sec_type == "CASH":
            contract = Forex(cls._fx_pair(symbol, currency), exchange=exchange, **kwargs)
        elif sec_type == "FUND":
            contract = MutualFund(symbol=str(symbol).upper(), exchange=exchange, currency=currency, **kwargs)
        elif sec_type == "BOND":
            contract = Bond(symbol=str(symbol).upper(), exchange=exchange, currency=currency, **kwargs)
        elif sec_type == "CRYPTO":
            contract = Crypto(str(symbol).upper(), exchange, currency, **kwargs)
        elif sec_type == "CFD":
            contract = CFD(str(symbol).upper(), exchange, currency, **kwargs)
        elif sec_type in {"CMDTY", "COMMODITY"}:
            contract = Commodity(str(symbol).upper(), exchange, currency, **kwargs)
        else:
            contract = Contract(
                secType=sec_type,
                symbol=str(symbol).upper(),
                exchange=exchange,
                currency=currency,
                **kwargs,
            )
        return contract

    @classmethod
    def _normalise_contract(cls, contract: Any) -> Dict[str, Any]:
        return {
            "symbol": cls._clean_text(cls._contract_field(contract, "symbol")) or "",
            "sec_type": cls._clean_text(cls._contract_field(contract, "secType")) or "",
            "exchange": cls._clean_text(cls._contract_field(contract, "exchange")),
            "primary_exchange": cls._clean_text(cls._contract_field(contract, "primaryExchange")),
            "currency": cls._clean_text(cls._contract_field(contract, "currency")),
            "con_id": int(cls._contract_field(contract, "conId") or 0) or None,
            "local_symbol": cls._clean_text(cls._contract_field(contract, "localSymbol")),
            "trading_class": cls._clean_text(cls._contract_field(contract, "tradingClass")),
        }

    @classmethod
    def _normalise_contract_details(cls, details: Any) -> Dict[str, Any]:
        contract = details.contract
        row = cls._normalise_contract(contract)
        row.update(
            {
                "long_name": cls._clean_text(getattr(details, "longName", None)),
                "market_name": cls._clean_text(getattr(details, "marketName", None)),
                "min_tick": cls._clean_float(getattr(details, "minTick", None)),
                "order_types": cls._clean_text(getattr(details, "orderTypes", None)),
                "valid_exchanges": cls._clean_text(getattr(details, "validExchanges", None)),
                "price_magnifier": int(getattr(details, "priceMagnifier", 0) or 0) or None,
                "under_con_id": int(getattr(details, "underConId", 0) or 0) or None,
            }
        )
        return row

    @classmethod
    def _normalise_quote(cls, contract: Any, ticker: Any, delayed: bool) -> Dict[str, Any]:
        contract_data = cls._normalise_contract(contract)
        return {
            "symbol": contract_data["symbol"],
            "sec_type": contract_data["sec_type"],
            "exchange": contract_data["exchange"],
            "currency": contract_data["currency"],
            "bid": cls._clean_float(getattr(ticker, "bid", None)),
            "ask": cls._clean_float(getattr(ticker, "ask", None)),
            "last": cls._clean_float(getattr(ticker, "last", None)),
            "close": cls._clean_float(getattr(ticker, "close", None)),
            "volume": cls._clean_float(getattr(ticker, "volume", None)),
            "timestamp": str(getattr(ticker, "time", None)) if getattr(ticker, "time", None) else None,
            "delayed": delayed or cls._delayed,
            "con_id": contract_data["con_id"],
        }

    @classmethod
    def _qualify_contract(cls, ib: Any, contract: Any) -> Any:
        try:
            qualified = ib.qualifyContracts(contract)
            if qualified:
                return qualified[0]
        except Exception:
            pass
        return contract

    @classmethod
    def get_market_quote(
        cls,
        symbol: str,
        sec_type: str = "STK",
        exchange: str = "SMART",
        currency: str = "USD",
        primary_exchange: Optional[str] = None,
        con_id: Optional[int] = None,
        local_symbol: Optional[str] = None,
        delayed: bool = False,
    ) -> Dict[str, Any]:
        def _get_market_quote() -> Dict[str, Any]:
            ib = cls._ensure_connected()
            if delayed or cls._delayed:
                ib.reqMarketDataType(3)
            else:
                ib.reqMarketDataType(1)
            contract = cls.build_contract(
                symbol=symbol,
                sec_type=sec_type,
                exchange=exchange,
                currency=currency,
                primary_exchange=primary_exchange,
                con_id=con_id,
                local_symbol=local_symbol,
            )
            contract = cls._qualify_contract(ib, contract)
            ticker = ib.reqMktData(contract, "", False, False)
            ib.sleep(0.7)
            row = cls._normalise_quote(contract, ticker, delayed)
            ib.cancelMktData(contract)
            return row

        return cls._run(_get_market_quote)

    @classmethod
    def get_market_historical(
        cls,
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
    ) -> List[Dict[str, Any]]:
        def _get_market_historical() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            if delayed or cls._delayed:
                ib.reqMarketDataType(3)
            else:
                ib.reqMarketDataType(1)
            contract = cls.build_contract(
                symbol=symbol,
                sec_type=sec_type,
                exchange=exchange,
                currency=currency,
                primary_exchange=primary_exchange,
                con_id=con_id,
                local_symbol=local_symbol,
            )
            contract = cls._qualify_contract(ib, contract)
            bars = ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=1,
            )
            results = []
            for bar in bars:
                results.append({
                    "date": str(bar.date),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "wap": getattr(bar, "wap", getattr(bar, "average", None)),
                    "bar_count": bar.barCount,
                })
            return results

        return cls._run(_get_market_historical)

    @classmethod
    def search_contracts(
        cls,
        symbol: str,
        sec_type: Optional[str] = None,
        exchange: str = "SMART",
        currency: str = "USD",
        primary_exchange: Optional[str] = None,
        con_id: Optional[int] = None,
        local_symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        def _search_contracts() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            if con_id or sec_type:
                contract = cls.build_contract(
                    symbol=symbol,
                    sec_type=sec_type or "STK",
                    exchange=exchange,
                    currency=currency,
                    primary_exchange=primary_exchange,
                    con_id=con_id,
                    local_symbol=local_symbol,
                )
                details = ib.reqContractDetails(contract)
                results = []
                for item in details[:limit]:
                    row = cls._normalise_contract(item.contract)
                    row["description"] = (
                        cls._clean_text(getattr(item, "longName", None))
                        or cls._clean_text(getattr(item, "marketName", None))
                    )
                    results.append(row)
                return results

            results = []
            for item in ib.reqMatchingSymbols(symbol)[:limit]:
                row = cls._normalise_contract(item.contract)
                row["description"] = cls._clean_text(getattr(item, "description", None))
                results.append(row)
            return results

        return cls._run(_search_contracts)

    @classmethod
    def get_contract_details(
        cls,
        symbol: str,
        sec_type: str = "STK",
        exchange: str = "SMART",
        currency: str = "USD",
        primary_exchange: Optional[str] = None,
        con_id: Optional[int] = None,
        local_symbol: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        def _get_contract_details() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            contract = cls.build_contract(
                symbol=symbol,
                sec_type=sec_type,
                exchange=exchange,
                currency=currency,
                primary_exchange=primary_exchange,
                con_id=con_id,
                local_symbol=local_symbol,
            )
            return [
                cls._normalise_contract_details(item)
                for item in ib.reqContractDetails(contract)[:limit]
            ]

        return cls._run(_get_contract_details)

    @classmethod
    def _qualify_option_underlying(cls, ib: Any, symbol: str, currency: str) -> Any:
        from ib_insync import Index, Stock

        symbol = symbol.upper()
        candidates = [
            Stock(symbol, "SMART", currency),
            Stock(symbol, "ARCA", currency),
            Index(symbol, "CBOE", currency),
            Index(symbol, "CFE", currency),
        ]
        for contract in candidates:
            qualified = ib.qualifyContracts(contract)
            if qualified:
                return qualified[0]
        return None

    @classmethod
    def _underlying_price(cls, ib: Any, underlying: Any, delayed: bool) -> Optional[float]:
        if delayed or cls._delayed:
            ib.reqMarketDataType(3)
        else:
            ib.reqMarketDataType(1)

        ticker = ib.reqMktData(underlying, "", False, False)
        ib.sleep(0.7)
        price = cls._clean_float(ticker.marketPrice())
        if price is None:
            price = cls._clean_float(ticker.last)
        if price is None:
            price = cls._clean_float(ticker.close)
        ib.cancelMktData(underlying)
        if price is not None:
            return price

        try:
            bars = ib.reqHistoricalData(
                underlying,
                endDateTime="",
                durationStr="5 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
        except Exception:
            return None
        for bar in reversed(bars):
            price = cls._clean_float(getattr(bar, "close", None))
            if price is not None and price > 0:
                return price
        return None

    @staticmethod
    def _select_option_params(params: list[Any], exchange: str) -> Any:
        if not params:
            return None
        exchange = str(exchange or "").upper()
        for item in params:
            if str(item.exchange).upper() == exchange:
                return item
        for preferred in ("SMART", "CBOE", "BOX", "AMEX", "NYSE"):
            for item in params:
                if str(item.exchange).upper() == preferred:
                    return item
        return params[0]

    @classmethod
    def get_option_chain(
        cls,
        symbol: str,
        exchange: str = "SMART",
        sec_type: str = "STK",
        currency: str = "USD",
        min_dte: int = 0,
        max_dte: int = 60,
        max_strikes: int = 80,
        delayed: bool = False,
    ) -> List[Dict[str, Any]]:
        """Discover IBKR option definitions for a U.S. stock or ETF."""

        def _get_option_chain() -> List[Dict[str, Any]]:
            ib = cls._ensure_connected()
            if delayed or cls._delayed:
                ib.reqMarketDataType(3)
            else:
                ib.reqMarketDataType(1)

            underlying = cls._qualify_option_underlying(ib, symbol, currency)
            if underlying is None:
                return []
            underlying_price = cls._underlying_price(ib, underlying, delayed)

            params = ib.reqSecDefOptParams(
                underlying.symbol,
                "",
                getattr(underlying, "secType", sec_type.upper()),
                underlying.conId,
            )
            selected = cls._select_option_params(params, exchange)
            if selected is None:
                return []

            today = date.today()
            expirations: list[tuple[str, int]] = []
            for expiry in sorted(selected.expirations):
                expiry_date = cls._parse_ibkr_expiry(expiry)
                if expiry_date is None:
                    continue
                dte = (expiry_date - today).days
                if min_dte <= dte <= max_dte:
                    expirations.append((expiry, dte))

            strikes = sorted(float(strike) for strike in selected.strikes if strike and float(strike) > 0)
            if underlying_price and max_strikes > 0 and len(strikes) > max_strikes:
                strikes = sorted(strikes, key=lambda strike: abs(strike - underlying_price))[:max_strikes]
                strikes = sorted(strikes)

            rows: list[dict[str, Any]] = []
            for expiry, _dte in expirations:
                for strike in strikes:
                    for right in ("C", "P"):
                        rows.append(
                            {
                                "underlying_symbol": underlying.symbol,
                                "trading_class": selected.tradingClass,
                                "exchange": selected.exchange,
                                "expiry": expiry,
                                "strike": strike,
                                "right": right,
                                "multiplier": selected.multiplier,
                                "currency": currency,
                            }
                        )
            return rows

        return cls._run(_get_option_chain)

    @staticmethod
    def _ticker_greeks(ticker: Any) -> Any:
        for attr in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks"):
            greeks = getattr(ticker, attr, None)
            if greeks is not None:
                return greeks
        return None

    @staticmethod
    def _option_flow_key(row: Dict[str, Any]) -> str:
        con_id = row.get("con_id")
        if con_id:
            return f"con_id:{con_id}"
        return ":".join(
            str(row.get(key) or "")
            for key in ("underlying_symbol", "expiry", "strike", "right", "exchange", "currency")
        )

    @classmethod
    def _flow_contract_from_row(cls, row: Dict[str, Any]) -> Any:
        from ib_insync import Option

        contract = Option(
            str(row.get("underlying_symbol") or row.get("symbol") or ""),
            str(row.get("expiry") or ""),
            float(row.get("strike") or 0),
            str(row.get("right") or "").upper()[:1],
            cls._safe_exchange(str(row.get("exchange") or "SMART")),
            currency=str(row.get("currency") or "USD"),
            multiplier=str(row.get("multiplier") or "100"),
        )
        con_id = row.get("con_id")
        if con_id:
            contract.conId = int(con_id)
        return contract

    @classmethod
    def _latest_flow_greeks(cls, state: Dict[str, Any]) -> Dict[str, Optional[float]]:
        greeks = cls._ticker_greeks(state.get("quote_ticker"))
        return {
            "delta": cls._clean_float(getattr(greeks, "delta", None)) if greeks is not None else state.get("delta"),
            "gamma": cls._clean_float(getattr(greeks, "gamma", None)) if greeks is not None else state.get("gamma"),
            "vega": cls._clean_float(getattr(greeks, "vega", None)) if greeks is not None else state.get("vega"),
        }

    @classmethod
    def _classify_option_trade(
        cls,
        price: Optional[float],
        bid: Optional[float],
        ask: Optional[float],
    ) -> int:
        if price is None or bid is None or ask is None or ask < bid:
            return 0
        midpoint = (bid + ask) / 2
        if price >= ask or price > midpoint:
            return 1
        if price <= bid or price < midpoint:
            return -1
        return 0

    @classmethod
    def _empty_flow_totals(cls) -> Dict[str, Any]:
        return {
            "call_volume": 0.0,
            "put_volume": 0.0,
            "call_premium": 0.0,
            "put_premium": 0.0,
            "net_volume": 0.0,
            "net_premium": 0.0,
            "net_delta": 0.0,
            "net_gamma": 0.0,
            "net_vega": 0.0,
            "total_trades": 0,
            "unknown_trades": 0,
            "unknown_volume": 0.0,
            "started_at": datetime.utcnow().isoformat(),
            "updated_at": None,
        }

    @classmethod
    def _empty_flow_contract(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "underlying_symbol": row.get("underlying_symbol") or row.get("symbol"),
            "expiry": row.get("expiry"),
            "strike": row.get("strike"),
            "right": row.get("right"),
            "multiplier": cls._clean_float(row.get("multiplier")) or 100.0,
            "volume": 0.0,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "unknown_volume": 0.0,
            "unknown_trades": 0,
            "trades": 0,
            "net_volume": 0.0,
            "net_premium": 0.0,
            "net_delta": 0.0,
            "net_gamma": 0.0,
            "net_vega": 0.0,
            "avg_price": None,
            "last_price": None,
            "last_trade_time": None,
            "started_at": datetime.utcnow().isoformat(),
            "updated_at": None,
        }

    @classmethod
    def _apply_option_flow_trade(
        cls,
        totals: Dict[str, Any],
        contract_flow: Dict[str, Any],
        price: Optional[float],
        size: Optional[float],
        direction: int,
        greeks: Dict[str, Optional[float]],
        trade_time: Any = None,
    ) -> None:
        trade_size = cls._clean_float(size) or 0.0
        trade_price = cls._clean_float(price)
        if trade_size <= 0:
            return

        multiplier = cls._clean_float(contract_flow.get("multiplier")) or 100.0
        contract_flow["trades"] += 1
        contract_flow["volume"] += trade_size
        contract_flow["last_price"] = trade_price
        contract_flow["last_trade_time"] = str(trade_time) if trade_time else datetime.utcnow().isoformat()
        previous_volume = contract_flow["volume"] - trade_size
        if trade_price is not None:
            previous_total = (contract_flow.get("avg_price") or 0.0) * previous_volume
            contract_flow["avg_price"] = (previous_total + trade_price * trade_size) / contract_flow["volume"]

        totals["total_trades"] += 1
        is_call = str(contract_flow.get("right") or "").upper().startswith("C")
        is_put = str(contract_flow.get("right") or "").upper().startswith("P")
        if is_call:
            totals["call_volume"] += trade_size
        elif is_put:
            totals["put_volume"] += trade_size
        if trade_price is not None:
            side_premium = trade_size * trade_price * multiplier
            if is_call:
                totals["call_premium"] += side_premium
            elif is_put:
                totals["put_premium"] += side_premium

        if direction == 0:
            contract_flow["unknown_volume"] += trade_size
            contract_flow["unknown_trades"] += 1
            totals["unknown_trades"] += 1
            totals["unknown_volume"] += trade_size
        elif direction > 0:
            contract_flow["buy_volume"] += trade_size
        else:
            contract_flow["sell_volume"] += trade_size

        if direction != 0:
            signed_size = direction * trade_size
            contract_flow["net_volume"] += signed_size
            if trade_price is not None:
                premium = signed_size * trade_price * multiplier
                contract_flow["net_premium"] += premium
                totals["net_premium"] += premium
            for greek_name in ("delta", "gamma", "vega"):
                greek_value = cls._clean_float(greeks.get(greek_name))
                if greek_value is None:
                    continue
                exposure = signed_size * multiplier * greek_value
                contract_flow[f"net_{greek_name}"] += exposure
                totals[f"net_{greek_name}"] += exposure
        totals["updated_at"] = datetime.utcnow().isoformat()
        contract_flow["updated_at"] = totals["updated_at"]

    @classmethod
    def aggregate_option_flow(cls, contracts: List[Dict[str, Any]]) -> Dict[str, Any]:
        totals = cls._empty_flow_totals()
        contract_rows: list[dict[str, Any]] = []
        by_strike: dict[float, dict[str, Any]] = {}

        for contract in contracts:
            row = dict(contract)
            contract_rows.append(row)
            strike = cls._clean_float(row.get("strike"))
            if strike is None:
                continue
            strike_row = by_strike.setdefault(
                strike,
                {
                    "strike": strike,
                    "call_volume": 0.0,
                    "put_volume": 0.0,
                    "net_volume": 0.0,
                    "net_premium": 0.0,
                    "net_delta": 0.0,
                    "net_gamma": 0.0,
                    "net_vega": 0.0,
                    "trades": 0,
                },
            )
            volume = cls._clean_float(row.get("volume")) or 0.0
            if str(row.get("right") or "").upper().startswith("C"):
                strike_row["call_volume"] += volume
                totals["call_volume"] += volume
                totals["call_premium"] += abs(cls._clean_float(row.get("net_premium")) or 0.0)
            elif str(row.get("right") or "").upper().startswith("P"):
                strike_row["put_volume"] += volume
                totals["put_volume"] += volume
                totals["put_premium"] += abs(cls._clean_float(row.get("net_premium")) or 0.0)
            for key in ("net_volume", "net_premium", "net_delta", "net_gamma", "net_vega"):
                strike_row[key] += cls._clean_float(row.get(key)) or 0.0
                totals[key] += cls._clean_float(row.get(key)) or 0.0
            trades = int(cls._clean_float(row.get("trades")) or 0)
            strike_row["trades"] += trades
            totals["total_trades"] += trades
            totals["unknown_trades"] += int(cls._clean_float(row.get("unknown_trades")) or 0)
            totals["unknown_volume"] += cls._clean_float(row.get("unknown_volume")) or 0.0
            if row.get("started_at") and (
                totals.get("started_at") is None or str(row["started_at"]) < str(totals["started_at"])
            ):
                totals["started_at"] = row["started_at"]
            if row.get("updated_at") and (
                totals.get("updated_at") is None or str(row["updated_at"]) > str(totals["updated_at"])
            ):
                totals["updated_at"] = row["updated_at"]

        totals["p_c_ratio"] = (
            totals["put_volume"] / totals["call_volume"] if totals["call_volume"] > 0 else None
        )
        totals["call_put_premium_ratio"] = (
            totals["call_premium"] / totals["put_premium"] if totals["put_premium"] > 0 else None
        )
        total_abs_delta = abs(totals["net_delta"])
        totals["net_option_delta_bias"] = totals["net_delta"] if total_abs_delta > 0 else 0.0
        total_abs_vega = abs(totals["net_vega"])
        totals["net_option_vega_bias"] = totals["net_vega"] if total_abs_vega > 0 else 0.0
        contract_rows.sort(key=lambda item: (-(cls._clean_float(item.get("volume")) or 0.0), item.get("expiry") or ""))
        return {
            "totals": totals,
            "contracts": contract_rows,
            "strikes": [by_strike[key] for key in sorted(by_strike)],
        }

    @classmethod
    def _process_option_flow_state(cls, state: Dict[str, Any]) -> None:
        quote_ticker = state.get("quote_ticker")
        trade_ticker = state.get("trade_ticker")
        ticks = list(getattr(trade_ticker, "tickByTicks", None) or [])
        processed_count = int(state.get("processed_count") or 0)
        if processed_count >= len(ticks):
            return

        for tick in ticks[processed_count:]:
            price = cls._clean_float(getattr(tick, "price", None))
            size = cls._clean_float(getattr(tick, "size", None))
            bid = cls._clean_float(getattr(quote_ticker, "bid", None))
            ask = cls._clean_float(getattr(quote_ticker, "ask", None))
            direction = cls._classify_option_trade(price, bid, ask)
            cls._apply_option_flow_trade(
                state["totals"],
                state["contract_flow"],
                price,
                size,
                direction,
                cls._latest_flow_greeks(state),
                getattr(tick, "time", None),
            )
        state["processed_count"] = len(ticks)

    @classmethod
    def get_option_flow(
        cls,
        option_rows: List[Dict[str, Any]],
        delayed: bool = False,
    ) -> Dict[str, Any]:
        """Subscribe to live option ticks and return session-to-date flow aggregates."""

        def _get_option_flow() -> Dict[str, Any]:
            if delayed or cls._delayed:
                raise IbkrConnectionError("True option flow requires real-time IBKR data. Set delayed=false.")

            ib = cls._ensure_connected()
            ib.reqMarketDataType(1)

            for row in option_rows:
                key = cls._option_flow_key(row)
                if key in cls._option_flow_subscriptions:
                    continue
                contract = cls._flow_contract_from_row(row)
                try:
                    if not getattr(contract, "conId", None):
                        qualified = ib.qualifyContracts(contract)
                        if qualified:
                            contract = qualified[0]
                    quote_ticker = ib.reqMktData(contract, "100,101,104,106", False, False)
                    trade_ticker = ib.reqTickByTickData(contract, "AllLast", 0, False)
                except Exception as exc:
                    raise IbkrConnectionError(f"Could not subscribe to option flow for {key}: {exc}") from exc

                greeks = cls._ticker_greeks(quote_ticker)
                cls._option_flow_subscriptions[key] = {
                    "contract": contract,
                    "quote_ticker": quote_ticker,
                    "trade_ticker": trade_ticker,
                    "processed_count": 0,
                    "totals": cls._empty_flow_totals(),
                    "contract_flow": cls._empty_flow_contract(row),
                    "delta": cls._clean_float(getattr(greeks, "delta", None)) if greeks else cls._clean_float(row.get("delta")),
                    "gamma": cls._clean_float(getattr(greeks, "gamma", None)) if greeks else cls._clean_float(row.get("gamma")),
                    "vega": cls._clean_float(getattr(greeks, "vega", None)) if greeks else cls._clean_float(row.get("vega")),
                }

            ib.sleep(0.2)
            active_keys = {cls._option_flow_key(row) for row in option_rows}
            contracts = []
            for key in active_keys:
                state = cls._option_flow_subscriptions.get(key)
                if state is None:
                    continue
                cls._process_option_flow_state(state)
                contracts.append(dict(state["contract_flow"]))
            return cls.aggregate_option_flow(contracts)

        return cls._run(_get_option_flow)

    @classmethod
    def get_option_screener(
        cls,
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
    ) -> List[Dict[str, Any]]:
        """Return quote-enriched option contracts with screening metrics."""

        def _get_option_screener() -> List[Dict[str, Any]]:
            from ib_insync import Option

            ib = cls._ensure_connected()
            if delayed or cls._delayed:
                ib.reqMarketDataType(3)
            else:
                ib.reqMarketDataType(1)

            underlying = cls._qualify_option_underlying(ib, symbol, currency)
            if underlying is None:
                return []
            underlying_price = cls._underlying_price(ib, underlying, delayed)

            params = ib.reqSecDefOptParams(
                underlying.symbol,
                "",
                getattr(underlying, "secType", "STK"),
                underlying.conId,
            )
            selected = cls._select_option_params(params, exchange)
            if selected is None:
                return []

            today = date.today()
            expirations: list[tuple[str, date, int]] = []
            requested_expiry = str(expiry).replace("-", "") if expiry else None
            for option_expiry in sorted(selected.expirations):
                if requested_expiry and str(option_expiry).replace("-", "") != requested_expiry:
                    continue
                expiry_date = cls._parse_ibkr_expiry(option_expiry)
                if expiry_date is None:
                    continue
                dte = (expiry_date - today).days
                if min_dte <= dte <= max_dte:
                    expirations.append((option_expiry, expiry_date, dte))

            strikes = sorted(float(strike) for strike in selected.strikes if strike and float(strike) > 0)
            if min_strike is not None:
                strikes = [strike for strike in strikes if strike >= float(min_strike)]
            if max_strike is not None:
                strikes = [strike for strike in strikes if strike <= float(max_strike)]
            if underlying_price:
                strikes = sorted(strikes, key=lambda strike: abs(strike - underlying_price))
            elif len(strikes) > max_contracts:
                middle = len(strikes) // 2
                half_window = max(max_contracts // 4, 10)
                strikes = strikes[max(0, middle - half_window) : middle + half_window]

            rights = ("C", "P") if right.lower() in {"both", "all", ""} else (right.upper()[0],)
            candidates: list[tuple[Any, int]] = []
            candidate_limit = max(max_contracts * 5, max_contracts)
            for option_expiry, _expiry_date, dte in expirations:
                for strike in strikes:
                    for option_right in rights:
                        contract = Option(
                            underlying.symbol,
                            option_expiry,
                            strike,
                            option_right,
                            cls._safe_exchange(selected.exchange or exchange),
                            currency=currency,
                            multiplier=selected.multiplier,
                        )
                        candidates.append((contract, dte))
                        if len(candidates) >= candidate_limit:
                            break
                    if len(candidates) >= candidate_limit:
                        break
                if len(candidates) >= candidate_limit:
                    break

            if not candidates:
                return []

            contracts = [item[0] for item in candidates]
            qualified_options = ib.qualifyContracts(*contracts)
            dte_by_key = {
                (contract.lastTradeDateOrContractMonth, float(contract.strike), contract.right): dte
                for contract, dte in candidates
            }

            tickers = []
            for contract in qualified_options[:max_contracts]:
                ticker = ib.reqMktData(contract, "100,101,104,106", False, False)
                tickers.append((contract, ticker))
            ib.sleep(1.5)

            rows: list[dict[str, Any]] = []
            for contract, ticker in tickers:
                bid = cls._clean_float(ticker.bid)
                ask = cls._clean_float(ticker.ask)
                last = cls._clean_float(ticker.last)
                close = cls._clean_float(getattr(ticker, "close", None))
                mid = (bid + ask) / 2 if bid is not None and ask is not None and ask >= bid else last or close
                spread = ask - bid if bid is not None and ask is not None and ask >= bid else None
                spread_percent = spread / mid if spread is not None and mid and mid > 0 else None
                greeks = cls._ticker_greeks(ticker)
                implied_vol = cls._clean_float(getattr(greeks, "impliedVol", None))
                delta = cls._clean_float(getattr(greeks, "delta", None))
                gamma = cls._clean_float(getattr(greeks, "gamma", None))
                theta = cls._clean_float(getattr(greeks, "theta", None))
                vega = cls._clean_float(getattr(greeks, "vega", None))
                volume = cls._clean_float(getattr(ticker, "volume", None))
                open_interest = (
                    cls._clean_float(getattr(ticker, "callOpenInterest", None))
                    if contract.right == "C"
                    else cls._clean_float(getattr(ticker, "putOpenInterest", None))
                )
                if open_interest is None:
                    open_interest = cls._clean_float(getattr(ticker, "openInterest", None))

                dte = dte_by_key.get((contract.lastTradeDateOrContractMonth, float(contract.strike), contract.right))
                moneyness = (
                    float(contract.strike) / underlying_price
                    if underlying_price and underlying_price > 0
                    else None
                )
                volume_oi_ratio = (
                    volume / open_interest
                    if volume is not None and open_interest and open_interest > 0
                    else None
                )
                spread_penalty = max(0.0, 1.0 - min(spread_percent or 1.0, 1.0))
                volume_score = min((volume or 0) / 1000, 1.0)
                oi_score = min((open_interest or 0) / 5000, 1.0)
                liquidity_score = 100 * (0.45 * volume_score + 0.35 * oi_score + 0.20 * spread_penalty)
                delta_score = 1.0
                if delta is not None:
                    delta_score = max(0.0, 1.0 - abs(abs(delta) - 0.30) / 0.30)
                strategy_score = liquidity_score * (0.65 + 0.35 * delta_score)

                row = {
                    "underlying_symbol": underlying.symbol,
                    "con_id": getattr(contract, "conId", None),
                    "expiry": contract.lastTradeDateOrContractMonth,
                    "strike": float(contract.strike),
                    "right": contract.right,
                    "dte": dte,
                    "moneyness": moneyness,
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "last": last,
                    "volume": volume,
                    "open_interest": open_interest,
                    "implied_vol": implied_vol,
                    "delta": delta,
                    "gamma": gamma,
                    "theta": theta,
                    "vega": vega,
                    "spread": spread,
                    "spread_percent": spread_percent,
                    "volume_oi_ratio": volume_oi_ratio,
                    "liquidity_score": liquidity_score,
                    "strategy_score": strategy_score,
                    "underlying_price": underlying_price,
                    "trading_class": getattr(contract, "tradingClass", selected.tradingClass),
                    "exchange": contract.exchange,
                    "multiplier": contract.multiplier,
                    "currency": contract.currency,
                    "iv_source": "market" if implied_vol is not None else None,
                }
                if min_volume > 0 and (volume is None or volume < min_volume):
                    continue
                if min_open_interest > 0 and (open_interest is None or open_interest < min_open_interest):
                    continue
                if max_spread_percent is not None and spread_percent is not None and spread_percent > max_spread_percent:
                    continue
                if min_delta is not None and min_delta > 0 and (delta is None or abs(delta) < min_delta):
                    continue
                if max_delta is not None and max_delta < 1 and (delta is None or abs(delta) > max_delta):
                    continue
                rows.append(row)

            for contract, ticker in tickers:
                ib.cancelMktData(contract)

            from openbb_ibkr.utils.iv_fallback import fill_iv_gaps
            fill_iv_gaps(rows, symbol, underlying_price)

            rows.sort(key=lambda item: (-(item.get("strategy_score") or 0), item.get("dte") or 9999, item["strike"]))
            return rows

        return cls._run(_get_option_screener)


def _get_perm_id(trade) -> Optional[int]:
    try:
        return trade.order.permId
    except AttributeError:
        return None
