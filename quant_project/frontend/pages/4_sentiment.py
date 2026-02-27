"""
페이지 4: 감성분석 피드
ticker별 감성점수 바 차트 + 최신 기사 헤드라인 + TF-IDF 키워드 + Reddit
"""

import requests
import streamlit as st

API = "http://localhost:8000"

st.set_page_config(page_title="감성분석", layout="wide")

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

st.title("4. 감성분석 피드")
st.markdown('<div class="qv-hint">📌 RSS·Reddit 감성 점수는 <b>3. 포트폴리오 모니터</b>의 <code>sentiment_weight</code> 슬라이더를 통해 ML 신호에 합산됩니다. 극단적 점수(< -0.1 또는 > 0.1)가 지속되면 레짐 필터와 함께 포지션 조정을 고려하세요.</div>', unsafe_allow_html=True)

# ── 사이드바 ─────────────────────────────────────────────────
with st.sidebar:
    ticker_filter = st.text_input("종목 필터 (비우면 전체)", "").upper() or None
    limit = st.slider("기사 수", 10, 100, 30)
    refresh = st.button("새로 수집", type="primary")

# ── 요약 지표 ────────────────────────────────────────────────
try:
    summary = requests.get(f"{API}/api/sentiment/summary",
                           params={"refresh": refresh}, timeout=30).json()
    col1, col2, col3 = st.columns(3)
    score = summary.get("overall_score", 0)
    color = "normal" if abs(score) < 0.1 else ("inverse" if score < 0 else "normal")
    col1.metric("전체 감성 점수", f"{score:+.3f}")
    col2.metric("수집 기사 수", summary.get("n_articles", 0))
    col3.metric("기준 시각", summary.get("as_of", "")[:16])

    # 키워드
    keywords = summary.get("keywords", [])
    if keywords:
        st.markdown("**TF-IDF 주요 키워드:** " + " · ".join(f"`{k}`" for k in keywords[:10]))
except Exception as e:
    st.warning(f"감성 요약 로드 실패: {e}")

st.divider()

# ── 감성 점수 차트 ────────────────────────────────────────────
st.subheader("기사별 감성 점수")
try:
    feed = requests.get(f"{API}/api/sentiment/feed",
                        params={"ticker": ticker_filter, "limit": limit}, timeout=30).json()
    if feed:
        import pandas as pd
        import plotly.express as px

        df = pd.DataFrame(feed)
        df = df.sort_values("sentiment")
        df["color"] = df["sentiment"].apply(lambda x: "부정" if x < 0 else "긍정")

        fig = px.bar(
            df.tail(40), x="sentiment", y="title", orientation="h",
            color="color",
            color_discrete_map={"긍정": "#2ecc71", "부정": "#e74c3c"},
            height=max(400, len(df) * 18),
            labels={"sentiment": "감성 점수", "title": ""},
        )
        fig.update_layout(showlegend=True, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

        # 기사 목록
        with st.expander("기사 목록 전체 보기"):
            for item in feed:
                score = item["sentiment"]
                icon = "🟢" if score > 0.05 else ("🔴" if score < -0.05 else "⚪")
                st.markdown(
                    f"{icon} [{item['title']}]({item['url']})  \n"
                    f"_출처: {item['source']} | 점수: {score:+.3f}_"
                )
    else:
        st.info("감성 데이터 없음. '새로 수집' 버튼을 눌러주세요.")
except Exception as e:
    st.warning(f"감성 피드 로드 실패: {e}")

st.divider()

# ── Reddit ───────────────────────────────────────────────────
st.subheader("Reddit 감성")
col_r1, col_r2 = st.columns(2)
for sub, col in [("investing", col_r1), ("stocks", col_r2)]:
    with col:
        try:
            rd = requests.get(f"{API}/api/sentiment/reddit",
                              params={"subreddit": sub}, timeout=15).json()
            score = rd.get("score", 0)
            st.metric(f"r/{sub}", f"{score:+.3f}")
            for p in rd.get("posts", [])[:5]:
                icon = "🟢" if p["sentiment"] > 0 else "🔴"
                st.caption(f"{icon} {p['title'][:80]}")
        except Exception:
            st.caption(f"r/{sub} 데이터 없음 (Reddit API 키 확인)")

st.divider()

# ── 전략 통합 안내 ─────────────────────────────────────────────
st.markdown('<div class="qv-section-header">📊 감성 지표 → 전략 활용 방법</div>', unsafe_allow_html=True)
col_a, col_b = st.columns(2)
with col_a:
    st.markdown("""
    **감성 점수 활용 순서:**
    1. 이 페이지에서 전체 시장 심리 파악
    2. **3. 포트폴리오 모니터** → `sentiment_weight` 슬라이더 조정
       - 긍정적 심리 (`> 0.1`): weight 0.1~0.2 설정
       - 부정적 심리 (`< -0.1`): weight 0 또는 신중히 설정
    3. 감성 점수가 ML 신호에 합산되어 종목 순위 변동
    """)
with col_b:
    st.markdown("""
    **감성 점수 기준:**
    | 점수 | 해석 | 권장 행동 |
    |------|------|-----------|
    | `> +0.15` | 강한 긍정 | 포지션 확대 고려 |
    | `+0.05 ~ +0.15` | 약한 긍정 | 현상 유지 |
    | `-0.05 ~ +0.05` | 중립 | ML 신호 중심 |
    | `< -0.05` | 부정적 | 감성 가중치 낮추기 |
    | `< -0.15` | 강한 부정 | 레짐 필터 우선 |
    """)

st.divider()

# ── AI 해설 패널 ──────────────────────────────────────────────
st.markdown('<div class="qv-section-header">🤖 AI 퀀트 어드바이저 해설</div>', unsafe_allow_html=True)

if st.button("AI 해설 생성", key="bt_ai_sent"):
    with st.spinner("분석 중..."):
        try:
            summary_data = requests.get(f"{API}/api/sentiment/summary", timeout=10).json()
            ctx = {
                "overall_score": summary_data.get("overall_score", 0),
                "n_articles": summary_data.get("n_articles", 0),
                "keywords": summary_data.get("keywords", [])[:5],
            }
            r = requests.post(f"{API}/api/advisor/insight",
                              json={"page": "sentiment", "context": ctx}, timeout=15)
            insight = r.json().get("insight", "")
            if insight:
                st.info(insight)
        except Exception:
            st.caption("AI 해설을 생성할 수 없습니다. ANTHROPIC_API_KEY를 .env에 설정하세요.")
