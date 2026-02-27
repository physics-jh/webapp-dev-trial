"""
정성 분석 엔드포인트 — P6 신규
GET /api/analysis/{ticker}  → FreeAnalysisPlugin (→ MCPPlugin 전환 가능)
결과를 data/processed/analysis_{ticker}.json 에 캐싱
"""

import json
import logging
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

# 캐시 유효 시간 (시간 단위)
CACHE_TTL_HOURS = 24


def _cache_path(ticker: str) -> str:
    from config import DATA_PROCESSED
    return os.path.join(DATA_PROCESSED, f"analysis_{ticker.upper()}.json")


def _load_cache(ticker: str) -> dict | None:
    path = _cache_path(ticker)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    generated = data.get("generated_at", "")
    if generated:
        try:
            age = datetime.utcnow() - datetime.fromisoformat(generated)
            if age < timedelta(hours=CACHE_TTL_HOURS):
                return data
        except ValueError:
            pass
    return None


def _save_cache(ticker: str, data: dict):
    path = _cache_path(ticker)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.get("/{ticker}")
def get_analysis(ticker: str, refresh: bool = False):
    """
    종목 정성 분석 반환.
    - 캐시 히트(24h 이내): 캐시 반환
    - 캐시 미스 또는 refresh=true: AnalysisPlugin 호출 후 캐싱
    - FUNDAMENTAL_SOURCE=plugin_free (기본) / plugin_mcp (실전)
    """
    ticker = ticker.upper()

    if not refresh:
        cached = _load_cache(ticker)
        if cached:
            cached["cache_hit"] = True
            return cached

    try:
        from services.analysis_plugin import get_analysis_plugin
        plugin = get_analysis_plugin()

        one_pager  = plugin.get_one_pager(ticker)
        earnings   = plugin.analyze_earnings(ticker, quarter="latest")
        thesis     = plugin.get_investment_thesis(ticker)

        result = {
            "ticker":      ticker,
            "one_pager":   one_pager,
            "earnings":    earnings,
            "thesis":      thesis,
            "generated_at": datetime.utcnow().isoformat(),
            "cache_hit":   False,
        }
        _save_cache(ticker, result)
        return result

    except Exception as e:
        logger.error(f"analysis({ticker}) 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{ticker}/cache")
def invalidate_cache(ticker: str):
    """캐시 무효화 — 다음 요청 시 강제 갱신"""
    path = _cache_path(ticker.upper())
    if os.path.exists(path):
        os.remove(path)
        return {"message": f"{ticker.upper()} 캐시 삭제 완료"}
    return {"message": f"{ticker.upper()} 캐시 없음"}


@router.get("/")
def list_cached_tickers():
    """캐시된 분석 종목 목록 반환"""
    from config import DATA_PROCESSED
    tickers = []
    if os.path.exists(DATA_PROCESSED):
        for f in os.listdir(DATA_PROCESSED):
            if f.startswith("analysis_") and f.endswith(".json"):
                tickers.append(f[9:-5])  # "analysis_AAPL.json" → "AAPL"
    return {"tickers": sorted(tickers), "count": len(tickers)}
