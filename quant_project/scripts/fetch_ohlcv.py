"""
P1-A: OHLCV 데이터 다운로드
- 50종목 배치, 1초 간격 (rate limit 방지)
- 체크포인트: data/checkpoints/ohlcv_progress.json
- 출력: data/processed/ohlcv.parquet
"""

import os
import sys
import json
import time
import logging
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import DATA_CONSTITUENTS, DATA_CHECKPOINTS, TRAIN_START, TRAIN_END
from services.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHECKPOINT_PATH = os.path.join(DATA_CHECKPOINTS, "ohlcv_progress.json")
BATCH_SIZE = 50
os.makedirs(DATA_CHECKPOINTS, exist_ok=True)


def load_tickers() -> list[str]:
    csv_path = os.path.join(DATA_CONSTITUENTS, "sp500_tickers.csv")
    df = pd.read_csv(csv_path)
    tickers = df["ticker"].dropna().unique().tolist()
    logger.info(f"대상 종목: {len(tickers)}개")
    return tickers


def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH) as f:
            return json.load(f)
    return {"completed_batches": [], "failed_tickers": []}


def save_checkpoint(state: dict):
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(state, f, indent=2)


def download_batch(tickers: list[str], start: str, end: str) -> pd.DataFrame | None:
    import yfinance as yf
    try:
        data = yf.download(
            tickers, start=start, end=end,
            auto_adjust=True, progress=False, threads=True
        )
        if data.empty:
            logger.warning(f"빈 데이터: {tickers[:3]}...")
            return None
        return data
    except Exception as e:
        logger.error(f"배치 다운로드 실패: {e}")
        return None


def main():
    import yfinance as yf

    tickers = load_tickers()
    state = load_checkpoint()
    storage = get_storage()

    # 배치 분할
    batches = [tickers[i:i + BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]
    total_batches = len(batches)
    logger.info(f"총 {total_batches}배치 (배치당 {BATCH_SIZE}종목)")

    all_frames = []

    # 기존 데이터 로드
    if storage.exists("ohlcv"):
        logger.info("기존 ohlcv.parquet 로드 중...")
        all_frames.append(storage.load("ohlcv"))

    for batch_idx, batch in enumerate(batches):
        batch_key = f"batch_{batch_idx}"

        if batch_key in state["completed_batches"]:
            logger.info(f"  [{batch_idx+1}/{total_batches}] 스킵 (체크포인트)")
            continue

        logger.info(f"  [{batch_idx+1}/{total_batches}] 다운로드: {batch[:3]}... ({len(batch)}종목)")
        data = download_batch(batch, TRAIN_START, TRAIN_END)

        if data is not None:
            all_frames.append(data)
            state["completed_batches"].append(batch_key)
            save_checkpoint(state)
            logger.info(f"    → {data.shape[0]}일 × {data.shape[1]}열")
        else:
            state["failed_tickers"].extend(batch)
            save_checkpoint(state)

        time.sleep(1)  # rate limit

    if not all_frames:
        logger.error("다운로드된 데이터 없음")
        return

    # 병합 및 저장
    logger.info("데이터 병합 중...")
    combined = pd.concat(all_frames, axis=1)
    # 중복 컬럼 제거
    combined = combined.loc[:, ~combined.columns.duplicated()]
    combined.sort_index(inplace=True)

    storage.save(combined, "ohlcv")
    logger.info(f"ohlcv.parquet 저장 완료: {combined.shape}")

    if state["failed_tickers"]:
        logger.warning(f"실패 종목 {len(state['failed_tickers'])}개: {state['failed_tickers'][:10]}")

    return combined


if __name__ == "__main__":
    main()
