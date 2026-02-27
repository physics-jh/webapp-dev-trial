"""
페이지 3: 포트폴리오 모니터
종목 테이블 (가격/당일수익/ML신호/RSI/감성) + 30초 자동 갱신
사이드바에 Agent F review_log.md 최신 코멘트
"""

import time

import requests
import streamlit as st

API = "http://localhost:8000"

st.set_page_config(page_title="포트폴리오 모니터", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #0e1117; color: #e6edf3; }
[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
p, [data-testid="stMarkdownContainer"] p { color: #e6edf3 !important; }
.qv-hint { background:#1c2128; border-left:3px solid #1f6feb; border-radius:0 6px 6px 0;
           padding:10px 14px; font-size:0.85rem; color:#c9d1d9; margin:8px 0; }
.qv-section-header { font-size:1.05rem; font-weight:600; color:#e6edf3;
                     border-left:3px solid #238636; padding-left:10px; margin:20px 0 12px 0; }
[data-testid="stExpander"] summary { color: #e6edf3 !important; }
</style>
""", unsafe_allow_html=True)

st.title("3. 포트폴리오 모니터")
st.markdown('<div class="qv-hint">📌 ML 신호 상위 종목을 변동성 역가중으로 구성합니다. <b>감성 가중치 > 0</b> 설정 시 뉴스·Reddit 감성 점수가 종목 선정에 반영됩니다.</div>', unsafe_allow_html=True)

# ── 자동 갱신 설정 ────────────────────────────────────────────
auto_refresh = st.sidebar.checkbox("30초 자동 갱신", value=True)
top_n = st.sidebar.slider("포지션 수", 5, 20, 10)
sentiment_weight = st.sidebar.slider(
    "감성 가중치 (sentiment_weight)",
    min_value=0.0, max_value=0.3, value=0.0, step=0.05,
    help="0: ML 신호만 사용 | 0.1~0.3: 감성 점수를 ML 신호에 합산"
)
if sentiment_weight > 0:
    st.sidebar.caption(f"✅ 감성 가중치 적용 중: adjusted_signal = signal × (1 + {sentiment_weight} × sentiment)")

# ── Agent F review_log ────────────────────────────────────────
with st.sidebar:
    st.subheader("Agent F 리뷰")
    import os
    log_path = os.path.join(os.path.dirname(__file__), "..", "..", "review_log.md")
    if os.path.exists(log_path):
        with open(log_path) as f:
            lines = f.readlines()
        # 최신 5줄
        st.markdown("".join(lines[-20:]))
    else:
        st.caption("review_log.md 없음")


def load_portfolio():
    r = requests.get(f"{API}/api/portfolio/current",
                     params={"top_n": top_n, "sentiment_weight": sentiment_weight}, timeout=10)
    r.raise_for_status()
    return r.json()


def load_regime():
    r = requests.get(f"{API}/api/portfolio/regime", timeout=5)
    r.raise_for_status()
    return r.json()


# ── 메인 컨텐츠 ──────────────────────────────────────────────
placeholder = st.empty()

while True:
    with placeholder.container():
        try:
            portfolio = load_portfolio()
            regime    = load_regime()

            # 레짐 뱃지
            regime_color = {"bull": "🟢", "bear": "🔴", "neutral": "🟡"}
            st.markdown(
                f"**시장 레짐:** {regime_color.get(regime['regime'], '⚪')} {regime['regime'].upper()}"
                f"　VIX: {regime.get('vix', 'N/A')}　T10Y2Y: {regime.get('t10y2y', 'N/A')}"
                f"　기준: {portfolio.get('as_of', '')}"
            )

            positions = portfolio.get("positions", [])
            if positions:
                import pandas as pd
                df = pd.DataFrame(positions)
                df = df.rename(columns={
                    "ticker": "티커", "name": "종목명", "sector": "섹터",
                    "weight": "비중", "signal": "ML신호", "ret_1d": "당일수익",
                    "ret_1m": "1개월수익", "rsi": "RSI", "sentiment": "감성점수",
                })
                df["비중"] = df["비중"].apply(lambda x: f"{x*100:.1f}%")
                df["당일수익"] = df["당일수익"].apply(lambda x: f"{x*100:+.2f}%")
                df["1개월수익"] = df["1개월수익"].apply(lambda x: f"{x*100:+.2f}%")
                df["ML신호"] = df["ML신호"].apply(lambda x: f"{x:.4f}")
                if "감성점수" in df.columns:
                    df["감성점수"] = df["감성점수"].apply(
                        lambda x: f"{x:+.3f}" if x is not None else "N/A"
                    )

                # 포지션 테이블
                col_table, col_chart = st.columns([2, 1])
                with col_table:
                    st.dataframe(df.set_index("티커"), use_container_width=True, height=400)
                    st.caption(f"포지션 {len(positions)}개 | 섹터 제약: 업종별 최대 30%")

                # 섹터 비중 파이차트
                with col_chart:
                    import plotly.express as px
                    raw_df = pd.DataFrame(positions)
                    if "sector" in raw_df.columns and "weight" in raw_df.columns:
                        sector_agg = raw_df.groupby("sector")["weight"].sum().reset_index()
                        sector_agg.columns = ["섹터", "비중"]
                        fig = px.pie(
                            sector_agg, values="비중", names="섹터",
                            title="섹터 비중",
                            hole=0.4,
                        )
                        fig.update_layout(height=400, showlegend=True,
                                          legend=dict(orientation="v", x=1.05))
                        st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("포지션 데이터 없음 (모델/데이터 확인 필요)")

        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
            st.caption("FastAPI 서버가 실행 중인지 확인하세요.")

        st.caption(f"마지막 갱신: {time.strftime('%H:%M:%S')} | 감성 가중치: {sentiment_weight:.2f}")

    if not auto_refresh:
        break
    time.sleep(30)
    placeholder.empty()

# ── AI 해설 패널 (자동 갱신 종료 후 표시) ─────────────────────
if not auto_refresh:
    st.divider()
    st.markdown('<div class="qv-section-header">🤖 AI 퀀트 어드바이저 해설</div>', unsafe_allow_html=True)
    if st.button("AI 해설 생성", key="bt_ai_port"):
        with st.spinner("분석 중..."):
            try:
                regime_data = requests.get(f"{API}/api/portfolio/regime", timeout=5).json()
                ctx = {
                    "regime": regime_data.get("regime", "neutral"),
                    "vix": regime_data.get("vix", 0),
                    "t10y2y": regime_data.get("t10y2y", 0),
                    "spy_below_ma200": regime_data.get("spy_below_ma200", False),
                    "top_n": top_n,
                    "sentiment_weight": sentiment_weight,
                }
                r = requests.post(f"{API}/api/advisor/insight",
                                  json={"page": "portfolio", "context": ctx}, timeout=15)
                insight = r.json().get("insight", "")
                if insight:
                    st.info(insight)
            except Exception:
                st.caption("AI 해설을 생성할 수 없습니다.")
