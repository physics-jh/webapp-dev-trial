"""
백테스트 결과 엔드포인트 — P6 실제 JSON 파일 연결
models/results/backtest_summary.json
data/processed/sharpe_contour.json
"""

import json
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class BacktestSummary(BaseModel):
    total_return:   float
    cagr:           float
    sharpe:         float
    sortino:        float | None = None
    max_drawdown:   float
    calmar:         float | None = None
    win_rate:       float
    start_date:     str
    end_date:       str


class SharpeContourPoint(BaseModel):
    ml_weight:   float
    rule_weight: float | None = None
    top_n:       int
    sharpe:      float
    cagr:        float | None = None
    mdd:         float | None = None


def _load_json(path: str) -> dict | list | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


@router.get("/summary", response_model=BacktestSummary)
def get_backtest_summary():
    """최신 백테스트 요약 결과 반환"""
    from config import BASE_DIR, DATA_PROCESSED
    # data/processed/ 우선, 없으면 models/results/ 폴백
    path = os.path.join(DATA_PROCESSED, "backtest_summary.json")
    if not os.path.exists(path):
        path = os.path.join(BASE_DIR, "models", "results", "backtest_summary.json")
    data = _load_json(path)
    if data is None:
        raise HTTPException(status_code=404, detail="backtest_summary.json 없음. P5 백테스트를 먼저 실행하세요.")
    return BacktestSummary(**data)


@router.get("/sharpe-contour", response_model=list[SharpeContourPoint])
def get_sharpe_contour():
    """ml_weight × rule_weight(또는 top_n) 파라미터 스윕 결과 반환"""
    from config import DATA_PROCESSED
    path = os.path.join(DATA_PROCESSED, "sharpe_contour.json")
    data = _load_json(path)
    if data is None:
        return []
    results = []
    for p in data:
        results.append(SharpeContourPoint(
            ml_weight   = p.get("ml_weight", 0.0),
            rule_weight = p.get("rule_weight"),      # None이면 그대로
            top_n       = int(p.get("top_n", 10)),
            sharpe      = p.get("sharpe", 0.0),
            cagr        = p.get("cagr"),
            mdd         = p.get("mdd"),
        ))
    return results


@router.get("/optimal-params")
def get_optimal_params(metric: str = "sharpe", top_k: int = 5):
    """
    sharpe_contour.json 기반 파라미터 최적화 결과 반환.

    metric: "sharpe"(기본) | "mdd"(낙폭 최소) | "cagr" | "risk-adj"(sharpe/|mdd|)
    top_k: 상위 몇 개 조합 반환 (기본 5)
    """
    from config import DATA_PROCESSED
    path = os.path.join(DATA_PROCESSED, "sharpe_contour.json")
    raw: list | None = _load_json(path)
    if not raw:
        raise HTTPException(status_code=404, detail="sharpe_contour.json 없음. P5 백테스트 재실행 필요.")

    # 점수 계산
    def _score(p: dict) -> float:
        if metric == "mdd":
            return p.get("mdd", -1.0)       # 덜 부정적일수록 높음 (내림차순)
        if metric == "cagr":
            return p.get("cagr", 0.0)
        if metric == "risk-adj":
            mdd = abs(p.get("mdd", -1.0)) or 1e-9
            return p.get("sharpe", 0.0) / mdd
        return p.get("sharpe", 0.0)         # 기본: sharpe

    sorted_combos = sorted(raw, key=_score, reverse=True)

    # 파라미터 그리드 추출
    ml_weights   = sorted(set(p["ml_weight"]   for p in raw))
    top_ns       = sorted(set(p["top_n"]       for p in raw))
    rule_weights = sorted(set(p["rule_weight"] for p in raw if "rule_weight" in p and p["rule_weight"] is not None))

    # 백테스트 기간
    summary_path = os.path.join(DATA_PROCESSED, "backtest_summary.json")
    summary = _load_json(summary_path) or {}
    start_date = summary.get("start_date", "N/A")
    end_date   = summary.get("end_date",   "N/A")

    ranked = [
        {
            "rank":        i + 1,
            "ml_weight":   p["ml_weight"],
            "rule_weight": p.get("rule_weight"),
            "top_n":       p["top_n"],
            "sharpe":      round(p.get("sharpe", 0), 4),
            "cagr":        round(p.get("cagr",   0), 4),
            "mdd":         round(p.get("mdd",    0), 4),
            "score":       round(_score(p), 4),
        }
        for i, p in enumerate(sorted_combos)
    ]

    # 3가지 프로필 선택
    # high_sharpe: sharpe 최대
    best_sharpe = max(raw, key=lambda p: p.get("sharpe", 0))
    # low_risk: mdd 가장 작음 (덜 부정적) → top_n 최대 조합 우선
    best_mdd    = max(raw, key=lambda p: p.get("mdd", -99))
    # balanced: 전체 조합의 median top_n + median ml_weight
    median_top_n = sorted(top_ns)[len(top_ns) // 2]
    balanced_candidates = [p for p in raw if p["top_n"] == median_top_n]
    best_balanced = max(balanced_candidates, key=lambda p: p.get("sharpe", 0)) if balanced_candidates else ranked[0]

    def _fmt(p: dict) -> dict:
        return {
            "ml_weight":   p["ml_weight"],
            "rule_weight": p.get("rule_weight"),
            "top_n":       p["top_n"],
            "sharpe":      round(p.get("sharpe", 0), 4),
            "cagr":        round(p.get("cagr",   0), 4),
            "mdd":         round(p.get("mdd",    0), 4),
        }

    return {
        "metadata": {
            "total_combos":       len(raw),
            "evaluation_period":  f"{start_date} ~ {end_date}",
            "optimized_metric":   metric,
            "param_grid": {
                "ml_weight":   ml_weights,
                "rule_weight": rule_weights if rule_weights else None,
                "top_n":       top_ns,
            },
        },
        "best":   {**_fmt(best_sharpe), "rank": 1, "score": round(_score(best_sharpe), 4)},
        "top_k":  ranked[:top_k],
        "profiles": {
            "high_sharpe": _fmt(best_sharpe),
            "balanced":    _fmt(best_balanced),
            "low_risk":    _fmt(best_mdd),
        },
    }


@router.get("/equity-curve")
def get_equity_curve():
    """누적 수익률 시계열 반환 (전략 vs SPY)"""
    from config import BASE_DIR, DATA_PROCESSED
    # equity_curve.parquet → JSON 변환 or equity_curve.json 직접 로드
    parquet_path = os.path.join(DATA_PROCESSED, "equity_curve.parquet")
    if os.path.exists(parquet_path):
        import pandas as pd
        ec = pd.read_parquet(parquet_path)
        cols = ec.columns.tolist()
        return {
            "dates": ec.index.astype(str).tolist() if ec.index.dtype != object else ec.index.tolist(),
            "strategy":  ec[cols[0]].tolist() if cols else [],
            "benchmark": ec[cols[1]].tolist() if len(cols) > 1 else [],
        }
    path = os.path.join(DATA_PROCESSED, "equity_curve.json")
    if not os.path.exists(path):
        path = os.path.join(BASE_DIR, "models", "results", "equity_curve.json")
    data = _load_json(path)
    if data is None:
        return {"dates": [], "strategy": [], "benchmark": []}
    return data
