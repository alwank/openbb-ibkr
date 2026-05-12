from typing import List, Optional

from openbb_core.provider.abstract.data import Data
from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.standard_models.equity_historical import (
    EquityHistoricalData,
    EquityHistoricalQueryParams,
)
from openbb_core.provider.standard_models.equity_quote import (
    EquityQuoteData,
    EquityQuoteQueryParams,
)

from openbb_ibkr.utils.client import IbkrClient


class IbkrEquityQuoteQueryParams(EquityQuoteQueryParams):
    delayed: bool = False


class IbkrEquityQuoteData(EquityQuoteData):
    pass


class IbkrEquityQuoteFetcher(Fetcher[IbkrEquityQuoteQueryParams, List[IbkrEquityQuoteData]]):
    require_credentials = False

    @staticmethod
    def transform_query(params: dict) -> IbkrEquityQuoteQueryParams:
        return IbkrEquityQuoteQueryParams(**params)

    @staticmethod
    def extract_data(query: IbkrEquityQuoteQueryParams, credentials: Optional[dict]) -> List[dict]:
        if credentials:
            IbkrClient.configure(
                host=credentials.get("ibkr_host"),
                port=credentials.get("ibkr_port"),
                client_id=credentials.get("ibkr_client_id"),
            )
        return [IbkrClient.get_quote(query.symbol, delayed=query.delayed)]

    @staticmethod
    def transform_data(query: IbkrEquityQuoteQueryParams, data: List[dict]) -> List[IbkrEquityQuoteData]:
        return [IbkrEquityQuoteData(**d) for d in data]


class IbkrEquityHistoricalQueryParams(EquityHistoricalQueryParams):
    interval: Optional[str] = None
    delayed: bool = False


class IbkrEquityHistoricalData(EquityHistoricalData):
    pass


class IbkrEquityHistoricalFetcher(Fetcher[IbkrEquityHistoricalQueryParams, List[IbkrEquityHistoricalData]]):
    require_credentials = False

    @staticmethod
    def transform_query(params: dict) -> IbkrEquityHistoricalQueryParams:
        return IbkrEquityHistoricalQueryParams(**params)

    @staticmethod
    def extract_data(query: IbkrEquityHistoricalQueryParams, credentials: Optional[dict]) -> List[dict]:
        if credentials:
            IbkrClient.configure(
                host=credentials.get("ibkr_host"),
                port=credentials.get("ibkr_port"),
                client_id=credentials.get("ibkr_client_id"),
            )
        return IbkrClient.get_historical(query.symbol, delayed=query.delayed)

    @staticmethod
    def transform_data(query: IbkrEquityHistoricalQueryParams, data: List[dict]) -> List[IbkrEquityHistoricalData]:
        return [IbkrEquityHistoricalData(**d) for d in data]
