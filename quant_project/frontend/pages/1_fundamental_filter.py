"""
페이지 1: 펀더멘털 필터
ROE, PER, PBR, D/E, EPS성장률 슬라이더 → /api/fundamentals/screen
캐시 기반 고속 조회 + 다크모드 텍스트 최적화
"""

import requests
import streamlit as st

API = "http://localhost:8000"

st.set_page_config(page_title="펀더멘털 필터", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #0e1117; color: #e6edf3; }
[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
/* 모든 텍스트 흰색 */
p, span, div, label, h1, h2, h3, h4, h5, h6,
[data-testid="stMarkdownContainer"] p,
[data-testid="stText"],
.stMarkdown, .stMarkdown p { color: #e6edf3 !important; }
/* 힌트 박스 */
.qv-hint { background:#1c2128; border-left:3px solid #1f6feb; border-radius:0 6px 6px 0;
           padding:10px 14px; font-size:0.85rem; color:#c9d1d9; margin:8px 0; }
/* 섹션 헤더 */
.qv-section-header { font-size:1.05rem; font-weight:600; color:#e6edf3;
                     border-left:3px solid #238636; padding-left:10px; margin:20px 0 12px 0; }
/* 캐시 상태 배지 */
.cache-ok  { background:#1a4731; color:#3fb950; border:1px solid #238636;
             padding:4px 12px; border-radius:8px; font-size:0.8rem; font-weight:600; display:inline-block; }
.cache-miss { background:#4a1313; color:#f85149; border:1px solid #da3633;
              padding:4px 12px; border-radius:8px; font-size:0.8rem; font-weight:600; display:inline-block; }
.cache-building { background:#3b2f00; color:#d29922; border:1px solid #9e6a03;
                  padding:4px 12px; border-radius:8px; font-size:0.8rem; font-weight:600; display:inline-block; }
/* 데이터프레임 텍스트 */
.stDataFrame td, .stDataFrame th { color: #e6edf3 !important; }
/* 탭 */
button[data-baseweb="tab"] { color: #8b949e; }
button[data-baseweb="tab"][aria-selected="true"] { color: #e6edf3; }
/* 슬라이더 라벨 */
[data-testid="stSlider"] > label { color: #c9d1d9 !important; }
/* expander */
[data-testid="stExpander"] summary, [data-testid="stExpander"] p { color: #e6edf3 !important; }
/* 버튼 */
.stButton > button { background:#238636; color:#fff; border:none; border-radius:6px; font-weight:600; }
.stButton > button:hover { background:#2ea043; }
</style>
""", unsafe_allow_html=True)

st.title("1. 펀더멘털 필터")
st.markdown('<div class="qv-hint">📌 1단계: 재무 건전성 기준으로 S&P 500 후보군을 축소합니다. 통과된 종목은 2단계(백테스트)의 ML 신호 입력으로 활용됩니다.</div>', unsafe_allow_html=True)

# ── 캐시 상태 확인 ──────────────────────────────────────────
@st.cache_data(ttl=10)
def get_cache_status():
    try:
        r = requests.get(f"{API}/api/fundamentals/status", timeout=5)
        return r.json() if r.ok else {}
    except Exception:
        return {}

cache_info = get_cache_status()
cache_exists = cache_info.get("cache_exists", False)
n_tickers   = cache_info.get("n_tickers", 0)
age_hours   = cache_info.get("age_hours")
building    = cache_info.get("build_in_progress", False)

# 캐시 상태 표시
col_status, col_refresh = st.columns([3, 1])
with col_status:
    if building:
        st.markdown('<span class="cache-building">🔄 캐시 빌드 중... (약 3~10분 소요)</span>', unsafe_allow_html=True)
    elif cache_exists and n_tickers > 0:
        age_txt = f"{age_hours:.0f}시간 전 갱신" if age_hours is not None else ""
        st.markdown(f'<span class="cache-ok">✅ 캐시 정상 — {n_tickers}개 종목 {age_txt}</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="cache-miss">⚠️ 캐시 없음 — 오른쪽 버튼으로 캐시를 생성하세요</span>', unsafe_allow_html=True)

with col_refresh:
    if st.button("캐시 생성 / 갱신", help="yfinance에서 전체 종목 펀더멘털 수집 (3~10분)"):
        try:
            r = requests.post(f"{API}/api/fundamentals/refresh", timeout=5)
            msg = r.json().get("status", "")
            st.success(msg)
            st.cache_data.clear()
        except Exception as e:
            st.error(f"refresh 실패: {e}")

if not cache_exists and not building:
    st.info("💡 펀더멘털 캐시가 없습니다. '캐시 생성 / 갱신' 버튼을 눌러 데이터를 먼저 수집하세요. 약 3~10분 소요됩니다.")

st.divider()

# ── 사이드바 필터 ─────────────────────────────────────────────
with st.sidebar:
    st.header("필터 조건")
    per_max        = st.slider("PER 상한",          5.0,  100.0, 30.0, 1.0)
    pbr_max        = st.slider("PBR 상한",          0.1,  20.0,  5.0,  0.1)
    roe_min        = st.slider("ROE 하한",          0.0,  0.5,   0.10, 0.01, format="%.2f")
    de_max         = st.slider("D/E 상한",          0.0,  10.0,  2.0,  0.1)
    eps_growth_min = st.slider("EPS 성장률 하한",   -0.5, 1.0,   0.0,  0.05, format="%.2f")
    limit          = st.slider("최대 종목 수",       10,   200,   150,  10)
    run = st.button("스크리닝 실행", type="primary", disabled=(not cache_exists))

    if not cache_exists:
        st.caption("캐시 생성 후 스크리닝을 실행할 수 있습니다.")

# ── 실행 ─────────────────────────────────────────────────────
if run:
    with st.spinner("스크리닝 중..."):
        try:
            r = requests.get(f"{API}/api/fundamentals/screen", params={
                "per_max": per_max, "pbr_max": pbr_max,
                "roe_min": roe_min, "de_max": de_max,
                "eps_growth_min": eps_growth_min, "limit": limit,
            }, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            st.error(f"API 오류: {e}")
            st.stop()

    if not data:
        st.warning("조건에 맞는 종목이 없습니다. 필터를 완화해보세요. (예: ROE 하한 낮추기, PER 상한 높이기)")
    else:
        st.success(f"✅ {len(data)}개 종목 통과")

        import pandas as pd
        df = pd.DataFrame(data)

        # 수치 포맷
        for col in ["PER", "PBR", "ROE", "DE_ratio", "EPS_growth"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(3)

        display_df = df[["ticker", "name", "sector", "PER", "PBR", "ROE", "DE_ratio", "EPS_growth"]].copy()
        display_df.columns = ["티커", "종목명", "섹터", "PER", "PBR", "ROE(%)", "D/E", "EPS성장률"]

        # ROE % 변환 (yfinance는 소수로 반환)
        if "ROE(%)" in display_df.columns:
            display_df["ROE(%)"] = (display_df["ROE(%)"] * 100).round(1)

        # 섹터별 분포
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("스크리닝 결과")
            st.dataframe(display_df, use_container_width=True, height=500)
        with col2:
            st.subheader("섹터 분포")
            sector_cnt = display_df["섹터"].value_counts()
            import plotly.express as px
            fig = px.pie(
                values=sector_cnt.values, names=sector_cnt.index,
                title="섹터별 종목 수",
                color_discrete_sequence=px.colors.sequential.Viridis,
            )
            fig.update_layout(
                paper_bgcolor="#161b22",
                plot_bgcolor="#161b22",
                font=dict(color="#e6edf3"),
            )
            st.plotly_chart(fig, use_container_width=True)
else:
    if cache_exists:
        st.info("왼쪽 사이드바에서 조건을 설정하고 '스크리닝 실행' 버튼을 누르세요.")

st.divider()

# ── 지표 가이드 ────────────────────────────────────────────────
with st.expander("📖 펀더멘털 지표 기준 가이드"):
    st.markdown("""
    | 지표 | 기준 | 의미 |
    |------|------|------|
    | **PER** | ≤ 30 | 주가/순이익 — 낮을수록 저평가 |
    | **PBR** | ≤ 5.0 | 주가/순자산 — 1 이하면 자산가치 이하 |
    | **ROE** | ≥ 10% | 자기자본 수익률 — 높을수록 수익성 우수 |
    | **D/E** | ≤ 2.0 | 부채/자본 — 낮을수록 재무 안정성 높음 |
    | **EPS 성장률** | ≥ 0% | 주당순이익 성장 — 성장주 필터 |

    > **캐시 갱신 주기**: APScheduler가 매일 18:00 KST에 자동 갱신합니다.
    """)

st.divider()

# ── AI 해설 패널 ──────────────────────────────────────────────
st.markdown('<div class="qv-section-header">🤖 AI 퀀트 어드바이저 해설</div>', unsafe_allow_html=True)

if st.button("AI 해설 생성", key="bt_ai_fund"):
    with st.spinner("분석 중..."):
        ctx = {
            "per_max": per_max, "pbr_max": pbr_max,
            "roe_min": roe_min, "de_max": de_max,
            "eps_growth_min": eps_growth_min,
            "n_stocks": 0,
        }
        try:
            r = requests.post(f"{API}/api/advisor/insight",
                              json={"page": "fundamental_filter", "context": ctx}, timeout=15)
            insight = r.json().get("insight", "")
            if insight:
                st.info(insight)
        except Exception:
            st.caption("AI 해설을 생성할 수 없습니다. ANTHROPIC_API_KEY를 .env에 설정하세요.")
