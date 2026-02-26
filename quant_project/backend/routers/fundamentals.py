"""
P3 뼈대 / P6에서 실제 데이터 연결
펀더멘털 스크리닝 엔드포인트
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class FundamentalFilter(BaseModel):
    per_max:    float = 30.0
    pbr_max:    float = 5.0
    roe_min:    float = 0.1
    de_max:     float = 2.0
    eps_growth_min: float = 0.0


class ScreenResult(BaseModel):
    ticker:     str
    name:       str
    sector:     str
    PER:        float | None
    PBR:        float | None
    ROE:        float | None
    DE_ratio:   float | None
    EPS_growth: float | None


@router.get("/screen", response_model=list[ScreenResult])
def screen_fundamentals(
    per_max:        float = Query(30.0, description="PER 상한"),
    pbr_max:        float = Query(5.0,  description="PBR 상한"),
    roe_min:        float = Query(0.1,  description="ROE 하한"),
    de_max:         float = Query(2.0,  description="부채비율 상한"),
    eps_growth_min: float = Query(0.0,  description="EPS 성장률 하한"),
    limit:          int   = Query(150,  description="최대 반환 종목 수"),
):
    """
    펀더멘털 필터로 S&P 500 → 최대 150종목 스크리닝
    P6에서 실제 yfinance 데이터로 교체
    """
    # TODO(P6): 실제 데이터 연결
    return []


@router.get("/ticker/{ticker}", response_model=ScreenResult)
def get_ticker_fundamental(ticker: str):
    """특정 종목 펀더멘털 조회 — P6에서 구현"""
    # TODO(P6)
    return ScreenResult(
        ticker=ticker, name="", sector="",
        PER=None, PBR=None, ROE=None, DE_ratio=None, EPS_growth=None,
    )
