"""
QuantVision — Streamlit 메인 앱 v2
단계별 퀀트 전략 수립 워크플로우 + 다크테마 대시보드
"""

import requests
import streamlit as st

st.set_page_config(
    page_title="QuantVision",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 글로벌 CSS (다크테마 + 전문가 레이아웃) ───────────────────
st.markdown("""
<style>
/* 기본 배경 + 글로벌 텍스트 */
[data-testid="stAppViewContainer"] {
    background-color: #0e1117;
    color: #e6edf3;
}
[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #30363d;
}
/* 모든 마크다운 텍스트 가독성 */
p, [data-testid="stMarkdownContainer"] p { color: #e6edf3 !important; }
[data-testid="stExpander"] summary { color: #e6edf3 !important; }
td, th { color: #e6edf3 !important; }

/* 카드 스타일 */
.qv-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.qv-card-title {
    font-size: 0.75rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
}
.qv-card-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #e6edf3;
}
.qv-card-sub {
    font-size: 0.8rem;
    color: #8b949e;
    margin-top: 2px;
}

/* 워크플로우 스테퍼 */
.qv-step {
    display: flex;
    align-items: center;
    padding: 8px 12px;
    border-radius: 8px;
    margin-bottom: 6px;
    cursor: pointer;
    border: 1px solid transparent;
}
.qv-step:hover {
    border-color: #30363d;
    background: #1c2128;
}
.qv-step-num {
    width: 26px; height: 26px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 700;
    margin-right: 10px; flex-shrink: 0;
}
.qv-step-active .qv-step-num  { background: #238636; color: #fff; }
.qv-step-default .qv-step-num { background: #21262d; color: #8b949e; }
.qv-step-label {
    font-size: 0.85rem;
    color: #c9d1d9;
    font-weight: 500;
}
.qv-step-desc {
    font-size: 0.72rem;
    color: #8b949e;
    margin-top: 1px;
}

/* 레짐 배지 */
.badge-bull     { background:#1a4731; color:#3fb950; border:1px solid #238636; padding:3px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
.badge-neutral  { background:#3b2f00; color:#d29922; border:1px solid #9e6a03; padding:3px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
.badge-bear     { background:#4a1313; color:#f85149; border:1px solid #da3633; padding:3px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }

/* 섹션 헤더 */
.qv-section-header {
    font-size: 1.05rem;
    font-weight: 600;
    color: #e6edf3;
    border-left: 3px solid #238636;
    padding-left: 10px;
    margin: 20px 0 12px 0;
}

/* 지표 설명 박스 */
.qv-hint {
    background: #1c2128;
    border-left: 3px solid #1f6feb;
    border-radius: 0 6px 6px 0;
    padding: 10px 14px;
    font-size: 0.82rem;
    color: #8b949e;
    margin: 8px 0;
}
</style>
""", unsafe_allow_html=True)

API = "http://localhost:8000"


def _get(endpoint: str, **params):
    try:
        r = requests.get(f"{API}{endpoint}", params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ── 사이드바: 워크플로우 스테퍼 ──────────────────────────────
with st.sidebar:
    st.markdown("## 📈 QuantVision")
    st.markdown("<div style='color:#8b949e;font-size:0.78rem;margin-bottom:16px;'>S&P 500 ML 팩터 전략 플랫폼</div>", unsafe_allow_html=True)

    # 백엔드 상태
    health = _get("/health")
    if health:
        st.markdown("<span style='color:#3fb950;font-size:0.8rem;'>● API 연결 정상</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span style='color:#f85149;font-size:0.8rem;'>● API 연결 실패 (포트 8000)</span>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📋 전략 수립 워크플로우")

    STEPS = [
        ("1", "펀더멘털 필터",    "ROE·PER·D/E 기준 종목 스크리닝"),
        ("2", "백테스트 검증",    "ML×룰베이스 파라미터 최적화"),
        ("3", "포트폴리오 구성",  "ML 신호 + 레짐 기반 포지션"),
        ("4", "감성분석 확인",    "RSS·Reddit 시장 심리 체크"),
        ("5", "정성 리포트",      "AI 기반 종목 원페이저 생성"),
        ("6", "전략 어드바이저",  "레짐별 통합 전략 권고"),
    ]

    for num, label, desc in STEPS:
        active_class = "qv-step-active" if num == "1" else "qv-step-default"
        st.markdown(f"""
        <div class="qv-step {active_class}">
            <div class="qv-step-num">{num}</div>
            <div>
                <div class="qv-step-label">{label}</div>
                <div class="qv-step-desc">{desc}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<div style='color:#8b949e;font-size:0.75rem;'>데이터 자동 갱신: 매일 18:00 KST</div>", unsafe_allow_html=True)


# ── 메인: 홈 대시보드 ─────────────────────────────────────────
st.markdown("# 📈 QuantVision")
st.markdown("<div style='color:#8b949e;margin-bottom:24px;'>S&P 500 ML 팩터 전략 + 정성분석 플랫폼 | 왼쪽 사이드바에서 페이지를 선택하세요</div>", unsafe_allow_html=True)

# 레짐 배지
regime_data = _get("/api/portfolio/regime")
if regime_data:
    r = regime_data.get("regime", "neutral")
    vix = regime_data.get("vix", 0)
    t10 = regime_data.get("t10y2y", 0)
    spy_below = regime_data.get("spy_below_ma200", False)
    badge_class = f"badge-{r}"
    label_map   = {"bull": "🟢 BULL", "neutral": "🟡 NEUTRAL", "bear": "🔴 BEAR"}
    st.markdown(
        f"<span class='{badge_class}'>{label_map.get(r, r.upper())}</span>"
        f"&nbsp;&nbsp;<span style='color:#8b949e;font-size:0.85rem;'>VIX {vix:.1f} &nbsp;|&nbsp; T10Y2Y {t10:.2f}% &nbsp;|&nbsp; SPY 200MA {'⚠️ 하향' if spy_below else '✅ 상향'}</span>",
        unsafe_allow_html=True,
    )
    st.markdown("")

# 핵심 지표 4개 카드
col1, col2, col3, col4 = st.columns(4)

summary = _get("/api/backtest/summary")
if summary:
    col1.markdown(f"""
    <div class="qv-card">
        <div class="qv-card-title">Sharpe Ratio</div>
        <div class="qv-card-value" style="color:#3fb950;">{summary.get('sharpe', 0):.3f}</div>
        <div class="qv-card-sub">CAGR {summary.get('cagr', 0)*100:.1f}%</div>
    </div>""", unsafe_allow_html=True)
    mdd = summary.get('max_drawdown', 0)
    mdd_color = "#f85149" if mdd < -0.30 else "#3fb950"
    col2.markdown(f"""
    <div class="qv-card">
        <div class="qv-card-title">MDD (최대낙폭)</div>
        <div class="qv-card-value" style="color:{mdd_color};">{mdd*100:.1f}%</div>
        <div class="qv-card-sub">승률 {summary.get('win_rate', 0)*100:.1f}%</div>
    </div>""", unsafe_allow_html=True)
else:
    col1.markdown('<div class="qv-card"><div class="qv-card-title">Sharpe Ratio</div><div class="qv-card-value" style="color:#8b949e;">—</div></div>', unsafe_allow_html=True)
    col2.markdown('<div class="qv-card"><div class="qv-card-title">MDD</div><div class="qv-card-value" style="color:#8b949e;">—</div></div>', unsafe_allow_html=True)

portfolio_data = _get("/api/portfolio/current", top_n=10)
if portfolio_data:
    n_pos = portfolio_data.get("n_positions", 0)
    col3.markdown(f"""
    <div class="qv-card">
        <div class="qv-card-title">현재 포지션 수</div>
        <div class="qv-card-value">{n_pos}</div>
        <div class="qv-card-sub">레짐: {portfolio_data.get('regime', '—').upper()}</div>
    </div>""", unsafe_allow_html=True)
else:
    col3.markdown('<div class="qv-card"><div class="qv-card-title">포지션 수</div><div class="qv-card-value" style="color:#8b949e;">—</div></div>', unsafe_allow_html=True)

sentiment_data = _get("/api/sentiment/summary")
if sentiment_data:
    sc = sentiment_data.get("overall_score", 0)
    sc_color = "#3fb950" if sc > 0.05 else ("#f85149" if sc < -0.05 else "#d29922")
    col4.markdown(f"""
    <div class="qv-card">
        <div class="qv-card-title">시장 감성 점수</div>
        <div class="qv-card-value" style="color:{sc_color};">{sc:+.3f}</div>
        <div class="qv-card-sub">기사 {sentiment_data.get('n_articles', 0)}건</div>
    </div>""", unsafe_allow_html=True)
else:
    col4.markdown('<div class="qv-card"><div class="qv-card-title">감성 점수</div><div class="qv-card-value" style="color:#8b949e;">—</div></div>', unsafe_allow_html=True)

st.markdown("")

# ── 페이지 안내 테이블 ─────────────────────────────────────────
st.markdown('<div class="qv-section-header">페이지 구성 및 전략 수립 순서</div>', unsafe_allow_html=True)

st.markdown("""
| # | 페이지 | 주요 기능 | 핵심 지표 |
|---|--------|-----------|-----------|
| 1️⃣ | **펀더멘털 필터** | ROE·PER·D/E·EPS성장률 조건으로 S&P 500 스크리닝 | PER ≤ 30, ROE ≥ 10%, D/E ≤ 2.0 |
| 2️⃣ | **백테스트 & 최적화** | ML×룰베이스 3D Sharpe Surface + 누적수익 vs SPY | Sharpe ≥ 0.80, MDD ≤ -30% |
| 3️⃣ | **포트폴리오 모니터** | ML 신호 + 감성가중 포지션 + 레짐 조정 | 섹터 분산 30%, 손절 -10% |
| 4️⃣ | **감성분석 피드** | RSS·Reddit 뉴스 VADER 감성점수 + TF-IDF 키워드 | 감성 -1 ~ +1 |
| 5️⃣ | **종목 정성 리포트** | AI 기반 원페이저 + 어닝스 분석 | FreePlugin / MCPPlugin |
| 6️⃣ | **전략 어드바이저** | 레짐별 통합 전략 권고 + 다음 시나리오 경고 | 리스크 레벨 1-4 |
""")

# ── 지표 가이드 ────────────────────────────────────────────────
with st.expander("📖 주요 지표 해설 (처음이라면 읽어보세요)"):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("""
        **Sharpe Ratio** — 위험 대비 수익률
        - `≥ 1.0` 우수 | `0.7~1.0` 양호 | `< 0.5` 재검토
        - 공식: `(연수익률 - 무위험수익률) / 연변동성`

        **MDD (최대낙폭)**
        - `≤ -20%` 일반 | `≤ -30%` 목표 | `> -40%` 위험
        - 포트폴리오 최저점까지의 하락폭

        **레짐 (Regime)**
        - `BULL` VIX < 15 & SPY > 200MA → 최대 포지션
        - `NEUTRAL` 중간 조건 → 정상 운용
        - `BEAR` VIX > 25 or SPY < 200MA → 1/3 축소
        """)
    with col_b:
        st.markdown("""
        **ML 신호 (Signal Score)**
        - XGBoost + LightGBM 앙상블 예측 점수
        - 높을수록 다음달 수익률 상위 예측 종목

        **감성 점수 (Sentiment)**
        - VADER 기반 복합 점수: `-1` (극도 부정) ~ `+1` (극도 긍정)
        - `> 0.05` 긍정적 심리 | `< -0.05` 부정적 심리

        **Walk-Forward 검증**
        - k-fold 금지 → 날짜 기준 시계열 분할
        - 학습 3년 / 검증 6개월 / 스텝 3개월
        """)
