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

# ─── 레짐 필터 임계값 (mdd-improvement v2 — 균형 조정) ──────────
# VIX > 20이 28% 빈도 → 과포지션 축소 문제 → VIX 기준 25 복원
# SPY 200MA는 추가 조건으로 온건하게 적용 (×0.80)
VIX_BEAR_THRESHOLD    = 25.0   # VIX > 25: bear 공포 구간 (기존 유지)
VIX_EXTREME_THRESHOLD = 32.0   # VIX > 32: 극단적 공포 (추가 축소)
T10Y2Y_THRESHOLD      = 0.0    # 장단기금리차 < 0: 추가 축소
STOP_LOSS_1M          = -0.10  # 개별 손절: 1개월 수익률 < -10%
SPY_MA_WINDOW         = 200    # SPY 200일 이평 윈도우


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


def generate_rule_scores(factors: pd.DataFrame) -> pd.DataFrame:
    """룰베이스 신호 생성 — 모멘텀 + 저변동성 혼합 팩터
    rule_score = 0.5×ret_3m + 0.3×ret_1m + 0.2×(1/vol_20) (정규화)
    기술적 팩터만 사용하므로 factors.parquet로 즉시 계산 가능.
    """
    logger.info("룰베이스 신호 생성 중...")
    f = factors.copy()

    # 사용 가능한 컬럼만 활용 (존재하지 않으면 0)
    ret3m = f["ret_3m"] if "ret_3m" in f.columns else pd.Series(0.0, index=f.index)
    ret1m = f["ret_1m"] if "ret_1m" in f.columns else pd.Series(0.0, index=f.index)
    vol20 = f["vol_20"].clip(lower=1e-4) if "vol_20" in f.columns else pd.Series(0.2, index=f.index)

    raw = 0.5 * ret3m + 0.3 * ret1m + 0.2 * (1.0 / vol20)
    f["rule_score"] = raw

    rule_scores = f["rule_score"].unstack(level="ticker")
    logger.info(f"룰베이스 신호 피벗: {rule_scores.shape}")
    return rule_scores


# ─── 3. 레짐 필터 ────────────────────────────────────────────

def get_regime_multiplier(
    macro: pd.DataFrame,
    dates: pd.DatetimeIndex,
    close: pd.DataFrame | None = None,
) -> pd.Series:
    """날짜별 포지션 크기 배수 (3단계 레짐 — mdd-improvement)

    1단계: VIX > 20 or SPY < 200MA → 1/3 축소 (0.333)
    2단계: T10Y2Y < 0               → 추가 25% 축소 (*0.75)
    3단계: VIX > 25                 → 현금 30% 확보 (*0.70)
    """
    macro_aligned = macro.reindex(dates, method="ffill")
    mult = pd.Series(1.0, index=dates)

    vix    = macro_aligned["VIXCLS"]    if "VIXCLS" in macro_aligned.columns else None
    t10y2y = macro_aligned["T10Y2Y"]   if "T10Y2Y" in macro_aligned.columns else None

    # SPY 200일 이평 조건
    spy_below_ma200 = pd.Series(False, index=dates)
    if close is not None and "SPY" in close.columns:
        spy = close["SPY"].reindex(dates, method="ffill")
        ma200 = spy.rolling(SPY_MA_WINDOW, min_periods=100).mean()
        spy_below_ma200 = spy < ma200

    # 1단계: SPY < 200MA → 20% 축소 (온건한 추가 방어)
    mult[spy_below_ma200] *= 0.80

    # 2단계: VIX > 25 → 50% 축소 (공포 구간 기존 수준 유지)
    if vix is not None:
        mult[vix > VIX_BEAR_THRESHOLD] *= 0.50

    # 3단계: T10Y2Y < 0 → 추가 15% 축소 (완화: 기존 25% → 15%)
    if t10y2y is not None:
        mult[t10y2y < T10Y2Y_THRESHOLD] *= 0.85

    # 4단계: VIX > 32 → 극단적 공포, 추가 30% 축소 (코로나 같은 구간)
    if vix is not None:
        mult[vix > VIX_EXTREME_THRESHOLD] *= 0.70

    return mult.clip(upper=1.0)


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
    rule_scores: pd.DataFrame | None = None,
    rule_weight: float = 0.0,
    start: str = "2017-01-01",
    spy_ret: pd.Series | None = None,
) -> dict:
    """
    단일 파라미터 조합 백테스트 (mdd-improvement).
    월별 리밸런싱 → 변동성 역가중 → 레짐 조정 → 손절 필터.
    rule_scores / rule_weight 추가: ML + 룰베이스 혼합 점수 지원.
    """
    dates = scores.index[scores.index >= start]
    months = pd.PeriodIndex(dates, freq="M")
    rebal_mask  = np.concatenate([[True], months[1:] != months[:-1]])
    rebal_dates = set(dates[rebal_mask])

    tickers_all  = scores.columns.tolist()
    close_common = close.reindex(columns=tickers_all).reindex(dates).ffill()
    # SPY 포함 close 전달 (200MA 계산)
    regime_mult  = get_regime_multiplier(macro, dates, close=close)

    # ── 혼합 점수 계산 (퍼센타일 랭킹 후 가중합) ──────────────────
    total_w = ml_weight + (rule_weight if rule_scores is not None else 0.0)
    if rule_scores is not None and rule_weight > 0.0 and total_w > 0:
        ml_ranks   = scores.rank(axis=1, pct=True)
        rule_ranks = rule_scores.reindex(index=scores.index, columns=scores.columns).rank(axis=1, pct=True)
        combined   = (ml_weight * ml_ranks + rule_weight * rule_ranks) / total_w
    else:
        combined = scores  # 순수 ML 모드

    prev_weights  = pd.Series(0.0, index=tickers_all)
    daily_returns = []

    for i, date in enumerate(dates):
        if date in rebal_dates:
            day_scores = combined.loc[date].dropna() if date in combined.index else scores.loc[date].dropna()
            if len(day_scores) < top_n:
                weights = prev_weights
            else:
                # 손절 필터: 1개월 수익률 < -10% 종목 후보에서 제외
                if i >= 22:
                    prev22_date = dates[max(i - 22, 0)]
                    ret_1m = (close_common.loc[date] / close_common.loc[prev22_date] - 1).fillna(0)
                    valid_scores = day_scores[
                        day_scores.index.map(lambda t: ret_1m.get(t, 0) >= STOP_LOSS_1M)
                    ]
                    if len(valid_scores) < 3:
                        valid_scores = day_scores  # 손절 후 종목 너무 적으면 무시
                else:
                    valid_scores = day_scores

                # 상위 top_n 선택
                ranked = valid_scores.nlargest(top_n).index.tolist()

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
    return _calc_metrics(ret_series, spy_ret=spy_ret)


def _calc_metrics(ret: pd.Series, spy_ret: pd.Series | None = None) -> dict:
    """수익률 시계열 → 성과 지표 계산. spy_ret 제공 시 벤치마크 곡선 포함."""
    cum   = (1 + ret).cumprod()
    total = float(cum.iloc[-1] - 1)
    n_years = len(ret) / 252
    cagr  = float((cum.iloc[-1]) ** (1 / max(n_years, 0.1)) - 1)
    sharpe = float(ret.mean() / (ret.std() + 1e-9) * np.sqrt(252))
    roll_max = cum.cummax()
    mdd   = float(((cum - roll_max) / roll_max).min())
    win   = float((ret > 0).mean())

    result = {
        "total_return": round(total, 4),
        "cagr":         round(cagr, 4),
        "sharpe":       round(sharpe, 4),
        "max_drawdown": round(mdd, 4),
        "win_rate":     round(win, 4),
        "start_date":   str(ret.index[0].date()),
        "end_date":     str(ret.index[-1].date()),
        "equity_curve": (1 + ret).cumprod().round(6).to_dict(),
    }
    if spy_ret is not None:
        spy_aligned = spy_ret.reindex(ret.index).fillna(0)
        result["spy_curve"] = (1 + spy_aligned).cumprod().round(6).to_dict()
    return result


# ─── 6. 파라미터 스윕 ────────────────────────────────────────

def param_sweep(
    scores, close, factors, macro,
    rule_scores=None,
    ml_weights=None,
    rule_weights=None,
    top_n: int = 10,
) -> list[dict]:
    """ml_weight × rule_weight 2D 그리드 탐색 → 3D Sharpe Surface 데이터
    rule_scores 없으면 기존 ml_weight × top_n 1D 스윕으로 폴백.
    """
    if rule_scores is not None:
        # 신규: 2D 스윕 (ml_weight × rule_weight), top_n 고정
        ml_weights   = ml_weights   or [0.1, 0.3, 0.5, 0.7, 0.9]
        rule_weights = rule_weights or [0.1, 0.3, 0.5, 0.7, 0.9]
        total = len(ml_weights) * len(rule_weights)
        logger.info(f"2D 파라미터 스윕: {total}개 조합 (ml_weight × rule_weight, top_n={top_n})")

        results = []
        for ml_w in ml_weights:
            for rb_w in rule_weights:
                logger.info(f"  [{len(results)+1}/{total}] ml_w={ml_w}, rb_w={rb_w}")
                metrics = run_single_backtest(
                    scores, close, factors, macro,
                    ml_weight=ml_w, top_n=top_n,
                    rule_scores=rule_scores, rule_weight=rb_w,
                )
                results.append({
                    "ml_weight":   ml_w,
                    "rule_weight": rb_w,
                    "top_n":       top_n,
                    "sharpe":      metrics["sharpe"],
                    "cagr":        metrics["cagr"],
                    "mdd":         metrics["max_drawdown"],
                })
    else:
        # 레거시 폴백: ml_weight × top_n 스윕
        ml_weights = ml_weights or [0.3, 0.4, 0.5, 0.6, 0.7]
        top_ns     = [5, 10, 15, 20]
        total = len(ml_weights) * len(top_ns)
        logger.info(f"1D 파라미터 스윕 (레거시): {total}개 조합")

        results = []
        for ml_w in ml_weights:
            for tn in top_ns:
                logger.info(f"  [{len(results)+1}/{total}] ml_weight={ml_w}, top_n={tn}")
                metrics = run_single_backtest(scores, close, factors, macro, ml_w, tn)
                results.append({
                    "ml_weight":   ml_w,
                    "rule_weight": 0.0,
                    "top_n":       tn,
                    "sharpe":      metrics["sharpe"],
                    "cagr":        metrics["cagr"],
                    "mdd":         metrics["max_drawdown"],
                })

    return results


# ─── 7. 메인 ─────────────────────────────────────────────────

def main():
    models, scaler, meta = load_model()
    factors, close, macro = load_data()
    features = meta["features"]

    # ML 신호 + 룰베이스 신호
    scores      = generate_signals(factors, models, scaler, features)
    rule_scores = generate_rule_scores(factors)

    # SPY 일별 수익률 (벤치마크용)
    spy_ret = None
    if "SPY" in close.columns:
        spy_ret = close["SPY"].pct_change().fillna(0)
        logger.info("SPY 벤치마크 수익률 준비 완료")

    # ── baseline 저장 (기존 결과 보존) ───────────────────────────
    baseline_path = BASE_DIR / "models" / "results" / "baseline_summary.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    existing_summary = OUT_DIR / "backtest_summary.json"
    if existing_summary.exists() and not baseline_path.exists():
        import shutil
        shutil.copy(existing_summary, baseline_path)
        logger.info(f"baseline_summary.json 저장: {baseline_path}")

    # ── 개선된 파라미터로 백테스트 ─────────────────────────────
    logger.info("개선된 백테스트 실행 (mdd-improvement v2: SPY 200MA + 손절 + 룰베이스 혼합)...")
    base_metrics = run_single_backtest(
        scores, close, factors, macro,
        ml_weight=0.5, top_n=10,
        rule_scores=rule_scores, rule_weight=0.3,
        spy_ret=spy_ret,
    )

    # 수익률 곡선 저장 (전략 + SPY 벤치마크)
    eq_dict  = base_metrics.pop("equity_curve")
    spy_dict = base_metrics.pop("spy_curve", {})
    eq_curve = pd.Series(eq_dict, name="equity")
    eq_curve.index = pd.to_datetime(eq_curve.index)

    storage = get_storage()
    if spy_dict:
        spy_curve = pd.Series(spy_dict, name="spy")
        spy_curve.index = pd.to_datetime(spy_curve.index)
        eq_df = pd.concat([eq_curve, spy_curve], axis=1).sort_index()
    else:
        eq_df = eq_curve.to_frame()
    storage.save(eq_df, "equity_curve")
    logger.info(f"equity_curve 저장: {eq_df.shape} (컬럼: {eq_df.columns.tolist()})")

    # backtest_summary.json 갱신
    summary_path = OUT_DIR / "backtest_summary.json"
    with open(summary_path, "w") as f:
        json.dump(base_metrics, f, indent=2)
    logger.info(f"backtest_summary.json 갱신: {base_metrics}")

    # ── 2D 파라미터 스윕 (ml_weight × rule_weight) ───────────────
    logger.info("2D 파라미터 스윕 시작 (ml_weight × rule_weight, 25 조합)...")
    sweep = param_sweep(scores, close, factors, macro, rule_scores=rule_scores, top_n=10)
    contour_path = OUT_DIR / "sharpe_contour.json"
    with open(contour_path, "w") as f:
        json.dump(sweep, f, indent=2)
    logger.info(f"sharpe_contour.json 저장 ({len(sweep)}개 조합)")

    # ── 개선 전후 비교 출력 ───────────────────────────────────────
    best = max(sweep, key=lambda x: x["sharpe"])

    baseline = {}
    if baseline_path.exists():
        with open(baseline_path) as f:
            baseline = json.load(f)

    print(f"\n{'='*60}")
    print(f"✅ mdd-improvement 백테스트 완료")
    print(f"{'─'*60}")
    print(f"  {'지표':<12} {'기존 (baseline)':>18} {'개선 후':>18}")
    print(f"{'─'*60}")
    for key, label in [("cagr", "CAGR"), ("sharpe", "Sharpe"), ("max_drawdown", "MDD"), ("win_rate", "Win Rate")]:
        old = baseline.get(key)
        new = base_metrics.get(key)
        old_str = f"{old*100:.1f}%" if old is not None and key in ("cagr","max_drawdown","win_rate") else (f"{old:.3f}" if old else "N/A")
        new_str = f"{new*100:.1f}%" if new is not None and key in ("cagr","max_drawdown","win_rate") else (f"{new:.3f}" if new else "N/A")
        mdd_ok = "✅" if key == "max_drawdown" and new is not None and new >= -0.30 else ("⚠️" if key == "max_drawdown" else "")
        print(f"  {label:<12} {old_str:>18} {new_str:>18} {mdd_ok}")
    print(f"{'─'*60}")
    print(f"  최적 파라미터: ml_weight={best['ml_weight']}, top_n={best['top_n']}, Sharpe={best['sharpe']:.3f}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
