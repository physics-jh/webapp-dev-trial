"""
P2-B: 팩터 계산 + IC/VIF 검증
PRD 팩터 그룹:
  모멘텀    : ret_1m, ret_3m, mom_gap
  변동성    : vol_20, downside_vol, natr, skew, kurt
  유동성    : dol_vol, vol_zscore, mfi
  추세/반전 : rsi, disparity_20, ma_cross
타겟:
  target_next   = 익일 수익률  (학습용)
  target_smooth = 5일 이동평균 (EDA 전용 — 학습 절대 금지)
산출물:
  data/processed/factors.parquet
  data/processed/selected_features.json
"""

import os, sys, json, logging, warnings
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.storage import get_storage

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

IC_MIN   = 0.02   # IC 절댓값 기준 미달 시 제거
VIF_MAX  = 10.0   # VIF 초과 시 제거
FEAT_TARGET = (10, 15)   # 최종 선택 범위


# ─── 1. 데이터 로드 ───────────────────────────────────────────

def load_price_data() -> tuple[pd.DataFrame, ...]:
    """OHLCV에서 Close/High/Low/Volume 추출 후 유효 종목만 반환"""
    storage = get_storage()
    ohlcv = storage.load("ohlcv")
    ohlcv.index = pd.to_datetime(ohlcv.index)

    close  = ohlcv["Close"]
    high   = ohlcv["High"]
    low    = ohlcv["Low"]
    volume = ohlcv["Volume"]

    # 결측 30% 이하 종목만 사용
    valid_mask = close.isna().mean() < 0.3
    tickers = valid_mask[valid_mask].index.tolist()
    logger.info(f"유효 종목: {len(tickers)}개")

    return (
        close[tickers].ffill(),
        high[tickers].ffill(),
        low[tickers].ffill(),
        volume[tickers].ffill().fillna(0),
        tickers,
    )


# ─── 2. 팩터 계산 ─────────────────────────────────────────────

def calc_factors(
    close: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    volume: pd.DataFrame,
) -> pd.DataFrame:
    """종목별로 ta 라이브러리 사용, 결과를 (date × ticker, factor) 형태로 반환"""
    import ta

    all_records = []

    tickers = close.columns.tolist()
    logger.info(f"팩터 계산 시작: {len(tickers)}종목")

    for i, ticker in enumerate(tickers):
        if (i + 1) % 50 == 0:
            logger.info(f"  진행: {i+1}/{len(tickers)}")

        c = close[ticker].dropna()
        h = high[ticker].reindex(c.index).ffill()
        l = low[ticker].reindex(c.index).ffill()
        v = volume[ticker].reindex(c.index).fillna(0)

        if len(c) < 60:
            continue

        try:
            rec = _calc_single(ticker, c, h, l, v)
            all_records.append(rec)
        except Exception as e:
            logger.debug(f"  [{ticker}] 팩터 계산 오류: {e}")
            continue

    df = pd.concat(all_records)
    logger.info(f"팩터 계산 완료: {df.shape}")
    return df


def _calc_single(
    ticker: str,
    c: pd.Series,
    h: pd.Series,
    l: pd.Series,
    v: pd.Series,
) -> pd.DataFrame:
    import ta

    ret = c.pct_change()

    # ── 모멘텀 ──────────────────────────────────────────────
    ret_1m  = c.pct_change(21)
    ret_3m  = c.pct_change(63)
    ma50    = c.rolling(50).mean()
    ma200   = c.rolling(200).mean()
    mom_gap = (ma50 - ma200) / ma200          # 50일 MA와 200일 MA 괴리

    # ── 변동성 ──────────────────────────────────────────────
    vol_20      = ret.rolling(20).std() * np.sqrt(252)
    down_ret    = ret.clip(upper=0)
    downside_vol = down_ret.rolling(20).std() * np.sqrt(252)
    tr          = pd.concat([
                    h - l,
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()
                  ], axis=1).max(axis=1)
    natr        = tr.rolling(14).mean() / c     # Normalized ATR
    skew        = ret.rolling(60).skew()
    kurt        = ret.rolling(60).kurt()

    # ── 유동성 ──────────────────────────────────────────────
    dol_vol     = (c * v).rolling(20).mean()    # 달러 거래량 (20일 평균)
    vol_mean    = v.rolling(20).mean()
    vol_std     = v.rolling(20).std()
    vol_zscore  = (v - vol_mean) / (vol_std + 1e-9)

    # MFI (Money Flow Index) — ta 라이브러리
    mfi = ta.volume.MFIIndicator(
        high=h, low=l, close=c, volume=v, window=14, fillna=False
    ).money_flow_index()

    # ── 추세/반전 ────────────────────────────────────────────
    rsi = ta.momentum.RSIIndicator(close=c, window=14, fillna=False).rsi()
    disparity_20 = (c / c.rolling(20).mean() - 1) * 100   # 이격도
    ma_cross     = (ma50 > ma200).astype(float)            # 골든크로스 1, 데스크로스 0

    # ── 타겟 ─────────────────────────────────────────────────
    target_next   = ret.shift(-1)                          # 익일 수익률 (학습 타겟)
    target_smooth = target_next.rolling(5).mean()          # EDA 전용 — 학습 금지

    df = pd.DataFrame({
        # 모멘텀
        "ret_1m":       ret_1m,
        "ret_3m":       ret_3m,
        "mom_gap":      mom_gap,
        # 변동성
        "vol_20":       vol_20,
        "downside_vol": downside_vol,
        "natr":         natr,
        "skew":         skew,
        "kurt":         kurt,
        # 유동성
        "dol_vol":      dol_vol,
        "vol_zscore":   vol_zscore,
        "mfi":          mfi,
        # 추세/반전
        "rsi":          rsi,
        "disparity_20": disparity_20,
        "ma_cross":     ma_cross,
        # 타겟
        "target_next":   target_next,
        "target_smooth": target_smooth,
    }, index=c.index)

    df.index.name = "date"
    df["ticker"] = ticker
    df = df.dropna(subset=["target_next"])
    df = df.reset_index().set_index(["date", "ticker"])
    return df


# ─── 3. IC 검증 ───────────────────────────────────────────────

FACTOR_COLS = [
    "ret_1m", "ret_3m", "mom_gap",
    "vol_20", "downside_vol", "natr", "skew", "kurt",
    "dol_vol", "vol_zscore", "mfi",
    "rsi", "disparity_20", "ma_cross",
]


def compute_ic(df: pd.DataFrame) -> pd.DataFrame:
    """날짜별 Rank IC (Spearman) 계산 후 평균/t-stat 반환"""
    logger.info("IC 계산 중...")
    records = []

    for date, group in df.groupby(level="date"):
        if len(group) < 20:
            continue
        target = group["target_next"].values
        for col in FACTOR_COLS:
            vals = group[col].values
            mask = ~(np.isnan(vals) | np.isnan(target))
            if mask.sum() < 10:
                continue
            corr, _ = stats.spearmanr(vals[mask], target[mask])
            records.append({"date": date, "factor": col, "ic": corr})

    ic_df = pd.DataFrame(records)
    summary = (
        ic_df.groupby("factor")["ic"]
        .agg(ic_mean="mean", ic_std="std", ic_count="count")
        .assign(ic_ir=lambda x: x["ic_mean"] / (x["ic_std"] + 1e-9))
        .assign(ic_abs=lambda x: x["ic_mean"].abs())
        .sort_values("ic_abs", ascending=False)
    )
    logger.info(f"\n=== IC 요약 ===\n{summary.to_string()}")
    return summary


# ─── 4. VIF 검증 ──────────────────────────────────────────────

def compute_vif(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """VIF(분산팽창인수) 계산 — 다중공선성 검사"""
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    logger.info("VIF 계산 중...")
    # 날짜별로 샘플링해서 패널 데이터 구성
    sample = df[features].dropna()
    if len(sample) > 10000:
        sample = sample.sample(10000, random_state=42)

    X = sample.values
    vif_data = pd.DataFrame({
        "feature": features,
        "VIF": [variance_inflation_factor(X, i) for i in range(X.shape[1])]
    }).sort_values("VIF", ascending=False)

    logger.info(f"\n=== VIF 요약 ===\n{vif_data.to_string()}")
    return vif_data


# ─── 5. 팩터 선택 ─────────────────────────────────────────────

def select_features(ic_summary: pd.DataFrame, vif_data: pd.DataFrame) -> list[str]:
    """IC >= 0.02 이고 VIF <= 10인 팩터, 10~15개 선택"""

    # IC 필터
    ic_pass = ic_summary[ic_summary["ic_abs"] >= IC_MIN].index.tolist()
    logger.info(f"IC 통과: {len(ic_pass)}개 — {ic_pass}")

    # VIF 필터 (IC 통과 팩터 중에서)
    vif_pass = vif_data[
        (vif_data["feature"].isin(ic_pass)) &
        (vif_data["VIF"] <= VIF_MAX)
    ]["feature"].tolist()
    logger.info(f"VIF 통과: {len(vif_pass)}개 — {vif_pass}")

    # 10~15개 범위 조정
    # 부족하면 IC 순으로 보충, 넘으면 IC IR 순으로 상위 15개
    if len(vif_pass) < FEAT_TARGET[0]:
        ic_ranked = ic_summary.sort_values("ic_abs", ascending=False).index.tolist()
        for f in ic_ranked:
            if f not in vif_pass:
                vif_pass.append(f)
            if len(vif_pass) >= FEAT_TARGET[0]:
                break
        logger.warning(f"VIF 조건 완화 적용 → {len(vif_pass)}개")

    if len(vif_pass) > FEAT_TARGET[1]:
        # IC IR 기준 상위 15개
        ir_ranked = ic_summary.loc[vif_pass].sort_values("ic_ir", ascending=False).index[:FEAT_TARGET[1]].tolist()
        vif_pass = ir_ranked
        logger.info(f"IC IR 기준 상위 {FEAT_TARGET[1]}개로 축소")

    logger.info(f"\n✅ 최종 선택 팩터 {len(vif_pass)}개: {vif_pass}")
    return vif_pass


# ─── 6. 메인 ─────────────────────────────────────────────────

def main():
    storage = get_storage()

    # 데이터 로드
    close, high, low, volume, tickers = load_price_data()

    # 팩터 계산
    factors_df = calc_factors(close, high, low, volume)

    # IC 검증
    ic_summary = compute_ic(factors_df)

    # VIF 검증 (IC 통과 후보만)
    ic_candidates = ic_summary[ic_summary["ic_abs"] >= IC_MIN / 2].index.tolist()
    if len(ic_candidates) < 3:
        ic_candidates = FACTOR_COLS  # 후보 부족시 전체 사용

    vif_data = compute_vif(factors_df, ic_candidates)

    # 팩터 선택
    selected = select_features(ic_summary, vif_data)

    # 저장
    # factors.parquet: 선택 팩터 + 타겟만 저장
    save_cols = selected + ["target_next", "target_smooth"]
    factors_save = factors_df[save_cols].reset_index()
    storage.save(factors_save, "factors")
    logger.info(f"factors.parquet 저장: {factors_save.shape}")

    # selected_features.json
    result = {
        "selected_features": selected,
        "ic_summary": ic_summary[["ic_mean", "ic_std", "ic_ir"]].to_dict(),
        "vif_summary": vif_data.set_index("feature")["VIF"].to_dict(),
        "n_tickers": len(tickers),
        "date_range": [str(factors_save["date"].min()), str(factors_save["date"].max())],
    }
    out_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "processed", "selected_features.json"
    )
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"selected_features.json 저장: {out_path}")

    print(f"\n{'='*50}")
    print(f"✅ P2 팩터 계산 완료")
    print(f"   선택 팩터 {len(selected)}개: {selected}")
    print(f"   전체 데이터: {factors_save.shape[0]:,}행")
    print(f"{'='*50}")

    return selected


if __name__ == "__main__":
    main()
