import os
from dotenv import load_dotenv

load_dotenv()

# ─── 데이터 소스 ───────────────────────────────────────────────
# 교체 시 이 값만 변경 (상위 레이어 수정 금지)
DATA_PROVIDER      = os.getenv("DATA_PROVIDER",      "yfinance")     # → "alpaca" → "polygon"
STORAGE_BACKEND    = os.getenv("STORAGE_BACKEND",    "parquet")      # → "postgres"
FUNDAMENTAL_SOURCE = os.getenv("FUNDAMENTAL_SOURCE", "plugin_free")  # → "plugin_mcp"
SENTIMENT_SOURCE   = os.getenv("SENTIMENT_SOURCE",   "rss_vader")    # → "newsapi_finbert"

# ─── API 키 ───────────────────────────────────────────────────
FRED_API_KEY    = os.getenv("FRED_API_KEY",    "")
ALPACA_KEY      = os.getenv("ALPACA_KEY",      "")
ALPACA_SECRET   = os.getenv("ALPACA_SECRET",   "")
POLYGON_KEY     = os.getenv("POLYGON_KEY",     "")
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID",     "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
NEWS_API_KEY         = os.getenv("NEWS_API_KEY",          "")

# MCP 정성 분석 제공업체 키 (실전 전환 시)
FACTSET_API_KEY      = os.getenv("FACTSET_API_KEY",      "")
MORNINGSTAR_API_KEY  = os.getenv("MORNINGSTAR_API_KEY",  "")
SP_GLOBAL_API_KEY    = os.getenv("SP_GLOBAL_API_KEY",    "")

# ─── 데이터 경로 ──────────────────────────────────────────────
BASE_DIR        = os.path.dirname(__file__)
DATA_RAW        = os.path.join(BASE_DIR, "data", "raw")
DATA_PROCESSED  = os.path.join(BASE_DIR, "data", "processed")
DATA_CONSTITUENTS = os.path.join(BASE_DIR, "data", "constituents")
DATA_CHECKPOINTS  = os.path.join(BASE_DIR, "data", "checkpoints")

# ─── 학습 기간 ────────────────────────────────────────────────
TRAIN_START = "2014-01-01"
TRAIN_END   = "2024-12-31"
