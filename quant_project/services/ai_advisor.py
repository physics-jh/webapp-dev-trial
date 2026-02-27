"""
AI Advisor — Claude API 기반 실시간 퀀트 전략 해설
ANTHROPIC_API_KEY 필요 (.env에 설정)

각 Streamlit 페이지 컨텍스트를 수신하여 한국어 해설/전략 권고 반환.
5분 인메모리 캐싱으로 반복 호출 최소화.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# ─── 캐시 ──────────────────────────────────────────────────────
_CACHE: dict[str, tuple[float, str]] = {}  # key → (timestamp, response)
CACHE_TTL = 300  # 5분


def _cache_key(page: str, context: dict) -> str:
    raw = page + json.dumps(context, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str) -> str | None:
    if key in _CACHE:
        ts, val = _CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return val
        del _CACHE[key]
    return None


# ─── 페이지별 시스템 프롬프트 ──────────────────────────────────

_SYSTEM_PROMPTS: dict[str, str] = {
    "fundamental_filter": (
        "당신은 QuantVision 플랫폼의 퀀트 전문가 AI 어드바이저입니다. "
        "사용자가 S&P 500 펀더멘털 스크리닝 결과를 보고 있습니다. "
        "제공된 스크리닝 결과(통과 종목 수, 섹터 분포, 필터 조건)를 분석하여 "
        "① 현재 조건의 타당성, ② 주목할 섹터 편중 여부, ③ 다음 단계 권고를 "
        "간결하고 실용적인 한국어로 설명하세요. 최대 150자."
    ),
    "backtest": (
        "당신은 QuantVision 플랫폼의 퀀트 전문가 AI 어드바이저입니다. "
        "제공된 백테스트 성과 지표(CAGR, Sharpe, MDD, 승률)와 최적 파라미터 프로필을 분석하여 "
        "① 성과 품질 평가, ② 최적 파라미터 선택 근거, ③ 운용 시 주의사항을 "
        "간결하고 실용적인 한국어로 설명하세요. 최대 200자."
    ),
    "portfolio": (
        "당신은 QuantVision 플랫폼의 퀀트 전문가 AI 어드바이저입니다. "
        "현재 시장 레짐(VIX, T10Y2Y, SPY 200MA), 포트폴리오 구성(섹터 분포, 상위 종목), "
        "ML 신호 강도를 분석하여 "
        "① 현재 레짐 해석, ② 포트폴리오 적절성 평가, ③ 단기 리밸런싱 방향을 "
        "간결하고 실용적인 한국어로 설명하세요. 최대 200자."
    ),
    "sentiment": (
        "당신은 QuantVision 플랫폼의 퀀트 전문가 AI 어드바이저입니다. "
        "RSS·Reddit 감성 점수, 주요 키워드, 섹터별 감성 분포를 분석하여 "
        "① 시장 심리 요약, ② 감성 데이터와 기술적 신호의 일치/괴리 여부, "
        "③ 현재 감성 환경이 전략에 주는 시사점을 "
        "간결하고 실용적인 한국어로 설명하세요. 최대 200자."
    ),
    "strategy_advisor": (
        "당신은 QuantVision 플랫폼의 수석 퀀트 전략가 AI 어드바이저입니다. "
        "현재 레짐, 추천 전략 프로필, 백테스트 성과를 종합하여 "
        "① 현재 시장 상황에서 최적 전략 방향, ② 파라미터 조정 근거, "
        "③ 투자자가 가장 주의해야 할 리스크를 "
        "전문적이고 실용적인 한국어로 설명하세요. 최대 250자."
    ),
}

_DEFAULT_SYSTEM = (
    "당신은 QuantVision 퀀트 전략 AI 어드바이저입니다. "
    "제공된 데이터를 분석하여 간결하고 실용적인 한국어 해설을 제공하세요. 최대 200자."
)


# ─── 핵심 함수 ────────────────────────────────────────────────

def get_page_insight(page: str, context: dict[str, Any]) -> str:
    """
    page: 'fundamental_filter' | 'backtest' | 'portfolio' | 'sentiment' | 'strategy_advisor'
    context: 현재 페이지의 주요 지표 딕셔너리

    Returns:
        한국어 AI 해설 문자열 (캐시 적중 시 캐시 반환)
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _fallback_insight(page, context)

    key = _cache_key(page, context)
    cached = _get_cached(key)
    if cached:
        logger.debug(f"AI 해설 캐시 적중: {page}")
        return cached

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = _SYSTEM_PROMPTS.get(page, _DEFAULT_SYSTEM)
        user_message  = f"현재 데이터:\n{json.dumps(context, ensure_ascii=False, indent=2, default=str)}"

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",   # 빠른 응답용 haiku
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        result = message.content[0].text.strip()
        _CACHE[key] = (time.time(), result)
        return result

    except ImportError:
        logger.warning("anthropic 패키지 미설치. 폴백 해설 사용.")
        return _fallback_insight(page, context)
    except Exception as e:
        logger.warning(f"Claude API 오류 ({page}): {e}")
        return _fallback_insight(page, context)


# ─── 폴백: API 키 없을 때 임계값 기반 템플릿 ──────────────────

def _fallback_insight(page: str, context: dict) -> str:
    """ANTHROPIC_API_KEY 없거나 API 오류 시 임계값 기반 한국어 해설"""
    if page == "fundamental_filter":
        n = context.get("n_stocks", 0)
        if n == 0:
            return "⚠️ 통과 종목 없음 — 필터 조건을 완화하세요 (PER 상한 또는 D/E 상한 조정 권장)."
        elif n < 20:
            return f"✅ {n}개 종목 통과 — 엄격한 필터. 소수 정예 스크리닝으로 ML 입력 품질 높음."
        else:
            return f"📊 {n}개 종목 통과 — 다양한 후보군. 2단계 백테스트에서 최적 top_n 확인 권장."

    elif page == "backtest":
        sharpe = context.get("sharpe", 0)
        mdd    = context.get("mdd", -1)
        if sharpe >= 1.0:
            q = "우수"
        elif sharpe >= 0.7:
            q = "양호"
        else:
            q = "검토 필요"
        mdd_msg = "MDD 목표 달성 ✅" if mdd >= -0.30 else f"MDD {mdd*100:.1f}% — 레짐 필터 강화 고려"
        return f"📈 Sharpe {sharpe:.2f} ({q}). {mdd_msg}. 경사가 완만한 파라미터 영역을 선택하세요."

    elif page == "portfolio":
        regime = context.get("regime", "neutral")
        vix    = context.get("vix", 0)
        msgs   = {"bull": "강세 — 최대 포지션 유지.", "bear": "약세 — top_n 축소·현금 확보 권장.", "neutral": "중립 — 정상 운용."}
        return f"🏦 레짐 {regime.upper()}: {msgs.get(regime, '')} VIX {vix:.1f}."

    elif page == "sentiment":
        score = context.get("overall_score", 0)
        if score > 0.1:
            return f"📰 감성 점수 {score:+.2f} — 긍정적 시장 심리. ML 신호와 일치 시 포지션 신뢰도 상승."
        elif score < -0.1:
            return f"📰 감성 점수 {score:+.2f} — 부정적 시장 심리. 레짐 필터와 함께 포지션 축소 고려."
        else:
            return f"📰 감성 점수 {score:+.2f} — 중립적 심리. 다른 팩터(VIX, 모멘텀) 중심으로 판단 권장."

    else:
        return "📊 현재 데이터를 기반으로 전략을 검토 중입니다. ANTHROPIC_API_KEY 설정 시 상세 해설 제공."
