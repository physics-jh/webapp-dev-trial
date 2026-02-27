"""
generate_signals.py — ML 신호 사전 캐싱 스크립트

build_factors.py 실행 후 호출됨 (APScheduler 18:10).
factors.parquet 최신 날 데이터에 학습된 모델을 적용해 신호를 계산하고
data/processed/latest_signals.json 으로 저장한다.

portfolio.py _load_signals()는 이미 실시간 계산을 지원하므로
이 스크립트가 없어도 API는 정상 동작하지만, 캐시가 있으면 응답 속도를 높인다.
"""

import json
import logging
import os
import sys

import numpy as np
import pandas as pd

# quant_project 루트를 sys.path에 추가
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    from config import BASE_DIR, DATA_PROCESSED
    import joblib

    factors_path = os.path.join(DATA_PROCESSED, "factors.parquet")
    model_dir    = os.path.join(BASE_DIR, "models", "trained", "latest")
    output_path  = os.path.join(DATA_PROCESSED, "latest_signals.json")
    sel_path     = os.path.join(DATA_PROCESSED, "selected_features.json")

    if not os.path.exists(factors_path):
        logger.warning("factors.parquet 없음 — generate_signals 스킵")
        return
    if not os.path.exists(model_dir):
        logger.warning("models/trained/latest 없음 — generate_signals 스킵")
        return

    df = pd.read_parquet(factors_path)

    with open(sel_path) as f:
        raw = json.load(f)
    features = raw.get("selected_features", list(raw.keys())) if isinstance(raw, dict) else raw

    # 마지막 날 데이터 추출
    if "date" in df.columns:
        last_date = pd.to_datetime(df["date"]).max()
        last_df   = df[pd.to_datetime(df["date"]) == last_date].copy()
        last_df   = last_df.set_index("ticker")
    else:
        last_date = df.index.get_level_values("date").max()
        last_df   = df.xs(last_date, level="date")

    X = last_df[features].fillna(0)

    scaler = None
    scaler_path = os.path.join(model_dir, "scaler.pkl")
    if os.path.exists(scaler_path):
        scaler = joblib.load(scaler_path)

    preds = []
    for model_file in ["lgbm.pkl", "lightgbm.pkl", "ridge.pkl"]:
        mpath = os.path.join(model_dir, model_file)
        if os.path.exists(mpath):
            model = joblib.load(mpath)
            X_arr   = scaler.transform(X.values) if scaler else X.values
            X_input = pd.DataFrame(X_arr, index=X.index, columns=X.columns)
            preds.append(model.predict(X_input))

    if not preds:
        logger.warning("모델 파일 없음 — generate_signals 스킵")
        return

    signal = np.mean(preds, axis=0)
    result = {
        "as_of": str(last_date.date()) if hasattr(last_date, "date") else str(last_date),
        "signals": {ticker: float(sig) for ticker, sig in zip(last_df.index, signal)},
    }

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    logger.info(f"신호 캐시 저장 완료: {output_path} ({len(result['signals'])}개 종목, 기준일={result['as_of']})")


if __name__ == "__main__":
    main()
