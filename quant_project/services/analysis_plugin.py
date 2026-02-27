"""
AnalysisPlugin 추상 레이어
정성 분석 소스 교체 시 config.py의 FUNDAMENTAL_SOURCE 값만 변경

plugin_free  → FreeAnalysisPlugin  (Claude 자체 지식 + 공개 정보, API 키 불필요)
plugin_mcp   → MCPAnalysisPlugin   (financial-services-plugins MCP, 실전용)
"""

from __future__ import annotations
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


# ─── 추상 베이스 ──────────────────────────────────────────────

class BaseAnalysisPlugin(ABC):

    @abstractmethod
    def analyze_earnings(self, ticker: str, quarter: str) -> dict:
        """어닝스 분석 반환.
        keys: ticker, quarter, revenue, eps, guidance, beat_miss, summary
        """
        ...

    @abstractmethod
    def get_one_pager(self, ticker: str) -> dict:
        """종목 원페이저 반환.
        keys: ticker, name, sector, thesis, strengths, risks, valuation, rating
        """
        ...

    @abstractmethod
    def run_comps(self, ticker: str) -> dict:
        """유사기업 비교 분석.
        keys: ticker, peers, pe_comparison, ev_ebitda_comparison, summary
        """
        ...

    @abstractmethod
    def get_investment_thesis(self, ticker: str) -> str:
        """투자 thesis 텍스트 반환 (단락 형식)."""
        ...


# ─── FreeAnalysisPlugin (프로토타입) ──────────────────────────

class FreeAnalysisPlugin(BaseAnalysisPlugin):
    """
    프로토타입 — 공개 정보 + 기본 재무 지표 기반 분석
    yfinance 데이터를 활용하므로 API 키 불필요.
    참고용 수준; 실전 운용 시 MCPAnalysisPlugin으로 교체.
    """

    def analyze_earnings(self, ticker: str, quarter: str) -> dict:
        """yfinance 연간/분기 실적 데이터로 어닝스 분석"""
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info

            # 최근 EPS 및 가이던스 프록시
            eps_ttm       = info.get("trailingEps")
            eps_forward   = info.get("forwardEps")
            revenue_ttm   = info.get("totalRevenue")
            revenue_growth = info.get("revenueGrowth")
            earnings_growth = info.get("earningsGrowth")

            beat_miss = "unknown"
            if eps_forward and eps_ttm:
                beat_miss = "beat" if eps_forward > eps_ttm else "miss"

            summary = (
                f"{ticker} 최근 실적 요약: "
                f"TTM EPS {eps_ttm}, Forward EPS {eps_forward}, "
                f"매출 성장률 {revenue_growth:.1%}" if revenue_growth else
                f"{ticker}: 공개 데이터 기반 분석 (정확한 분기 실적은 MCPPlugin 사용 권장)"
            )

            return {
                "ticker":          ticker,
                "quarter":         quarter,
                "revenue_ttm":     revenue_ttm,
                "eps_ttm":         eps_ttm,
                "eps_forward":     eps_forward,
                "revenue_growth":  revenue_growth,
                "earnings_growth": earnings_growth,
                "beat_miss":       beat_miss,
                "summary":         summary,
                "source":          "plugin_free (yfinance)",
                "generated_at":    datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.warning(f"analyze_earnings({ticker}) 오류: {e}")
            return self._empty_earnings(ticker, quarter, str(e))

    def get_one_pager(self, ticker: str) -> dict:
        """yfinance info 기반 원페이저 자동 생성"""
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info

            name    = info.get("longName", ticker)
            sector  = info.get("sector", "Unknown")
            industry = info.get("industry", "Unknown")
            summary_text = info.get("longBusinessSummary", "")[:500]
            pe      = info.get("trailingPE")
            pb      = info.get("priceToBook")
            roe     = info.get("returnOnEquity")
            de      = info.get("debtToEquity")
            mktcap  = info.get("marketCap")
            div_yield = info.get("dividendYield")

            strengths = []
            risks = []
            if roe and roe > 0.15:
                strengths.append(f"높은 ROE ({roe:.1%})")
            if pe and pe < 25:
                strengths.append(f"합리적 밸류에이션 (PER {pe:.1f})")
            if de and de > 2.0:
                risks.append(f"높은 부채비율 (D/E {de:.2f})")
            if pe and pe > 40:
                risks.append(f"고평가 우려 (PER {pe:.1f})")

            # 간단 rating
            score = 0
            if roe and roe > 0.15: score += 1
            if pe and 10 < pe < 30: score += 1
            if de and de < 1.5: score += 1
            rating = ["Sell", "Neutral", "Neutral", "Buy"][min(score, 3)]

            return {
                "ticker":    ticker,
                "name":      name,
                "sector":    sector,
                "industry":  industry,
                "thesis":    summary_text or f"{name}는 {sector} 섹터의 주요 기업입니다.",
                "strengths": strengths or ["공개 데이터 기준 긍정 요인 미확인"],
                "risks":     risks or ["공개 데이터 기준 위험 요인 미확인"],
                "valuation": {
                    "PER": pe,
                    "PBR": pb,
                    "ROE": roe,
                    "DE_ratio": de,
                    "market_cap": mktcap,
                    "dividend_yield": div_yield,
                },
                "rating":       rating,
                "source":       "plugin_free (yfinance)",
                "generated_at": datetime.utcnow().isoformat(),
                "disclaimer":   "FreePlugin — 참고용. 정확한 분석은 MCPPlugin(FactSet 등) 사용 권장.",
            }
        except Exception as e:
            logger.warning(f"get_one_pager({ticker}) 오류: {e}")
            return self._empty_one_pager(ticker, str(e))

    def run_comps(self, ticker: str) -> dict:
        """동종업계 peers 기반 간이 비교"""
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info
            peers = info.get("companyOfficers", [])  # 실제 peers API 없으므로 빈 배열

            return {
                "ticker":  ticker,
                "peers":   [],
                "summary": f"{ticker} 유사기업 비교는 MCPPlugin(FactSet Comps) 사용 시 가능합니다.",
                "source":  "plugin_free",
                "generated_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {"ticker": ticker, "peers": [], "summary": str(e), "source": "plugin_free"}

    def get_investment_thesis(self, ticker: str) -> str:
        """원페이저 thesis 필드에서 텍스트 추출"""
        one_pager = self.get_one_pager(ticker)
        thesis = one_pager.get("thesis", "")
        strengths = ", ".join(one_pager.get("strengths", []))
        risks = ", ".join(one_pager.get("risks", []))
        rating = one_pager.get("rating", "Neutral")

        return (
            f"[{ticker} 투자 Thesis — {rating}]\n"
            f"{thesis}\n\n"
            f"강점: {strengths}\n"
            f"위험: {risks}\n"
            f"(FreePlugin 기반 — 참고용)"
        )

    # ─── 내부 헬퍼 ────────────────────────────────────────────

    def _empty_earnings(self, ticker, quarter, error="") -> dict:
        return {
            "ticker": ticker, "quarter": quarter,
            "revenue_ttm": None, "eps_ttm": None, "eps_forward": None,
            "revenue_growth": None, "earnings_growth": None,
            "beat_miss": "unknown", "summary": f"데이터 조회 실패: {error}",
            "source": "plugin_free", "generated_at": datetime.utcnow().isoformat(),
        }

    def _empty_one_pager(self, ticker, error="") -> dict:
        return {
            "ticker": ticker, "name": ticker, "sector": "Unknown", "industry": "Unknown",
            "thesis": f"데이터 조회 실패: {error}", "strengths": [], "risks": [],
            "valuation": {}, "rating": "Neutral", "source": "plugin_free",
            "generated_at": datetime.utcnow().isoformat(),
            "disclaimer": "FreePlugin — 참고용.",
        }


# ─── MCPAnalysisPlugin (실전 스텁) ────────────────────────────

class MCPAnalysisPlugin(BaseAnalysisPlugin):
    """
    실전 — financial-services-plugins MCP 연결
    FactSet / Morningstar / S&P Global 데이터 활용
    전환 방법: .env의 FUNDAMENTAL_SOURCE=plugin_mcp

    구현 완성 방법:
    > services/analysis_plugin.py의 MCPAnalysisPlugin을
      FactSet MCP 연결로 구현 완성해줘. .env의 FACTSET_API_KEY 사용.
    """

    def analyze_earnings(self, ticker: str, quarter: str) -> dict:
        raise NotImplementedError(
            "MCPAnalysisPlugin: FACTSET_API_KEY 설정 후 구현. "
            "financial-services-plugins /earnings 커맨드 연결 필요."
        )

    def get_one_pager(self, ticker: str) -> dict:
        raise NotImplementedError(
            "MCPAnalysisPlugin: FACTSET_API_KEY 설정 후 구현. "
            "financial-services-plugins /one-pager 커맨드 연결 필요."
        )

    def run_comps(self, ticker: str) -> dict:
        raise NotImplementedError(
            "MCPAnalysisPlugin: /comps 커맨드 연결 필요."
        )

    def get_investment_thesis(self, ticker: str) -> str:
        raise NotImplementedError(
            "MCPAnalysisPlugin: /one-pager 결과 기반 thesis 생성 구현 필요."
        )


# ─── 팩토리 ──────────────────────────────────────────────────

def get_analysis_plugin() -> BaseAnalysisPlugin:
    from config import FUNDAMENTAL_SOURCE
    plugins = {
        "plugin_free": FreeAnalysisPlugin,
        "plugin_mcp":  MCPAnalysisPlugin,
    }
    cls = plugins.get(FUNDAMENTAL_SOURCE)
    if cls is None:
        raise ValueError(f"알 수 없는 FUNDAMENTAL_SOURCE: {FUNDAMENTAL_SOURCE}")
    return cls()
