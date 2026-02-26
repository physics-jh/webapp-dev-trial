"""
P3 뼈대 / P6에서 실제 데이터 연결
포트폴리오 모니터링 엔드포인트
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class Position(BaseModel):
    ticker:      str
    name:        str
    sector:      str
    weight:      float
    signal:      float   # ML 모델 예측 점수
    ret_1d:      float
    ret_1m:      float


class PortfolioStatus(BaseModel):
    as_of:       str
    n_positions: int
    positions:   list[Position]
    regime:      str   # "bull" | "bear" | "neutral"


@router.get("/current", response_model=PortfolioStatus)
def get_current_portfolio():
    """현재 포트폴리오 구성 — P6에서 모델 예측 연결"""
    # TODO(P6)
    return PortfolioStatus(
        as_of="", n_positions=0, positions=[], regime="neutral"
    )


@router.get("/history")
def get_portfolio_history(days: int = 30):
    """포트폴리오 히스토리 — P6에서 구현"""
    # TODO(P6)
    return {"dates": [], "values": []}


@router.get("/regime")
def get_market_regime():
    """VIX/금리차 기반 시장 레짐 — P6에서 macro.parquet 연결"""
    # TODO(P6)
    return {"regime": "neutral", "vix": None, "t10y2y": None}
