"""
DataProvider 추상 레이어
데이터 소스 교체 시 config.py의 DATA_PROVIDER 값만 변경
"""

from __future__ import annotations
import time
import logging
from abc import ABC, abstractmethod
import pandas as pd

logger = logging.getLogger(__name__)


# ─── 추상 베이스 ──────────────────────────────────────────────

class BaseDataProvider(ABC):

    @abstractmethod
    def get_ohlcv(self, tickers: list[str], start: str, end: str) -> pd.DataFrame:
        """일봉 OHLCV 데이터 반환. columns: [Open, High, Low, Close, Volume] MultiIndex(ticker, field)"""
        ...

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict:
        """펀더멘털 지표 반환. keys: PER, PBR, EPS_growth, ROE, DE_ratio"""
        ...

    @abstractmethod
    def get_macro(self, series_id: str, start: str, end: str) -> pd.Series:
        """매크로 시계열 반환. index: DatetimeIndex"""
        ...


# ─── yfinance 구현체 (프로토타입) ─────────────────────────────

class YfinanceProvider(BaseDataProvider):

    def get_ohlcv(self, tickers: list[str], start: str, end: str) -> pd.DataFrame:
        import yfinance as yf
        frames = []
        for i in range(0, len(tickers), 50):          # 50종목 배치
            batch = tickers[i:i + 50]
            logger.info(f"OHLCV 다운로드 배치 {i//50 + 1}: {len(batch)}종목")
            data = yf.download(
                batch, start=start, end=end,
                auto_adjust=True, progress=False, threads=True
            )
            frames.append(data)
            time.sleep(1)                              # rate limit 방지
        return pd.concat(frames, axis=1) if len(frames) > 1 else frames[0]

    def get_fundamentals(self, ticker: str) -> dict:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        return {
            "PER":        info.get("trailingPE"),
            "PBR":        info.get("priceToBook"),
            "EPS_growth": info.get("earningsGrowth"),
            "ROE":        info.get("returnOnEquity"),
            "DE_ratio":   info.get("debtToEquity"),
        }

    def get_macro(self, series_id: str, start: str, end: str) -> pd.Series:
        """FRED API 사용 (FRED_API_KEY 필요). 키 없으면 yfinance 폴백."""
        from config import FRED_API_KEY
        if FRED_API_KEY:
            return self._get_macro_fred(series_id, start, end)
        return self._get_macro_yfinance_fallback(series_id, start, end)

    def _get_macro_fred(self, series_id: str, start: str, end: str) -> pd.Series:
        import pandas_datareader as pdr
        return pdr.DataReader(series_id, "fred", start, end).squeeze()

    def _get_macro_yfinance_fallback(self, series_id: str, start: str, end: str) -> pd.Series:
        """FRED 키 없을 때 yfinance로 대체 가능한 지표만"""
        import yfinance as yf
        FALLBACK = {
            "VIXCLS": "^VIX",
            "DGS10":  "^TNX",
            "DTWEXBGS": "DX-Y.NYB",
        }
        ticker = FALLBACK.get(series_id)
        if ticker is None:
            logger.warning(f"FRED 키 없음. {series_id} 폴백 불가 → 빈 Series 반환")
            return pd.Series(dtype=float, name=series_id)
        data = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        return data["Close"].rename(series_id)


# ─── 실전 스텁 ───────────────────────────────────────────────

class AlpacaProvider(BaseDataProvider):
    """실전 v1 — Alpaca Markets (~$99/월)"""

    def get_ohlcv(self, tickers, start, end):
        raise NotImplementedError("AlpacaProvider: config.py에서 ALPACA_KEY 설정 후 구현")

    def get_fundamentals(self, ticker):
        raise NotImplementedError

    def get_macro(self, series_id, start, end):
        raise NotImplementedError


class PolygonProvider(BaseDataProvider):
    """실전 v2 — Polygon.io ($29~199/월)"""

    def get_ohlcv(self, tickers, start, end):
        raise NotImplementedError("PolygonProvider: config.py에서 POLYGON_KEY 설정 후 구현")

    def get_fundamentals(self, ticker):
        raise NotImplementedError

    def get_macro(self, series_id, start, end):
        raise NotImplementedError


class SharadarProvider(BaseDataProvider):
    """퀀트 고도화 — Sharadar PIT 펀더멘털 ($50~/월)"""

    def get_ohlcv(self, tickers, start, end):
        raise NotImplementedError

    def get_fundamentals(self, ticker):
        raise NotImplementedError("SharadarProvider: PIT 펀더멘털 — 실전 운용 전 필수")

    def get_macro(self, series_id, start, end):
        raise NotImplementedError


# ─── 팩토리 ──────────────────────────────────────────────────

def get_provider() -> BaseDataProvider:
    from config import DATA_PROVIDER
    providers = {
        "yfinance": YfinanceProvider,
        "alpaca":   AlpacaProvider,
        "polygon":  PolygonProvider,
        "sharadar": SharadarProvider,
    }
    cls = providers.get(DATA_PROVIDER)
    if cls is None:
        raise ValueError(f"알 수 없는 DATA_PROVIDER: {DATA_PROVIDER}")
    return cls()
