"""
P1-A: FRED 매크로 데이터 수집
- 수집 지표: VIX, DXY, TNX, T10Y2Y (장단기금리차)
- FRED_API_KEY 있으면 FRED API 사용, 없으면 yfinance 폴백
- 출력: data/processed/macro.parquet
"""

import os
import sys
import logging
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import FRED_API_KEY, TRAIN_START, TRAIN_END
from services.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# FRED 시리즈 ID → yfinance 폴백 티커
MACRO_SERIES = {
    "VIXCLS":   "^VIX",         # VIX 공포지수
    "DTWEXBGS": "DX-Y.NYB",     # 달러 인덱스 (DXY)
    "DGS10":    "^TNX",         # 10년 국채 금리
    "T10Y2Y":   None,            # 장단기금리차 (yfinance 직접 없음)
}


def fetch_via_yfinance(series_id: str, yf_ticker: str, start: str, end: str) -> pd.Series | None:
    import yfinance as yf
    if yf_ticker is None:
        logger.warning(f"{series_id}: yfinance 폴백 없음 → FRED API 키 필요")
        return None
    data = yf.download(yf_ticker, start=start, end=end, auto_adjust=True, progress=False)
    if data.empty:
        return None
    # yfinance 최신 버전은 MultiIndex 컬럼 반환 가능
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]  # 단일 티커이므로 첫 번째 열
    s = close.copy()
    s.name = series_id
    s.index = pd.to_datetime(s.index)
    return s


def fetch_via_fred(series_id: str, start: str, end: str) -> pd.Series | None:
    try:
        import pandas_datareader as pdr
        s = pdr.DataReader(series_id, "fred", start, end).squeeze()
        s.name = series_id
        return s
    except Exception as e:
        logger.error(f"FRED {series_id} 실패: {e}")
        return None


def _squeeze_close(data: pd.DataFrame) -> pd.Series:
    """yfinance MultiIndex 대응: Close 컬럼을 Series로 반환"""
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close


def compute_t10y2y_from_yf(start: str, end: str) -> pd.Series | None:
    """yfinance로 10년-2년 금리차 직접 계산"""
    import yfinance as yf
    t10 = _squeeze_close(yf.download("^TNX", start=start, end=end, auto_adjust=True, progress=False))
    t2  = _squeeze_close(yf.download("^IRX", start=start, end=end, auto_adjust=True, progress=False))
    if t10.empty or t2.empty:
        return None
    spread = t10 - t2 / 10  # TNX는 %, IRX는 연율 조정
    spread.name = "T10Y2Y"
    spread.index = pd.to_datetime(spread.index)
    return spread


def main():
    storage = get_storage()
    frames = {}

    for series_id, yf_ticker in MACRO_SERIES.items():
        logger.info(f"수집 중: {series_id}")

        if series_id == "T10Y2Y":
            # 장단기금리차: FRED 키 있으면 FRED, 없으면 직접 계산
            if FRED_API_KEY:
                s = fetch_via_fred(series_id, TRAIN_START, TRAIN_END)
            else:
                logger.info("T10Y2Y: yfinance 직접 계산 (^TNX - ^IRX)")
                s = compute_t10y2y_from_yf(TRAIN_START, TRAIN_END)
        elif FRED_API_KEY:
            s = fetch_via_fred(series_id, TRAIN_START, TRAIN_END)
        else:
            s = fetch_via_yfinance(series_id, yf_ticker, TRAIN_START, TRAIN_END)

        if s is not None and not s.empty:
            frames[series_id] = s
            logger.info(f"  → {len(s)}개 데이터 포인트 ({s.index[0].date()} ~ {s.index[-1].date()})")
        else:
            logger.warning(f"  → {series_id} 수집 실패")

    if not frames:
        logger.error("매크로 데이터 수집 실패")
        return

    macro_df = pd.DataFrame(frames)
    macro_df.index = pd.to_datetime(macro_df.index)
    macro_df.sort_index(inplace=True)

    # 주말/공휴일 제거 및 전진채움
    macro_df = macro_df.ffill()

    storage.save(macro_df, "macro")
    logger.info(f"macro.parquet 저장 완료: {macro_df.shape}")
    print("\n=== 매크로 데이터 미리보기 ===")
    print(macro_df.tail())
    print(f"\n누락값:\n{macro_df.isna().sum()}")
    return macro_df


if __name__ == "__main__":
    main()
