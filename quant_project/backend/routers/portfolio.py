"""
포트폴리오 모니터링 엔드포인트 — P6 실제 데이터 연결
- ML 모델 예측 신호 (latest 모델)
- macro.parquet 기반 VIX/금리차 레짐 판단
"""

import logging
import os
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 리스크 제어 상수 (mdd-improvement) ──────────────────────────
STOP_LOSS_1M          = -0.10   # 개별 손절: 1개월 수익률 < -10%
VIX_BEAR_THRESHOLD    = 25.0    # VIX > 25 → bear (공포 구간, 기존 수준 복원)
VIX_EXTREME           = 32.0    # VIX > 32 → 극단적 공포
CASH_RESERVE_EXTREME  = 0.30    # VIX > 32 시 현금 유보 비중
SPY_MA_WINDOW         = 200     # SPY 200일 이평 윈도우


class Position(BaseModel):
    ticker:      str
    name:        str
    sector:      str
    weight:      float
    signal:      float        # ML 모델 예측 점수 (z-score)
    ret_1d:      float
    ret_1m:      float
    rsi:         float | None = None
    sentiment:   float | None = None  # VADER compound: -1 ~ +1


class PortfolioStatus(BaseModel):
    as_of:       str
    n_positions: int
    positions:   list[Position]
    regime:      str   # "bull" | "bear" | "neutral"


def _load_signals() -> pd.DataFrame | None:
    """factors.parquet 마지막 날 기준 ML 신호 로드"""
    try:
        from config import DATA_PROCESSED, BASE_DIR
        import joblib

        factors_path = os.path.join(DATA_PROCESSED, "factors.parquet")
        model_dir    = os.path.join(BASE_DIR, "models", "trained", "latest")

        if not os.path.exists(factors_path) or not os.path.exists(model_dir):
            return None

        df = pd.read_parquet(factors_path)
        selected_path = os.path.join(DATA_PROCESSED, "selected_features.json")
        if not os.path.exists(selected_path):
            return None

        import json
        with open(selected_path) as f:
            raw = json.load(f)
        # selected_features.json이 {"selected_features": [...]} 또는 직접 리스트 모두 처리
        if isinstance(raw, dict):
            features = raw.get("selected_features", list(raw.keys()))
        else:
            features = raw

        # 마지막 날 데이터 — RangeIndex 또는 MultiIndex 양쪽 처리
        if "date" in df.columns:
            # RangeIndex + 컬럼 형태
            last_date = pd.to_datetime(df["date"]).max()
            last_df = df[pd.to_datetime(df["date"]) == last_date].copy()
            last_df = last_df.set_index("ticker")
        else:
            # MultiIndex (date, ticker) 형태
            last_date = df.index.get_level_values("date").max()
            last_df   = df.xs(last_date, level="date")

        # 스케일러 로드 (있으면 사용)
        scaler = None
        scaler_path = os.path.join(model_dir, "scaler.pkl")
        if os.path.exists(scaler_path):
            scaler = joblib.load(scaler_path)

        X = last_df[features].fillna(0)

        # 앙상블 모델 로드 (파일명 lgbm.pkl 또는 lightgbm.pkl 모두 시도)
        preds = []
        for model_file in ["lgbm.pkl", "lightgbm.pkl", "ridge.pkl"]:
            mpath = os.path.join(model_dir, model_file)
            if os.path.exists(mpath):
                model = joblib.load(mpath)
                if scaler is not None:
                    X_arr = scaler.transform(X.values)
                    X_input = pd.DataFrame(X_arr, index=X.index, columns=X.columns)
                else:
                    X_input = X
                preds.append(model.predict(X_input))

        if not preds:
            return None

        signal = np.mean(preds, axis=0)
        result = last_df[["rsi"]].copy() if "rsi" in last_df.columns else pd.DataFrame(index=last_df.index)
        result["signal"] = signal
        return result

    except Exception as e:
        logger.warning(f"신호 로드 실패: {e}")
        return None


def _get_regime() -> tuple[str, float | None, float | None, bool]:
    """VIX / T10Y2Y / SPY 200MA 기반 레짐 판단 (mdd-improvement)
    Returns: (regime, vix, t10y2y, spy_below_ma200)
    """
    try:
        from config import DATA_PROCESSED
        path = os.path.join(DATA_PROCESSED, "macro.parquet")
        if not os.path.exists(path):
            return "neutral", None, None, False
        macro = pd.read_parquet(path)
        vix    = float(macro["VIXCLS"].dropna().iloc[-1]) if "VIXCLS" in macro.columns else None
        t10y2y = float(macro["T10Y2Y"].dropna().iloc[-1]) if "T10Y2Y" in macro.columns else None

        # SPY 200일 이평 조건
        spy_below_ma200 = False
        try:
            ohlcv_path = os.path.join(DATA_PROCESSED, "ohlcv.parquet")
            if os.path.exists(ohlcv_path):
                ohlcv = pd.read_parquet(ohlcv_path)
                spy_prices = _get_close_prices_raw(ohlcv, "SPY")
                if len(spy_prices) >= SPY_MA_WINDOW:
                    ma200 = spy_prices.rolling(SPY_MA_WINDOW, min_periods=100).mean().iloc[-1]
                    spy_current = spy_prices.iloc[-1]
                    spy_below_ma200 = bool(spy_current < ma200)
        except Exception:
            spy_below_ma200 = False

        # 레짐 결정: VIX > 25(공포) or T10Y2Y < 0 or SPY < 200MA → bear
        is_bear = (
            (vix is not None and vix > VIX_BEAR_THRESHOLD)
            or (t10y2y is not None and t10y2y < 0)
            or spy_below_ma200
        )
        if is_bear:
            return "bear", vix, t10y2y, spy_below_ma200
        if vix is not None and vix < 15 and not spy_below_ma200:
            return "bull", vix, t10y2y, spy_below_ma200
        return "neutral", vix, t10y2y, spy_below_ma200

    except Exception as e:
        logger.warning(f"레짐 판단 실패: {e}")
        return "neutral", None, None, False


def _get_close_prices_raw(ohlcv: pd.DataFrame, ticker: str) -> pd.Series:
    """Wide-format OHLCV에서 ticker 종가 시계열 (인덱스 정렬)"""
    if isinstance(ohlcv.columns, pd.MultiIndex):
        if ("Close", ticker) in ohlcv.columns:
            return ohlcv[("Close", ticker)].dropna().sort_index()
    return pd.Series(dtype=float)


def _get_close_prices(ohlcv: pd.DataFrame, ticker: str) -> pd.Series:
    """Wide-format OHLCV에서 특정 ticker 종가 시계열 추출"""
    if isinstance(ohlcv.columns, pd.MultiIndex):
        # (Price, Ticker) MultiIndex 컬럼
        if ("Close", ticker) in ohlcv.columns:
            return ohlcv[("Close", ticker)].dropna().sort_index()
        return pd.Series(dtype=float)
    else:
        # 단순 컬럼 형태
        if "Close" in ohlcv.columns:
            return ohlcv[ohlcv.get("ticker", pd.Series()) == ticker]["Close"].sort_index()
        return pd.Series(dtype=float)


def _vol_weight(signals: pd.Series, ohlcv_path: str) -> pd.Series:
    """변동성 역가중 — 60일 변동성 역수 비례"""
    try:
        df = pd.read_parquet(ohlcv_path)
        tickers = signals.index.tolist()
        vols = {}
        for tk in tickers:
            try:
                prices = _get_close_prices(df, tk).iloc[-60:]
                vols[tk] = prices.pct_change().std() if len(prices) > 1 else 1.0
            except Exception:
                vols[tk] = 1.0
        vol_ser = pd.Series(vols)
        inv_vol = 1.0 / vol_ser.clip(lower=1e-6)
        return inv_vol / inv_vol.sum()
    except Exception:
        n = len(signals)
        return pd.Series(1.0 / n, index=signals.index)


@router.get("/current", response_model=PortfolioStatus)
def get_current_portfolio(top_n: int = 10, sentiment_weight: float = 0.0):
    """
    현재 포트폴리오 구성 반환
    - ML 신호 상위 top_n 종목 선택
    - 변동성 역가중
    - 레짐 기반 포지션 크기 조정
    - sentiment_weight > 0 시 감성 점수를 ML 신호에 합산
      adjusted_signal = signal * (1 + sentiment_weight * clamp(sentiment, -1, 1))
    """
    from config import DATA_PROCESSED

    signals_df = _load_signals()
    if signals_df is None or signals_df.empty:
        return PortfolioStatus(as_of=str(datetime.utcnow().date()), n_positions=0, positions=[], regime="neutral")

    regime, regime_vix, regime_t10y2y, spy_below_ma200 = _get_regime()

    # 감성 점수 로드 (캐시)
    sentiment_by_ticker: dict[str, float] = {}
    try:
        from services.sentiment_service import load_cached_sentiment
        cached = load_cached_sentiment()
        if cached:
            for item in cached.get("items", []):
                tk = item.get("ticker")
                if tk:
                    prev = sentiment_by_ticker.get(tk, [])
                    if isinstance(prev, list):
                        prev.append(item["sentiment"])
                        sentiment_by_ticker[tk] = prev
            sentiment_by_ticker = {
                tk: sum(scores) / len(scores)
                for tk, scores in sentiment_by_ticker.items()
                if isinstance(scores, list)
            }
    except Exception as e:
        logger.debug(f"감성 점수 로드 실패 (무시): {e}")

    # ── 감성 가중치 적용: adjusted_signal = signal * (1 + sw * sentiment) ──
    # 전체 시장 감성 점수 (폴백: 티커별 데이터 없을 때 사용)
    overall_sentiment = 0.0
    try:
        from services.sentiment_service import load_cached_sentiment
        cached_full = load_cached_sentiment()
        if cached_full:
            overall_sentiment = float(cached_full.get("overall_score", 0.0))
    except Exception:
        pass

    if sentiment_weight > 0.0:
        def _adjust(row):
            # 티커별 → 없으면 전체 시장 감성 폴백
            s = sentiment_by_ticker.get(row.name, overall_sentiment)
            s = float(np.clip(s, -1.0, 1.0))
            return row["signal"] * (1.0 + sentiment_weight * s)
        signals_df = signals_df.copy()
        signals_df["signal"] = signals_df.apply(_adjust, axis=1)
        logger.info(f"감성 가중치 적용: sentiment_weight={sentiment_weight}, overall={overall_sentiment:.3f}")

    # 레짐 조정: bear 1/3, neutral 80%, bull 100%
    if regime == "bear":
        effective_n = max(top_n // 3, 3)
    elif regime == "neutral":
        effective_n = max(int(top_n * 0.8), 5)
    else:
        effective_n = top_n

    # 손절 필터 여유분: 후보를 2배 확보 후 손절 종목 제외
    candidate_n = min(effective_n * 2, len(signals_df))
    top = signals_df.nlargest(candidate_n, "signal")

    ohlcv_path = os.path.join(DATA_PROCESSED, "ohlcv.parquet")

    # OHLCV 로드
    try:
        ohlcv = pd.read_parquet(ohlcv_path)
    except Exception:
        ohlcv = None

    # ── 손절 필터: 1개월 수익률 < -10% 종목 제외 ──────────────
    stop_loss_excluded = set()
    if ohlcv is not None:
        for ticker in top.index:
            try:
                prices = _get_close_prices(ohlcv, ticker)
                if len(prices) >= 22:
                    ret_1m = float((prices.iloc[-1] - prices.iloc[-22]) / prices.iloc[-22])
                    if ret_1m < STOP_LOSS_1M:
                        stop_loss_excluded.add(ticker)
                        logger.debug(f"손절 제외: {ticker} (1개월 수익률 {ret_1m*100:.1f}%)")
            except Exception:
                pass

    # 손절 제외 후 상위 effective_n 선택
    filtered_top = top[~top.index.isin(stop_loss_excluded)].head(effective_n)
    if filtered_top.empty:
        filtered_top = top.head(effective_n)  # 모두 손절이면 필터 무시

    weights = _vol_weight(filtered_top["signal"], ohlcv_path)

    # ── 초강세 bear: VIX > 25 → 현금 30% 확보 ─────────────────
    cash_multiplier = 1.0
    if regime == "bear" and regime_vix is not None and regime_vix > VIX_EXTREME:
        cash_multiplier = 1.0 - CASH_RESERVE_EXTREME  # 0.70
        logger.info(f"초강세 bear (VIX={regime_vix:.1f}) → 현금 {CASH_RESERVE_EXTREME*100:.0f}% 확보")

    import yfinance as yf

    # 섹터 정보 수집
    SECTOR_MAX_WEIGHT = 0.30
    sector_map: dict[str, str] = {}
    for ticker in filtered_top.index:
        try:
            info = yf.Ticker(ticker).info
            sector_map[ticker] = info.get("sector", "Unknown")
        except Exception:
            sector_map[ticker] = "Unknown"

    # 섹터 분산 제약: 사전 스크리닝 (pre-normalization)
    sector_weight_used: dict[str, float] = {}
    selected_tickers: list[str] = []
    for ticker in filtered_top.index:
        sec = sector_map.get(ticker, "Unknown")
        used = sector_weight_used.get(sec, 0.0)
        raw_w = float(weights.get(ticker, 1.0 / max(effective_n, 1)))
        if used + raw_w <= SECTOR_MAX_WEIGHT:
            selected_tickers.append(ticker)
            sector_weight_used[sec] = used + raw_w
        elif used < SECTOR_MAX_WEIGHT:
            selected_tickers.append(ticker)
            sector_weight_used[sec] = SECTOR_MAX_WEIGHT

    # 비중 재정규화 + 현금 비중 적용 (VIX>25 시 cash_multiplier=0.70)
    total_w = sum(float(weights.get(tk, 1.0 / max(effective_n, 1))) for tk in selected_tickers)
    if total_w <= 0:
        total_w = 1.0

    # ── 사후 섹터 제약 (post-normalization): 정규화 후 30% 초과 섹터 반복 보정 ──
    for _iter in range(5):
        sector_post: dict[str, float] = {}
        for tk in selected_tickers:
            sec = sector_map.get(tk, "Unknown")
            w   = float(weights.get(tk, 1.0 / max(effective_n, 1))) / total_w
            sector_post[sec] = sector_post.get(sec, 0.0) + w
        overweight = {s for s, w in sector_post.items() if w > SECTOR_MAX_WEIGHT + 1e-6}
        if not overweight:
            break
        # 초과 섹터의 최저 신호 종목을 1개 제거
        for tk in reversed(selected_tickers):
            if sector_map.get(tk, "Unknown") in overweight:
                selected_tickers.remove(tk)
                total_w = sum(float(weights.get(t, 1.0 / max(effective_n, 1))) for t in selected_tickers)
                if total_w <= 0:
                    total_w = 1.0
                break

    positions: list = []
    for ticker in selected_tickers:
        signal_val = float(filtered_top.loc[ticker, "signal"])
        rsi_val    = float(filtered_top.loc[ticker, "rsi"]) if "rsi" in filtered_top.columns else None
        weight     = float(weights.get(ticker, 1.0 / max(effective_n, 1))) / total_w * cash_multiplier

        ret_1d = 0.0
        ret_1m = 0.0
        if ohlcv is not None:
            try:
                prices = _get_close_prices(ohlcv, ticker)
                if len(prices) >= 2:
                    ret_1d = float((prices.iloc[-1] - prices.iloc[-2]) / prices.iloc[-2])
                if len(prices) >= 22:
                    ret_1m = float((prices.iloc[-1] - prices.iloc[-22]) / prices.iloc[-22])
            except Exception:
                pass

        try:
            info = yf.Ticker(ticker).info
            name   = info.get("shortName", ticker)
            sector = info.get("sector", "Unknown")
        except Exception:
            name   = ticker
            sector = sector_map.get(ticker, "Unknown")

        sentiment_val = sentiment_by_ticker.get(ticker)

        positions.append(Position(
            ticker=ticker, name=name, sector=sector,
            weight=weight, signal=signal_val,
            ret_1d=ret_1d, ret_1m=ret_1m, rsi=rsi_val,
            sentiment=sentiment_val,
        ))

    return PortfolioStatus(
        as_of=str(datetime.utcnow().date()),
        n_positions=len(positions),
        positions=positions,
        regime=regime,
    )


@router.get("/history")
def get_portfolio_history(days: int = 30):
    """포트폴리오 가치 히스토리 (equity_curve.json 활용)"""
    from config import BASE_DIR
    import json
    path = os.path.join(BASE_DIR, "models", "results", "equity_curve.json")
    if not os.path.exists(path):
        return {"dates": [], "values": []}
    with open(path) as f:
        data = json.load(f)
    dates    = data.get("dates", [])[-days:]
    strategy = data.get("strategy", [])[-days:]
    return {"dates": dates, "values": strategy}


@router.get("/regime")
def get_market_regime():
    """VIX/금리차/SPY 200MA 기반 시장 레짐 반환"""
    regime, vix, t10y2y, spy_below_ma200 = _get_regime()
    return {
        "regime": regime,
        "vix": vix,
        "t10y2y": t10y2y,
        "spy_below_ma200": spy_below_ma200,
    }


@router.get("/strategy-guide")
def get_strategy_guide():
    """현재 레짐 기반 전략 권고 반환"""
    import json
    from config import DATA_PROCESSED

    regime, vix, t10y2y, spy_below_ma200 = _get_regime()

    # 위험 수준 분류 (1~4)
    extreme_bear = (regime == "bear") and (vix is not None) and (vix > VIX_EXTREME)
    if regime == "bull":
        risk_level = 1
    elif regime == "neutral":
        risk_level = 2
    elif extreme_bear:
        risk_level = 4
    else:
        risk_level = 3

    # 레짐별 권장 프로필 및 파라미터
    profile_map = {
        1: ("high_sharpe",  "상승장 — 공격적 운용",  10),
        2: ("balanced",     "중립 시장 — 정상 운용",  8),
        3: ("low_risk",     "하락장 — 방어적 운용",   4),
        4: ("low_risk",     "극단적 공포 — 초방어 운용", 3),
    }
    recommended_profile, strategy_title, recommended_top_n = profile_map[risk_level]
    cash_reserve = CASH_RESERVE_EXTREME if extreme_bear else 0.0

    # 레짐 설명 문자열
    vix_str   = f"VIX {vix:.1f}" if vix else "VIX 데이터 없음"
    spy_str   = "SPY가 200일 이동평균 아래" if spy_below_ma200 else "SPY가 200일 이동평균 위"
    t10y2_str = f"장단기금리차 {t10y2y:.2f}%" if t10y2y else ""

    bodies = {
        1: (f"{vix_str}로 시장 변동성이 낮고, {spy_str}에서 추세 상승 중입니다. "
            f"ML 신호가 강한 종목에 집중 투자하세요."),
        2: (f"{vix_str}로 변동성이 보통 수준입니다. {spy_str}에 위치해 있습니다. "
            f"포지션을 정상 비중으로 유지하세요."),
        3: (f"{vix_str}로 시장 변동성이 높습니다. {spy_str}에 위치해 있습니다. "
            f"포지션을 1/3 수준으로 줄이고 방어적으로 운용하세요."),
        4: (f"{vix_str}로 극도의 공포 구간입니다. {spy_str}에 위치해 있습니다. "
            f"포지션 최소화 + 현금 {int(CASH_RESERVE_EXTREME*100)}% 유보를 권장합니다."),
    }
    strategy_body = bodies[risk_level]

    # 다음 전환 시나리오
    next_scenarios = [
        {"trigger": "VIX > 25",    "outcome": "Bear 레짐 → top_n 1/3 축소"},
        {"trigger": "SPY < 200MA", "outcome": "Bear 레짐 → 포지션 감소"},
        {"trigger": "VIX > 32",    "outcome": "초강세 bear → 현금 30% 확보"},
        {"trigger": "VIX < 15 (유지)", "outcome": "Bull 레짐 → 최대 포지션 운용"},
    ]

    # 백테스트 성과 참고값
    summary_path = os.path.join(DATA_PROCESSED, "backtest_summary.json")
    perf = {}
    if os.path.exists(summary_path):
        with open(summary_path) as f:
            perf = json.load(f)

    return {
        "regime":               regime,
        "vix":                  vix,
        "t10y2y":               t10y2y,
        "spy_below_ma200":      spy_below_ma200,
        "risk_level":           risk_level,
        "recommended_profile":  recommended_profile,
        "recommended_top_n":    recommended_top_n,
        "cash_reserve":         cash_reserve,
        "strategy_title":       strategy_title,
        "strategy_body":        strategy_body,
        "next_scenarios":       next_scenarios,
        "backtest_reference": {
            "cagr":         perf.get("cagr"),
            "sharpe":       perf.get("sharpe"),
            "max_drawdown": perf.get("max_drawdown"),
            "win_rate":     perf.get("win_rate"),
            "start_date":   perf.get("start_date"),
            "end_date":     perf.get("end_date"),
        },
    }
