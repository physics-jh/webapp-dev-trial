"""
QuantVision — FastAPI 메인 앱
P6: 실제 데이터 연결 + APScheduler 일일 파이프라인
"""

import logging
import os
import subprocess
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import advisor, analysis, backtest, fundamentals, portfolio, sentiment

logger = logging.getLogger(__name__)

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
app.include_router(analysis.router,     prefix="/api/analysis",     tags=["analysis"])
app.include_router(advisor.router,      prefix="/api/advisor",      tags=["advisor"])


# ─── APScheduler 일일 파이프라인 ──────────────────────────────

def _run_script(script_path: str, log_label: str):
    """quant_project/.venv로 서브프로세스 실행"""
    from config import BASE_DIR
    venv_python = os.path.join(BASE_DIR, ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = sys.executable
    try:
        result = subprocess.run(
            [venv_python, script_path],
            capture_output=True, text=True, timeout=3600,
        )
        if result.returncode != 0:
            logger.error(f"{log_label} 실패:\n{result.stderr[:500]}")
        else:
            logger.info(f"{log_label} 완료")
    except Exception as e:
        logger.error(f"{log_label} 예외: {e}")


def job_ohlcv_update():
    """18:00 KST — OHLCV 갱신"""
    from config import BASE_DIR
    script = os.path.join(BASE_DIR, "scripts", "fetch_ohlcv.py")
    _run_script(script, "OHLCV 갱신")


def job_factor_signal():
    """18:10 KST — 팩터 재계산 + ML 신호 업데이트"""
    from config import BASE_DIR
    for script, label in [
        (os.path.join(BASE_DIR, "scripts", "build_factors.py"),  "팩터 재계산"),
        (os.path.join(BASE_DIR, "scripts", "generate_signals.py"), "ML 신호"),
    ]:
        _run_script(script, label)


def job_analysis_cache():
    """18:20 KST — 정성 분석 캐시 갱신 (포트폴리오 보유 종목 위주)"""
    try:
        from backend.routers.portfolio import get_current_portfolio
        from backend.routers.analysis import get_analysis
        portfolio_data = get_current_portfolio()
        for pos in portfolio_data.positions:
            try:
                get_analysis(pos.ticker, refresh=True)
                logger.info(f"분석 캐시 갱신: {pos.ticker}")
            except Exception as e:
                logger.warning(f"분석 캐시 갱신 실패 ({pos.ticker}): {e}")
    except Exception as e:
        logger.error(f"정성 분석 캐시 갱신 오류: {e}")


def job_sentiment():
    """18:30 KST — 감성분석 갱신"""
    from services.sentiment_service import collect_sentiment
    collect_sentiment()
    logger.info("감성분석 갱신 완료")


scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(job_ohlcv_update,   "cron", hour=18, minute=0,  id="ohlcv")
scheduler.add_job(job_factor_signal,  "cron", hour=18, minute=10, id="factor_signal")
scheduler.add_job(job_analysis_cache, "cron", hour=18, minute=20, id="analysis_cache")
scheduler.add_job(job_sentiment,      "cron", hour=18, minute=30, id="sentiment")


@app.on_event("startup")
def startup():
    scheduler.start()
    logger.info("APScheduler 시작 (18:00~18:30 KST 일일 파이프라인)")


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown(wait=False)


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/admin/run-pipeline")
def run_pipeline_now():
    """수동 파이프라인 즉시 실행 (테스트용)"""
    job_ohlcv_update()
    job_factor_signal()
    job_analysis_cache()
    job_sentiment()
    return {"message": "파이프라인 수동 실행 완료"}
