"""
QuantVision — FastAPI 메인 앱
P3: 라우터 뼈대 등록 / P6에서 실제 데이터 연결
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import fundamentals, backtest, portfolio, sentiment

app = FastAPI(
    title="QuantVision API",
    description="S&P 500 ML 팩터 전략 백엔드 — QuantVision v1",
    version="1.0.0",
)

# Streamlit 프론트엔드에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fundamentals.router, prefix="/api/fundamentals", tags=["fundamentals"])
app.include_router(backtest.router,     prefix="/api/backtest",     tags=["backtest"])
app.include_router(portfolio.router,    prefix="/api/portfolio",    tags=["portfolio"])
app.include_router(sentiment.router,    prefix="/api/sentiment",    tags=["sentiment"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
