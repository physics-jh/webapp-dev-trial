"""
페이지 5: 종목 정성 리포트 — PRD v4.0 신규
종목 선택 → FreeAnalysisPlugin 원페이저 자동 생성
ML 정량 신호 + 정성 분석 병렬 표시
/api/analysis/{ticker} 호출
"""

import requests
import streamlit as st

API = "http://localhost:8000"

st.set_page_config(page_title="종목 정성 리포트", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #0e1117; color: #e6edf3; }
[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
p, [data-testid="stMarkdownContainer"] p { color: #e6edf3 !important; }
.qv-section-header { font-size:1.05rem; font-weight:600; color:#e6edf3;
                     border-left:3px solid #238636; padding-left:10px; margin:20px 0 12px 0; }
[data-testid="stExpander"] summary { color: #e6edf3 !important; }
</style>
""", unsafe_allow_html=True)

st.title("5. 종목 정성 리포트")

# MCP 업그레이드 안내 배너
st.info(
    "**FreeAnalysisPlugin** 기반 분석 (공개 데이터 + yfinance). "
    "더 정확한 FactSet/Morningstar 데이터는 `.env`에 `FUNDAMENTAL_SOURCE=plugin_mcp` 설정 후 MCPPlugin으로 전환하세요.",
    icon="ℹ️",
)

# ── 종목 입력 ────────────────────────────────────────────────
with st.sidebar:
    st.header("종목 선택")
    ticker_input = st.text_input("티커 입력 (예: AAPL)", "AAPL").upper()
    refresh = st.checkbox("캐시 무시 (강제 갱신)", value=False)
    run = st.button("리포트 생성", type="primary")

    st.divider()
    # 캐시된 종목 목록
    try:
        cached = requests.get(f"{API}/api/analysis/", timeout=5).json()
        tickers = cached.get("tickers", [])
        if tickers:
            st.caption(f"캐시된 종목 ({cached['count']}개)")
            selected = st.selectbox("캐시에서 선택", ["직접 입력"] + tickers)
            if selected != "직접 입력":
                ticker_input = selected
    except Exception:
        pass


def render_report(data: dict):
    one_pager = data.get("one_pager", {})
    earnings  = data.get("earnings", {})
    thesis    = data.get("thesis", "")
    ticker    = data.get("ticker", "")
    cached    = data.get("cache_hit", False)

    # ── 헤더 ──────────────────────────────────────────────────
    rating = one_pager.get("rating", "Neutral")
    rating_color = {"Buy": "🟢", "Neutral": "🟡", "Sell": "🔴"}.get(rating, "⚪")
    st.subheader(f"{ticker} — {one_pager.get('name', ticker)}")
    col_r, col_s, col_c = st.columns(3)
    col_r.metric("투자 의견", f"{rating_color} {rating}")
    col_s.metric("섹터", one_pager.get("sector", ""))
    col_c.metric("업종", one_pager.get("industry", ""))
    if cached:
        st.caption(f"캐시 기준: {data.get('generated_at', '')[:16]} UTC (refresh=True로 갱신)")

    st.divider()

    # ── 2열 레이아웃: 정량 vs 정성 ───────────────────────────
    col_q, col_a = st.columns(2)

    with col_q:
        st.markdown("#### 정량 밸류에이션")
        val = one_pager.get("valuation", {})
        metrics = [
            ("PER",     val.get("PER")),
            ("PBR",     val.get("PBR")),
            ("ROE",     val.get("ROE")),
            ("D/E",     val.get("DE_ratio")),
            ("시총",    val.get("market_cap")),
            ("배당수익률", val.get("dividend_yield")),
        ]
        for name, value in metrics:
            if value is not None:
                if isinstance(value, float) and value < 10:
                    st.metric(name, f"{value:.2f}")
                elif isinstance(value, float):
                    st.metric(name, f"{value:,.0f}")
                else:
                    st.metric(name, str(value))

    with col_a:
        st.markdown("#### 정성 분석 (FreePlugin)")
        st.markdown("**투자 thesis**")
        st.write(one_pager.get("thesis", ""))

        strengths = one_pager.get("strengths", [])
        risks     = one_pager.get("risks", [])
        if strengths:
            st.markdown("**강점**")
            for s in strengths:
                st.markdown(f"- ✅ {s}")
        if risks:
            st.markdown("**위험**")
            for r in risks:
                st.markdown(f"- ⚠️ {r}")

    st.divider()

    # ── 어닝스 분석 ───────────────────────────────────────────
    st.markdown("#### 어닝스 분석")
    col_e1, col_e2, col_e3 = st.columns(3)
    beat = earnings.get("beat_miss", "unknown")
    col_e1.metric("EPS (TTM)",    earnings.get("eps_ttm", "N/A"))
    col_e2.metric("EPS (Forward)", earnings.get("eps_forward", "N/A"))
    col_e3.metric("Beat/Miss", beat.upper() if beat else "N/A")
    growth = earnings.get("revenue_growth")
    if growth is not None:
        st.metric("매출 성장률", f"{growth*100:+.1f}%")
    st.caption(earnings.get("summary", ""))

    st.divider()

    # ── 투자 Thesis 전문 ──────────────────────────────────────
    with st.expander("투자 Thesis 전문"):
        st.markdown(thesis.replace("\n", "  \n"))

    st.caption(
        f"생성 시각: {data.get('generated_at', '')[:16]} UTC | "
        f"소스: {one_pager.get('source', 'plugin_free')} | "
        f"{one_pager.get('disclaimer', '')}"
    )


# ── 실행 ─────────────────────────────────────────────────────
if run and ticker_input:
    with st.spinner(f"{ticker_input} 분석 생성 중..."):
        try:
            r = requests.get(
                f"{API}/api/analysis/{ticker_input}",
                params={"refresh": refresh},
                timeout=60,
            )
            r.raise_for_status()
            render_report(r.json())
        except requests.HTTPError as e:
            st.error(f"API 오류 ({e.response.status_code}): {e.response.text}")
        except Exception as e:
            st.error(f"분석 실패: {e}")
else:
    st.info("왼쪽 사이드바에서 종목을 입력하고 '리포트 생성' 버튼을 누르세요.")
    st.markdown("""
**지원 종목**: S&P 500 전 종목 (yfinance 공개 데이터 기반)

**MCPPlugin 전환 방법**:
```
# .env 수정
FUNDAMENTAL_SOURCE=plugin_mcp
FACTSET_API_KEY=your_key
```
""")
