"""
P1-A: S&P 500 Historical Constituents 수집
- Wikipedia 현재 구성 종목 스크래핑
- 상장폐지/편출 종목 수동 보완 메모 포함
- 출력: data/constituents/sp500_tickers.csv
"""

import os
import sys
import json
import logging
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import DATA_CONSTITUENTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

os.makedirs(DATA_CONSTITUENTS, exist_ok=True)
OUT_CSV = os.path.join(DATA_CONSTITUENTS, "sp500_tickers.csv")


def fetch_wikipedia_sp500() -> pd.DataFrame:
    """Wikipedia에서 현재 S&P 500 구성종목 수집"""
    import io
    import requests
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    logger.info(f"Wikipedia S&P 500 목록 수집 중...")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; QuantVision/1.0; research)"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = tables[0][["Symbol", "Security", "GICS Sector", "GICS Sub-Industry", "Date added"]]
    df.columns = ["ticker", "name", "sector", "sub_industry", "date_added"]
    df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)  # BRK.B → BRK-B
    df["source"] = "wikipedia_current"
    logger.info(f"Wikipedia: {len(df)}종목 수집 완료")
    return df


def add_historical_delisted(df: pd.DataFrame) -> pd.DataFrame:
    """
    생존편향 방지: 2014~2024 기간 주요 상장폐지/편출 종목 추가
    NOTE: 완전한 historical constituents는 Compustat/CRSP 유료 데이터 필요
          프로토타입에서는 주요 종목만 수동 보완
    """
    delisted = [
        # (ticker, name, sector, 편출/상폐 이유)
        ("GE",    "General Electric",     "Industrials",       "분사 후 편출 2021"),
        ("XOM",   "ExxonMobil",           "Energy",            "2024 복귀 전 일시 편출"),
        ("CELG",  "Celgene",              "Health Care",       "2019 BMS 인수합병"),
        ("MON",   "Monsanto",             "Materials",         "2018 Bayer 인수합병"),
        ("COL",   "Rockwell Collins",     "Industrials",       "2018 UTX 인수합병"),
        ("PCLN",  "Priceline",            "Consumer Discr.",   "2018 Booking Holdings로 변경"),
        ("ANDV",  "Andeavor",             "Energy",            "2018 MPC 인수합병"),
        ("CA",    "CA Technologies",      "Info Technology",   "2018 Broadcom 인수합병"),
        ("TWX",   "Time Warner",          "Communication",     "2018 AT&T 인수합병"),
        ("ESRX",  "Express Scripts",      "Health Care",       "2018 Cigna 인수합병"),
        ("RHT",   "Red Hat",              "Info Technology",   "2019 IBM 인수합병"),
        ("UTX",   "United Technologies",  "Industrials",       "2020 RTX로 변경"),
        ("AGN",   "Allergan",             "Health Care",       "2020 AbbVie 인수합병"),
        ("LB",    "L Brands",             "Consumer Discr.",   "2021 BBWI/VSCO 분사"),
        ("PBCT",  "People's United",      "Financials",        "2022 M&T Bank 인수합병"),
        ("XLNX",  "Xilinx",              "Info Technology",   "2022 AMD 인수합병"),
        ("ATVI",  "Activision Blizzard",  "Communication",     "2023 Microsoft 인수합병"),
        ("VMW",   "VMware",              "Info Technology",   "2023 Broadcom 인수합병"),
    ]
    df_hist = pd.DataFrame(delisted, columns=["ticker", "name", "sector", "sub_industry"])
    df_hist["date_added"] = pd.NaT
    df_hist["source"] = "historical_manual"

    combined = pd.concat([df, df_hist], ignore_index=True)
    combined = combined.drop_duplicates(subset="ticker", keep="first")
    logger.info(f"역사적 종목 추가 후: {len(combined)}종목")
    return combined


def main():
    df = fetch_wikipedia_sp500()
    df = add_historical_delisted(df)

    df.to_csv(OUT_CSV, index=False)
    logger.info(f"저장 완료: {OUT_CSV}")

    # 섹터 분포 출력
    print("\n=== 섹터 분포 ===")
    print(df["sector"].value_counts().to_string())
    print(f"\n총 {len(df)}종목")

    return df


if __name__ == "__main__":
    main()
