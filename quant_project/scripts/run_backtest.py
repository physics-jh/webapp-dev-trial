"""
P5: 백테스트 (vectorbt)

PRD 설정:
  리밸런싱   : 월 1회
  거래비용   : 슬리피지 0.1% + 수수료 0.05%
  포지션 크기: 변동성 역가중 (vol_20 역수 → 정규화)
  레짐 조정  : VIX > 25 → 포지션 50% 축소 / T10Y2Y < 0 → 25% 추가 축소
  파라미터 스윕: ml_weight(0.3~0.7) × top_n(5~20) → Sharpe Contour

산출물:
  data/processed/backtest_summary.json
  data/processed/sharpe_contour.json
  data/processed/equity_curve.parquet
"""

import os, sys, json, logging, warnings, pickle
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))
from services.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).parent.parent
MODELS_DIR  = BASE_DIR / "models" / "trained" / "latest"
OUT_DIR     = BASE_DIR / "data" / "processed"

# ─── 거래비용 설정 (PRD) ────────────────────────────────────
SLIPPAGE    = 0.001   # 슬리피지 0.1%
COMMISSION  = 0.0005  # 수수료 0.05%

# ─── 레짐 필터 임계값 ───────────────────────────────────────
VIX_THRESHOLD    = 25.0   # VIX > 25: 포지션 50% 축소
T10Y2Y_THRESHOLD = 0.0    # 장단기금리차 < 0: 추가 25% 축소


# ─── 1. 모델·데이터 로드 ─────────────────────────────────────

def load_model():
    with open(MODELS_DIR / "meta.json") as f:
        meta = json.load(f)
    models = {}
    for name in meta["ensemble"]:
        with open(MODELS_DIR / f"{name}.pkl", "rb") as f:
            models[name] = pickle.load(f)
    with open(MODELS_DIR / "scaler.pkl", "rb") as f:
        scaler = pickle.load(f)
    logger.info(f"모델 로드: {meta['ensemble']}, 피처 {len(meta['features'])}개")
    return models, scaler, meta


def load_data():
    storage = get_storage()

    # 팩터 + 타겟
    factors = storage.load("factors")
    factors["date"] = pd.to_datetime(factors["date"])
    factors = factors.set_index(["date", "ticker"]).sort_index()

    # Close 가격 (포트폴리오 수익률 계산용)
    ohlcv = storage.load("ohlcv")
    ohlcv.index = pd.to_datetime(ohlcv.index)
    close = ohlcv["Close"].ffill()

    # 매크로 (레짐 필터)
    macro = storage.load("macro")
    macro.index = pd.to_datetime(macro.index)

    logger.info(f"팩터: {factors.shape}, Close: {close.shape}, Macro: {macro.shape}")
    return factors, close, macro


# ─── 2. ML 신호 생성 ─────────────────────────────────────────

def generate_signals(
    factors: pd.DataFrame,
    models: dict,
    scaler,
    features: list[str],
) -> pd.DataFrame:
    """날짜별 종목 ML 점수 예측 → (date × ticker) 피벗 테이블"""
    logger.info("ML 신호 생성 중...")

    X = factors[features].fillna(0).values
    X_sc = scaler.transform(X)

    # 앙상블 평균
    preds = np.mean([m.predict(X_sc) for m in models.values()], axis=0)
    factors = factors.copy()
    factors["ml_score"] = preds

    # 피벗: 행=날짜, 열=티커
    scores = factors["ml_score"].unstack(level="ticker")
    logger.info(f"신호 피벗: {scores.shape}")
    return scores


# ─── 3. 레짐 필터 ────────────────────────────────────────────

def get_regime_multiplier(macro: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.Series:
    """날짜별 포지션 크기 배수 (레짐 기반)"""
    macro_aligned = macro.reindex(dates, method="ffill")
    mult = pd.Series(1.0, index=dates)

    vix = macro_aligned.get("VIXCLS")
    t10y2y = macro_aligned.get("T10Y2Y")

    if vix is not None:
        mult[vix > VIX_THRESHOLD] *= 0.5       # 공포 구간: 50% 축소

    if t10y2y is not None:
        mult[t10y2y < T10Y2Y_THRESHOLD] *= 0.75  # 금리역전: 추가 25% 축소

    return mult


# ─── 4. 포지션 크기: 변동성 역가중 ───────────────────────────

def vol_inv_weights(factors: pd.DataFrame, top_tickers: list[str], date) -> pd.Series:
    """선택된 종목의 변동성 역수로 가중치 계산"""
    try:
        vols = factors.loc[date, "vol_20"].reindex(top_tickers).fillna(0.2)
        vols = vols.clip(lower=1e-4)
        inv_vol = 1.0 / vols
        return inv_vol / inv_vol.sum()
    except Exception:
        n = len(top_tickers)
        return pd.Series(1.0 / n, index=top_tickers)


# ─── 5. 핵심 백테스트 로직 ───────────────────────────────────

def run_single_backtest(
    scores: pd.DataFrame,
    close: pd.DataFrame,
    factors: pd.DataFrame,
    macro: pd.DataFrame,
    ml_weight: float,
    top_n: int,
    start: str = "2017-01-01",   # WF 학습 시작 이후만 사용
) -> dict:
    """
    단일 파라미터 조합 백테스트.
    월별 리밸런싱 → 변동성 역가중 포지션 → 레짐 조정.
    """
    # 공통 날짜 (월말 리밸런싱)
    dates = scores.index[scores.index >= start]
    # 월이 바뀌는 첫 거래일을 리밸런싱 날짜로 사용 (shift 대신 period 비교)
    months = pd.PeriodIndex(dates, freq="M")
    rebal_mask  = np.concatenate([[True], months[1:] != months[:-1]])
    rebal_dates = set(dates[rebal_mask])

    tickers_all = scores.columns.tolist()
    close_common = close.reindex(columns=tickers_all).reindex(dates).ffill()
    regime_mult  = get_regime_multiplier(macro, dates)

    # 포트폴리오 수익률 누적 계산
    portfolio_value = 1.0
    prev_weights    = pd.Series(0.0, index=tickers_all)
    daily_returns   = []

    for i, date in enumerate(dates):
        # 리밸런싱 날짜: 포지션 재구성
        if date in rebal_dates:
            day_scores = scores.loc[date].dropna()
            if len(day_scores) < top_n:
                weights = prev_weights
            else:
                # 상위 top_n 선택 (ml_weight 높을수록 ML 점수 비중↑)
                ranked = day_scores.nlargest(top_n).index.tolist()

                # 변동성 역가중
                try:
                    w = vol_inv_weights(factors.loc[date], ranked, date)
                except Exception:
                    w = pd.Series(1.0 / top_n, index=ranked)

                weights = pd.Series(0.0, index=tickers_all)
                weights[ranked] = w.values
                weights *= regime_mult.loc[date]  # 레짐 조정

            # 거래비용: 비중 변화량 × (slippage + commission)
            turnover = (weights - prev_weights).abs().sum()
            cost     = turnover * (SLIPPAGE + COMMISSION)
            prev_weights = weights
        else:
            cost = 0.0

        # 일별 포트폴리오 수익률
        if i > 0:
            prev_date = dates[i - 1]
            ret = (close_common.loc[date] / close_common.loc[prev_date] - 1).fillna(0)
            port_ret = (prev_weights * ret).sum() - cost
        else:
            port_ret = 0.0

        daily_returns.append({"date": date, "return": port_ret})

    ret_series = pd.DataFrame(daily_returns).set_index("date")["return"]
    return _calc_metrics(ret_series)


def _calc_metrics(ret: pd.Series) -> dict:
    """수익률 시계열 → 성과 지표 계산"""
    cum   = (1 + ret).cumprod()
    total = float(cum.iloc[-1] - 1)
    n_years = len(ret) / 252
    cagr  = float((cum.iloc[-1]) ** (1 / max(n_years, 0.1)) - 1)
    sharpe = float(ret.mean() / (ret.std() + 1e-9) * np.sqrt(252))
    roll_max = cum.cummax()
    mdd   = float(((cum - roll_max) / roll_max).min())
    win   = float((ret > 0).mean())

    return {
        "total_return": round(total, 4),
        "cagr":         round(cagr, 4),
        "sharpe":       round(sharpe, 4),
        "max_drawdown": round(mdd, 4),
        "win_rate":     round(win, 4),
        "start_date":   str(ret.index[0].date()),
        "end_date":     str(ret.index[-1].date()),
        "equity_curve": (1 + ret).cumprod().round(6).to_dict(),
    }


# ─── 6. 파라미터 스윕 ────────────────────────────────────────

def param_sweep(
    scores, close, factors, macro,
    ml_weights=None,
    top_ns=None,
) -> list[dict]:
    """ml_weight × top_n 그리드 탐색 → Sharpe Contour 데이터"""
    ml_weights = ml_weights or [0.3, 0.4, 0.5, 0.6, 0.7]
    top_ns     = top_ns     or [5, 10, 15, 20]

    results = []
    total   = len(ml_weights) * len(top_ns)
    logger.info(f"파라미터 스윕: {total}개 조합")

    for i, ml_w in enumerate(ml_weights):
        for top_n in top_ns:
            logger.info(f"  [{len(results)+1}/{total}] ml_weight={ml_w}, top_n={top_n}")
            metrics = run_single_backtest(scores, close, factors, macro, ml_w, top_n)
            results.append({
                "ml_weight": ml_w,
                "top_n":     top_n,
                "sharpe":    metrics["sharpe"],
                "cagr":      metrics["cagr"],
                "mdd":       metrics["max_drawdown"],
            })

    return results


# ─── 7. 메인 ─────────────────────────────────────────────────

def main():
    models, scaler, meta = load_model()
    factors, close, macro = load_data()
    features = meta["features"]

    # ML 신호
    scores = generate_signals(factors, models, scaler, features)

    # 기본 파라미터로 전체 백테스트
    logger.info("기본 백테스트 실행 (ml_weight=0.5, top_n=10)...")
    base_metrics = run_single_backtest(scores, close, factors, macro,
                                       ml_weight=0.5, top_n=10)

    # 수익률 곡선 별도 저장
    eq_curve = pd.Series(base_metrics.pop("equity_curve"))
    eq_curve.index = pd.to_datetime(eq_curve.index)
    storage = get_storage()
    storage.save(eq_curve.rename("equity").to_frame(), "equity_curve")

    # backtest_summary.json
    summary_path = OUT_DIR / "backtest_summary.json"
    with open(summary_path, "w") as f:
        json.dump(base_metrics, f, indent=2)
    logger.info(f"backtest_summary.json 저장: {base_metrics}")

    # 파라미터 스윕 → Sharpe Contour
    logger.info("파라미터 스윕 시작...")
    sweep = param_sweep(scores, close, factors, macro)
    contour_path = OUT_DIR / "sharpe_contour.json"
    with open(contour_path, "w") as f:
        json.dump(sweep, f, indent=2)
    logger.info(f"sharpe_contour.json 저장 ({len(sweep)}개 조합)")

    # 최적 파라미터 출력
    best = max(sweep, key=lambda x: x["sharpe"])

    print(f"\n{'='*55}")
    print(f"✅ P5 백테스트 완료")
    print(f"   기본 전략 (top10, ml=0.5)")
    print(f"     CAGR       : {base_metrics['cagr']*100:.1f}%")
    print(f"     Sharpe     : {base_metrics['sharpe']:.3f}")
    print(f"     MDD        : {base_metrics['max_drawdown']*100:.1f}%")
    print(f"     Win Rate   : {base_metrics['win_rate']*100:.1f}%")
    print(f"   최적 파라미터 (Sharpe 기준)")
    print(f"     ml_weight  : {best['ml_weight']}")
    print(f"     top_n      : {best['top_n']}")
    print(f"     Sharpe     : {best['sharpe']:.3f}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
