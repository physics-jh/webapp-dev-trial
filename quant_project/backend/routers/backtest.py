"""
P3 뼈대 / P6에서 실제 데이터 연결
백테스트 결과 및 파라미터 스윕 엔드포인트
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class BacktestSummary(BaseModel):
    total_return:   float
    cagr:           float
    sharpe:         float
    max_drawdown:   float
    win_rate:       float
    start_date:     str
    end_date:       str


class SharpeContourPoint(BaseModel):
    ml_weight: float
    top_n:     int
    sharpe:    float


@router.get("/summary", response_model=BacktestSummary)
def get_backtest_summary():
    """최신 백테스트 요약 결과 — P6에서 backtest_summary.json 연결"""
    # TODO(P6)
    return BacktestSummary(
        total_return=0.0, cagr=0.0, sharpe=0.0,
        max_drawdown=0.0, win_rate=0.0,
        start_date="", end_date="",
    )


@router.get("/sharpe-contour", response_model=list[SharpeContourPoint])
def get_sharpe_contour():
    """ml_weight × top_n 파라미터 스윕 결과 — P6에서 sharpe_contour.json 연결"""
    # TODO(P6)
    return []


@router.get("/equity-curve")
def get_equity_curve():
    """누적 수익률 시계열 — P6에서 구현"""
    # TODO(P6)
    return {"dates": [], "values": []}
