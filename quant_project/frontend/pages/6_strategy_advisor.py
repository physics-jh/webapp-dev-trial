"""
페이지 6: 전략 어드바이저
현재 시장 레짐 분석 + 레짐 기반 전략 권고 + 파라미터 프로필 비교
"""

import requests
import streamlit as st

API = "http://localhost:8000"

st.set_page_config(page_title="전략 어드바이저", layout="wide")
st.title("6. 전략 어드바이저")
st.caption("현재 시장 레짐을 분석하고 최적 운용 전략을 안내합니다.")


def _get(endpoint: str, **params):
    r = requests.get(f"{API}{endpoint}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


# ── 데이터 로드 ────────────────────────────────────────────────
try:
    guide   = _get("/api/portfolio/strategy-guide")
    opt     = _get("/api/backtest/optimal-params", metric="sharpe", top_k=5)
except Exception as e:
    st.error(f"전략 데이터 로드 실패: {e}")
    st.stop()

regime   = guide["regime"]
vix      = guide.get("vix")
t10y2y   = guide.get("t10y2y")
spy_ok   = not guide.get("spy_below_ma200", False)
risk_lvl = guide.get("risk_level", 2)
title    = guide.get("strategy_title", "")
body     = guide.get("strategy_body",  "")
profiles = opt.get("profiles", {})
perf     = guide.get("backtest_reference", {})

# ── 현재 레짐 배지 ─────────────────────────────────────────────
REGIME_STYLE = {
    "bull":    ("green",   "🟢 BULL  — 상승장"),
    "neutral": ("orange",  "🟡 NEUTRAL — 중립"),
    "bear":    ("red",     "🔴 BEAR  — 하락장"),
}
color, label = REGIME_STYLE.get(regime, ("gray", "UNKNOWN"))

st.markdown(f"## {label}")

col_r1, col_r2, col_r3, col_r4 = st.columns(4)
col_r1.metric("VIX",           f"{vix:.1f}"    if vix     else "N/A",
              help="20 이하: 안정 | 25 이상: 주의 | 32 이상: 공포")
col_r2.metric("장단기금리차",   f"{t10y2y:.3f}%" if t10y2y else "N/A",
              help="음수 = 경기 침체 신호")
col_r3.metric("SPY 200MA",     "위 ✅" if spy_ok else "아래 ⚠️",
              help="SPY가 200일 이동평균 아래면 bear 레짐 강화")
col_r4.metric("리스크 레벨",    f"{risk_lvl} / 4",
              help="1=Bull, 2=Neutral, 3=Bear, 4=극단적 Bear")

# 리스크 레벨 게이지 바
risk_colors = {1: "#28a745", 2: "#fd7e14", 3: "#dc3545", 4: "#6f0000"}
bar_html = "".join(
    f'<span style="display:inline-block;width:60px;height:14px;'
    f'background:{risk_colors.get(i, "#ccc")};margin-right:4px;'
    f'border-radius:4px;opacity:{"1" if i <= risk_lvl else "0.25"}"></span>'
    for i in range(1, 5)
)
st.markdown(f"리스크 게이지: {bar_html}", unsafe_allow_html=True)

st.divider()

# ── 전략 가이드 ─────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader(f"전략 가이드 — {title}")
    st.markdown(f"> {body}")

    cash_r = guide.get("cash_reserve", 0.0)
    rec_n  = guide.get("recommended_top_n", 8)
    rec_p  = guide.get("recommended_profile", "balanced")
    PROFILE_LABEL = {
        "high_sharpe": "HIGH SHARPE (공격적)",
        "balanced":    "BALANCED (균형)",
        "low_risk":    "LOW RISK (방어적)",
    }
    p_data = profiles.get(rec_p, {})
    st.markdown("---")
    st.markdown(f"**현재 레짐 기준 권장 프로필:** {PROFILE_LABEL.get(rec_p, rec_p)}")
    if p_data:
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("권장 top_n",    rec_n)
        pc2.metric("ml_weight",     p_data.get("ml_weight", "-"))
        pc3.metric("현금 유보",      f"{int(cash_r*100)}%")

    if cash_r > 0:
        st.warning(f"극단적 공포 구간 — 포지션의 {int(cash_r*100)}%를 현금으로 유보하세요.")

with col_right:
    st.subheader("다음 레짐 전환 시나리오")
    for sc in guide.get("next_scenarios", []):
        icon = "⚠️" if "Bear" in sc["outcome"] or "공포" in sc["outcome"] else "✅"
        st.markdown(f"{icon} **{sc['trigger']}** → {sc['outcome']}")

st.divider()

# ── 파라미터 프로필 3종 비교 ────────────────────────────────────
st.subheader("파라미터 프로필 비교")
st.caption("백테스트(2017~2024) 기반 성과 — 현재 레짐 기준 권장 프로필이 강조됩니다.")

hs = profiles.get("high_sharpe", {})
ba = profiles.get("balanced",    {})
lr = profiles.get("low_risk",    {})

p1, p2, p3 = st.columns(3)
profile_cards = [
    (p1, "high_sharpe", "HIGH SHARPE", "수익률 최우선",   hs, "normal"),
    (p2, "balanced",    "BALANCED",    "수익-위험 균형",  ba, "success"),
    (p3, "low_risk",    "LOW RISK",    "낙폭 최소화",     lr, "warning"),
]
for col, pkey, plabel, pdesc, pdata, pstyle in profile_cards:
    with col:
        is_rec = (pkey == rec_p)
        rec_badge = " ← 현재 권장" if is_rec else ""
        st.markdown(f"##### {plabel}{rec_badge}")
        st.caption(pdesc)
        if pdata:
            col.metric("Sharpe",  f"{pdata.get('sharpe', 0):.3f}")
            col.metric("CAGR",    f"{pdata.get('cagr', 0)*100:.1f}%")
            col.metric("MDD",     f"{pdata.get('mdd', 0)*100:.1f}%")
            params_msg = f"ml_weight={pdata.get('ml_weight')} | top_n={pdata.get('top_n')}"
            if pstyle == "success":
                st.success(params_msg)
            elif pstyle == "warning":
                st.warning(params_msg)
            else:
                st.info(params_msg)

st.divider()

# ── 백테스트 성과 참고 ──────────────────────────────────────────
st.subheader("현재 파라미터 기준 백테스트 성과 참고")
if perf.get("cagr") is not None:
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("CAGR",    f"{perf['cagr']*100:.1f}%")
    b2.metric("Sharpe",  f"{perf['sharpe']:.3f}")
    b3.metric("MDD",     f"{perf['max_drawdown']*100:.1f}%")
    b4.metric("승률",    f"{perf['win_rate']*100:.1f}%")
    st.caption(f"평가 기간: {perf.get('start_date','?')} ~ {perf.get('end_date','?')}")
else:
    st.info("백테스트 성과 데이터 없음 (run_backtest.py 실행 필요)")

# ── 자동 갱신 ──────────────────────────────────────────────────
with st.sidebar:
    st.header("전략 어드바이저 설정")
    if st.button("데이터 새로고침"):
        st.rerun()
    st.caption("레짐 데이터는 매일 18:10 자동 갱신됩니다.")
