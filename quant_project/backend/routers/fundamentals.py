"""
펀더멘털 스크리닝 엔드포인트 — 캐시 기반 고속 조회
- fundamentals_cache.parquet 로드 → 즉시 필터 적용 (수 ms)
- /refresh 엔드포인트로 yfinance 병렬 재수집 (백그라운드)
- DATA_PROVIDER 변경 시 _fetch_one_ticker() 만 교체
"""

import logging
import os
import threading
import concurrent.futures
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 모듈 레벨 인메모리 캐시 ──────────────────────────────────
_fund_df: pd.DataFrame | None = None
_fund_lock = threading.Lock()
_build_in_progress = False


def _cache_path() -> str:
    from config import DATA_PROCESSED
    return os.path.join(DATA_PROCESSED, "fundamentals_cache.parquet")


def _load_from_disk() -> pd.DataFrame | None:
    """디스크 캐시 로드 — 앱 시작 시 호출"""
    global _fund_df
    path = _cache_path()
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        with _fund_lock:
            _fund_df = df
        logger.info(f"펀더멘털 캐시 로드: {len(df)}개 종목")
        return df
    except Exception as e:
        logger.warning(f"펀더멘털 캐시 로드 실패: {e}")
        return None


def _get_sp500_tickers() -> list[str]:
    """ohlcv.parquet에서 종목 목록 추출"""
    try:
        from config import DATA_PROCESSED
        path = os.path.join(DATA_PROCESSED, "ohlcv.parquet")
        if not os.path.exists(path):
            return []
        df = pd.read_parquet(path)
        cols = df.columns
        if isinstance(cols, pd.MultiIndex):
            tickers = cols.get_level_values(1).unique().tolist()
        elif isinstance(df.index, pd.MultiIndex):
            tickers = df.index.get_level_values("ticker").unique().tolist()
        elif "ticker" in df.columns:
            tickers = df["ticker"].unique().tolist()
        else:
            return []
        return sorted(t for t in tickers if isinstance(t, str) and t)
    except Exception as e:
        logger.warning(f"SP500 tickers 로드 실패: {e}")
        return []


def _fetch_one_ticker(ticker: str) -> dict | None:
    """단일 종목 yfinance 1회 호출로 모든 필드 수집"""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        # yfinance가 빈 dict 반환하면 스킵
        if not info or not info.get("regularMarketPrice"):
            return None
        return {
            "ticker":     ticker,
            "name":       info.get("longName") or ticker,
            "sector":     info.get("sector") or "Unknown",
            "PER":        info.get("trailingPE"),
            "PBR":        info.get("priceToBook"),
            "ROE":        info.get("returnOnEquity"),
            "DE_ratio":   info.get("debtToEquity"),
            "EPS_growth": info.get("earningsGrowth"),
            "FCF":        info.get("freeCashflow"),
        }
    except Exception as e:
        logger.debug(f"yfinance 조회 실패 ({ticker}): {e}")
        return None


def _build_cache(tickers: list[str]) -> pd.DataFrame:
    """ThreadPoolExecutor로 병렬 수집 후 parquet 저장"""
    logger.info(f"펀더멘털 캐시 빌드 시작: {len(tickers)}개 종목")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
        futures = {ex.submit(_fetch_one_ticker, t): t for t in tickers}
        for i, fut in enumerate(concurrent.futures.as_completed(futures)):
            row = fut.result()
            if row:
                results.append(row)
            if (i + 1) % 50 == 0:
                logger.info(f"  진행: {i+1}/{len(tickers)} ({len(results)} 성공)")

    if not results:
        return pd.DataFrame(columns=["ticker","name","sector","PER","PBR","ROE","DE_ratio","EPS_growth","FCF"])

    df = pd.DataFrame(results)
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    logger.info(f"펀더멘털 캐시 저장 완료: {len(df)}개 종목 → {path}")
    return df


def _build_cache_bg():
    """백그라운드 캐시 재빌드"""
    global _fund_df, _build_in_progress
    _build_in_progress = True
    try:
        tickers = _get_sp500_tickers()
        if not tickers:
            logger.warning("종목 목록 없음 — ohlcv.parquet 확인 필요")
            return
        df = _build_cache(tickers)
        with _fund_lock:
            _fund_df = df
    except Exception as e:
        logger.error(f"캐시 빌드 실패: {e}")
    finally:
        _build_in_progress = False


# ── 앱 시작 시 캐시 로드 ──────────────────────────────────────
_load_from_disk()


# ── Pydantic 모델 ─────────────────────────────────────────────
class ScreenResult(BaseModel):
    ticker:     str
    name:       str
    sector:     str
    PER:        float | None = None
    PBR:        float | None = None
    ROE:        float | None = None
    DE_ratio:   float | None = None
    EPS_growth: float | None = None
    FCF:        float | None = None


# ── 엔드포인트 ────────────────────────────────────────────────

@router.get("/status")
def cache_status():
    """캐시 상태 조회"""
    path = _cache_path()
    exists = os.path.exists(path)
    n_tickers = 0
    age_hours = None
    if exists:
        mtime = os.path.getmtime(path)
        age_hours = (datetime.now().timestamp() - mtime) / 3600
        if _fund_df is not None:
            n_tickers = len(_fund_df)
        else:
            try:
                df = pd.read_parquet(path)
                n_tickers = len(df)
            except Exception:
                pass
    return {
        "cache_exists": exists,
        "n_tickers": n_tickers,
        "age_hours": round(age_hours, 1) if age_hours is not None else None,
        "build_in_progress": _build_in_progress,
    }


@router.post("/refresh")
def refresh_cache(background_tasks: BackgroundTasks):
    """캐시 재생성 (백그라운드) — 약 3~10분 소요"""
    global _build_in_progress
    if _build_in_progress:
        return {"status": "이미 빌드 중입니다. 잠시 후 다시 확인하세요."}
    background_tasks.add_task(_build_cache_bg)
    return {"status": "캐시 재생성 시작됨", "message": "약 3~10분 후 완료됩니다."}


@router.get("/screen", response_model=list[ScreenResult])
def screen_fundamentals(
    per_max:        float = Query(30.0,  description="PER 상한"),
    pbr_max:        float = Query(5.0,   description="PBR 상한"),
    roe_min:        float = Query(0.1,   description="ROE 하한"),
    de_max:         float = Query(2.0,   description="부채비율 상한"),
    eps_growth_min: float = Query(0.0,   description="EPS 성장률 하한"),
    limit:          int   = Query(150,   description="최대 반환 종목 수"),
):
    """캐시 기반 고속 스크리닝 (수 ms). 캐시가 없으면 [] 반환"""
    global _fund_df

    # 캐시 로드 시도
    df = _fund_df
    if df is None:
        df = _load_from_disk()
    if df is None or len(df) == 0:
        return []

    # 벡터화 필터 (None/NaN 은 통과)
    mask = pd.Series([True] * len(df), index=df.index)
    for col, op, val in [
        ("PER",        "le", per_max),
        ("PBR",        "le", pbr_max),
        ("ROE",        "ge", roe_min),
        ("DE_ratio",   "le", de_max),
        ("EPS_growth", "ge", eps_growth_min),
    ]:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if op == "le":
            mask &= (s.isna() | (s <= val))
        else:  # ge
            mask &= (s.isna() | (s >= val))

    # 음수 PBR 제외 (음수 장부가 = 데이터 이상)
    if "PBR" in df.columns:
        pbr = pd.to_numeric(df["PBR"], errors="coerce")
        mask &= (pbr.isna() | (pbr > 0))

    # PER / PBR / ROE 중 최소 1개 이상 유효한 데이터 있어야 반환
    core_cols = [c for c in ["PER", "PBR", "ROE"] if c in df.columns]
    if core_cols:
        has_data = df[core_cols].apply(pd.to_numeric, errors="coerce").notna().any(axis=1)
        mask &= has_data

    filtered = df[mask].head(limit)
    rows = filtered.to_dict(orient="records")
    results = []
    for row in rows:
        results.append(ScreenResult(
            ticker=row.get("ticker", ""),
            name=row.get("name", ""),
            sector=row.get("sector", "Unknown"),
            PER=row.get("PER"),
            PBR=row.get("PBR"),
            ROE=row.get("ROE"),
            DE_ratio=row.get("DE_ratio"),
            EPS_growth=row.get("EPS_growth"),
            FCF=row.get("FCF"),
        ))
    return results


@router.get("/ticker/{ticker}", response_model=ScreenResult)
def get_ticker_fundamental(ticker: str):
    """특정 종목 펀더멘털 조회 (캐시 우선, 없으면 실시간 조회)"""
    t = ticker.upper()
    df = _fund_df
    if df is not None and len(df) > 0 and "ticker" in df.columns:
        row = df[df["ticker"] == t]
        if not row.empty:
            r = row.iloc[0]
            return ScreenResult(
                ticker=t,
                name=r.get("name", t),
                sector=r.get("sector", "Unknown"),
                PER=r.get("PER"),
                PBR=r.get("PBR"),
                ROE=r.get("ROE"),
                DE_ratio=r.get("DE_ratio"),
                EPS_growth=r.get("EPS_growth"),
                FCF=r.get("FCF"),
            )
    # 캐시에 없으면 실시간 조회
    result = _fetch_one_ticker(t)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{t} 펀더멘털 데이터 없음")
    return ScreenResult(**result)
