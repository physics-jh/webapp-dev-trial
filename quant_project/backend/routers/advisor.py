"""
AI Advisor 엔드포인트
POST /api/advisor/insight — 페이지·지표 컨텍스트 수신 → 한국어 AI 해설 반환
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class InsightRequest(BaseModel):
    page: str              # 'fundamental_filter' | 'backtest' | 'portfolio' | 'sentiment' | 'strategy_advisor'
    context: dict[str, Any]  # 현재 페이지 주요 지표


class InsightResponse(BaseModel):
    insight: str
    cached:  bool = False


@router.post("/insight", response_model=InsightResponse)
def get_insight(req: InsightRequest):
    """
    페이지 컨텍스트 기반 AI 해설 반환.
    services/ai_advisor.py → Claude Haiku API 호출 (5분 캐싱).
    ANTHROPIC_API_KEY 없으면 임계값 기반 폴백 해설 반환.
    """
    try:
        from services.ai_advisor import get_page_insight
        text = get_page_insight(req.page, req.context)
        return InsightResponse(insight=text)
    except Exception as e:
        logger.error(f"AI 해설 생성 오류: {e}")
        return InsightResponse(insight="⚠️ AI 해설 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
